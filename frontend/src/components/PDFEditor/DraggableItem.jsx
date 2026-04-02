import React, { useState, useRef, useEffect } from 'react';

export function DraggableItem({
  item,
  index,
  selectedIdx,
  hasEdit,
  scale,
  r,
  boxTop,
  boxHeight,
  onSelect,
  updateEdit,
  children
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const startPos = useRef({ x: 0, y: 0 });

  const storedDx = (hasEdit?.pdfDx || 0) * scale;
  const storedDy = (hasEdit?.pdfDy || 0) * scale;

  useEffect(() => {
    if (!isDragging) return;

    const handlePointerMove = (e) => {
      setDragOffset({
        x: e.clientX - startPos.current.x,
        y: e.clientY - startPos.current.y
      });
    };

    const handlePointerUp = () => {
      setIsDragging(false);
      // We only commit if it actually moved
      setDragOffset(curr => {
        if (curr.x !== 0 || curr.y !== 0) {
          const finalPdfDx = (hasEdit?.pdfDx || 0) + (curr.x / scale);
          const finalPdfDy = (hasEdit?.pdfDy || 0) + (curr.y / scale);
          updateEdit(hasEdit.pageNum, index, { pdfDx: finalPdfDx, pdfDy: finalPdfDy });
        }
        return { x: 0, y: 0 };
      });
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isDragging, scale, hasEdit, index, updateEdit]);

  const handlePointerDown = (e) => {
    if (!hasEdit) return; // Only draggable if it's edited
    // Don't drag if clicking the inline editor itself
    if (e.button !== 0) return; // Only left click
    
    e.stopPropagation(); // Avoid triggering selection closure
    setIsDragging(true);
    startPos.current = { x: e.clientX, y: e.clientY };
    onSelect(index); // Ensure it's selected while dragging
  };

  const xOffset = storedDx + dragOffset.x;
  const yOffset = storedDy + dragOffset.y;

  return (
    <div
      onClick={(e) => {
        if (dragOffset.x === 0 && dragOffset.y === 0) {
           e.stopPropagation();
           onSelect(index);
        }
      }}
      onPointerDown={handlePointerDown}
      style={{
        position: 'absolute',
        left: r.x,
        top: boxTop,
        width: hasEdit && hasEdit.newStr !== item.str ? 'max-content' : r.w,
        minWidth: r.w,
        height: boxHeight,
        cursor: isDragging ? 'grabbing' : (hasEdit ? 'grab' : 'text'),
        pointerEvents: 'all',
        backgroundColor: hasEdit || selectedIdx === index ? 'white' : 'transparent',
        display: 'flex',
        alignItems: 'baseline',
        transform: `translate(${xOffset}px, ${yOffset}px)`,
        userSelect: 'none', // Prevent text selection highlight during drag
      }}
      className={`box-border transition-colors duration-0 rounded-[1px] ${
        selectedIdx === index
          ? 'ring-2 ring-blue-500 bg-blue-500/10'
          : hasEdit
            ? 'hover:bg-blue-50/30'
            : 'border-[1px] border-dashed border-transparent hover:border-blue-500 hover:bg-blue-500/5'
      }`}
      title={hasEdit ? `Edited: ${hasEdit.newStr}` : item.str}
    >
      {children}
    </div>
  );
}
