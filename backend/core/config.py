"""
Environment configuration, optional dependency detection, and shared constants.
"""
import os
import shutil
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# ── Optional dependency detection ──────────────────────────────────────────

try:
    from pdf2docx import Converter as Pdf2DocxConverter
    PDF2DOCX_AVAILABLE = True
except ImportError:
    PDF2DOCX_AVAILABLE = False
    Pdf2DocxConverter = None
    print("   [i] pdf2docx not available — PDF to Word disabled")

try:
    from PIL import Image
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    Image = None
    print("   [i] Pillow/reportlab not available — Image to PDF disabled")

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    convert_from_bytes = None
    print("   [i] pdf2image not available — PDF to Images disabled")

# Auto-detect Poppler bin path for pdf2image
POPPLER_PATH = None
_poppler_candidates = [
    r'C:\Program Files\poppler\poppler-25.12.0\Library\bin',
    r'C:\Program Files\poppler\Library\bin',
    r'C:\Program Files (x86)\poppler\Library\bin',
]
for _pp in _poppler_candidates:
    if os.path.isdir(_pp) and os.path.isfile(os.path.join(_pp, 'pdftoppm.exe')):
        POPPLER_PATH = _pp
        break
if not POPPLER_PATH:
    # Search for any poppler version folder
    _base = r'C:\Program Files\poppler'
    if os.path.isdir(_base):
        for _d in os.listdir(_base):
            _candidate = os.path.join(_base, _d, 'Library', 'bin')
            if os.path.isdir(_candidate) and os.path.isfile(os.path.join(_candidate, 'pdftoppm.exe')):
                POPPLER_PATH = _candidate
                break
if POPPLER_PATH:
    print(f"   [OK] Poppler found at: {POPPLER_PATH}")
else:
    print("   [i] Poppler not found — PDF to Images may not work")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    # Try to find tesseract on PATH or common install locations
    _tess_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]
    for _p in _tess_paths:
        if os.path.isfile(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None
    print("   [i] pytesseract not available — OCR disabled")

# ── API Key Manager ───────────────────────────────────────────────────────

try:
    from api_key_manager import get_api_key_manager
    KEY_MANAGER_AVAILABLE = True
except ImportError:
    KEY_MANAGER_AVAILABLE = False
    get_api_key_manager = None
    print("   [i] api_key_manager not found, using single API key mode")

# ── API Key ───────────────────────────────────────────────────────────────

API_KEY = os.environ.get("GOOGLE_API_KEY")

# ── Style Guides ──────────────────────────────────────────────────────────

from harvard_guide import HARVARD_GUIDE
from apa_guide import APA_GUIDE
from vancouver_guide import VANCOUVER_GUIDE
