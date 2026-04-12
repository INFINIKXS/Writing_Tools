"""Diagnostic: Inspect PDF font structure for the loaded document.
Run with: .\venv\Scripts\python.exe diag_font.py <path_to_pdf>
"""
import sys, re, struct, io
sys.stdout.reconfigure(encoding="utf-8")

import fitz

pdf_path = sys.argv[1] if len(sys.argv) > 1 else input("PDF path: ").strip('"')
doc = fitz.open(pdf_path)
page = doc[0]

print("=" * 70)
print(f"PAGE 0 FONTS (get_fonts full=True)")
print("=" * 70)

for entry in page.get_fonts(full=True):
    xref = entry[0]
    ext  = entry[1]
    ftype = entry[2]
    basefont = entry[3]
    refname = entry[4] if len(entry) > 4 else ""
    encoding = entry[5] if len(entry) > 5 else ""
    
    print(f"\n--- xref={xref}  ext={ext}  type={ftype}  basefont={basefont}  ref={refname}  enc={encoding} ---")
    
    # Dump the raw PDF object for this xref
    try:
        obj_str = doc.xref_object(xref, compressed=False)
        print(f"  RAW OBJECT (first 500 chars):\n    {obj_str[:500]}")
    except Exception as e:
        print(f"  Could not read xref object: {e}")
    
    # Check for ToUnicode key
    try:
        tu = doc.xref_get_key(xref, "ToUnicode")
        print(f"  ToUnicode key: type={tu[0]}, val={tu[1][:100] if tu[1] else 'None'}")
    except Exception as e:
        print(f"  ToUnicode lookup: {e}")
    
    # Check for DescendantFonts
    try:
        df = doc.xref_get_key(xref, "DescendantFonts")
        print(f"  DescendantFonts: type={df[0]}, val={df[1][:100] if df[1] else 'None'}")
    except Exception as e:
        print(f"  DescendantFonts lookup: {e}")
    
    # Check for Encoding
    try:
        enc = doc.xref_get_key(xref, "Encoding")
        print(f"  Encoding key: type={enc[0]}, val={enc[1][:100] if enc[1] else 'None'}")
    except Exception as e:
        print(f"  Encoding lookup: {e}")
    
    # Check for Subtype
    try:
        st = doc.xref_get_key(xref, "Subtype")
        print(f"  Subtype: type={st[0]}, val={st[1][:100] if st[1] else 'None'}")
    except Exception as e:
        print(f"  Subtype lookup: {e}")

    # Try to extract font bytes
    try:
        fd = doc.extract_font(xref)
        font_bytes = fd[-1]
        print(f"  extract_font: name={fd[0]}, ext={fd[1]}, type={fd[2]}, bytes={len(font_bytes) if font_bytes else 0}")
    except Exception as e:
        print(f"  extract_font failed: {e}")

    # Now do exactly what _parse_tounicode does
    try:
        tu_ref = doc.xref_get_key(xref, "ToUnicode")
        if tu_ref and tu_ref[0] != "null":
            m = re.match(r"(\d+)\s+\d+\s+R", tu_ref[1].strip())
            if m:
                tu_xref = int(m.group(1))
                raw = doc.xref_stream(tu_xref)
                if raw:
                    text = raw.decode("latin-1", errors="replace")
                    # Count beginbfchar / beginbfrange entries
                    bfchars = len(re.findall(r"beginbfchar", text))
                    bfranges = len(re.findall(r"beginbfrange", text))
                    pairs = re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", text)
                    print(f"  ToUnicode stream: {len(raw)} bytes, {bfchars} bfchar sections, {bfranges} bfrange sections, {len(pairs)} hex pairs")
                    # Show first 5 mappings
                    for p in pairs[:5]:
                        cid = int(p[0], 16)
                        uchar = chr(int(p[1], 16)) if len(p[1]) == 4 else p[1]
                        print(f"    CID 0x{p[0]} → U+{p[1]} ('{uchar}')")
                else:
                    print(f"  ToUnicode stream: EMPTY (xref={tu_xref})")
            else:
                print(f"  ToUnicode ref did not match pattern: {tu_ref[1]}")
        else:
            print(f"  ToUnicode: NOT PRESENT or null")
    except Exception as e:
        print(f"  ToUnicode parsing error: {e}")

print("\n" + "=" * 70)
print("TEXT TRACE (first 10 spans)")
print("=" * 70)
try:
    traces = page.get_texttrace()
    for i, span in enumerate(traces[:10]):
        font = span.get("font", "?")
        chars = span.get("chars", [])
        print(f"  Span {i}: font={font}, {len(chars)} chars")
        for ch in chars[:5]:
            if len(ch) == 4:
                ucp, gid, origin, bbox = ch
                label = chr(ucp) if 32 <= ucp < 127 else f"U+{ucp:04X}"
                print(f"    char={label} (U+{ucp:04X}), gid={gid}")
except Exception as e:
    print(f"  get_texttrace failed: {e}")

doc.close()
print("\nDone.")
