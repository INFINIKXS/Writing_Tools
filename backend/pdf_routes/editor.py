import os
import tempfile
import ocrmypdf
import fitz  # PyMuPDF
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import FileResponse, JSONResponse
from pypdf import PdfReader, PdfWriter
import logging

logger = logging.getLogger(__name__)

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

def _get_column_boundaries(page):
    """
    Detect columns by clustering the left-edge x-coordinates of text lines.

    Real two-column body text has a distinctive signature: most lines start
    at one of exactly two x-coordinates (the left edge of each column).
    Full-width text has lines that all start at roughly ONE x-coordinate.
    This is a structural property and is robust against:
      - Full-width boxes mixed into two-column pages
      - Margin/sidebar text (doesn't contribute enough lines to form a peak)
      - Page headers and footers
      - Rotated text

    Algorithm:
      1. Get line-level bboxes from PyMuPDF (get_text("dict")).
      2. Filter out single-line blocks and tiny lines.
      3. Cluster line x0 values into buckets of width FONT_SIZE.
      4. Find the two most popular buckets.
      5. If the two top buckets are well-separated (>50pt apart) and
         each has a substantial count, this is a two-column page.
    """
    try:
        data = page.get_text("dict")
    except Exception:
        return [[0, page.rect.width]]

    # Collect line x0 (left edge) and x1 (right edge) for every line with
    # substantial text content. Skip very short lines (captions, footers).
    line_starts = []  # list of (x0, x1, width)
    line_sizes = []   # font sizes seen

    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox", (0, 0, 0, 0))
            lw = bbox[2] - bbox[0]
            if lw < 20:  # skip tiny stubs
                continue

            # Collect font size from the first span
            spans = line.get("spans", [])
            if spans:
                line_sizes.append(spans[0].get("size", 10))

            line_starts.append((bbox[0], bbox[2], lw))

    if len(line_starts) < 5:
        return [[0, page.rect.width]]

    # Determine dominant font size (for bucket width)
    from collections import Counter
    size_counts = Counter(round(s * 2) / 2 for s in line_sizes)
    dominant_size = size_counts.most_common(1)[0][0] if size_counts else 10.0
    bucket_width = max(dominant_size, 6.0)

    # Filter to lines at dominant font size (removes caption-size text)
    filtered_starts = [
        (x0, x1, lw)
        for (x0, x1, lw), sz in zip(line_starts, line_sizes)
        if abs(round(sz * 2) / 2 - dominant_size) <= 1.0
    ]
    if len(filtered_starts) < 5:
        filtered_starts = line_starts

    # Bucket the x0 values
    bucket_counts = Counter()
    for x0, x1, lw in filtered_starts:
        bucket = round(x0 / bucket_width) * bucket_width
        bucket_counts[bucket] += 1

    # Find the two most popular buckets
    top = bucket_counts.most_common()
    if len(top) < 2:
        return [[filtered_starts[0][0], max(f[1] for f in filtered_starts)]]

    b1_x, b1_count = top[0]
    b2_x, b2_count = top[1]
    total_lines = len(filtered_starts)

    # For a true two-column page, BOTH clusters should account for at least
    # 15% of the dominant-size lines. If only one cluster dominates (>70%),
    # it's single-column text.
    min_cluster_share = 0.15
    is_two_column = (
        b1_count >= total_lines * min_cluster_share
        and b2_count >= total_lines * min_cluster_share
        and abs(b1_x - b2_x) > 50  # columns must be at least 50pt apart
    )

    # Overall x-range
    text_x_min = min(f[0] for f in filtered_starts)
    text_x_max = max(f[1] for f in filtered_starts)

    if is_two_column:
        left_start = min(b1_x, b2_x)
        right_start = max(b1_x, b2_x)

        # Find the actual gap: max right-edge of left-column lines,
        # vs min left-edge of right-column lines.
        left_col_rights = [
            x1 for x0, x1, lw in filtered_starts
            if abs(round(x0 / bucket_width) * bucket_width - left_start) < bucket_width
        ]
        right_col_lefts = [
            x0 for x0, x1, lw in filtered_starts
            if abs(round(x0 / bucket_width) * bucket_width - right_start) < bucket_width
        ]

        if left_col_rights and right_col_lefts:
            left_col_right_edge = max(left_col_rights)
            right_col_left_edge = min(right_col_lefts)
            split_x = (left_col_right_edge + right_col_left_edge) / 2
        else:
            split_x = (left_start + right_start) / 2

        logger.info(
            f"Column detection: two columns "
            f"(left starts at x≈{left_start:.0f} [{b1_count} lines], "
            f"right starts at x≈{right_start:.0f} [{b2_count} lines], "
            f"split at x={split_x:.1f}, total lines={total_lines})"
        )
        return [[text_x_min, split_x], [split_x, text_x_max]]

    logger.info(
        f"Column detection: single column "
        f"(top bucket x≈{b1_x:.0f} has {b1_count}/{total_lines} lines, "
        f"2nd bucket x≈{b2_x:.0f} has {b2_count} — not enough for 2 cols)"
    )
    return [[text_x_min, text_x_max]]


