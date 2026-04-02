import fitz
from fastapi import APIRouter, UploadFile, Form, File
from fastapi.responses import StreamingResponse
import json
import io
from .font_utils import get_usable_font

router = APIRouter()

@router.post("/apply-edits")
async def apply_edits(file: UploadFile = File(...), edits: str = Form(...)):
    data = await file.read()
    edits_list = json.loads(edits)
    
    # Open from bytes so we don't overwrite any local disk file
    doc = fitz.open(stream=data, filetype="pdf")

    # CRITICAL: prevents PyMuPDF from using the font's maximum ascender/descender
    # which frequently causes redax boxes to bleed into sentences above or below.
    fitz.TOOLS.set_small_glyph_heights(True)  

    for edit in edits_list:
        # 1-indexed to 0-indexed translation
        page = doc[edit["pageNum"] - 1]       
        
        # Rect dimensions sent in pure PDF points
        r = fitz.Rect(
            edit["rect"]["x"],
            edit["rect"]["y"],
            edit["rect"]["x"] + edit["rect"]["w"],
            edit["rect"]["y"] + edit["rect"]["h"],
        )
        
        fontsize = edit["origFontSize"] + edit.get("fontSizeAdj", 0)

        # Attempt typography match
        final_fontname, font_bytes = get_usable_font(doc, page, edit)
        
        # If we successfully extracted embedded native bytes, register it into the doc
        if font_bytes:
            # We must insert the raw TTF/OTF bytes into the document tree so add_redact_annot can use it
            page.insert_font(fontname=final_fontname, fontbuffer=font_bytes)
            
        # Extract the original text color
        original_color = (0, 0, 0)
        try:
            text_dict = page.get_text("dict", clip=r)
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        hex_color = span.get("color", 0)
                        # PyMuPDF color is an integer 0xRRGGBB. Convert to (0-1) tuple.
                        original_color = (
                            ((hex_color >> 16) & 255) / 255.0,
                            ((hex_color >> 8) & 255) / 255.0,
                            (hex_color & 255) / 255.0
                        )
                        break
        except Exception:
            pass # Fallback to black

        # Apply redaction annotation over the original box
        page.add_redact_annot(
            r,
            text=edit["newStr"],
            fontname=final_fontname,
            fontsize=fontsize,
            fill=(1, 1, 1),           # Whiteout original
            text_color=original_color,     # Inherit Original color
        )
        page.apply_redactions()

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    buf.seek(0)
    
    return StreamingResponse(
        buf, 
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=edited.pdf", "Access-Control-Expose-Headers": "Content-Disposition"}
    )
