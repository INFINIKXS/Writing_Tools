import React, { useRef, useEffect, useState } from 'react';
import { pdfToScreen } from '../../utils/pdfCoords';

import { DraggableItem } from './DraggableItem';
import { pdfEditStore, activeFileId } from '../../stores/pdfEditStore';

/**
 * Renders the replacement text for an edited item, scaling it horizontally
 * to exactly fill the container width — the same trick pdfjs uses with scaleX.
 * Uses the actual renderedFontFamily from pdfjs for exact font matching.
 */
function ScaledTextSpan({ text, origText, fontFamily, fontSize, fontWeight, fontStyle, color, containerW }) {
  const spanRef = useRef(null);
  const [scaleX, setScaleX] = useState(1);

  useEffect(() => {
    if (!spanRef.current || containerW <= 0) return;
    requestAnimationFrame(() => {
      if (!spanRef.current) return;
      
      // If the user actually changed the text content, do not stretch it to fit the old box.
      // We only stretch if the text is identical (e.g. they only changed the color/style),
      // to perfectly align with the PDF's native internal kerning.
      if (text !== origText) {
        setScaleX(1);
        return;
      }
      
      const naturalW = spanRef.current.scrollWidth;
      if (naturalW > 0) {
        setScaleX(containerW / naturalW);
      }
    });
  }, [text, origText, fontFamily, fontSize, fontWeight, fontStyle, containerW]);

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

export function TextOverlay({ items, scale, selectedIdx, onSelect, edits = [] }) {
  if (!items || items.length === 0) return null;

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 50 }}>
      {items.map((item, i) => {
        if (!item.str || item.str.trim() === '') return null;

        const r = pdfToScreen(item, scale);
        
        // Exact top left bounds via MuPDF combined matrix transform
        const boxTop = r.y;
        const boxHeight = r.h;

        const hasEdit = edits.find(e => e.nodeIndex === i);

        return (
          <DraggableItem
            key={i}
            item={item}
            index={i}
            selectedIdx={selectedIdx}
            hasEdit={hasEdit}
            scale={scale}
            r={r}
            boxTop={boxTop}
            boxHeight={boxHeight}
            onSelect={onSelect}
            updateEdit={(pNum, idx, partial) => pdfEditStore.updateEdit(activeFileId, pNum, idx, partial)}
          >
            {hasEdit && (
              <ScaledTextSpan
                text={hasEdit.newStr}
                origText={hasEdit.origStr || item.str}
                fontFamily={
                  (hasEdit.customFontFamily && hasEdit.customFontFamily !== 'Original')
                    ? hasEdit.customFontFamily
                    : (item.renderedFontFamily || `ForceSpace, "${hasEdit.fontName}", sans-serif`)
                }
                fontSize={
                  (item.renderedFontSize || Math.max(4, hasEdit.origFontSize * scale)) + hasEdit.fontSizeAdj
                }
                fontWeight={hasEdit.isBold ? 'bold' : (item.renderedFontWeight || 'normal')}
                fontStyle={hasEdit.isItalic ? 'italic' : (item.renderedFontStyle || 'normal')}
                color={hasEdit.color !== undefined ? hasEdit.color : (item.color || '#000000')}
                containerW={r.w}
              />
            )}
          </DraggableItem>
        );
      })}
    </div>
  );
}
