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
    Detect column x-boundaries from character-level positions.

    Three-pass algorithm:
      1. Collect all characters with their baseline and font size
      1b. Filter to dominant font size (excludes superscripts, headers that
          corrupt the distribution)
      2. Find the 90th percentile of within-line gaps (robust against outlier
          gaps caused by cross-column characters sharing a baseline after
          redaction + reinsertion)
      3. Find the largest gap between all x-midpoints; if it's > 2× the p90
          within-line gap AND > 10pt absolute, it's a column gutter.
    """
    try:
        rd = page.get_text("rawdict")
    except Exception:
        return [[0, page.rect.width]]

    # ── Pass 1: Collect characters with size ──
    raw_chars = []
    for block in rd.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_size = span.get("size", 0)
                for ch in span.get("chars", []):
                    c = ch.get("c", "")
                    if not c or c.isspace():
                        continue
                    bbox = ch.get("bbox", (0, 0, 0, 0))
                    origin = ch.get("origin", (0, 0))
                    x_mid = (bbox[0] + bbox[2]) / 2
                    raw_chars.append((x_mid, bbox[0], bbox[2], origin[1], span_size))

    if len(raw_chars) < 10:
        return [[0, page.rect.width]]

    # ── Pass 1b: Filter to dominant font size ──
    from collections import Counter, defaultdict
    size_counts = Counter(round(c[4] * 2) / 2 for c in raw_chars)
    dominant_size = size_counts.most_common(1)[0][0]

    size_filtered = [
        (x_mid, x0, x1, y)
        for x_mid, x0, x1, y, sz in raw_chars
        if abs(round(sz * 2) / 2 - dominant_size) <= 1.0
    ]
    if len(size_filtered) < 10:
        size_filtered = [(x_mid, x0, x1, y) for x_mid, x0, x1, y, sz in raw_chars]

    # ── Pass 1c: Filter out margin/sidebar text ──
    # Rotated sidebars have each char on its own baseline — drop them.
    MIN_CHARS_PER_BASELINE = 5

    baseline_counts = defaultdict(int)
    for x_mid, x0, x1, y in size_filtered:
        key = round(y * 2) / 2
        baseline_counts[key] += 1

    sidebar_filtered = [
        (x_mid, x0, x1, y)
        for x_mid, x0, x1, y in size_filtered
        if baseline_counts[round(y * 2) / 2] >= MIN_CHARS_PER_BASELINE
    ]

    if len(sidebar_filtered) < 10:
        sidebar_filtered = size_filtered

    # ── Pass 1d: Filter out full-width baselines ──
    # Full-width boxes (definition panels, headers, tables) have baselines
    # whose characters span almost the entire page width — they bridge the
    # gutter and hide it from detection. A real column-text baseline only
    # spans about half the page width. We measure each baseline's x-span
    # and exclude baselines that span more than FULL_WIDTH_THRESHOLD of
    # the overall text x-range.
    baseline_xranges = defaultdict(lambda: [float("inf"), float("-inf")])
    for x_mid, x0, x1, y in sidebar_filtered:
        key = round(y * 2) / 2
        if x0 < baseline_xranges[key][0]:
            baseline_xranges[key][0] = x0
        if x1 > baseline_xranges[key][1]:
            baseline_xranges[key][1] = x1

    # Overall text x-range on this page (from sidebar-filtered chars)
    if sidebar_filtered:
        overall_x_min = min(c[1] for c in sidebar_filtered)
        overall_x_max = max(c[2] for c in sidebar_filtered)
        overall_width = overall_x_max - overall_x_min
    else:
        overall_width = page.rect.width

    # A baseline is "full-width" if its x-span exceeds 70% of the overall
    # text width. Column baselines span ~45-50% of the text width.
    FULL_WIDTH_THRESHOLD = 0.70

    all_chars = [
        (x_mid, x0, x1, y)
        for x_mid, x0, x1, y in sidebar_filtered
        if (
            baseline_xranges[round(y * 2) / 2][1]
            - baseline_xranges[round(y * 2) / 2][0]
        )
        / overall_width
        < FULL_WIDTH_THRESHOLD
    ]

    # Safety: if the full-width filter is too aggressive (removes everything),
    # fall back to the sidebar-filtered set
    if len(all_chars) < 10:
        all_chars = sidebar_filtered

    logger.info(
        f"Column detection: dominant_size={dominant_size}pt, "
        f"using {len(all_chars)}/{len(raw_chars)} chars "
        f"(dropped {len(size_filtered) - len(sidebar_filtered)} sidebar, "
        f"{len(sidebar_filtered) - len(all_chars)} full-width chars)"
    )

    # ── Pass 2: 90th-percentile within-line gap ──
    baseline_groups = defaultdict(list)
    for x_mid, x0, x1, y in all_chars:
        key = round(y * 2) / 2
        baseline_groups[key].append((x0, x1))

    all_within_line_gaps = []
    for key, chars_on_line in baseline_groups.items():
        if len(chars_on_line) < 2:
            continue
        sorted_chars = sorted(chars_on_line, key=lambda c: c[0])
        for i in range(1, len(sorted_chars)):
            gap = sorted_chars[i][0] - sorted_chars[i - 1][1]
            if gap > 0:
                all_within_line_gaps.append(gap)

    if all_within_line_gaps:
        all_within_line_gaps.sort()
        p90_idx = int(len(all_within_line_gaps) * 0.90)
        p90_idx = min(p90_idx, len(all_within_line_gaps) - 1)
        max_within_line_gap = all_within_line_gaps[p90_idx]
    else:
        max_within_line_gap = 0

    # ── Pass 3: Find the best center-gutter candidate ──
    # A true two-column gutter must satisfy:
    #   (a) Be significantly wider than normal word spacing (2× p90)
    #   (b) Sit in the CENTRAL region of the text area (25%-75% of x-range)
    #   (c) Have substantial text on BOTH sides (at least 20% of chars per side)
    # This is more robust than "just pick the largest gap" because headers,
    # footers, and margin strips can create larger edge-gaps than the real gutter.
    x_mids = sorted([c[0] for c in all_chars])
    text_x_min = x_mids[0]
    text_x_max = x_mids[-1]
    text_width = text_x_max - text_x_min

    # Central zone: 25%-75% of the text's x-range
    central_min = text_x_min + text_width * 0.25
    central_max = text_x_min + text_width * 0.75

    # Enumerate all gaps; pick the largest one that falls in the central zone
    # AND has significant text on both sides.
    best_gap = 0
    best_gap_idx = -1
    for i in range(1, len(x_mids)):
        gap = x_mids[i] - x_mids[i - 1]
        gap_mid = (x_mids[i - 1] + x_mids[i]) / 2

        # Must be in central zone
        if gap_mid < central_min or gap_mid > central_max:
            continue

        # Must have enough chars on both sides (at least 20% each)
        left_count = i
        right_count = len(x_mids) - i
        min_side_count = len(x_mids) * 0.20
        if left_count < min_side_count or right_count < min_side_count:
            continue

        if gap > best_gap:
            best_gap = gap
            best_gap_idx = i

    is_gutter = (
        best_gap > max_within_line_gap * 2
        and best_gap > 10
        and best_gap_idx > 0
    )

    if is_gutter:
        split_x = (x_mids[best_gap_idx - 1] + x_mids[best_gap_idx]) / 2
        left_col = [text_x_min, split_x]
        right_col = [split_x, text_x_max]
        logger.info(
            f"Column detection: gutter={best_gap:.1f}pt at x={split_x:.1f} "
            f"(p90 within-line gap={max_within_line_gap:.1f}pt, "
            f"ratio={best_gap/max_within_line_gap:.1f}x, "
            f"central zone={central_min:.0f}-{central_max:.0f})"
        )
        return [left_col, right_col]

    ratio_str = f"{best_gap/max_within_line_gap:.1f}x" if max_within_line_gap > 0 else "inf"
    logger.info(
        f"Column detection: single column "
        f"(best central gap={best_gap:.1f}pt, p90 within-line gap={max_within_line_gap:.1f}pt, "
        f"ratio={ratio_str}, central zone={central_min:.0f}-{central_max:.0f})"
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
