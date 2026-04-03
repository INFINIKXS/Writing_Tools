/**
 * Convert an item's pre-computed PDF-point coordinates to CSS pixels.
 *
 * Coordinates (pdfX, pdfY_top, pdfW, pdfH) are stored on each item by
 * Viewer.jsx using Util.transform(viewport1.transform, item.transform) at
 * scale=1.  That transform already produces top-left-origin, Y-downward
 * values identical to PyMuPDF's coordinate system.  All we need to do for
 * screen rendering is multiply by the current zoom scale.
 *
 * There is NO pageHeight subtraction here — that would double-flip Y.
 */
export function pdfToScreen(item, scale) {
  return {
    x: item.pdfX     * scale,
    y: item.pdfY_top * scale,
    w: item.pdfW     * scale,
    h: item.pdfH     * scale,
  };
}
