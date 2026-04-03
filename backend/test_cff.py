import sys
import io
import fitz

def extract_and_convert(pdf_path):
    print(f"Opening {pdf_path}")
    doc = fitz.open(pdf_path)
    page = doc[1] # Page 2
    for xref, ext, ftype, basefont, name, *_ in page.get_fonts():
        if "Type1" in ftype or ext == "cff" or "Type0" in ftype:
            print(f"Found font: {basefont} (ext: {ext}, ftype: {ftype}, xref: {xref})")
            font_data = doc.extract_font(xref)
            if font_data and font_data[3]:
                raw_bytes = font_data[3]
                print(f"Extracted {len(raw_bytes)} bytes")
                # Try to load with fontTools
                try:
                    from fontTools.ttLib import TTFont
                    from fontTools.cffLib import CFFFontSet
                    
                    # CFF to OTF wrapping logic
                    cff = CFFFontSet()
                    cff.decompile(io.BytesIO(raw_bytes), None)
                    print("Successfully parsed CFF with cffLib!")
                    
                    # Create empty OTF wrapper
                    otf = TTFont(sfntVersion="OTTO")
                    otf["CFF "] = cff
                    
                    # Setup basic required tables
                    from fontTools.fontBuilder import FontBuilder
                    fb = FontBuilder(1000, isTTF=False)
                    # We would need to set up cmap, glyphOrder, etc.
                    
                    print(f"Success! Ready to build full TTFont.")
                except Exception as e:
                    print(f"Error: {e}")
                print("-" * 20)

import glob
pdfs = glob.glob(r"c:\Users\Paradox-Labs\Documents\Projects\Writing_Tools\backend\uploads\*.pdf")
if pdfs:
    extract_and_convert(pdfs[0])
else:
    print("No PDFs found in uploads.")
