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

LIGATURE_SUB = [
    ("ffl", "\uFB04"), ("ffi", "\uFB03"), ("ff", "\uFB00"),
    ("fi",  "\uFB01"), ("fl",  "\uFB02"), ("st", "\uFB06"),
]
def _substitute_ligatures(text: str) -> str:
    """Replaces component strings with Unicode ligatures for heavily compressed subsets."""
    for seq, lig in LIGATURE_SUB:
        text = text.replace(seq, lig)
    return text


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

    for edit in edits_list:
        page     = doc[edit["pageNum"] - 1]
        new_text = edit.get("newStr", "")
        # Enforce sanitization of HTML non-breaking spaces injected by contenteditable
        new_text = new_text.replace("\u00A0", " ").replace("&nbsp;", " ")
        new_text = _substitute_ligatures(new_text)

        # ── Coordinates (all in MuPDF space via Util.transform at scale=1) ──
        x0       = edit["rect"]["x"]
        y0       = edit["rect"]["y"]
        x1       = x0 + edit["rect"]["w"]
        y1       = y0 + edit["rect"]["h"]
        origin_y = edit.get("origin_y", y1 - 2)
        fontsize = edit.get("origFontSize", 11) + edit.get("fontSizeAdj", 0)
        fontsize = max(4.0, fontsize)  # MuPDF minimum

        # ── Font resolution ──────────────────────────────────────────────────
        # PDF.js on the frontend generates synthetic names (like "g_d0_f9") for fonts.
        # We must map this back to the genuine PyMuPDF BaseFont by sampling the spatial coordinates.
        edit["fontName"] = _resolve_font_name(page, edit, x0, y0, x1, y1)
        font_result = get_font_for_edit(doc, page, edit)

        if font_result.fallback_used:
            warning_entry = {
                "pageNum":  edit["pageNum"],
                "origStr":  edit.get("origStr", ""),
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
        # (Base-14 and pymupdf-fonts codes need no pre-registration)

        # ── Determine insert color ───────────────────────────────────────────
        insert_color = _resolve_color(page, edit, x0, y0, x1, y1)

        # ── Erase the original text ──────────────────────────────────────────
        # draw_rect paints at the graphics layer — covers fill text, stroke text,
        # and vector drawings unconditionally. This handles bold text rendered
        # with stroke+fill mode (render mode 2) which add_redact_annot misses.
        ascender_h  = edit.get("ascender_h",  fontsize * 0.8)
        descender_h = edit.get("descender_h", fontsize * 0.2)

        erase_y0 = origin_y - ascender_h
        erase_y1 = origin_y + descender_h

        # Ensure page content stream is balanced before drawing
        if not page.is_wrapped:
            page.wrap_contents()

        erase_rect = fitz.Rect(x0 - 1, erase_y0 - 1, x1 + 1, erase_y1 + 1)
        page.draw_rect(erase_rect, color=(1, 1, 1), fill=(1, 1, 1))

        # ── Insert new text at the baseline ─────────────────────────────────
        # Subset fonts notoriously exclude the Space (U+0020) glyph, relying instead
        # on positional kerning (TJ arrays) in the PDF. We measure the space width
        # to ensure it exists; if missing, we manually advance the cursor between words.
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

        # Subset fonts notoriously exclude or break the Space (U+0020) glyph.
        # We MUST force algorithmic word spacing if we injected a custom buffer,
        # or if the space width mathematically resolves poorly.
        if not has_space or space_width < fontsize * 0.1:
            fallback_space = fontsize * 0.25  # Standard 1/4 em space
            cursor_x = x0
            for word in new_text.split(" "):
                if word:
                    page.insert_text(
                        fitz.Point(cursor_x, origin_y),
                        word,
                        fontname=font_result.fontname,
                        fontsize=fontsize,
                        color=insert_color,
                    )
                    try:
                        cursor_x += measure_font.text_length(word, fontsize=fontsize)
                    except Exception:
                        cursor_x += len(word) * (fontsize * 0.5)
                cursor_x += fallback_space
        else:
            page.insert_text(
                fitz.Point(x0, origin_y),
                new_text,
                fontname=font_result.fontname,
                fontsize=fontsize,
                color=insert_color,
            )

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
