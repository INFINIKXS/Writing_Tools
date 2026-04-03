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

        # ── Coordinates (all in MuPDF space via Util.transform at scale=1) ──
        x0       = edit["rect"]["x"]
        y0       = edit["rect"]["y"]
        x1       = x0 + edit["rect"]["w"]
        y1       = y0 + edit["rect"]["h"]
        origin_y = edit.get("origin_y", y1 - 2)
        fontsize = edit.get("origFontSize", 11) + edit.get("fontSizeAdj", 0)
        fontsize = max(4.0, fontsize)  # MuPDF minimum

        # ── Font resolution ──────────────────────────────────────────────────
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
