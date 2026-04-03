import fitz
from fastapi import APIRouter, UploadFile, Form, File
from fastapi.responses import StreamingResponse
import json
import io
from .font_utils import get_usable_font

router = APIRouter()

# Module-level: prevents PyMuPDF from using max ascender/descender heights,
# which cause redaction boxes to bleed into adjacent lines.
fitz.TOOLS.set_small_glyph_heights(True)

# Get Helvetica metrics once — reuse for all edits
_helv = fitz.Font("helv")
HELV_ASCENDER  = _helv.ascender   # ~0.7179  (above baseline)
HELV_DESCENDER = _helv.descender  # ~-0.2821 (below baseline)

@router.post("/apply-edits")
async def apply_edits(file: UploadFile = File(...), edits: str = Form(...)):
    data = await file.read()
    edits_list = json.loads(edits)
    
    # Open from bytes so we don't overwrite any local disk file
    doc = fitz.open(stream=data, filetype="pdf")


    for edit in edits_list:
        # 1-indexed to 0-indexed translation
        page = doc[edit["pageNum"] - 1]       
        
        # Coordinates arrived from frontend already in MuPDF space (via Util.transform at scale=1)
        x0 = edit["rect"]["x"]
        y0 = edit["rect"]["y"]
        x1 = x0 + edit["rect"]["w"]
        y1 = y0 + edit["rect"]["h"]
        
        # Initial fontsize from frontend — overridden below by span data if available
        frontend_fontsize = edit["origFontSize"] + edit.get("fontSizeAdj", 0)

        # ── THE BULLETPROOF SPAN LOOKUP ──
        # Ask PyMuPDF for the exact metrics of the target span *before* choosing
        # the font — so we can pass authoritative bold/italic flags to get_usable_font.
        true_origin_x = None
        true_origin_y = None
        true_bbox     = None
        true_fontsize = None
        true_is_bold  = None   # from span["flags"] bit 4
        true_is_italic = None  # from span["flags"] bit 1
        original_color = (0, 0, 0)
        try:
            search_rect = fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
            text_dict = page.get_text("dict", clip=search_rect)
            orig_str = edit.get("origStr", "").strip()
            best_span = None

            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "").strip()
                        if span_text == orig_str:
                            best_span = span
                            break
                        if best_span is None and orig_str in span_text:
                            best_span = span
                    if best_span and best_span.get("text", "").strip() == orig_str:
                        break
                if best_span and best_span.get("text", "").strip() == orig_str:
                    break

            if best_span:
                flags = best_span.get("flags", 0)
                true_origin_x  = best_span["origin"][0]
                true_origin_y  = best_span["origin"][1]
                true_bbox      = best_span["bbox"]
                true_fontsize  = best_span["size"]
                true_is_bold   = bool(flags & 16)   # bit 4 = bold
                true_is_italic = bool(flags & 2)    # bit 1 = italic
                hex_color = best_span.get("color", 0)
                original_color = (
                    ((hex_color >> 16) & 255) / 255.0,
                    ((hex_color >> 8)  & 255) / 255.0,
                    (hex_color         & 255) / 255.0,
                )
        except Exception as e:
            print(f"Span lookup failed: {e}")

        # Build an enriched edit that layers PyMuPDF-derived bold/italic on top of
        # the frontend values.  If the user explicitly chose a custom font family,
        # their UI toggle choices take precedence; otherwise use span flags.
        user_chose_custom = bool(
            edit.get("customFontFamily") and edit.get("customFontFamily") != "Original"
        )
        enriched_edit = {
            **edit,
            "isBold":   edit.get("isBold", False)   if user_chose_custom else (true_is_bold   if true_is_bold   is not None else edit.get("isBold",   False)),
            "isItalic": edit.get("isItalic", False) if user_chose_custom else (true_is_italic if true_is_italic is not None else edit.get("isItalic", False)),
        }

        # Attempt typography match using the fully-enriched edit
        final_fontname, font_bytes = get_usable_font(doc, page, enriched_edit)
        if font_bytes:
            page.insert_font(fontname=final_fontname, fontbuffer=font_bytes)

        # Honour an explicit color chosen in the editor; otherwise use sampled PDF color
        explicit_color = edit.get("color")
        if explicit_color and explicit_color.startswith("#") and len(explicit_color) == 7:
            r_ch = int(explicit_color[1:3], 16) / 255.0
            g_ch = int(explicit_color[3:5], 16) / 255.0
            b_ch = int(explicit_color[5:7], 16) / 255.0
            insert_color = (r_ch, g_ch, b_ch)
        else:
            insert_color = original_color

        # Ensure the page content stream is in a balanced state before drawing
        if not page.is_wrapped:
            page.wrap_contents()

        # Final insertion coordinates — span data when available, frontend fallback otherwise
        origin_x = true_origin_x if true_origin_x is not None else x0
        origin_y = true_origin_y if true_origin_y is not None else edit.get("origin_y", y1 - 2)
        fontsize  = (true_fontsize if true_fontsize is not None else edit["origFontSize"]) + edit.get("fontSizeAdj", 0)

        # ── Erase rect: use span bbox (pixel-tight) or ratio fallback ──
        if true_bbox:
            erase_rect = fitz.Rect(
                true_bbox[0] - 1,
                true_bbox[1],
                true_bbox[2] + 1,
                true_bbox[3],
            )
        else:
            safe_ascender  = fontsize * 0.75
            safe_descender = fontsize * 0.25
            erase_rect = fitz.Rect(x0 - 1, origin_y - safe_ascender, x1 + 1, origin_y + safe_descender)
        page.draw_rect(erase_rect, color=(1, 1, 1), fill=(1, 1, 1))

        # Insert new text
        page.insert_text(
            fitz.Point(origin_x, origin_y),
            edit["newStr"],
            fontname=final_fontname,
            fontsize=fontsize,
            color=insert_color,
        )


    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    buf.seek(0)
    
    return StreamingResponse(
        buf, 
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=edited.pdf", "Access-Control-Expose-Headers": "Content-Disposition"}
    )
