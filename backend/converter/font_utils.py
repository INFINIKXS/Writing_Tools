import fitz
import io
import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import cmap_format_4

logger = logging.getLogger(__name__)


# ── Base-14 / common font name aliases ──────────────────────────────────────
# Maps substrings found in PDF font names to PyMuPDF built-in codes.
# PyMuPDF supports these without any extra package:
#   helv  → Helvetica      tiro  → Times-Roman
#   cour  → Courier        zadb  → ZapfDingbats
_BASE14_MAP = {
    "helvetica":    "helv",
    "arial":        "helv",
    "times":        "tiro",
    "timesnewroman":"tiro",
    "timesnewromanpsmt": "tiro",
    "courier":      "cour",
    "couriernew":   "cour",
}

# pymupdf-fonts codes (pip install pymupdf-fonts required).
# We only call these as fallback — never as the primary path.
_PYMUPDF_SERIF_CODE  = "times"   # Nimbus Roman — visually ≈ Times New Roman
_PYMUPDF_SANS_CODE   = "notos"   # Noto Sans — visually ≈ Helvetica/Arial
_PYMUPDF_MONO_CODE   = "spacemo" # Space Mono


@dataclass
class FontResult:
    """Everything pdf_edit.py needs to insert text with the right font."""
    fontname:      str            # name to pass to page.insert_font / insert_text
    font_buffer:   Optional[bytes] = None  # raw bytes if embedded font was extracted
    fallback_used: bool = False
    fallback_reason: str = ""
    missing_glyphs: list = field(default_factory=list)  # chars not in the font


# ── Public entry point ───────────────────────────────────────────────────────

def get_font_for_edit(doc: fitz.Document, page: fitz.Page, edit: dict) -> FontResult:
    """
    Return the best FontResult for inserting edit["newStr"] into the page.

    Steps:
      1. Try to extract the embedded font whose name matches edit["fontName"].
      2. Validate the extracted bytes with fitz.Font().
      3. Check that every character in newStr has a glyph in that font.
      4. If all good: return the embedded font (no fallback).
      5. If font is unusable or glyphs are missing: fall back to the closest
         built-in / pymupdf-font and set fallback_used=True with a reason.
    """
    new_text  = edit.get("newStr", "")
    font_name = edit.get("fontName", "")
    is_bold   = edit.get("isBold", False)
    is_italic = edit.get("isItalic", False)

    # ── Step 1: Try to find and extract the matching embedded font ───────────
    extracted = _extract_matching_font(doc, page, font_name)

    if extracted is not None:
        font_bytes, matched_basefont, xref = extracted
        
        # ── Step 1.5: Inject OS Cmap for subsets ────────────────────────────
        font_bytes = _inject_cmap(font_bytes, doc, xref)

        # ── Step 2: Validate — can MuPDF parse these bytes? ─────────────────
        try:
            test_font = fitz.Font(fontbuffer=font_bytes)
        except Exception as e:
            reason = (
                f"Embedded font '{matched_basefont}' could not be parsed by MuPDF "
                f"({type(e).__name__}: {e}). This is typical for CFF/Type1 subsets "
                f"and Identity-H CID composites."
            )
            logger.warning(reason)
            return _fallback(font_name, is_bold, is_italic, reason)

        # ── Step 3: Check glyph coverage for the new text ───────────────────
        missing = _find_missing_glyphs(test_font, new_text)

        if missing:
            # Font parsed but subset doesn't have all required characters.
            # This is expected for subset fonts — the original PDF only embedded
            # glyphs that appeared in the document.
            reason = (
                f"Embedded font '{matched_basefont}' is missing glyphs for: "
                f"{missing!r}. These characters were not present in the original "
                f"document's font subset."
            )
            logger.warning(reason)
            return FontResult(
                fontname=f"emb_{matched_basefont[:20]}",
                font_buffer=font_bytes,
                fallback_used=True,
                fallback_reason=reason,
                missing_glyphs=missing,
            )

        # ── Step 4: All good — return embedded font ──────────────────────────
        logger.info(f"Using embedded font '{matched_basefont}' for edit.")
        return FontResult(
            fontname=f"emb_{matched_basefont[:20]}",
            font_buffer=font_bytes,
            fallback_used=False,
        )

    # ── Step 5: No extractable font found — try Base-14 match first ─────────
    base14 = _match_base14(font_name)
    if base14:
        logger.info(f"Using Base-14 font '{base14}' matched from '{font_name}'.")
        return FontResult(fontname=base14, fallback_used=False)

    # ── Step 6: Full fallback to pymupdf-fonts ───────────────────────────────
    reason = (
        f"No embedded font matched '{font_name}' in the PDF font table, "
        f"and no Base-14 alias was found."
    )
    logger.warning(reason)
    return _fallback(font_name, is_bold, is_italic, reason)


