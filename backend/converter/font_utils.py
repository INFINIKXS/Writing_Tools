import fitz
import io
import re
import struct
import logging
from dataclasses import dataclass, field
from typing import Optional
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

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

# ── Layer 1 & 2: CFF-to-OTF Integration ──────────────────────────────────────

def detect_font_format(font_bytes: bytes) -> str:
    """
    Detect the actual binary format of extracted font bytes.
    Returns: 'ttf', 'otf', 'cff', or 'unknown'
    """
    if len(font_bytes) < 4:
        return 'unknown'
    
    magic = font_bytes[:4]
    if magic == b'\x00\x01\x00\x00':
        return 'ttf'
    elif magic == b'OTTO':
        return 'otf'
    elif magic == b'true':
        return 'ttf'
    elif magic[0] == 0x01 and magic[1] == 0x00:
        return 'cff'
    elif magic == b'wOFF':
        return 'woff'
    return 'unknown'

def _synthesize_required_otf_tables(otf: TTFont, cff_reader):
    from fontTools.ttLib import newTable
    
    head = newTable('head')
    head.tableVersion    = 1.0
    head.fontRevision    = 1.0
    head.checkSumAdjustment = 0
    head.magicNumber     = 0x5F0F3CF5
    head.flags           = 0x000B
    
    units = 1000
    if hasattr(cff_reader, "topDictIndex") and len(cff_reader.topDictIndex) > 0:
        topDict = cff_reader.topDictIndex[0]
        if hasattr(topDict, "FontMatrix") and topDict.FontMatrix[0] != 0:
            units = int(round(1.0 / topDict.FontMatrix[0]))
    head.unitsPerEm      = units
    
    head.created         = head.modified = 0
    head.xMin = head.yMin = head.xMax = head.yMax = 0
    head.macStyle        = 0
    head.lowestRecPPEM   = 8
    head.fontDirectionHint = 2
    head.indexToLocFormat  = 0
    head.glyphDataFormat   = 0
    otf['head'] = head
    
    # Derive authoritative glyph order strictly from the CFF table
    glyph_order = otf.getGlyphOrder()
    
    hhea = newTable('hhea')
    hhea.tableVersion      = 0x00010000  # raw int — NOT floatToFixed, NOT fi2ve
    hhea.ascent            = 800
    hhea.descent           = -200
    hhea.lineGap           = 0
    hhea.advanceWidthMax   = 1000
    hhea.minLeftSideBearing  = 0
    hhea.minRightSideBearing = 0
    hhea.xMaxExtent        = 0
    hhea.caretSlopeRise    = 1
    hhea.caretSlopeRun     = 0
    hhea.caretOffset       = 0
    hhea.reserved0 = hhea.reserved1 = hhea.reserved2 = hhea.reserved3 = 0
    hhea.metricDataFormat  = 0
    hhea.numberOfHMetrics  = len(otf.getGlyphOrder())
    otf['hhea'] = hhea
    
    maxp = newTable('maxp')
    maxp.tableVersion = 0x00005000; maxp.numGlyphs = len(glyph_order)
    otf['maxp'] = maxp
    
    os2 = newTable('OS/2')
    os2.version = 4; os2.xAvgCharWidth = 500; os2.usWeightClass = 400; os2.usWidthClass = 5
    os2.fsType = 0; os2.ySubscriptXSize = 650; os2.ySubscriptYSize = 600
    os2.ySubscriptXOffset = 0; os2.ySubscriptYOffset = 75; os2.ySuperscriptXSize = 650
    os2.ySuperscriptYSize = 600; os2.ySuperscriptXOffset = 0; os2.ySuperscriptYOffset = 350
    os2.yStrikeoutSize = 50; os2.yStrikeoutPosition = 300; os2.sFamilyClass = 0
    
    from fontTools.ttLib.tables.O_S_2f_2 import Panose
    panose = Panose()
    panose.bFamilyType = 0; panose.bSerifStyle = 0; panose.bWeight = 0; panose.bProportion = 0
    panose.bContrast = 0; panose.bStrokeVariation = 0; panose.bArmStyle = 0; panose.bLetterForm = 0
    panose.bMidline = 0; panose.bXHeight = 0
    os2.panose = panose
    
    os2.ulUnicodeRange1 = 0; os2.ulUnicodeRange2 = 0
    os2.ulUnicodeRange3 = 0; os2.ulUnicodeRange4 = 0; os2.achVendID = "NONE"
    os2.fsSelection = 0; os2.usFirstCharIndex = 32; os2.usLastCharIndex = 65535
    os2.sTypoAscender = 1000; os2.sTypoDescender = -250; os2.sTypoLineGap = 0
    os2.usWinAscent = 1000; os2.usWinDescent = 250; os2.ulCodePageRange1 = 0
    os2.ulCodePageRange2 = 0; os2.sxHeight = 500; os2.sCapHeight = 700
    os2.usDefaultChar = 0; os2.usBreakChar = 32; os2.usMaxContext = 0
    otf['OS/2'] = os2
    
    post = newTable('post')
    post.formatType        = 3.0
    post.italicAngle       = 0
    post.underlinePosition  = -75
    post.underlineThickness = 50
    post.isFixedPitch      = 0
    post.minMemType42 = post.maxMemType42 = 0
    post.minMemType1  = post.maxMemType1  = 0
    otf['post'] = post
    
    name = newTable('name')
    name.names = []
    otf['name'] = name
    
    hmtx = newTable('hmtx')
    metrics = {}
    cff_font = list(cff_reader.values())[0] if hasattr(cff_reader, "values") else cff_reader[cff_reader.fontNames[0]]
    char_strings = cff_font.CharStrings
    private = cff_font.Private
    default_width = getattr(private, 'defaultWidthX', 500)
    nominal_width = getattr(private, 'nominalWidthX', 0)
    
    for gname in glyph_order:
        width = default_width  # fallback
        if gname in char_strings:
            cs = char_strings[gname]
            try:
                cs.decompile()
                if hasattr(cs, 'width') and cs.width is not None:
                    width = cs.width + nominal_width
                else:
                    width = default_width
            except Exception:
                width = default_width
        metrics[gname] = (int(width), 0)
    
    hmtx.metrics = metrics
    otf['hmtx'] = hmtx

