import fitz
import io
import json
import logging
from fastapi import APIRouter, UploadFile, Form, File
from fastapi.responses import StreamingResponse
from .font_utils import get_font_for_edit

logger = logging.getLogger(__name__)
router = APIRouter()

# Module-level: prevents PyMuPDF from using max ascender/descender heights,
# which cause redaction boxes to bleed into adjacent lines.
fitz.TOOLS.set_small_glyph_heights(True)

# Expand Unicode ligature codepoints to their component characters.
# rawdict always reports ligatures as separate chars (e.g. 'f','i' not 'fi'),
# so we must normalize user text to match. The old _substitute_ligatures did
# the OPPOSITE (converting 'fi' → U+FB01), creating false diffs.
LIGATURE_EXPAND = {
    "\uFB00": "ff", "\uFB01": "fi", "\uFB02": "fl",
    "\uFB03": "ffi", "\uFB04": "ffl",
    "\uFB05": "st", "\uFB06": "st",
}
def _expand_ligatures(text: str) -> str:
    """Expands Unicode ligature codepoints to component characters."""
    for lig, expanded in LIGATURE_EXPAND.items():
        text = text.replace(lig, expanded)
    return text


# ── Helper: measure true rendered width from rawdict per-character bboxes ────

def _measure_span_width(
    page: fitz.Page,
    x0: float,
    origin_y: float,
    edit_x0: float = None,
    edit_x1: float = None,
):
    """
    Measure the true rendered width of text at the given baseline origin
    AND return the full line's per-character data.

    A "span" in PyMuPDF's rawdict is a run of identically-styled text — a
    long visual line that contains bold/italic/font-size variations (e.g.
    citations like ²⁵, italicised terms) is split into multiple spans.
    For correct minimal-diff editing we need ALL chars on the line, not
    just one span's chars. This function unions every span on the same
    baseline into a synthetic "line span" and returns it.

    IMPORTANT — COLUMN-AWARENESS:
    In multi-column PDFs, two columns frequently share the exact same
    baseline origin_y. Naively unifying every same-baseline span merges
    text ACROSS columns, producing a Frankenstein "line" that does not
    exist in the rendered PDF. When the caller provides edit_x0/edit_x1
    (the x-range of the edit's bounding rect), we restrict unification to
    spans whose x-range overlaps the caller's column. This prevents the
    cross-column corruption.

    If edit_x0/edit_x1 are not provided, falls back to the old behavior
    of unifying all same-baseline spans (kept for backwards compatibility,
    but apply_edits should always pass the column bounds).

    Returns: (width, synthetic_line_span_dict) or (None, None) on failure.
    """
    # Tight baseline tolerance: spans whose origin_y matches the line's
    # dominant baseline. Super/sub spans (which sit at different baselines)
    # are handled separately — we keep them out of THIS unification to
    # avoid accidentally merging adjacent lines, and instead include them
    # via a second pass below.
    BASELINE_TOLERANCE = 2.0  # points

    # IMPORTANT: PyMuPDF's `clip` parameter silently omits any span that
    # is not FULLY contained inside the clip rect. Use a page-wide clip
    # bounded only in Y so long spans aren't dropped.
    page_rect = page.rect
    clip = fitz.Rect(page_rect.x0, origin_y - 15, page_rect.x1, origin_y + 10)
    try:
        rd = page.get_text("rawdict", clip=clip)
    except Exception:
        return None, None

    # ── Pass 1: collect spans at the main baseline ───────────────────────
    baseline_spans = []
    for block in rd.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_origin = span.get("origin", (0, 0))
                if abs(span_origin[1] - origin_y) <= BASELINE_TOLERANCE:
                    baseline_spans.append(span)

    if not baseline_spans:
        return None, None

    # ── Pass 2: look for script spans (super/sub) on the same LINE ───────
    # PyMuPDF groups spans into lines in its rawdict output. A line can
    # contain both normal spans and script spans (super/sub) at offset
    # baselines. We find the line(s) our main spans belong to, then pull
    # in the OTHER spans from those same lines — this safely captures
    # super/sub without merging adjacent visual lines.
    script_spans = []
    seen_line_ids = set()
    for block in rd.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            line_spans = line.get("spans", [])
            # Is any main-baseline span part of this line?
            line_has_main = any(
                abs(s.get("origin", (0, 0))[1] - origin_y) <= BASELINE_TOLERANCE
                for s in line_spans
            )
            if not line_has_main:
                continue
            # Pull non-main spans that could be super/sub (baseline offset
            # typically 1-5pt; reject anything more than 7pt away — that's
            # a different visual line).
            for span in line_spans:
                span_origin = span.get("origin", (0, 0))
                offset = abs(span_origin[1] - origin_y)
                if offset <= BASELINE_TOLERANCE:
                    continue  # already in baseline_spans
                if offset <= 7.0:
                    script_spans.append(span)

    baseline_spans.extend(script_spans)

    # ── COLUMN FILTER ────────────────────────────────────────────────────
    # If the caller provided column bounds, keep only spans whose x-range
    # overlaps the caller's column. Use a small tolerance to handle edits
    # that cross tight column gutters. The overlap test:
    #   span_x0 < edit_x1 AND span_x1 > edit_x0
    # is standard interval overlap.
    #
    # Without this filter, same-baseline spans from OTHER columns would be
    # unioned into the synthetic line, producing text that doesn't exist
    # at the edit's location and breaking minimal-diff editing.
    if edit_x0 is not None and edit_x1 is not None:
        COLUMN_TOLERANCE = 5.0  # points — allow for slight gutter overlap
        col_x0 = edit_x0 - COLUMN_TOLERANCE
        col_x1 = edit_x1 + COLUMN_TOLERANCE

        def _span_in_column(span):
            chars = span.get("chars", [])
            if not chars:
                sb = span.get("bbox", (0, 0, 0, 0))
                span_x0, span_x1 = sb[0], sb[2]
            else:
                span_x0 = min(c["bbox"][0] for c in chars)
                span_x1 = max(c["bbox"][2] for c in chars)
            # Overlap test
            return span_x0 < col_x1 and span_x1 > col_x0

        filtered = [s for s in baseline_spans if _span_in_column(s)]
        if filtered:
            baseline_spans = filtered
        # If nothing overlapped (unusual — caller's rect may be stale),
        # fall through to using all spans; at worst we reproduce the old
        # behavior rather than returning no data.

    # Union every char from every same-baseline span IN THIS COLUMN,
    # sorted by x-position.
    # CRITICAL: Attach each span's color to its chars before flattening,
    # since color is a span-level attribute, not char-level.
    all_chars = []
    for span in baseline_spans:
        span_color = span.get("color", 0)  # sRGB int from the span
        for ch in span.get("chars", []):
            # Copy so we don't mutate the original rawdict
            ch_copy = dict(ch)
            ch_copy["color"] = span_color
            all_chars.append(ch_copy)
    if not all_chars:
        best_span = min(baseline_spans, key=lambda s: abs(s["origin"][0] - x0))
        sb = best_span.get("bbox", (0, 0, 0, 0))
        return sb[2] - sb[0], best_span

    all_chars.sort(key=lambda c: c["bbox"][0])

    # Width = leftmost char's x0 to rightmost char's x1
    measured_w = all_chars[-1]["bbox"][2] - all_chars[0]["bbox"][0]

    # Build a synthetic "line span" carrying the unified char list.
    closest_span = min(baseline_spans, key=lambda s: abs(s["origin"][0] - x0))
    synthetic_span = dict(closest_span)
    synthetic_span["chars"] = all_chars
    synthetic_span["bbox"] = (
        all_chars[0]["bbox"][0],
        min(c["bbox"][1] for c in all_chars),
        all_chars[-1]["bbox"][2],
        max(c["bbox"][3] for c in all_chars),
    )

    logger.info(
        f"_measure_span_width: x0={x0:.1f} origin_y={origin_y:.1f} "
        f"col=[{edit_x0}..{edit_x1}] → width={measured_w:.2f}, "
        f"unified {len(baseline_spans)} span(s) into {len(all_chars)} chars"
    )
    return measured_w, synthetic_span


