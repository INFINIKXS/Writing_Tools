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

def _measure_span_width(page: fitz.Page, x0: float, origin_y: float):
    """
    Measure the true rendered width of text at the given baseline origin
    AND return the full line's per-character data.

    A "span" in PyMuPDF's rawdict is a run of identically-styled text — a
    long visual line that contains bold/italic/font-size variations (e.g.
    citations like ²⁵, italicised terms) is split into multiple spans.
    For correct minimal-diff editing we need ALL chars on the line, not
    just one span's chars. This function unions every span on the same
    baseline into a synthetic "line span" and returns it.

    Returns: (width, synthetic_line_span_dict) or (None, None) on failure.
    The synthetic span dict has the standard rawdict shape including a
    "chars" key with EVERY char on the line, sorted by x-position.
    """
    BASELINE_TOLERANCE = 2.0  # points

    # IMPORTANT: PyMuPDF's `clip` parameter silently omits any span that
    # is not FULLY contained inside the clip rect (see docs). Use a
    # page-wide clip bounded only in Y so long spans aren't dropped.
    page_rect = page.rect
    clip = fitz.Rect(page_rect.x0, origin_y - 15, page_rect.x1, origin_y + 10)
    try:
        rd = page.get_text("rawdict", clip=clip)
    except Exception:
        return None, None

    # Collect every span whose baseline matches origin_y
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

    # Union every char from every same-baseline span, sorted by x-position.
    # This gives us the COMPLETE line of text — across all style boundaries.
    all_chars = []
    for span in baseline_spans:
        all_chars.extend(span.get("chars", []))
    if not all_chars:
        # Fall back to bbox of the closest span
        best_span = min(baseline_spans, key=lambda s: abs(s["origin"][0] - x0))
        sb = best_span.get("bbox", (0, 0, 0, 0))
        return sb[2] - sb[0], best_span

    all_chars.sort(key=lambda c: c["bbox"][0])

    # Width = leftmost char's x0 to rightmost char's x1
    measured_w = all_chars[-1]["bbox"][2] - all_chars[0]["bbox"][0]

    # Build a synthetic "line span" carrying the unified char list.
    # Use the closest-to-x0 span's metadata (font, size, color, origin)
    # since that's most likely the styling at the click point.
    closest_span = min(baseline_spans, key=lambda s: abs(s["origin"][0] - x0))
    synthetic_span = dict(closest_span)  # shallow copy of metadata
    synthetic_span["chars"] = all_chars
    # Recompute bbox to cover all chars
    synthetic_span["bbox"] = (
        all_chars[0]["bbox"][0],
        min(c["bbox"][1] for c in all_chars),
        all_chars[-1]["bbox"][2],
        max(c["bbox"][3] for c in all_chars),
    )

    logger.info(
        f"_measure_span_width: x0={x0:.1f} origin_y={origin_y:.1f} → "
        f"width={measured_w:.2f}, "
        f"unified {len(baseline_spans)} span(s) into {len(all_chars)} chars"
    )
    return measured_w, synthetic_span


