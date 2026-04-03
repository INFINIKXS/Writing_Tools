import io
import fitz
import logging

# Set up logging for production visibility
logger = logging.getLogger(__name__)

def extract_font_for_edit(doc, page, font_name):
    """Try to extract the embedded font matching font_name.
    Returns (font_bytes, is_subset) or (None, False) if not found."""
    for xref, ext, ftype, basefont, name, *_ in page.get_fonts():
        if font_name in (name, basefont):
            font_data = doc.extract_font(xref)
            if font_data and font_data[3]:    # font_data[3] = raw bytes
                # A subset font is prefixed with 6 uppercase letters and a '+'
                is_subset = name[:6].isupper() and len(name) > 6 and name[6] == '+'
                return font_data[3], is_subset
    return None, False

def all_glyphs_present(font_bytes, text):
    """Checks if the embedded font stream contains the necessary characters."""
    try:
        from fontTools import ttLib
        # Load the font directly from the byte stream
        tt = ttLib.TTFont(io.BytesIO(font_bytes))
        cmap = tt.getBestCmap()
        
        if not cmap:
            return False
            
        # Check if every character the user typed exists in the font's character map
        return all(ord(ch) in cmap for ch in text)
        
    except ImportError:
        logger.warning("fontTools is not installed. Cannot verify glyph presence.")
        return None # Return None to indicate we couldn't verify
    except Exception as e:
        logger.error(f"Font mapping error: {e}")
        return False

def get_usable_font(doc, page, edit):
    """
    Return (fontname_str, fontfile_bytes_or_None) for use in redact.
    Respects user UI overrides and checks for subset glyph availability.
    """
    original_font_name = edit.get("fontName", "helv")
    new_str = edit.get("newStr", "")
    
    # 1. Did the user explicitly choose a new font from the UI dropdown?
    custom_font = edit.get("customFontFamily")
    if custom_font and custom_font != "Original":
        # PyMuPDF has built-in base-14 fonts we can map to
        builtin_map = {
            "Arial": "helv",
            "Times New Roman": "tiro",
            "Courier": "cour",
            "Helvetica": "helv",
            "Georgia": "tiro" # Fallback to Times
        }
        mapped_name = builtin_map.get(custom_font, "helv")
        
        # If they want it bold/italic, PyMuPDF uses different codes (e.g., helvbo)
        if edit.get("isBold") and edit.get("isItalic"):
            return mapped_name + "bi", None
        elif edit.get("isBold"):
            return mapped_name + "bo", None
        elif edit.get("isItalic"):
            return mapped_name + "it", None
            
        return mapped_name, None

    # 2. User chose "Original". Try extracting the embedded native font.
    fb, is_subset = extract_font_for_edit(doc, page, original_font_name)
    
    if fb:
        has_glyphs = all_glyphs_present(fb, new_str)
        
        if has_glyphs is True:
            # The font has the characters! Safe to use.
            return original_font_name, fb
            
        elif has_glyphs is None:
            # fontTools wasn't installed. If it's a subset, it's too risky. 
            # If it's a full font, take a gamble and use it.
            if not is_subset:
                return original_font_name, fb
                
        else:
            # has_glyphs is False. The user typed a character that the font doesn't have.
            logger.info(f"Font {original_font_name} lacks necessary glyphs. Falling back to default.")

    # 3. Fallback: If extraction fails or glyphs are missing, use a safe PyMuPDF base font
    fallback_font = "helv"
    if edit.get("isBold") and edit.get("isItalic"): fallback_font = "helvbi"
    elif edit.get("isBold"): fallback_font = "helvbo"
    elif edit.get("isItalic"): fallback_font = "helvit"
    
    return fallback_font, None