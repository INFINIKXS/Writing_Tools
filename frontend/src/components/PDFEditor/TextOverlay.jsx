import React, { useRef, useEffect, useState } from 'react';
import { pdfToScreen } from '../../utils/pdfCoords';

/**
 * Renders the replacement text for an edited item, scaling it horizontally
 * to exactly fill the container width — the same trick pdfjs uses with scaleX.
 * Uses the actual renderedFontFamily from pdfjs for exact font matching.
 */
function ScaledTextSpan({ text, fontFamily, fontSize, fontWeight, fontStyle, color, containerW }) {
  const spanRef = useRef(null);
  const [scaleX, setScaleX] = useState(1);

  useEffect(() => {
    if (!spanRef.current || containerW <= 0) return;
    // Wait a frame for the font to load and render
    requestAnimationFrame(() => {
      if (!spanRef.current) return;
      const naturalW = spanRef.current.scrollWidth;
      if (naturalW > 0) {
        setScaleX(containerW / naturalW);
      }
    });
  }, [text, fontFamily, fontSize, fontWeight, fontStyle, containerW]);

  return (
    <span
      ref={spanRef}
      style={{
        display: 'inline-block',
        whiteSpace: 'nowrap',
        color,
        fontSize,
        fontFamily,
        fontWeight: fontWeight || 'normal',
        fontStyle: fontStyle || 'normal',
        transformOrigin: 'left center',
        transform: `scaleX(${scaleX})`,
        lineHeight: 1,
      }}
    >
      {text}
    </span>
  );
}

export function TextOverlay({ items, pageHeight, scale, selectedIdx, onSelect, edits = [] }) {
  if (!items || items.length === 0) return null;

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 50 }}>
      {items.map((item, i) => {
        if (!item.str || item.str.trim() === '') return null;

        const r = pdfToScreen(item, pageHeight, scale);

        // item.h from pdfjs is often just the glyph height (tiny/0). Use a roomy
        // minimum based on the fontSize so the hover box actually contains the text.
        const minH = item.fontSize * scale * 1.2;
        const displayH = Math.max(r.h, minH);

        const hasEdit = edits.find(e => e.nodeIndex === i);

        return (
          <div
            key={i}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(i);
            }}
            style={{
              position: 'absolute',
              left: r.x,
              top: r.y,
              width: r.w,
              height: displayH,
              cursor: 'text',
              pointerEvents: 'all',
              // When edited: white background masks the original PDF text underneath
              backgroundColor: hasEdit ? 'white' : 'transparent',
              // Align text to the bottom of the box (baseline-like alignment)
              display: 'flex',
              alignItems: 'flex-end',
            }}
            className={`box-border transition-colors duration-150 rounded-[2px] ${
              selectedIdx === i
                ? 'ring-2 ring-blue-500 bg-blue-500/10'
                : hasEdit
                  ? 'hover:bg-blue-50/30'
                  : 'border-[1px] border-dashed border-slate-300/60 hover:border-[1.5px] hover:border-solid hover:border-blue-500 hover:bg-blue-500/5'
            }`}
            title={hasEdit ? `Edited: ${hasEdit.newStr}` : item.str}
          >
            {hasEdit && (
              <ScaledTextSpan
                text={hasEdit.newStr}
                fontFamily={
                  (hasEdit.customFontFamily && hasEdit.customFontFamily !== 'Original')
                    ? hasEdit.customFontFamily
                    : (item.renderedFontFamily || `ForceSpace, "${hasEdit.fontName}", sans-serif`)
                }
                fontSize={
                  // Use the ACTUAL font-size pdfjs computed (in px, includes scale).
                  // Fall back to our formula if onRenderSuccess hasn't run yet.
                  (item.renderedFontSize || Math.max(4, hasEdit.origFontSize * scale)) + hasEdit.fontSizeAdj
                }
                fontWeight={hasEdit.isBold ? 'bold' : (item.renderedFontWeight || 'normal')}
                fontStyle={hasEdit.isItalic ? 'italic' : (item.renderedFontStyle || 'normal')}
                color={hasEdit.color !== undefined ? hasEdit.color : (item.color || '#000000')}
                containerW={r.w}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
