import os
import tempfile
import ocrmypdf
import fitz  # PyMuPDF
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import FileResponse, JSONResponse
from pypdf import PdfReader, PdfWriter

router = APIRouter()

@router.post("/run_ocr")
async def run_ocr(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Accepts a scanned PDF, runs OCRmyPDF on it, and returns a selectable PDF.
    """
    tmp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    
    # Save the upload to disk
    content = await file.read()
    tmp_input.write(content)
    tmp_input.close()
    
    try:
        # Run OCRmyPDF (force_ocr ensures we ignore existing text layers if broken)
        ocrmypdf.ocr(tmp_input.name, tmp_output.name, force_ocr=True)
    except Exception as e:
        os.remove(tmp_input.name)
        os.remove(tmp_output.name)
        return {"error": str(e)}

    # Ensure files are cleaned up after returning
    background_tasks.add_task(os.remove, tmp_input.name)
    background_tasks.add_task(os.remove, tmp_output.name)

    return FileResponse(
        tmp_output.name, 
        media_type="application/pdf", 
        filename=f"ocr_{file.filename}"
    )

@router.post("/detect_font")
async def detect_font(
    file: UploadFile = File(...),
    page_index: int = Form(...),
    x: float = Form(...),
    y: float = Form(...)
):
    """
    Given a raw x/y coordinate on a specific page, uses PyMuPDF to extract
    the font dictionary characteristics of the natively embedded text string.
    """
    pdf_bytes = await file.read()
    doc = fitz.open("pdf", pdf_bytes)
    
    if page_index < 0 or page_index >= len(doc):
        return JSONResponse(status_code=400, content={"error": "Invalid page index"})
        
    page = doc[page_index]
    
    best_match = None
    min_dist = float('inf')
    
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block["type"] == 0:  # text block
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span["bbox"] # [x0, y0, x1, y1]
                    
                    # If the click naturally falls perfectly inside a span BBOX
                    if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                         return {
                             "font": span.get("font"),
                             "size": round(span.get("size"), 1),
                             "text": span.get("text")
                         }
                    
                    # Otherwise map to the closest spanning block centroid
                    center_x = (bbox[0] + bbox[2]) / 2
                    center_y = (bbox[1] + bbox[3]) / 2
                    dist = ((center_x - x) ** 2 + (center_y - y) ** 2) ** 0.5
                    
                    if dist < min_dist:
                         min_dist = dist
                         best_match = {
                             "font": span.get("font"),
                             "size": round(span.get("size"), 1),
                             "text": span.get("text")
                         }
                         
    if best_match and min_dist < 100: # Ensure we didn't just match something 1000px away
        return best_match
        
    # Safe default fallback
    return {"font": "Helvetica", "size": 16, "text": ""}

@router.post("/encrypt")
async def encrypt_pdf(password: str, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Example PyPDF router endpoint securely encrypting the PDF.
    """
    tmp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    
    content = await file.read()
    tmp_input.write(content)
    tmp_input.close()
    
    reader = PdfReader(tmp_input.name)
    writer = PdfWriter()
    
    for page in reader.pages:
        writer.add_page(page)
        
    writer.encrypt(password)
    with open(tmp_output.name, "wb") as f:
        writer.write(f)
        
    background_tasks.add_task(os.remove, tmp_input.name)
    background_tasks.add_task(os.remove, tmp_output.name)

    return FileResponse(tmp_output.name, media_type="application/pdf", filename=f"encrypted_{file.filename}")
