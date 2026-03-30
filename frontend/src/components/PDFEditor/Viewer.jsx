import React, { useState, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

// Drag component strictly bound to page coordinates
function DraggableElement({ annotation, onUpdate, onDelete, scale }) {
  const [isDragging, setIsDragging] = useState(false);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  const displayX = annotation.x * scale;
  const displayY = annotation.y * scale;

  const handlePointerDown = (e) => {
    e.stopPropagation();
    setIsDragging(true);
    // Grab the exact clicking offset to prevent snapping
    setOffset({
      x: e.clientX - displayX,
      y: e.clientY - displayY
    });
  };

  const handlePointerMove = (e) => {
    if (!isDragging) return;
    const newX = (e.clientX - offset.x) / scale;
    const newY = (e.clientY - offset.y) / scale;
    onUpdate({ ...annotation, x: newX, y: newY });
  };

  const handlePointerUp = () => setIsDragging(false);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', handlePointerUp);
    }
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isDragging, offset, scale]);

  return (
    <div 
      style={{
        position: 'absolute',
        top: Math.max(0, displayY),
        left: Math.max(0, displayX),
        cursor: isDragging ? 'grabbing' : 'grab',
        zIndex: 50,
      }}
      onPointerDown={handlePointerDown}
      className={`border-2 border-dashed ${annotation.isEditing ? 'border-blue-500 bg-blue-50/20' : 'border-transparent hover:border-blue-300'} p-1 rounded min-w-[30px]`}
      onClick={(e) => { e.stopPropagation(); onUpdate({ ...annotation, isEditing: true }); }}
    >
      {annotation.isEditing && annotation.type !== 'redact' && (
        <div 
          className="absolute -top-[44px] left-0 flex items-center bg-white border border-gray-200 shadow-lg rounded-md px-2 py-1.5 gap-2 z-[60]"
          onPointerDown={e => e.stopPropagation()} // Prevent dragging when clicking UI
        >
           <select 
             value={annotation.font || "Helvetica"}
             onChange={e => onUpdate({...annotation, font: e.target.value})}
             className="text-xs rounded border-gray-300 bg-gray-50 py-0.5 px-1 cursor-pointer outline-none"
           >
             <option value="Helvetica">Helvetica</option>
             <option value="Times-Roman">Times Roman</option>
             <option value="Courier">Courier</option>
           </select>
           <div className="w-px h-4 bg-gray-300" />
           <input 
             type="number"
             value={annotation.size || 16}
             onChange={e => onUpdate({...annotation, size: Number(e.target.value)})}
             className="w-12 text-xs rounded border-gray-300 px-1 py-0.5 outline-none font-mono"
             min="1" max="100"
           />
        </div>
      )}

      {annotation.type === 'redact' ? (
        <div 
          style={{
            width: (annotation.width || 100) * scale,
            height: (annotation.height || 20) * scale,
            resize: 'both',
            overflow: 'hidden',
            backgroundColor: 'white',
            border: annotation.isEditing ? '1px solid #ccc' : 'none'
          }}
          onPointerUp={(e) => {
            // Readjust the underlying state sizes when user lets go of the CSS resize handle
            if (e.target.offsetWidth) {
              const rectWidth = e.target.offsetWidth / scale;
              const rectHeight = e.target.offsetHeight / scale;
              if (rectWidth !== annotation.width || rectHeight !== annotation.height) {
                onUpdate({ ...annotation, width: rectWidth, height: rectHeight });
              }
            }
          }}
        />
      ) : (
        <>
          {annotation.isEditing ? (
            <input 
              autoFocus
              value={annotation.text || ""}
              onChange={(e) => onUpdate({ ...annotation, text: e.target.value })}
              onBlur={() => onUpdate({ ...annotation, isEditing: false })}
              className="bg-transparent outline-none m-0 p-0 text-gray-900 border-b border-blue-400 tabular-nums"
              style={{ fontSize: (annotation.size || 16) * scale, fontFamily: 'sans-serif', minWidth: `${Math.max(4, (annotation.text||'').length + 1)}ch` }}
            />
          ) : (
            <div style={{ fontSize: (annotation.size || 16) * scale, fontFamily: 'sans-serif', whiteSpace: 'nowrap' }} className="text-gray-900 select-none tabular-nums">
              {annotation.text || "Empty"}
            </div>
          )}
        </>
      )}
      
      {annotation.isEditing && (
        <button 
          onPointerDown={(e) => { e.stopPropagation(); onDelete(); }}
          className="absolute -top-3 -right-3 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-red-600 shadow-md"
        >
          ✕
        </button>
      )}
    </div>
  );
}

export default function PDFViewer({ file, scale = 1.0, annotations = [], onUpdateAnnotation, onDeleteAnnotation, onCanvasClick, isWandActive }) {
  const [numPages, setNumPages] = useState(null);

  function onDocumentLoadSuccess({ numPages }) {
    setNumPages(numPages);
  }

  if (!file) {
    return (
      <div className="flex items-center justify-center p-12 bg-gray-100 rounded-lg shadow-inner h-96 w-full max-w-4xl mx-auto border-2 border-dashed border-gray-300">
        <p className="text-gray-500 font-medium text-lg">Please upload a PDF to begin editing.</p>
      </div>
    );
  }

  return (
    <div 
      className="flex flex-col items-center overflow-auto bg-gray-200 p-8 border rounded-xl shadow-inner h-full"
      // Clicking empty canvas dismisses active focus (sets all isEditing to false)
      onClick={() => annotations.forEach(a => { if(a.isEditing) onUpdateAnnotation({...a, isEditing: false}) })}
    >
      <Document
        file={file}
        onLoadSuccess={onDocumentLoadSuccess}
        className="flex flex-col gap-6"
        loading={<div className="font-semibold text-blue-500 animate-pulse">Loading document...</div>}
      >
        {Array.from(new Array(numPages), (el, index) => (
          <div 
            key={`page_${index + 1}`} 
            className={`relative bg-white shadow-2xl transition-all duration-300 ease-in-out ${isWandActive ? 'hover:shadow-indigo-200' : 'hover:shadow-cyan-100/50'}`}
            onPointerDown={(e) => {
              if (isWandActive) {
                e.preventDefault();
                const rect = e.currentTarget.getBoundingClientRect();
                const unscaledX = (e.clientX - rect.left) / scale;
                const unscaledY = (e.clientY - rect.top) / scale;
                onCanvasClick(index, unscaledX, unscaledY);
              }
            }}
          >
            <Page 
              pageNumber={index + 1} 
              scale={scale} 
              renderTextLayer={true} 
              renderAnnotationLayer={true} 
            />
            
            {/* Overlay the precisely calculated Elements */}
            {annotations.filter(a => a.pageIndex === index).map(ann => (
              <DraggableElement 
                key={ann.id}
                annotation={ann} 
                scale={scale}
                onUpdate={onUpdateAnnotation}
                onDelete={() => onDeleteAnnotation(ann.id)}
              />
            ))}
          </div>
        ))}
      </Document>
    </div>
  );
}