# ── Helper: get per-font space width from get_texttrace() ────────────────────

def _int_color_to_rgb(c: int) -> tuple:
    """
    Convert PyMuPDF rawdict packed integer color (0xRRGGBB) to RGB tuple.
    """
    r = ((c >> 16) & 0xFF) / 255.0
    g = ((c >>  8) & 0xFF) / 255.0
    b = ( c        & 0xFF) / 255.0
    return (r, g, b)


def _resolve_color_from_char(orig_char: dict, fallback_color: tuple) -> tuple:
    """
    Extract color from a rawdict character dict.
    If the char has a 'color' field, convert it to RGB; otherwise return fallback.
    """
    if orig_char and "color" in orig_char:
        return _int_color_to_rgb(orig_char["color"])
    return fallback_color


def _get_space_width(page: fitz.Page, x0: float, origin_y: float, fontsize: float) -> float:
    """
    Get the space width from get_texttrace() — far more accurate than fontsize * 0.25.

    get_texttrace() derives spacewidth from the font where possible, which is
    the maintainer-recommended replacement for the fixed 0.25em approximation.
    Spatially matches by baseline coordinates.
    Cross-validates against rawdict font size to compensate for the known trm bug.
    """
    BASELINE_TOL = 3.0
    try:
        for tspan in page.get_texttrace():
            tbox = tspan.get("bbox", (0, 0, 0, 0))
            # Check: does this trace span cover our x0 and share our baseline?
            if tbox[0] - 5 <= x0 <= tbox[2] + 5:
                # Baseline check: trace span bbox y-range should contain origin_y
                if tbox[1] - BASELINE_TOL <= origin_y <= tbox[3] + BASELINE_TOL:
                    sw = tspan.get("spacewidth")
                    if sw and sw > 0:
                        # Cross-validate font size (trm bug workaround)
                        trace_size = tspan.get("size", fontsize)
                        if trace_size > 0 and abs(trace_size - fontsize) > 1.0:
                            sw = sw * (fontsize / trace_size)
                        logger.info(f"_get_space_width: spacewidth={sw:.2f} from texttrace")
                        return sw
    except Exception as e:
        logger.debug(f"_get_space_width: texttrace failed: {e}")
    logger.info(f"_get_space_width: falling back to fontsize*0.25 = {fontsize * 0.25:.2f}")
    return fontsize * 0.25  # last resort


# ── Helper: build per-character advance width table from rawdict ──────────────