def wrap_cff_in_otf(cff_bytes: bytes) -> Optional[bytes]:
    """Wraps bare CFF bytes into an OTF (SFNT) shell."""
    try:
        from fontTools import cffLib, ttLib
        
        # Parse pristine CFF stream designed strictly for binary pass-through
        cff_reader_pristine = cffLib.CFFFontSet()
        cff_reader_pristine.decompile(io.BytesIO(cff_bytes), otFont=None, isCFF2=False)
        
        # Parse disposable CFF stream strictly for dimensional width extraction
        metrics_reader = cffLib.CFFFontSet()
        metrics_reader.decompile(io.BytesIO(cff_bytes), otFont=None, isCFF2=False)
        
        otf = TTFont(sfntVersion='OTTO')
        cff_table = ttLib.newTable('CFF ')
        cff_table.cff = cff_reader_pristine
        otf['CFF '] = cff_table
        
        _synthesize_required_otf_tables(otf, metrics_reader)
        
        out = io.BytesIO()
        otf.save(out)
        return out.getvalue()
    except Exception as e:
        logger.warning(f"CFF wrapping failed: {e}")
        return None

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
        
        # ── Step 1.2: Layer 2 Detection & OTF Wrapping ──────────────────────
        fmt = detect_font_format(font_bytes)
        logger.info(f"Extracted font '{matched_basefont}' (xref={xref}) detected as: {fmt}")
        
        if fmt == 'cff':
            logger.info("Bare CFF detected. Attempting OTF wrapper injection...")
            otf_bytes = wrap_cff_in_otf(font_bytes)
            if otf_bytes:
                font_bytes = otf_bytes
                logger.info("CFF successfully wrapped in OTF container.")
            else:
                reason = f"Embedded CFF font '{matched_basefont}' could not be wrapped into OTF."
                logger.warning(reason)
                return _fallback(font_name, is_bold, is_italic, reason)
        elif fmt == 'unknown':
            reason = f"Embedded font '{matched_basefont}' has unknown binary format."
            logger.warning(reason)
            return _fallback(font_name, is_bold, is_italic, reason)

        # ── Step 1.5: Inject OS Cmap for subsets ────────────────────────────
        font_bytes = _inject_cmap(font_bytes, doc, xref, page, matched_basefont)
        if font_bytes is None:
            reason = f"Embedded font '{matched_basefont}' has corrupt/unsupported data (failed to rebuild cmap dictionary). Falling back to generic font."
            logger.warning(reason)
            return _fallback(font_name, is_bold, is_italic, reason)

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