def extract_page_spacing_data(page):
    """
    Extract per-character spatial data from a page.

    Returns a list of blocks, each with lines, each with:
      - chars: per-char data (c, x0, x1, y0, y1, origin_x, origin_y, font, size, is_superscript)
      - gaps: inter-character gaps (length = len(chars) - 1)
      - line_x0, line_x1, line_y0, line_y1: line bbox
    """
    data = page.get_text("rawdict", flags=fitz.TEXTFLAGS_TEXT)
    blocks_out = []

    for block in data.get("blocks", []):
        if block.get("type", -1) != 0:
            continue  # skip image blocks

        block_lines = []
        for line in block.get("lines", []):
            line_chars = []

            for span in line.get("spans", []):
                is_superscript = bool(span.get("flags", 0) & fitz.TEXT_FONT_SUPERSCRIPT)

                for ch in span.get("chars", []):
                    line_chars.append({
                        "c":            ch["c"],
                        "x0":           ch["bbox"][0],
                        "x1":           ch["bbox"][2],
                        "y0":           ch["bbox"][1],
                        "y1":           ch["bbox"][3],
                        "origin_x":     ch["origin"][0],
                        "origin_y":     ch["origin"][1],
                        "font":         span["font"],
                        "size":         span["size"],
                        "is_superscript": is_superscript,
                    })

            if not line_chars:
                continue

            gaps = []
            for i in range(1, len(line_chars)):
                gap = line_chars[i]["x0"] - line_chars[i - 1]["x1"]
                gaps.append(gap)

            block_lines.append({
                "chars":   line_chars,
                "gaps":    gaps,
                "line_x0": line["bbox"][0],
                "line_x1": line["bbox"][2],
                "line_y0": line["bbox"][1],
                "line_y1": line["bbox"][3],
            })

        if block_lines:
            blocks_out.append({
                "block_number": block.get("number", 0),
                "lines": block_lines,
            })

    return blocks_out


def get_pdf_spacing_payload(pdf_bytes):
    """
    Process a PDF byte-string and return a per-page spacing payload.
    Each entry: {"page": int, "blocks": [...], "columns": [[xL, xR], ...]}
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    payload = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_blocks = extract_page_spacing_data(page)
        column_boundaries = _get_column_boundaries(page)
        payload.append({
            "page": page_index,
            "blocks": page_blocks,
            "columns": column_boundaries,
        })

    doc.close()
    return payload


@router.post("/extract-spacing")
async def extract_spacing(file: UploadFile = File(...)):
    """
    Extract per-character spacing data and column boundaries for every page.
    Used by the frontend to build editing boxes that correctly handle
    multi-column layouts and post-bake text positioning.
    """
    try:
        content = await file.read()
        payload = get_pdf_spacing_payload(content)
        return JSONResponse(status_code=200, content=payload)
    except Exception as e:
        logger.error(f"extract-spacing failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to extract spacing layout"},
        )