def _build_advance_table(rawdict_chars: list, fontsize: float) -> dict:
    """
    Build a per-character advance width table from rawdict character positions.

    Computes the advance width of each character from the origin.x difference
    between consecutive characters. This is the GROUND TRUTH — it reflects
    exactly how the PDF engine laid out the text, including all kerning,
    tracking, word spacing, and justification adjustments.

    Returns: {char: advance_in_pt} — advance widths in absolute points
    at the given fontsize. Values are the median of all observations for
    each character (robust against justification outliers).
    """
    if not rawdict_chars or fontsize <= 0:
        return {}

    # Collect all observed advances per character
    char_advances: dict[str, list[float]] = {}

    for i in range(len(rawdict_chars)):
        ch = rawdict_chars[i].get("c", "")
        if not ch:
            continue

        if i + 1 < len(rawdict_chars):
            # Normal case: advance = next origin - this origin
            this_x = rawdict_chars[i]["origin"][0]
            next_x = rawdict_chars[i + 1]["origin"][0]
            adv = next_x - this_x
        else:
            # Last character: use bbox width as fallback
            bbox = rawdict_chars[i].get("bbox", (0, 0, 0, 0))
            origin_x = rawdict_chars[i]["origin"][0]
            adv = bbox[2] - origin_x

        if adv > 0:
            char_advances.setdefault(ch, []).append(adv)

    # Use median of observations for each character
    result = {}
    for ch, advs in char_advances.items():
        sorted_advs = sorted(advs)
        result[ch] = sorted_advs[len(sorted_advs) // 2]

    # Log summary
    space_adv = result.get(" ", 0)
    letter_advs = [v for k, v in result.items() if k != " "]
    avg_letter = sum(letter_advs) / len(letter_advs) if letter_advs else fontsize * 0.5
    logger.info(
        f"_build_advance_table: {len(result)} chars, "
        f"space={space_adv:.2f}pt, avg_letter={avg_letter:.2f}pt"
    )
    return result

# ── Helper: find the minimal change range between two strings ────────────────

def _find_change_range(orig: str, new: str):
    """
    Find the character range that differs between orig and new.

    Returns (prefix_len, orig_end, new_end) where:
      - orig[prefix_len:orig_end] is the changed region of the original
      - new[prefix_len:new_end] is the replacement
      - orig[:prefix_len] == new[:prefix_len]  (common prefix)
      - orig[orig_end:] == new[new_end:]        (common suffix)
    """
    # Common prefix
    prefix_len = 0
    for i in range(min(len(orig), len(new))):
        if orig[i] == new[i]:
            prefix_len += 1
        else:
            break

    # Common suffix (from the end, not overlapping with prefix)
    suffix_len = 0
    max_suffix = min(len(orig) - prefix_len, len(new) - prefix_len)
    for i in range(1, max_suffix + 1):
        if orig[-i] == new[-i]:
            suffix_len += 1
        else:
            break

    orig_end = len(orig) - suffix_len
    new_end = len(new) - suffix_len

    return prefix_len, orig_end, new_end


@router.post("/apply-edits")
async def apply_edits(
    file:  UploadFile = File(...),
    edits: str        = Form(...),
):
    data       = await file.read()
    edits_list = json.loads(edits)

    doc = fitz.open(stream=data, filetype="pdf")

    # Accumulate warnings to return to the frontend
    warnings = []

    # Group edits by page
    from collections import defaultdict
    edits_by_page = defaultdict(list)
    for edit in edits_list:
        edits_by_page[edit["pageNum"]].append(edit)

    for page_num, page_edits in edits_by_page.items():
        page = doc[page_num - 1]
        
        # Ensure page content stream is balanced before drawing
        if not page.is_wrapped:
            page.wrap_contents()

        edit_plans = []

        # ── Phase 1: Measure everything BEFORE any mutations ──
        for edit in page_edits:
            orig_text = edit.get("origStr", "")
            new_text = edit.get("newStr", "")
            # Enforce sanitization of HTML non-breaking spaces injected by contenteditable
            new_text = new_text.replace("\u00A0", " ").replace("&nbsp;", " ")
            new_text = _expand_ligatures(new_text)

            # ── Coordinates (all in MuPDF space via Util.transform at scale=1) ──
            x0       = edit["rect"]["x"]
            y0       = edit["rect"]["y"]
            x1_frontend = x0 + edit["rect"]["w"]  # frontend-derived (fallback)
            y1       = y0 + edit["rect"]["h"]
            origin_y = edit.get("origin_y", y1 - 2)
            fontsize = edit.get("origFontSize", 11) + edit.get("fontSizeAdj", 0)
            fontsize = max(4.0, fontsize)  # MuPDF minimum

            # ── Backend-authoritative width measurement from rawdict ──────────
            # Pass the frontend's column bounds (rect.x .. rect.x + rect.w) so
            # span unification stays within the edit's column. Without this,
            # multi-column PDFs where two columns share a baseline get their
            # text merged into a Frankenstein line.
            measured_w, matched_span = _measure_span_width(
                page, x0, origin_y,
                edit_x0=x0,
                edit_x1=x1_frontend,
            )
            if measured_w and measured_w > 0:
                x1 = x0 + measured_w
                logger.info(
                    f"Using backend-measured width: {measured_w:.2f} "
                    f"(frontend was {edit['rect']['w']:.2f})"
                )
            else:
                x1 = x1_frontend
                logger.info(
                    f"Backend width measurement failed, using frontend width: "
                    f"{edit['rect']['w']:.2f}"
                )

            # ── Font resolution ──────────────────────────────────────────────────
            edit["fontName"] = _resolve_font_name(page, edit, x0, y0, x1_frontend, y1)
            font_result = get_font_for_edit(doc, page, edit)

            if font_result.fallback_used:
                warning_entry = {
                    "pageNum":  edit["pageNum"],
                    "origStr":  orig_text,
                    "reason":   font_result.fallback_reason,
                }
                if font_result.missing_glyphs:
                    warning_entry["missingGlyphs"] = font_result.missing_glyphs
                warnings.append(warning_entry)
                logger.warning(
                    f"Page {edit['pageNum']}: font fallback used. "
                    f"Reason: {font_result.fallback_reason}"
                )

            # Register the font with this page so insert_text can find it
            if font_result.font_buffer:
                page.insert_font(
                    fontname=font_result.fontname,
                    fontbuffer=font_result.font_buffer,
                )

            # ── Determine insert color ───────────────────────────────────────────
            insert_color = _resolve_color(page, edit, x0, y0, x1_frontend, y1)

            # ── Prepare font measurement ─────────────────────────────────────────
            try:
                if font_result.font_buffer:
                    measure_font = fitz.Font(fontbuffer=font_result.font_buffer)
                    has_space = measure_font.has_glyph(32)
                else:
                    measure_font = fitz.Font(fontname=font_result.fontname)
                    has_space = measure_font.has_glyph(32)
                space_width = measure_font.text_length(" ", fontsize=fontsize)
            except Exception:
                space_width = 0.0
                has_space = False
                measure_font = None

            # ── Erase metrics ────────────────────────────────────────────────────
            # Tight erase band: just enough to cover the line's own glyphs
            # (ascender above baseline, descender below). Super/sub chars on
            # the line are handled via the minimal-diff erase_rect (which
            # uses the actual char bboxes from rawdict) so they get covered
            # by the per-char bounds — no global expansion needed.
            ascender_h  = edit.get("ascender_h",  fontsize * 0.8)
            descender_h = edit.get("descender_h", fontsize * 0.2)
            erase_y0 = origin_y - ascender_h
            erase_y1 = origin_y + descender_h

            plan = {
                "erase_rects": [],
                "insert_chars": [],
                "font_registrations": {},
                "super_ranges": edit.get("superscriptRanges", []) or [],
                "new_text": new_text,
            }

            # ── Whole-line bypass for super/sub lines ─────────────────────
            # When the edit's payload includes super/sub ranges, the
            # minimal-diff path's char-offset math (which has line-text vs
            # op-stream coordinate mismatches) reliably mis-applies super
            # baselines to wrong characters. Bypass it: erase the whole
            # line's visual extent and re-insert newStr segment-by-segment,
            # using line-text-relative indices throughout.
            has_script_ranges = len(plan["super_ranges"]) > 0

            # Pre-record font registration for this edit
            if font_result.font_buffer:
                plan["font_registrations"][font_result.fontname] = font_result.font_buffer

            # ── MINIMAL-DIFF EDITING ─────────────────────────────────────────────
            rawdict_chars = matched_span.get("chars", []) if matched_span else []
            raw_text = "".join(ch.get("c", "") for ch in rawdict_chars)
            used_minimal_diff = False

            if raw_text and rawdict_chars:
                prefix_len, raw_end, new_end = _find_change_range(raw_text, new_text)
                changed_orig = raw_text[prefix_len:raw_end]
                changed_new = new_text[prefix_len:new_end]

                if prefix_len < raw_end or prefix_len < new_end:
                    if prefix_len < len(rawdict_chars) and raw_end <= len(rawdict_chars):
                        # Use the WIDEST x-range across the changed chars,
                        # since super chars have different bbox than normal.
                        changed_chars = rawdict_chars[prefix_len:raw_end]
                        if changed_chars:
                            erase_x0 = min(c["bbox"][0] for c in changed_chars)
                            erase_x1 = max(c["bbox"][2] for c in changed_chars)
                            # Use the MOST COMMON origin_y among the changed
                            # chars as the insertion baseline — super chars
                            # have a different origin_y and would mislocate.
                            from collections import Counter
                            y_counts = Counter(
                                round(c["origin"][1], 1) for c in changed_chars
                            )
                            change_origin_y = y_counts.most_common(1)[0][0]
                        else:
                            erase_x0 = rawdict_chars[prefix_len]["bbox"][0]
                            erase_x1 = rawdict_chars[raw_end - 1]["bbox"][2]
                            change_origin_y = rawdict_chars[prefix_len]["origin"][1]
                        erase_w = erase_x1 - erase_x0

                        logger.info(
                            f"MINIMAL DIFF: '{changed_orig}' → '{changed_new}' "
                            f"at chars[{prefix_len}:{raw_end}], "
                            f"erase_x=[{erase_x0:.1f}, {erase_x1:.1f}] (width={erase_w:.1f})"
                        )

                        if not changed_new and changed_orig.strip() == "":
                            logger.info("MINIMAL DIFF: whitespace-only removal — skipping erase")
                            used_minimal_diff = True
                        else:
                            if changed_chars:
                                char_erase_y0 = min(c["bbox"][1] for c in changed_chars)
                                char_erase_y1 = max(c["bbox"][3] for c in changed_chars)

                            # Y extent: use the LINE's own ascender/descender
                            # band, NOT the union of char bboxes. Super/sub
                            # chars sit within the line's allotted space
                            # (raised/lowered baselines inside the line band),
                            # not above it. Pulling Y out to char bboxes
                            # overreaches into the line above's descenders
                            # in tight-spaced multi-line layouts (e.g. journal
                            # affiliation blocks with ~12pt line spacing for
                            # 11pt text), erasing legitimate content from
                            # adjacent lines.
                            final_erase_y0 = erase_y0
                            final_erase_y1 = erase_y1

                            logger.info(
                                f"ERASE Y: line_band=[{erase_y0:.2f}, {erase_y1:.2f}], "
                                f"changed_chars=[{char_erase_y0:.2f}, {char_erase_y1:.2f}] "
                                f"→ final=[{final_erase_y0:.2f}, {final_erase_y1:.2f}] "
                                f"(origin_y={change_origin_y:.2f})"
                            ) if changed_chars else None

                            left_margin = fontsize * 0.15 if not changed_new else 0
                            y_pad = min(0.3, fontsize * 0.02)  # tight pad, stays within line
                            erase_rect = fitz.Rect(
                                erase_x0 + left_margin, final_erase_y0 - y_pad,
                                erase_x1 + 1, final_erase_y1 + y_pad
                            )
                            plan["erase_rects"].append(erase_rect)

                        if changed_new:
                            advance_table = _build_advance_table(rawdict_chars, fontsize)
                            letter_advs = [v for k, v in advance_table.items() if k != " "]
                            avg_letter_adv = sum(letter_advs) / len(letter_advs) if letter_advs else fontsize * 0.5
                            space_adv = advance_table.get(" ", None)
                            if space_adv is None or space_adv < fontsize * 0.05:
                                space_adv = _get_space_width(
                                    page, erase_x0, change_origin_y, fontsize
                                )

                            change_at_end = (raw_end >= len(rawdict_chars) - 1)

                            if change_at_end:
                                est_new_w = 0
                                for ch in changed_new:
                                    if ch == " ":
                                        est_new_w += space_adv
                                    else:
                                        est_new_w += advance_table.get(ch, avg_letter_adv)
                                if est_new_w > erase_w:
                                    extra_rect = fitz.Rect(
                                        erase_x1, erase_y0 - 1,
                                        erase_x0 + est_new_w + 2, erase_y1 + 1
                                    )
                                    plan["erase_rects"].append(extra_rect)
                                    logger.info(
                                        f"End-of-span: extended erase by "
                                        f"{est_new_w - erase_w:.1f}pt"
                                    )

                            # ── Super-aware segmented insertion ─────────────
                            # Split changed_new into segments at super_range
                            # boundaries that fall WITHIN the changed region.
                            # super_ranges have charStart/charEnd in line-text
                            # coordinates (new_text). Translate to changed_new
                            # coordinates by subtracting prefix_len.
                            #
                            # Each segment is emitted at its appropriate
                            # baseline (body or super/sub raised). Cursor
                            # advances by NATURAL width of each segment so
                            # everything stays within the redacted region.
                            local_super_segments = []
                            for sr in plan["super_ranges"]:
                                sr_s = sr.get("charStart", -1) - prefix_len
                                sr_e = sr.get("charEnd", -1) - prefix_len
                                # Clip to [0, len(changed_new))
                                sr_s = max(0, sr_s)
                                sr_e = min(len(changed_new), sr_e)
                                if sr_s < sr_e:
                                    local_super_segments.append({
                                        "start": sr_s,
                                        "end": sr_e,
                                        "kind": sr.get("kind", "super"),
                                        "fontSize": sr.get("fontSize"),
                                        "pdfY_top": sr.get("pdfY_top"),
                                    })
                            # Sort by start position
                            local_super_segments.sort(key=lambda s: s["start"])

                            # Build flat list of (start, end, kind_or_None, sr_dict)
                            segments = []
                            cursor_local = 0
                            for sr in local_super_segments:
                                if sr["start"] > cursor_local:
                                    segments.append((cursor_local, sr["start"], None, None))
                                segments.append((sr["start"], sr["end"], sr["kind"], sr))
                                cursor_local = max(cursor_local, sr["end"])
                            if cursor_local < len(changed_new):
                                segments.append((cursor_local, len(changed_new), None, None))

                            # Now emit one insert per segment, advancing cursor_x
                            cursor_x = erase_x0
                            for seg_start, seg_end, seg_kind, sr in segments:
                                seg_text = changed_new[seg_start:seg_end]
                                if not seg_text:
                                    continue

                                if seg_kind is None:
                                    # Normal body-baseline segment.
                                    # Emit word-by-word so spaces use space_adv
                                    # (matches original minimal-diff word grouping).
                                    word_buf = ""
                                    word_start_x = cursor_x
                                    for ch_idx, ch in enumerate(seg_text):
                                        # Map segment char index to rawdict_chars index
                                        orig_char_idx = prefix_len + seg_start + ch_idx
                                        seg_color = insert_color
                                        
                                        if orig_char_idx < len(rawdict_chars):
                                            orig_char = rawdict_chars[orig_char_idx]
                                            if "color" in orig_char:
                                                seg_color = _int_color_to_rgb(orig_char["color"])
                                                logger.info(
                                                    f"[INFO]   seg color from orig char[{orig_char_idx}]={orig_char.get('c')!r}: {seg_color}"
                                                )
                                        
                                        if ch == " ":
                                            if word_buf:
                                                plan["insert_chars"].append({
                                                    "pos": fitz.Point(word_start_x, change_origin_y),
                                                    "text": word_buf,
                                                    "fontname": font_result.fontname,
                                                    "fontsize": fontsize,
                                                    "color": seg_color,
                                                    "morph": None,
                                                })
                                                word_buf = ""
                                            cursor_x += space_adv
                                            word_start_x = cursor_x
                                        else:
                                            if not word_buf:
                                                word_start_x = cursor_x
                                            word_buf += ch
                                            if ch in advance_table:
                                                cursor_x += advance_table[ch]
                                            elif measure_font:
                                                try:
                                                    cursor_x += measure_font.text_length(
                                                        ch, fontsize=fontsize,
                                                    )
                                                except Exception:
                                                    cursor_x += avg_letter_adv
                                            else:
                                                cursor_x += avg_letter_adv
                                    if word_buf:
                                        # Final word in segment - determine its color
                                        orig_char_idx = prefix_len + seg_start + len(seg_text) - len(word_buf)
                                        seg_color = insert_color
                                        if orig_char_idx < len(rawdict_chars):
                                            orig_char = rawdict_chars[orig_char_idx]
                                            if "color" in orig_char:
                                                seg_color = _int_color_to_rgb(orig_char["color"])
                                                logger.info(
                                                    f"[INFO]   seg color from orig char[{orig_char_idx}]={orig_char.get('c')!r}: {seg_color}"
                                                )
                                        plan["insert_chars"].append({
                                            "pos": fitz.Point(word_start_x, change_origin_y),
                                            "text": word_buf,
                                            "fontname": font_result.fontname,
                                            "fontsize": fontsize,
                                            "color": seg_color,
                                            "morph": None,
                                        })
                                else:
                                    # Super or sub segment at raised/lowered baseline.
                                    # Look up color from the first character of this segment
                                    # Priority: explicit range color from frontend > orig char color > insert_color fallback
                                    seg_color = insert_color
                                    sr_explicit_color = sr.get("color") if sr else None
                                    if sr_explicit_color and isinstance(sr_explicit_color, str):
                                        # Parse "rgb(r, g, b)" or "#rrggbb"
                                        try:
                                            if sr_explicit_color.startswith("#") and len(sr_explicit_color) == 7:
                                                seg_color = (
                                                    int(sr_explicit_color[1:3], 16) / 255.0,
                                                    int(sr_explicit_color[3:5], 16) / 255.0,
                                                    int(sr_explicit_color[5:7], 16) / 255.0,
                                                )
                                            elif sr_explicit_color.startswith("rgb"):
                                                import re
                                                m = re.match(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", sr_explicit_color)
                                                if m:
                                                    seg_color = (int(m.group(1))/255, int(m.group(2))/255, int(m.group(3))/255)
                                        except Exception:
                                            pass
                                    else:
                                        orig_char_idx = prefix_len + seg_start
                                        if orig_char_idx < len(rawdict_chars):
                                            orig_char = rawdict_chars[orig_char_idx]
                                            if "color" in orig_char:
                                                seg_color = _int_color_to_rgb(orig_char["color"])
                                                logger.info(
                                                    f"[INFO]   seg color from orig char[{orig_char_idx}]={orig_char.get('c')!r}: {seg_color}"
                                                )
                                        else:
                                            logger.info(
                                                f"[INFO]   seg color fallback (orig_char_idx={orig_char_idx} >= len(rawdict_chars)={len(rawdict_chars)}): {seg_color}"
                                            )
                                    
                                    sr_size = sr.get("fontSize") if sr else None
                                    if not sr_size or sr_size <= 0:
                                        sr_size = fontsize * 0.60
                                    sr_y_top = sr.get("pdfY_top") if sr else None
                                    if sr_y_top is not None:
                                        sr_origin_y = sr_y_top + sr_size * 0.80
                                    elif seg_kind == "super":
                                        sr_origin_y = change_origin_y - fontsize * 0.33
                                    else:
                                        sr_origin_y = change_origin_y + fontsize * 0.15

                                    plan["insert_chars"].append({
                                        "pos": fitz.Point(cursor_x, sr_origin_y),
                                        "text": seg_text,
                                        "fontname": font_result.fontname,
                                        "fontsize": sr_size,
                                        "color": seg_color,
                                        "morph": None,
                                    })
                                    try:
                                        cursor_x += measure_font.text_length(
                                            seg_text, fontsize=sr_size,
                                        )
                                    except Exception:
                                        cursor_x += len(seg_text) * sr_size * 0.5

                                    logger.info(
                                        f"  minimal-diff segment {seg_kind} "
                                        f"'{seg_text}' at origin_y={sr_origin_y:.1f} "
                                        f"(parent={change_origin_y:.1f}), "
                                        f"fontsize={sr_size:.1f} "
                                        f"(parent={fontsize:.1f})"
                                    )

                        used_minimal_diff = True
                else:
                    logger.info("MINIMAL DIFF: no change between rawdict text and newStr — skipping")
                    used_minimal_diff = True

            # ── FALLBACK / SCRIPT-LINE PATH: Whole-line erase + segmented re-insert ──
            if not used_minimal_diff:
                logger.info(
                    f"WHOLE-LINE PATH: rawdict_chars={len(rawdict_chars)}, "
                    f"origStr_len={len(orig_text)}, "
                    f"super_ranges={len(plan['super_ranges'])}"
                )

                # Determine the erase rect's vertical extent.
                # For lines WITH script ranges, we MUST cover the super's
                # raised bbox AND the sub's lowered bbox, otherwise the
                # original super/sub glyphs survive the redaction.
                final_erase_y0 = erase_y0
                final_erase_y1 = erase_y1
                if has_script_ranges:
                    for sr in plan["super_ranges"]:
                        sr_y_top = sr.get("pdfY_top")
                        sr_h = sr.get("pdfH", 0)
                        if sr_y_top is not None:
                            sr_y_bottom = sr_y_top + sr_h
                            final_erase_y0 = min(final_erase_y0, sr_y_top - 1)
                            final_erase_y1 = max(final_erase_y1, sr_y_bottom + 1)

                # Use the actual rawdict char bboxes (if available) to set
                # the horizontal erase extent — this catches super chars
                # that may sit slightly outside the body x range.
                if rawdict_chars:
                    char_x0 = min(c["bbox"][0] for c in rawdict_chars)
                    char_x1 = max(c["bbox"][2] for c in rawdict_chars)
                    erase_left = min(x0, char_x0) - 1
                    erase_right = max(x1, char_x1) + 1
                else:
                    erase_left = x0 - 1
                    erase_right = x1 + 1

                erase_rect = fitz.Rect(
                    erase_left, final_erase_y0 - 1,
                    erase_right, final_erase_y1 + 1,
                )
                plan["erase_rects"].append(erase_rect)

                if has_script_ranges:
                    # ── Segmented insert: walk newStr left-to-right,
                    # splitting at super/sub range boundaries. Each
                    # segment becomes one insert op with its own baseline
                    # and font size. Indices in super_ranges refer to
                    # newStr (line-text coordinates), so no translation
                    # is needed.
                    super_ranges_sorted = sorted(
                        plan["super_ranges"],
                        key=lambda r: r.get("charStart", 0),
                    )

                    # Build a list of segments: [(start, end, kind_or_None, sr_dict_or_None)]
                    # 'normal' segments are between/before/after script ranges.
                    segments = []
                    cursor = 0
                    for sr in super_ranges_sorted:
                        s = sr.get("charStart", 0)
                        e = sr.get("charEnd", 0)
                        if s > cursor:
                            segments.append((cursor, s, None, None))
                        if e > s:
                            segments.append((s, e, sr.get("kind", "super"), sr))
                        cursor = max(cursor, e)
                    if cursor < len(new_text):
                        segments.append((cursor, len(new_text), None, None))

                    # Now compute the X cursor and emit one insert per segment.
                    # Use measure_font for cursor advancement.
                    seg_cursor_x = x0  # start at the line's left edge

                    for seg_start, seg_end, seg_kind, sr in segments:
                        seg_text = new_text[seg_start:seg_end]
                        if not seg_text:
                            continue

                        if seg_kind is None:
                            # Normal text segment at body baseline
                            # Resolve color from original character if available
                            seg_color = insert_color
                            if seg_start < len(rawdict_chars):
                                orig_char = rawdict_chars[seg_start]
                                if "color" in orig_char:
                                    seg_color = _int_color_to_rgb(orig_char["color"])
                                    logger.info(
                                        f"[INFO]   seg color from orig char[{seg_start}]={orig_char.get('c')!r}: {seg_color}"
                                    )
                            
                            plan["insert_chars"].append({
                                "pos": fitz.Point(seg_cursor_x, origin_y),
                                "text": seg_text,
                                "fontname": font_result.fontname,
                                "fontsize": fontsize,
                                "color": seg_color,
                                "morph": None,
                            })
                            try:
                                seg_cursor_x += measure_font.text_length(
                                    seg_text, fontsize=fontsize
                                )
                            except Exception:
                                seg_cursor_x += len(seg_text) * fontsize * 0.5
                        else:
                            # Super or sub segment at its own baseline + size
                            # Resolve color from original character if available
                            # Priority: explicit range color from frontend > orig char color > insert_color fallback
                            seg_color = insert_color
                            sr_explicit_color = sr.get("color") if sr else None
                            if sr_explicit_color and isinstance(sr_explicit_color, str):
                                # Parse "rgb(r, g, b)" or "#rrggbb"
                                try:
                                    if sr_explicit_color.startswith("#") and len(sr_explicit_color) == 7:
                                        seg_color = (
                                            int(sr_explicit_color[1:3], 16) / 255.0,
                                            int(sr_explicit_color[3:5], 16) / 255.0,
                                            int(sr_explicit_color[5:7], 16) / 255.0,
                                        )
                                    elif sr_explicit_color.startswith("rgb"):
                                        import re
                                        m = re.match(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", sr_explicit_color)
                                        if m:
                                            seg_color = (int(m.group(1))/255, int(m.group(2))/255, int(m.group(3))/255)
                                except Exception:
                                    pass
                            else:
                                if seg_start < len(rawdict_chars):
                                    orig_char = rawdict_chars[seg_start]
                                    if "color" in orig_char:
                                        seg_color = _int_color_to_rgb(orig_char["color"])
                                        logger.info(
                                            f"[INFO]   seg color from orig char[{seg_start}]={orig_char.get('c')!r}: {seg_color}"
                                        )
                                else:
                                    logger.info(
                                        f"[INFO]   seg color fallback (seg_start={seg_start} >= len(rawdict_chars)={len(rawdict_chars)}): {seg_color}"
                                    )
                            
                            sr_size = sr.get("fontSize") if sr else None
                            if not sr_size or sr_size <= 0:
                                sr_size = fontsize * 0.60
                            sr_y_top = sr.get("pdfY_top") if sr else None
                            if sr_y_top is not None:
                                # Place baseline 80% down from top of bbox
                                sr_origin_y = sr_y_top + sr_size * 0.80
                            elif seg_kind == "super":
                                sr_origin_y = origin_y - fontsize * 0.33
                            else:
                                sr_origin_y = origin_y + fontsize * 0.15

                            plan["insert_chars"].append({
                                "pos": fitz.Point(seg_cursor_x, sr_origin_y),
                                "text": seg_text,
                                "fontname": font_result.fontname,
                                "fontsize": sr_size,
                                "color": seg_color,
                                "morph": None,
                            })
                            try:
                                seg_cursor_x += measure_font.text_length(
                                    seg_text, fontsize=sr_size
                                )
                            except Exception:
                                seg_cursor_x += len(seg_text) * sr_size * 0.5

                            logger.info(
                                f"  segment {seg_kind} '{seg_text}' "
                                f"at origin_y={sr_origin_y:.1f} "
                                f"(parent={origin_y:.1f}), "
                                f"fontsize={sr_size:.1f} "
                                f"(parent={fontsize:.1f})"
                            )

                else:
                    # No script ranges — use the existing per-char fallback path
                    # for plain-text fallback when minimal-diff couldn't run.
                    if rawdict_chars:
                        raw_text_fb = "".join(ch.get("c", "") for ch in rawdict_chars)
                        prefix_len, raw_end, new_end = _find_change_range(raw_text_fb, new_text)
                        changed_new = new_text[prefix_len:new_end]

                        if prefix_len > 0:
                            prefix_text = "".join(
                                rawdict_chars[i]["c"] for i in range(prefix_len)
                            )
                            plan["insert_chars"].append({
                                "pos": fitz.Point(
                                    rawdict_chars[0]["origin"][0],
                                    rawdict_chars[0]["origin"][1],
                                ),
                                "text": prefix_text,
                                "fontname": font_result.fontname,
                                "fontsize": fontsize,
                                "color": insert_color,
                                "morph": None
                            })

                        if changed_new:
                            if raw_end > prefix_len and raw_end <= len(rawdict_chars):
                                ins_x = rawdict_chars[prefix_len]["bbox"][0]
                                ins_y = rawdict_chars[prefix_len]["origin"][1]
                                erase_w = rawdict_chars[raw_end - 1]["bbox"][2] - ins_x
                            else:
                                ins_x = rawdict_chars[-1]["bbox"][2] if rawdict_chars else x0
                                ins_y = origin_y
                                erase_w = 0

                            insert_pt = fitz.Point(ins_x, ins_y)
                            morph = None
                            if measure_font and erase_w > 0:
                                try:
                                    new_w = measure_font.text_length(changed_new, fontsize=fontsize)
                                    if new_w > 0:
                                        scale_x = erase_w / new_w
                                        if 0.5 <= scale_x <= 2.0:
                                            morph = (insert_pt, fitz.Matrix(scale_x, 1))
                                except Exception:
                                    pass

                            plan["insert_chars"].append({
                                "pos": insert_pt,
                                "text": changed_new,
                                "fontname": font_result.fontname,
                                "fontsize": fontsize,
                                "color": insert_color,
                                "morph": morph
                            })
                        if raw_end < len(rawdict_chars):
                            suffix_text = "".join(
                                rawdict_chars[i]["c"]
                                for i in range(raw_end, len(rawdict_chars))
                            )
                            plan["insert_chars"].append({
                                "pos": fitz.Point(
                                    rawdict_chars[raw_end]["origin"][0],
                                    rawdict_chars[raw_end]["origin"][1],
                                ),
                                "text": suffix_text,
                                "fontname": font_result.fontname,
                                "fontsize": fontsize,
                                "color": insert_color,
                                "morph": None
                            })

                    else:
                        # No rawdict_chars at all — emit the whole new_text
                        # as a single insert at the line's origin.
                        plan["insert_chars"].append({
                            "pos": fitz.Point(x0, origin_y),
                            "text": new_text,
                            "fontname": font_result.fontname,
                            "fontsize": fontsize,
                            "color": insert_color,
                            "morph": None
                        })

            edit_plans.append(plan)

        # ── Phase 2: Redact all erase regions at once ──
        # Sample the background color just above/below each erase rect.
        # This preserves colored backgrounds (table stripes, tinted boxes)
        # instead of painting them white.
        def _sample_background_color(page, rect):
            """Sample the pixel color in thin strips to the LEFT and RIGHT
            of the erase rect, on the SAME row. Sampling above/below is
            unreliable in tables — the strip above/below may fall into a
            different cell with a different background. Same-row sampling
            stays within the cell.

            Returns an (r, g, b) tuple in 0-1 range. Falls back to white if
            sampling fails or returns no samples (e.g. text spans the full
            cell width with no padding to sample).
            """
            try:
                pix = page.get_pixmap(dpi=72)  # 1pt = 1px at 72dpi
                samples = []

                # Sample strips to the LEFT and RIGHT of the erase rect on
                # the SAME row. We use a 4pt-wide strip and stay vertically
                # within the rect's y-range so we never cross into adjacent
                # cells/rows.
                strip_left = fitz.Rect(
                    max(0, rect.x0 - 5), rect.y0 + 1, rect.x0 - 1, rect.y1 - 1
                )
                strip_right = fitz.Rect(
                    rect.x1 + 1, rect.y0 + 1, rect.x1 + 5, rect.y1 - 1
                )

                for strip in (strip_left, strip_right):
                    x0i, y0i = int(max(0, strip.x0)), int(max(0, strip.y0))
                    x1i = int(min(pix.width, strip.x1))
                    y1i = int(min(pix.height, strip.y1))
                    if x1i <= x0i or y1i <= y0i:
                        continue
                    for py in range(y0i, y1i):
                        for px in range(x0i, x1i):
                            r, g, b = pix.pixel(px, py)[:3]
                            samples.append((r, g, b))

                # If horizontal sampling produced nothing useful (text fills
                # the cell with no padding), fall back to one row above the
                # rect — better than guessing white.
                if not samples:
                    strip_above = fitz.Rect(
                        rect.x0, max(0, rect.y0 - 2), rect.x1, rect.y0 - 0.5
                    )
                    x0i, y0i = int(max(0, strip_above.x0)), int(max(0, strip_above.y0))
                    x1i = int(min(pix.width, strip_above.x1))
                    y1i = int(min(pix.height, strip_above.y1))
                    if x1i > x0i and y1i > y0i:
                        for py in range(y0i, y1i):
                            for px in range(x0i, x1i):
                                r, g, b = pix.pixel(px, py)[:3]
                                samples.append((r, g, b))

                if not samples:
                    return (1.0, 1.0, 1.0)

                # Use median (not mean) — robust against any text pixel
                # leakage at the edges.
                samples.sort(key=lambda rgb: rgb[0] + rgb[1] + rgb[2])
                mid_rgb = samples[len(samples) // 2]
                return (mid_rgb[0] / 255.0, mid_rgb[1] / 255.0, mid_rgb[2] / 255.0)
            except Exception as e:
                logger.debug(f"background sample failed: {e}")
                return (1.0, 1.0, 1.0)

        for plan in edit_plans:
            for rect in plan["erase_rects"]:
                bg_color = _sample_background_color(page, rect)
                logger.info(
                    f"REDACT: rect=[{rect.x0:.2f}, {rect.y0:.2f}, "
                    f"{rect.x1:.2f}, {rect.y1:.2f}] bg={bg_color}"
                )
                # List what text is about to be erased INSIDE this rect
                try:
                    text_in_rect = page.get_text("text", clip=rect).strip()
                    if text_in_rect:
                        logger.info(f"  ERASING TEXT: {text_in_rect[:200]!r}")
                except Exception:
                    pass
                page.add_redact_annot(rect, fill=bg_color)
        page.apply_redactions(images=0, graphics=0)

        # ── Phase 2.5: Re-register fonts after redaction ──
        # apply_redactions() strips font resources from the page, so any
        # previously registered embedded fonts become unavailable.
        # Re-register every unique font we plan to use.
        registered_fonts = set()
        for plan in edit_plans:
            for fontname, font_buffer in plan["font_registrations"].items():
                if fontname not in registered_fonts:
                    page.insert_font(fontname=fontname, fontbuffer=font_buffer)
                    registered_fonts.add(fontname)
                    logger.info(f"Re-registered font '{fontname}' after redaction")

        # ── Phase 3.5: Apply super/sub baseline adjustments ──
        # For each plan's super_ranges, we need to: erase the chars that
        # Phase 3 just inserted at those positions, then re-insert them at
        # a raised/lowered baseline using the super's own (smaller) font size.
        # Since we can't easily erase just-inserted chars, we take a simpler
        # approach: identify which ops in the plan correspond to super ranges
        # BEFORE they get inserted, and insert those ops with adjusted y.
        # This is done inline in Phase 3, so this 3.5 pass is a no-op placeholder
        # unless we refactor. Keep for future extensibility.
        pass

        # ── Phase 3: Insert all new text ──
        # Ops carry their own correct positions and fontsizes. For lines
        # with super_ranges, Phase 1's segmented-insert path already split
        # super segments into separate ops with super-baseline + super-size
        # baked in. For lines without super_ranges, ops are normal-baseline.
        # All this phase does is emit each op, with optional coalescing of
        # adjacent single-char ops that share style + baseline (which
        # reduces fragmentation in the resulting PDF).
        for plan in edit_plans:
            ops = plan["insert_chars"]
            if not ops:
                continue

            i = 0
            while i < len(ops):
                op = ops[i]
                op_text = op["text"]

                # Multi-char or morphed ops emit solo (no coalescing needed)
                if len(op_text) > 1 or op["morph"] is not None:
                    page.insert_text(
                        op["pos"], op_text,
                        fontname=op["fontname"], fontsize=op["fontsize"],
                        color=op["color"], morph=op["morph"],
                    )
                    i += 1
                    continue

                # Single-char op — try to coalesce with adjacent single-char
                # ops that share font, size, color, and baseline.
                group_text = op_text
                j = i + 1
                while j < len(ops):
                    nxt = ops[j]
                    if (len(nxt["text"]) == 1
                            and nxt["morph"] is None
                            and nxt["fontname"] == op["fontname"]
                            and abs(nxt["fontsize"] - op["fontsize"]) < 0.01
                            and nxt["color"] == op["color"]
                            and abs(nxt["pos"].y - op["pos"].y) < 0.5):
                        group_text += nxt["text"]
                        j += 1
                    else:
                        break

                page.insert_text(
                    op["pos"], group_text,
                    fontname=op["fontname"], fontsize=op["fontsize"],
                    color=op["color"],
                )
                logger.info(
                    f"Grouped {j - i} char(s) into single insert: '{group_text[:40]}'"
                )
                i = j

    # ── Subset embedded fonts to keep file size reasonable ──────────────────
    # Only subsets newly embedded fonts; original subset fonts are untouched.
    try:
        doc.subset_fonts()
    except Exception as e:
        logger.warning(f"subset_fonts() failed (non-fatal): {e}")

    # ── Serialise ────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    buf.seek(0)

    # Encode warnings as a response header so the frontend can read them
    # without having to parse a multipart body.
    # Max header size is ~8 KB; warnings are short strings so this is safe.
    import urllib.parse
    warnings_header = urllib.parse.quote(json.dumps(warnings)) if warnings else ""

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":        "attachment; filename=edited.pdf",
            "Access-Control-Expose-Headers": "Content-Disposition, X-Font-Warnings",
            "X-Font-Warnings":            warnings_header,
        },
    )


# ── Helper: resolve the text color to use ────────────────────────────────────

def _resolve_color(
    page:  fitz.Page,
    edit:  dict,
    x0: float, y0: float, x1: float, y1: float,
) -> tuple:
    """
    Priority:
      1. Explicit hex color chosen by the user in the editor (#rrggbb).
      2. Color sampled from the original PDF span at the edit's bbox.
      3. Black (0, 0, 0).
    """
    explicit = edit.get("color", "")
    if explicit and explicit.startswith("#") and len(explicit) == 7:
        try:
            return (
                int(explicit[1:3], 16) / 255.0,
                int(explicit[3:5], 16) / 255.0,
                int(explicit[5:7], 16) / 255.0,
            )
        except ValueError:
            pass

    # Sample from the PDF's own text data
    try:
        clip     = fitz.Rect(x0, y0, x1, y1)
        text_dict = page.get_text("dict", clip=clip)
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    srgb = span.get("color", 0)
                    r, g, b = (
                        ((srgb >> 16) & 255) / 255.0,
                        ((srgb >>  8) & 255) / 255.0,
                        ( srgb        & 255) / 255.0,
                    )
                    logger.info(
                        f"_resolve_color: clip=[{x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}] "
                        f"sampled color from span {span.get('text', '')[:30]!r} "
                        f"→ RGB=({r:.2f}, {g:.2f}, {b:.2f})"
                    )
                    return (r, g, b)
    except Exception:
        pass

    return (0.0, 0.0, 0.0)  # default black

# ── Helper: resolve the true font name via spatial lookup ────────────────────

def _resolve_font_name(
    page:  fitz.Page,
    edit:  dict,
    x0: float, y0: float, x1: float, y1: float,
) -> str:
    """
    If the frontend sends a synthetic PDF.js font ID (like "g_d0_f9"), we query
    PyMuPDF's spatial text dictionary at the edit coordinates *before* erasure
    to extract the actual document root BaseFont name (like "DejaVuSans").
    """
    original_font = edit.get("fontName", "")
    
    # Check if it looks like a generated ID, or just always try to sample if possible
    # We will try sampling for everything to be safe. PDF.js usually uses "g_d...", "F1", etc.
    try:
        # We add a slight margin just in case the client tight-cropped the bbox
        clip = fitz.Rect(x0 - 1, y0, x1 + 1, y1)
        text_dict = page.get_text("dict", clip=clip)
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    found_font = span.get("font")
                    if found_font:
                        # Return the true underlying font name immediately
                        return found_font
    except Exception:
        pass
        
    return original_font
