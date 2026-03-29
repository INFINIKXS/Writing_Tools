"""
Document text extraction: PDF, DOCX, and legacy DOC formats.
"""
import io
import re
import struct

import olefile
from PyPDF2 import PdfReader
from docx import Document
from fastapi import HTTPException


def extract_pdf_text(file_bytes: bytes) -> str:
    text = ""
    with io.BytesIO(file_bytes) as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text


def extract_docx_text(file_bytes: bytes) -> str:
    with io.BytesIO(file_bytes) as f:
        doc = Document(f)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
    return text


def extract_doc_text(file_bytes: bytes) -> str:
    """Extract text from legacy .doc (Word 97-2003) files using olefile (pure Python)."""
    try:
        f = io.BytesIO(file_bytes)
        ole = olefile.OleFileIO(f)
        
        # The main text stream in .doc files is "WordDocument"
        # But the actual text content is in the "1Table" or "0Table" stream  
        # We'll read the WordDocument stream to get the raw text
        
        if ole.exists('WordDocument'):
            word_stream = ole.openstream('WordDocument').read()
        else:
            raise HTTPException(status_code=400, detail="This file does not appear to be a valid Word .doc file.")
        
        # Read the FIB (File Information Block) to locate text
        # Bytes 24-27 contain flags, bytes 0x01A2 onwards contain text positions
        # For simplicity, try to extract via the compound document text
        
        text_pieces = []
        
        # Method 1: Try to read from the data stream directly
        # The text in a .doc is stored as either ASCII or Unicode
        # We look at ccpText field in FIB at offset 0x004C (76)
        if len(word_stream) > 80:
            ccp_text = struct.unpack_from('<I', word_stream, 0x004C)[0]
            
            # Check if text is Unicode (bit 0 of flags at offset 0x000A)
            flags = struct.unpack_from('<H', word_stream, 0x000A)[0]
            is_complex = not (flags & 0x0004)  # fComplex flag
            
            if not is_complex and ccp_text > 0:
                # Simple file: text starts at offset 0x0200 (512)
                start = 0x0200
                if flags & 0x0100:  # Unicode
                    raw = word_stream[start:start + ccp_text * 2]
                    text_pieces.append(raw.decode('utf-16-le', errors='ignore'))
                else:
                    raw = word_stream[start:start + ccp_text]
                    text_pieces.append(raw.decode('cp1252', errors='ignore'))
        
        # Method 2: If Method 1 got nothing, try brute-force decoding 
        if not text_pieces or not ''.join(text_pieces).strip():
            # Try all text streams
            for stream_name in ['WordDocument']:
                data = ole.openstream(stream_name).read()
                # Skip the FIB header (first 512 bytes) and try to decode
                raw_text = data[512:]
                # Try UTF-16 first, then cp1252
                try:
                    decoded = raw_text.decode('utf-16-le', errors='ignore')
                    # Filter to printable characters
                    cleaned = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in decoded)
                    if len(cleaned.strip()) > 50:
                        text_pieces = [cleaned]
                except:
                    decoded = raw_text.decode('cp1252', errors='ignore')
                    cleaned = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in decoded)
                    if len(cleaned.strip()) > 50:
                        text_pieces = [cleaned]

        ole.close()
        
        result = '\n'.join(text_pieces)
        # Clean up control characters but keep newlines
        result = ''.join(c if c.isprintable() or c in '\n\r\t' else '\n' for c in result)
        # Collapse multiple blank lines
        while '\n\n\n' in result:
            result = result.replace('\n\n\n', '\n\n')
        
        return result.strip()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse .doc file: {str(e)}")
