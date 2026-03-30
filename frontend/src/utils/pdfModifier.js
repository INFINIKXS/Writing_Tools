import { PDFDocument, rgb, StandardFonts } from '@cantoo/pdf-lib';
import fontkit from '@pdf-lib/fontkit';

/**
 * Modifies an existing PDF loaded as a Javascript ArrayBuffer by drawing absolute-positioned
 * texts on top of any desired page before serializing it seamlessly to a Blob for download.
 * 
 * Accurately implements coordinate-space conversion mapping browser canvas to raw PDF DPI.
 */
export async function applyTextAnnotations(pdfBytes, textAnnotations) {
  const pdfDoc = await PDFDocument.load(pdfBytes);
  // Fontkit allows usage of external custom fonts
  pdfDoc.registerFontkit(fontkit);

  const pages = pdfDoc.getPages();
  const fontRefMap = {
    'Helvetica': await pdfDoc.embedFont(StandardFonts.Helvetica),
    'Times-Roman': await pdfDoc.embedFont(StandardFonts.TimesRoman),
    'Courier': await pdfDoc.embedFont(StandardFonts.Courier),
  };

  for (const ann of textAnnotations) {
    if (ann.pageIndex < 0 || ann.pageIndex >= pages.length) continue;
    
    const page = pages[ann.pageIndex];
    const { height } = page.getSize();
    
    // Explicitly handling coordinate mismatch:
    // Browser Y is top-down; PDF Y is bottom-up.
    const scale = ann.scale || 1.0;
    const pdfX = ann.x / scale;

    if (ann.type === 'redact') {
      const pWidth = ann.width || 100;
      const pHeight = ann.height || 20;
      
      const pdfY = height - (ann.y / scale) - pHeight;
      
      page.drawRectangle({
        x: pdfX,
        y: pdfY,
        width: pWidth,
        height: pHeight,
        color: rgb(1, 1, 1), // Pure whiteout
      });
    } else {
      const pdfY = height - (ann.y / scale) - (ann.size || 16); 
      const fontName = ann.font || 'Helvetica';

      page.drawText(ann.text || "", {
        x: pdfX,
        y: pdfY, 
        font: fontRefMap[fontName] || fontRefMap['Helvetica'],
        size: ann.size || 16,
        color: ann.color || rgb(0, 0, 0),
      });
    }
  }

  return await pdfDoc.save();
}