# ── Helper: get per-font space width from get_texttrace() ────────────────────

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
            measured_w, matched_span = _measure_span_width(page, x0, origin_y)
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
            ascender_h  = edit.get("ascender_h",  fontsize * 0.8)
            descender_h = edit.get("descender_h", fontsize * 0.2)
            erase_y0 = origin_y - ascender_h
            erase_y1 = origin_y + descender_h

            plan = {
                "erase_rects": [],
                "insert_chars": [],
                "font_registrations": {}  # fontname -> font_buffer for re-registration after redaction
            }

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
                            left_margin = fontsize * 0.15 if not changed_new else 0
                            erase_rect = fitz.Rect(
                                erase_x0 + left_margin, erase_y0 - 1,
                                erase_x1 + 1, erase_y1 + 1
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

                            # ── Word-grouped insertion ──
                            # Group characters into words, insert each word as one
                            # string.  Spaces are cursor advances between words.
                            # This produces one BT/ET (one TextItem) per word
                            # instead of per letter.
                            cursor_x = erase_x0
                            current_word = ""
                            word_start_x = cursor_x

                            for ch in changed_new:
                                if ch == " ":
                                    # Flush the current word as one insert
                                    if current_word:
                                        plan["insert_chars"].append({
                                            "pos": fitz.Point(word_start_x, change_origin_y),
                                            "text": current_word,
                                            "fontname": font_result.fontname,
                                            "fontsize": fontsize,
                                            "color": insert_color,
                                            "morph": None
                                        })
                                        current_word = ""
                                    cursor_x += space_adv
                                    word_start_x = cursor_x
                                else:
                                    if not current_word:
                                        word_start_x = cursor_x
                                    current_word += ch
                                    if ch in advance_table:
                                        cursor_x += advance_table[ch]
                                    elif measure_font:
                                        try:
                                            cursor_x += measure_font.text_length(
                                                ch, fontsize=fontsize
                                            )
                                        except Exception:
                                            cursor_x += avg_letter_adv
                                    else:
                                        cursor_x += avg_letter_adv

                            # Flush the last word
                            if current_word:
                                plan["insert_chars"].append({
                                    "pos": fitz.Point(word_start_x, change_origin_y),
                                    "text": current_word,
                                    "fontname": font_result.fontname,
                                    "fontsize": fontsize,
                                    "color": insert_color,
                                    "morph": None
                                })

                        used_minimal_diff = True
                else:
                    logger.info("MINIMAL DIFF: no change between rawdict text and newStr — skipping")
                    used_minimal_diff = True

            # ── FALLBACK: Per-character reconstruction ───────────────────────────
            if not used_minimal_diff:
                logger.info(
                    f"PER-CHAR RECONSTRUCTION: rawdict_chars={len(rawdict_chars)}, "
                    f"origStr_len={len(orig_text)}"
                )

                erase_rect = fitz.Rect(x0 - 1, erase_y0 - 1, x1 + 1, erase_y1 + 1)
                plan["erase_rects"].append(erase_rect)

                if rawdict_chars:
                    raw_text_fb = "".join(ch.get("c", "") for ch in rawdict_chars)
                    prefix_len, raw_end, new_end = _find_change_range(raw_text_fb, new_text)
                    changed_new = new_text[prefix_len:new_end]

                    # Insert prefix as one grouped string (one TextItem)
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
                                        logger.info(f"reconstruction morph scale_x={scale_x:.3f}")
                            except Exception:
                                pass

                        if " " in changed_new and (not has_space or space_width < fontsize * 0.1):
                            space_w = _get_space_width(page, ins_x, ins_y, fontsize)
                            cursor_x = ins_x
                            for word in changed_new.split(" "):
                                if word:
                                    plan["insert_chars"].append({
                                        "pos": fitz.Point(cursor_x, ins_y),
                                        "text": word,
                                        "fontname": font_result.fontname,
                                        "fontsize": fontsize,
                                        "color": insert_color,
                                        "morph": None
                                    })
                                    try:
                                        cursor_x += measure_font.text_length(word, fontsize=fontsize)
                                    except Exception:
                                        cursor_x += len(word) * (fontsize * 0.5)
                                cursor_x += space_w
                        else:
                            plan["insert_chars"].append({
                                "pos": insert_pt,
                                "text": changed_new,
                                "fontname": font_result.fontname,
                                "fontsize": fontsize,
                                "color": insert_color,
                                "morph": morph
                            })

                    # Insert suffix as one grouped string (one TextItem)
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

        # ── Phase 3: Insert all new text (grouped to minimize content stream objects) ──
        # Each insert_text() call creates a separate BT/ET + Tj in the content
        # stream.  PDF.js getTextContent() maps each BT/ET to one TextItem, so
        # per-character insertion means one editing box per letter.  By coalescing
        # consecutive single-char ops that share the same baseline, font, size,
        # and color into a single insert_text() call, we get one TextItem per
        # logical group (prefix, replacement, suffix).
        for plan in edit_plans:
            ops = plan["insert_chars"]
            if not ops:
                continue

            i = 0
            while i < len(ops):
                op = ops[i]

                # Multi-char text or morph — emit solo (already grouped or needs transform)
                if len(op["text"]) > 1 or op["morph"] is not None:
                    page.insert_text(
                        op["pos"], op["text"],
                        fontname=op["fontname"], fontsize=op["fontsize"],
                        color=op["color"], morph=op["morph"],
                    )
                    i += 1
                    continue

                # Try to coalesce consecutive single-char ops on the same baseline
                group_text = op["text"]
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

                # Insert the entire group as one string at the first char's position
                page.insert_text(
                    op["pos"], group_text,
                    fontname=op["fontname"], fontsize=op["fontsize"],
                    color=op["color"],
                )
                logger.info(f"Grouped {j - i} chars into single insert: '{group_text[:40]}...' " if len(group_text) > 40 else f"Grouped {j - i} char(s) into single insert: '{group_text}'")
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
                    return (
                        ((srgb >> 16) & 255) / 255.0,
                        ((srgb >>  8) & 255) / 255.0,
                        ( srgb        & 255) / 255.0,
                    )
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
