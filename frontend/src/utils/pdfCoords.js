export function pdfToScreen(item, pageHeight, scale) {
  return {
    x: item.x * scale,
    y: (pageHeight - item.y - item.h) * scale,  // flip Y
    w: item.w * scale,
    h: item.h * scale,
  };
}

export function screenToPdf(rect, pageHeight, scale) {
  return {
    x: rect.x / scale,
    y: pageHeight - (rect.y / scale) - (rect.h / scale),
    w: rect.w / scale,
    h: rect.h / scale,
  };
}