# ── Private helpers ──────────────────────────────────────────────────────────

def _extract_matching_font(
    doc: fitz.Document,
    page: fitz.Page,
    font_name: str,
) -> Optional[tuple]:
    """
    Search the page's font table for a font whose basefont name matches
    font_name (after stripping the ABCDEF+ subset prefix).

    Returns (font_bytes, matched_basefont) or None.
    """
    if not font_name:
        return None

    # Strip the 6-char uppercase subset prefix (e.g. "ABCDEF+TimesNewRoman" → "TimesNewRoman")
    target = font_name.split("+")[-1].lower().replace(" ", "").replace("-", "")

    for entry in page.get_fonts(full=True):
        # entry = (xref, ext, type, basefont, name, encoding, ...)
        xref      = entry[0]
        ext       = entry[1]   # "ttf", "cff", "cid", "n/a", etc.
        basefont  = entry[3]
        refname   = entry[4] if len(entry) > 4 else ""

        # Skip fonts with no extractable binary
        if ext == "n/a":
            continue

        candidate = basefont.split("+")[-1].lower().replace(" ", "").replace("-", "")
        refname_candidate = refname.lower().replace(" ", "").replace("-", "")

        # Require at least a partial match on basefont OR an exact match on refname
        if not (target in candidate or candidate in target or target == refname_candidate):
            continue

        try:
            font_data = doc.extract_font(xref)
            # extract_font returns (name, ext, type, [subbuffer], buffer)
            # The raw bytes are always the LAST element
            font_bytes = font_data[-1]
            if not font_bytes or len(font_bytes) < 64:
                continue
            return (font_bytes, basefont, xref)
        except Exception as e:
            logger.debug(f"extract_font({xref}) failed: {e}")
            continue

    return None


def _find_missing_glyphs(font: fitz.Font, text: str) -> list:
    """
    Return a list of characters in `text` that have no glyph in `font`.

    Uses Font.has_glyph() with fallback=False so we only count glyphs
    that are physically present in the font binary, not MuPDF substitutes.

    Note: valid_codepoints() is broken in PyMuPDF >= 1.24.x (issue #3933),
    so we use has_glyph() per-character instead.
    """
    missing = []
    seen = set()
    for ch in text:
        if ch in seen or ch in (" ", "\n", "\r", "\t"):
            continue
        seen.add(ch)
        try:
            # fallback=False → returns 0 if the glyph is genuinely absent
            if not font.has_glyph(ord(ch), fallback=False):
                missing.append(ch)
        except Exception:
            # If has_glyph raises (e.g. corrupt font), treat as missing
            missing.append(ch)
    return missing


def _match_base14(font_name: str) -> Optional[str]:
    """
    Try to match font_name to a PyMuPDF Base-14 code without extracting bytes.
    Returns the code string (e.g. "tiro") or None.
    """
    normalised = font_name.split("+")[-1].lower().replace(" ", "").replace("-", "")
    for key, code in _BASE14_MAP.items():
        if key in normalised or normalised in key:
            return code
    return None


