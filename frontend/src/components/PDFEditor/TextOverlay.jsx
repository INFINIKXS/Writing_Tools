import React, { useRef, useEffect, useState } from 'react';
import { blockToScreen } from '../../utils/pdfCoords';

import { DraggableItem } from './DraggableItem';
import { pdfEditStore, activeFileId } from '../../stores/pdfEditStore';

/**
 * Renders the replacement text for an edited block, with word-wrap
 * constrained to the block's width for visual reflow preview.
 */
function BlockTextPreview({ text, origText, fontFamily, fontSize, fontWeight, fontStyle, color, containerW, containerH }) {
  return (
    <div
      style={{
        width: containerW,
        minHeight: containerH,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        overflow: 'hidden',
        color,
        fontSize,
        fontFamily,
        fontWeight: fontWeight || 'normal',
        fontStyle: fontStyle || 'normal',
        lineHeight: 1.2,
        padding: 0,
        margin: 0,
      }}
    >
      {text}
    </div>
  );
}

export function TextOverlay({ blocks, scale, selectedIdx, onSelect, edits = [] }) {
  if (!blocks || blocks.length === 0) return null;

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 50 }}>
      {blocks.map((block, i) => {
        if (!block.text || block.text.trim() === '') return null;

        const r = blockToScreen(block, scale);

        const hasEdit = edits.find(e => e.editType === 'block' && e.blockIndex === i);

        return (
          <DraggableItem
            key={i}
            block={block}
            index={i}
            selectedIdx={selectedIdx}
            hasEdit={hasEdit}
            scale={scale}
            r={r}
            boxTop={r.y}
            boxHeight={r.h}
            onSelect={onSelect}
            updateEdit={(pNum, idx, partial) => pdfEditStore.updateEdit(activeFileId, pNum, idx, partial, 'block')}
          >
            {hasEdit && (
              <BlockTextPreview
                text={hasEdit.newStr}
                origText={hasEdit.origStr || block.text}
                fontFamily={
                  (hasEdit.customFontFamily && hasEdit.customFontFamily !== 'Original')
                    ? hasEdit.customFontFamily
                    : (block.fontName || 'sans-serif')
                }
                fontSize={
                  Math.max(4, (block.fontSize || 12) * scale) + (hasEdit.fontSizeAdj || 0)
                }
                fontWeight={hasEdit.isBold ? 'bold' : 'normal'}
                fontStyle={hasEdit.isItalic ? 'italic' : 'normal'}
                color={hasEdit.color !== undefined ? hasEdit.color : (block.color || '#000000')}
                containerW={r.w}
                containerH={r.h}
              />
            )}
          </DraggableItem>
        );
      })}
    </div>
  );
}
