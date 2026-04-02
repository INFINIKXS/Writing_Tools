import io
import fitz

def extract_font_for_edit(doc, page, font_name):
    """Try to extract the embedded font matching font_name.
    Returns (font_bytes, is_subset) or (None, False) if not found."""
    for xref, ext, ftype, basefont, name, enc, _ in page.get_fonts():
        if font_name in (name, basefont):
            font_data = doc.extract_font(xref)
            if font_data and font_data[3]:    # font_data[3] = raw bytes
                return font_data[3], True
    return None, False

def all_glyphs_present(font_bytes, text):
    try:
        from fontTools import ttLib
        tt = ttLib.TTFont(io.BytesIO(font_bytes))
        cmap = tt.getBestCmap()
        if not cmap:
            return False
        return all(ord(ch) in cmap for ch in text)
    except Exception as e:
        print(f"Font mapping error: {e}")
        return False

def get_usable_font(doc, page, edit):
    """Return (fontname_str, fontfile_bytes_or_None, external_font) for use in redact."""
    font_name = edit.get("fontName", "helv")
    new_str = edit.get("newStr", "")

    # Try extracting exact subset or embedded stream
    fb, is_sub = extract_font_for_edit(doc, page, font_name)
    if fb:
        # Verify the new text's glyphs are supported
        # If it's not a subset prefix, it's safer, but we check regardless if fontTools is available
        if all_glyphs_present(fb, new_str) or (
            not (font_name[:6].isupper() and len(font_name) > 6 and font_name[6] == '+')
        ):
            return font_name, fb

    return "helv", None