def _decode_unicode_hex(hex_str: str) -> str:
    hex_str = hex_str.strip()
    result = ""
    if len(hex_str) % 4 != 0:
        hex_str = hex_str.zfill((len(hex_str) // 4 + 1) * 4)
    for i in range(0, len(hex_str), 4):
        cp = int(hex_str[i:i+4], 16)
        result += chr(cp)
    return result

def _parse_tounicode(doc: fitz.Document, font_xref: int) -> tuple[dict, dict]:
    single_map, multi_map = {}, {}
    try:
        tu_ref = doc.xref_get_key(font_xref, "ToUnicode")
        if not tu_ref or tu_ref[0] == "null":
            return single_map, multi_map
        m = re.match(r"(\d+)\s+\d+\s+R", tu_ref[1].strip())
        if not m:
            return single_map, multi_map
        tu_xref = int(m.group(1))
        raw = doc.xref_stream(tu_xref)
        if not raw:
            return single_map, multi_map
        text = raw.decode("latin-1", errors="replace")
        
        for m in re.finditer(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", text):
            try:
                cid = int(m.group(1), 16)
                chars = _decode_unicode_hex(m.group(2))
                if len(chars) == 1:
                    single_map[cid] = chars
                else:
                    multi_map[cid] = chars
            except Exception:
                pass
                
        for m in re.finditer(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", text):
            try:
                start = int(m.group(1), 16)
                end = int(m.group(2), 16)
                # Guard: skip absurdly large ranges (Identity-H full-Unicode mappings).
                # A legitimate bfrange for a subset font is at most 256 entries.
                # Ranges like 0x0000-0x10FFEE produce 1.1M entries and overwhelm the map.
                if end - start > 256:
                    continue
                base_chars = _decode_unicode_hex(m.group(3))
                for offset in range(end - start + 1):
                    cid = start + offset
                    if len(base_chars) == 1:
                        single_map[cid] = chr(ord(base_chars) + offset)
                    else:
                        multi_map[cid] = base_chars
            except Exception:
                pass
                
        for m in re.finditer(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[\s*(.*?)\s*\]", text):
            try:
                start = int(m.group(1), 16)
                end = int(m.group(2), 16)
                arr_content = m.group(3)
                arr_matches = re.findall(r"<([0-9A-Fa-f]+)>", arr_content)
                for offset, hex_str in enumerate(arr_matches):
                    if start + offset <= end:
                        cid = start + offset
                        chars = _decode_unicode_hex(hex_str)
                        if len(chars) == 1:
                            single_map[cid] = chars
                        else:
                            multi_map[cid] = chars
            except Exception as e:
                pass
    except Exception as e:
        logger.debug(f"ToUnicode parse failed: {e}")
        
    return single_map, multi_map

def _extract_cidtogidmap(doc: fitz.Document, font_xref: int) -> Optional[dict]:
    try:
        desc_ref = doc.xref_get_key(font_xref, "DescendantFonts")
        if not desc_ref or desc_ref[0] == "null":
            return None
            
        inner = re.findall(r"(\d+)\s+\d+\s+R", desc_ref[1].strip())
        if not inner:
            return None
            
        cid_font_xref = int(inner[0])
        cgmap_ref = doc.xref_get_key(cid_font_xref, "CIDToGIDMap")
        
        if not cgmap_ref or cgmap_ref[0] == "null":
            return None
            
        val = cgmap_ref[1].strip()
        if val.lower() == "/identity" or val == "Identity":
            return None
            
        m = re.match(r"(\d+)\s+\d+\s+R", val)
        if not m:
            return None
            
        map_xref = int(m.group(1))
        raw = doc.xref_stream(map_xref)
        if not raw:
            return None
            
        n = len(raw) // 2
        gids = struct.unpack(f">{n}H", raw[:n*2])
        result = {}
        for cid, gid in enumerate(gids):
            if gid != 0:
                result[cid] = gid
        return result
    except Exception as e:
        logger.debug(f"CIDToGIDMap extraction failed: {e}")
        return None

def _inject_cmap(font_bytes: bytes, doc: fitz.Document, xref: int, page: Optional[fitz.Page] = None, basefont_name: str = "") -> bytes:
    """
    Subverts PyMuPDF's failure to natively render Identity-H subsets by wrapping the
    raw extracted font block in fontTools, parsing the PDF's /ToUnicode byte stream,
    querying the actual CIDToGIDMap layout, patching zero-width advances,
    and explicitly injecting a WinAnsi cmap subtable into the header.
    """
    try:
        logger.info(f"==== INJECT_CMAP START: {basefont_name} (page {page.number if page else 'none'}) ====")
        single_map, multi_map = _parse_tounicode(doc, xref)
        logger.info(f"Parse ToUnicode: single_map={len(single_map)}, multi_map={len(multi_map)}")
        
        cidtogid_map = _extract_cidtogidmap(doc, xref)
        logger.info(f"Extracted CIDToGIDMap: {'YES (' + str(len(cidtogid_map)) + ')' if cidtogid_map else 'NO'}")
        
        tt = TTFont(io.BytesIO(font_bytes))
        glyph_order = tt.getGlyphOrder()
        n_glyphs = len(glyph_order)
        logger.info(f"TTFont loaded. n_glyphs={n_glyphs}")
        
        cid_to_gid = cidtogid_map if cidtogid_map else {}

        # Build lookup from font's own existing cmap before we replace it.
        # This provides a reliable GID mapping for fonts where neither the
        # CIDToGIDMap nor trace recovery cover all codepoints.
        # Note: bare CFF fonts wrapped in OTF containers may not have a cmap
        # table yet — that's the whole reason _inject_cmap() exists.
        font_cmap_gids = {}
        existing_cmap = None
        if 'cmap' in tt:
            try:
                existing_cmap = tt.getBestCmap()
            except Exception as e:
                logger.debug(f"getBestCmap() failed: {e}")
        if existing_cmap:
            glyph_name_to_idx = {name: i for i, name in enumerate(glyph_order)}
            for cp, gname in existing_cmap.items():
                if gname in glyph_name_to_idx:
                    font_cmap_gids[cp] = glyph_name_to_idx[gname]
            logger.info(f"Built font_cmap_gids with {len(font_cmap_gids)} entries from existing cmap")
        else:
            logger.info("No existing cmap in font — font_cmap_gids is empty")
        
        # BUG 3 FIX: Initialize unicode_to_gid BEFORE the try block so it
        # always exists, regardless of whether trace recovery succeeds.
        unicode_to_gid = {}
        trace_has_data = False
        
        # ALWAYS run trace recovery if page is available. It is the only reliable way
        # to map UCP->GID when ToUnicode is missing or CIDToGIDMap is Identity.
        if page and basefont_name:
            logger.info(f"Attempting Trace CID Recovery for: {basefont_name}")
            try:
                target_short = basefont_name.split("+")[-1].lower().replace(" ", "").replace("-", "")
                for span in page.get_texttrace():
                    span_font = span.get("font", "").split("+")[-1].lower().replace(" ", "").replace("-", "")
                    if target_short in span_font or span_font in target_short:
                        chars_list = span.get("chars", [])
                        for idx, ch in enumerate(chars_list):
                            if len(ch) == 4:
                                ucp, gid, _, _ = ch
                                if ucp > 0 and gid > 0 and ucp != 0xFFFD:
                                    # Skip ligature first-components: if the NEXT char
                                    # has gid == -1, that means THIS char is the first
                                    # component of a ligature (e.g. 'f' in 'fi').
                                    # The gid we'd record is the ligature glyph's GID,
                                    # which has a double-width advance — wrong for
                                    # standalone 'f'. Skip it.
                                    if idx + 1 < len(chars_list):
                                        next_ch = chars_list[idx + 1]
                                        if len(next_ch) == 4 and next_ch[1] == -1:
                                            continue  # skip ligature first-component
                                    unicode_to_gid[ucp] = gid
                                    
                trace_has_data = len(unicode_to_gid) > 0
                logger.info(f"Trace extracted {len(unicode_to_gid)} unique (UCP -> GID) pairs.")
                changed_cids = 0
                for cid, uchar in single_map.items():
                    ucp = ord(uchar)
                    if ucp in unicode_to_gid:
                        gid = unicode_to_gid[ucp]
                        if cid != gid:
                            cid_to_gid[cid] = gid
                            changed_cids += 1
                logger.info(f"Adjusted {changed_cids} mismatched CID->GID mappings.")
            except Exception as e:
                logger.warning(f"Trace recovery failed entirely: {e}")
                
        unicode_to_glyph = {}
        
        # 1. Map single chars
        for cid, uchar in single_map.items():
            ucp = ord(uchar)
            # Priority chain for CID→GID resolution:
            #   1. Explicit CIDToGIDMap from the PDF (most authoritative)
            #   2. Trace recovery data (direct UCP→GID from MuPDF rendering)
            #   3. Font's own existing cmap table (built above before overwrite)
            #   4. Identity fallback (cid == gid) — true last resort
            # The old code used unconditional identity fallback which is only
            # correct for Identity-H fonts and causes wrong glyph widths
            # (and therefore character scatter) for all other CIDFonts.
            if cid in cid_to_gid:
                gid = cid_to_gid[cid]
            elif ucp in unicode_to_gid:
                gid = unicode_to_gid[ucp]
            elif ucp in font_cmap_gids:
                gid = font_cmap_gids[ucp]
            else:
                gid = cid  # true last resort identity fallback
            if 0 < gid < n_glyphs:
                unicode_to_glyph[ucp] = glyph_order[gid]
                
        # 1.5. Supplement with direct trace recoveries
        # BUG 3 FIX: unicode_to_gid is always defined now — no fragile locals() check
        for ucp, gid in unicode_to_gid.items():
            if 0 < gid < n_glyphs:
                unicode_to_glyph[ucp] = glyph_order[gid]
                
        # 2. Map multi-char ligatures
        LIGATURE_UNICODE_MAP = {
            0xFB00: "ff", 0xFB01: "fi", 0xFB02: "fl",
            0xFB03: "ffi", 0xFB04: "ffl", 0xFB05: "st", 0xFB06: "st"
        }
        for cid, lig_str in multi_map.items():
            gid = cid_to_gid.get(cid, cid)
            if 0 < gid < n_glyphs:
                gname = glyph_order[gid]
                # Map the ligature's OWN Unicode codepoint (e.g. U+FB01 for fi)
                lig_key = lig_str
                for lig_ucp, lig_chars in LIGATURE_UNICODE_MAP.items():
                    if lig_chars == lig_key:
                        unicode_to_glyph[lig_ucp] = gname
                        break
                # BUG 1 FIX: Do NOT map individual component characters
                # (e.g. 'f', 'i') to the ligature glyph. The ligature glyph
                # has a 2-char advance width, so mapping 'f' to it causes
                # the cursor to jump too far, displacing subsequent chars.
                # If 'f' isn't in the ToUnicode single_map, it stays unmapped
                # and MuPDF will use .notdef or fallback — which is correct.

        if not unicode_to_glyph:
            logger.warning("unicode_to_glyph is EMPTY! Returning original font_bytes.")
            return font_bytes

        # BUG 4 FIX: Diagnostic logging for commonly-broken codepoints
        logger.info(f"Generated unicode_to_glyph with {len(unicode_to_glyph)} entries")
        _SUSPECT_CHARS = {'f': 0x66, 'l': 0x6C, 'k': 0x6B, 'i': 0x69, ' ': 0x20}
        for label, ucp in _SUSPECT_CHARS.items():
            if ucp in unicode_to_glyph:
                logger.info(f"  DIAG: U+{ucp:04X} '{label}' → glyph '{unicode_to_glyph[ucp]}'")
            else:
                logger.info(f"  DIAG: U+{ucp:04X} '{label}' → NOT MAPPED")
            
        # 3. Patch hmtx zero-widths
        if "hmtx" in tt and "glyf" in tt:
            hmtx = tt["hmtx"].metrics
            glyf = tt["glyf"]
            valid_advances = [adv for gn, (adv, _) in hmtx.items() if adv > 0 and gn != ".notdef"]
            avg_advance = sum(valid_advances) // len(valid_advances) if valid_advances else 500
            
            for gname in glyph_order:
                if gname not in hmtx: continue
                advance, lsb = hmtx[gname]
                if advance == 0:
                    try:
                        g = glyf[gname]
                        has_outline = hasattr(g, "numberOfContours") and g.numberOfContours > 0
                        if has_outline:
                            hmtx[gname] = (avg_advance, lsb)
                    except Exception:
                        pass
        
        cmap_table = tt.get('cmap')
        if not cmap_table:
            from fontTools.ttLib import newTable
            tt['cmap'] = newTable('cmap')
            tt['cmap'].tableVersion = 0
            tt['cmap'].tables = []
            
        new_subtable = CmapSubtable.newSubtable(4)
        new_subtable.platformID = 3
        new_subtable.platEncID = 1
        new_subtable.language = 0
        new_subtable.cmap = unicode_to_glyph
        
        cmap_table = tt['cmap']
        cmap_table.tables = [t for t in cmap_table.tables if not (t.platformID == 3 and t.platEncID == 1)]
        cmap_table.tables.append(new_subtable)
        
        out = io.BytesIO()
        tt.save(out)
        out_bytes = out.getvalue()

        # Post-serialization validation: ensure fontTools didn't silently
        # drop the cmap table during save (happens with some non-compliant fonts).
        try:
            verify_tt = TTFont(io.BytesIO(out_bytes))
            verify_cmap = verify_tt.getBestCmap()
            if not verify_cmap:
                logger.warning("CMAP WAS DROPPED during fontTools serialization! Returning original font_bytes.")
                return font_bytes
            logger.info(f"Post-serialization cmap validated: {len(verify_cmap)} entries")
        except Exception as e:
            logger.warning(f"Post-serialization cmap validation failed: {e} — continuing anyway")

        logger.info(f"==== INJECT_CMAP SUCCESS. Injected ToUnicode CMap matrix + hmtx patch into {len(unicode_to_glyph)} subsets. ====")
        return out_bytes
        
    except Exception as e:
        logger.error(f"==== INJECT_CMAP FAILED: {e} ====", exc_info=True)
        return None