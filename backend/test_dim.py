import io, os
from fontTools.ttLib import TTFont
import converter.font_utils as fu
import pymupdf as fitz

pdf_path = '../frontend/public/test.pdf'
if os.path.exists(pdf_path):
    doc = fitz.open(pdf_path)
    for page in doc:
        for font in page.get_fonts():
            if 'AdvTT' in font[3]:
                raw = doc.extract_font(font[0])[-1]
                wrapped = fu.wrap_cff_in_otf(raw)
                if wrapped:
                    f = fitz.Font(fontbuffer=wrapped)
                    tt = TTFont(io.BytesIO(wrapped))
                    head = tt['head']
                    hhea = tt['hhea']
                    print(f"PyMuPDF text length for 'comes': {f.text_length('comes', fontsize=10)}")
                    print(f"unitsPerEm: {head.unitsPerEm}")
                    break