def _fallback(
    original_font_name: str,
    is_bold: bool,
    is_italic: bool,
    reason: str,
) -> FontResult:
    """
    Choose the best pymupdf-font fallback based on the original font name's
    visual characteristics (serif / sans-serif / monospaced).

    Requires: pip install pymupdf-fonts
    """
    name_lower = original_font_name.lower()

    # Monospaced detection
    if any(k in name_lower for k in ("courier", "mono", "consolas", "inconsolata", "code")):
        code = _PYMUPDF_MONO_CODE
        description = "Space Mono (monospaced fallback)"

    # Serif detection
    elif any(k in name_lower for k in (
        "times", "roman", "georgia", "garamond", "palatino",
        "minion", "cambria", "charter", "bookman", "caslon",
        "fruti", "nimbus", "utopia", "baskerville"
    )):
        code = _PYMUPDF_SERIF_CODE
        description = "Nimbus Roman (serif fallback ≈ Times New Roman)"

    # Default: sans-serif
    else:
        code = _PYMUPDF_SANS_CODE
        description = "Noto Sans (sans-serif fallback)"

    # Append bold/italic variant suffix where pymupdf-fonts supports it
    # pymupdf-fonts naming: "times" = regular, "timesbo" = bold, "timesit" = italic, "timesbi" = bold-italic
    suffix = ""
    if is_bold and is_italic:
        suffix = "bi"
    elif is_bold:
        suffix = "bo"
    elif is_italic:
        suffix = "it"

    full_code = code + suffix

    # Verify the variant exists — pymupdf-fonts doesn't have all combinations
    try:
        f = fitz.Font(full_code)
        chosen_code = full_code
        font_buf = f.buffer
    except Exception:
        # Variant not available — use regular weight
        chosen_code = code
        description += f" (bold/italic variant '{full_code}' not available, using regular)"
        f = fitz.Font(code)
        font_buf = f.buffer

    full_reason = f"{reason} Falling back to: {description}."

    return FontResult(
        fontname=chosen_code,
        font_buffer=font_buf,
        fallback_used=True,
        fallback_reason=full_reason,
        missing_glyphs=[],
    )


def _inject_cmap(font_bytes: bytes, doc: fitz.Document, xref: int) -> bytes:
    """
    Subverts PyMuPDF's failure to natively render Identity-H subsets by wrapping the
    raw extracted font block in fontTools, parsing the PDF's /ToUnicode byte stream,
    and explicitly injecting a WinAnsi cmap subtable into the header.
    """
    try:
        font_dict = doc.xref_object(xref)
        if "/ToUnicode" not in font_dict:
            return font_bytes
            
        parts = font_dict.split("/ToUnicode")
        if len(parts) < 2:
            return font_bytes
            
        tu_xref = int(parts[1].split()[0])
        cmap_data = doc.xref_stream(tu_xref).decode(errors="ignore")
        
        uni_to_cid = {}
        for m in re.finditer(r'<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>', cmap_data):
            cid = int(m.group(1), 16)
            uni = int(m.group(2), 16)
            uni_to_cid[uni] = cid
            
        for m in re.finditer(r'<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>', cmap_data):
            start_cid = int(m.group(1), 16)
            end_cid = int(m.group(2), 16)
            start_uni = int(m.group(3), 16)
            for offset in range(end_cid - start_cid + 1):
                uni_to_cid[start_uni + offset] = start_cid + offset

        if not uni_to_cid:
            return font_bytes

        tt = TTFont(io.BytesIO(font_bytes))
        
        # Build mapping from unicode to actual glyph name stored in the TTF
        glyph_order = tt.getGlyphOrder()
        new_cmap = {}
        for uni, cid in uni_to_cid.items():
            if cid < len(glyph_order):
                new_cmap[uni] = glyph_order[cid]
            else:
                gname = f"cid{cid:05d}"
                if gname in glyph_order:
                    new_cmap[uni] = gname
                    
        if not new_cmap:
            return font_bytes

        cmap_table = tt.get('cmap')
        if not cmap_table:
            tt['cmap'] = tt.getTableClass('cmap')()
            tt['cmap'].tableVersion = 0
            tt['cmap'].tables = []
            
        new_subtable = cmap_format_4(4)
        new_subtable.platformID = 3
        new_subtable.platEncID = 1
        new_subtable.language = 0
        new_subtable.cmap = new_cmap
        
        cmap_table = tt['cmap']
        cmap_table.tables = [t for t in cmap_table.tables if not (t.platformID == 3 and t.platEncID == 1)]
        cmap_table.tables.append(new_subtable)
        
        out = io.BytesIO()
        tt.save(out)
        logger.info(f"Successfully injected ToUnicode CMap matrix into {len(new_cmap)} subsets.")
        return out.getvalue()
        
    except Exception as e:
        logger.warning(f"CMap injection failed (falling back to raw subset bounds): {e}")
        return font_bytes