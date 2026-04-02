import React, { useState, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { TextOverlay } from './TextOverlay';
import { InlineEditor } from './InlineEditor';
import { useSyncExternalStore } from 'react';
import { pdfEditStore, activeFileId } from '../../stores/pdfEditStore';

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

  // Phase 1 tracking
  const [pageMetadata, setPageMetadata] = useState({});
  const [selectedTextIdx, setSelectedTextIdx] = useState(null);
  const [activePageNum, setActivePageNum] = useState(null);
  // Refs to page container divs so onRenderSuccess can read real DOM styles
  const pageContainerRefs = useRef({});

  // Phase 3 Edit State
  const edits = useSyncExternalStore(pdfEditStore.subscribe, () => pdfEditStore.getEdits(activeFileId));

  useEffect(() => {
    const handleGlobalKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        if (e.shiftKey) {
          pdfEditStore.redo(activeFileId);
        } else {
          pdfEditStore.undo(activeFileId);
        }
        e.preventDefault();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        pdfEditStore.redo(activeFileId);
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', handleGlobalKey);
    return () => window.removeEventListener('keydown', handleGlobalKey);
  }, []);

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
      onClick={() => {
        annotations.forEach(a => { if(a.isEditing) onUpdateAnnotation({...a, isEditing: false}) });
        setSelectedTextIdx(null);
      }}
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
            ref={el => { pageContainerRefs.current[index + 1] = el; }}
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
              onLoadSuccess={async (page) => {
                const newSize = {
                  height: page.originalHeight || page.view[3],
                  renderedScale: scale
                };
                
                try {
                  const textContent = await page.getTextContent();
                  const items = textContent.items.map(item => {
                    // Correct font-size: use Math.hypot of the vertical component of the transform
                    const fontSize = Math.hypot(item.transform[2], item.transform[3]);
                    return {
                      str: item.str,
                      x: item.transform[4],          
                      y: item.transform[5],          
                      w: item.width,
                      h: item.height,
                      fontSize,
                      fontName: item.fontName,
                      // Color will be populated by onRenderSuccess from the actual DOM
                      color: 'black'
                    };
                  });
                  
                  setPageMetadata(prev => ({
                     ...prev,
                     [index + 1]: { size: newSize, items }
                  }));
                } catch (err) {
                  console.error("Error extracting text layer:", err);
                  setPageMetadata(prev => ({
                     ...prev,
                     [index + 1]: { ...prev[index+1], size: newSize }
                  }));
                }
              }}
              onRenderSuccess={() => {
                // After pdfjs has fully painted, read actual styles from the DOM text spans
                // and sample text color from the canvas.
                const container = pageContainerRefs.current[index + 1];
                if (!container) return;
                
                // 1. Collect pdfjs text spans with their computed styles
                const textLayerDiv = container.querySelector('.react-pdf__Page__textContent');
                const allSpans = textLayerDiv ? Array.from(textLayerDiv.querySelectorAll('span')) : [];
                
                // Build a lookup: map span text content → array of {span, used}
                // pdfjs may skip empty items or create extra spans, so match by content
                const spansByText = {};
                for (const span of allSpans) {
                  const txt = span.textContent || '';
                  if (!spansByText[txt]) spansByText[txt] = [];
                  spansByText[txt].push({ span, used: false });
                }
                
                // 2. Get canvas for color sampling
                const canvas = container.querySelector('canvas');
                let ctx = null;
                if (canvas) {
                  try { ctx = canvas.getContext('2d', { willReadFrequently: true }); } catch(e) {}
                }
                
                setPageMetadata(prev => {
                  const existing = prev[index + 1];
                  if (!existing?.items) return prev;
                  
                  const canvasW = canvas?.width || 1;
                  const canvasH = canvas?.height || 1;
                  const displayW = canvas?.clientWidth || 1;
                  const displayH = canvas?.clientHeight || 1;
                  const pixelRatioX = canvasW / displayW;
                  const pixelRatioY = canvasH / displayH;
                  
                  const updatedItems = existing.items.map((item) => {
                    const updates = {};
                    
                    // Match this item to a pdfjs span by text content
                    const candidates = spansByText[item.str];
                    let matchedSpan = null;
                    if (candidates) {
                      const unused = candidates.find(c => !c.used);
                      if (unused) {
                        unused.used = true;
                        matchedSpan = unused.span;
                      }
                    }
                    
                    // Read actual font properties from the matched pdfjs span
                    if (matchedSpan) {
                      const cs = window.getComputedStyle(matchedSpan);
                      const fs = parseFloat(cs.fontSize);
                      if (fs > 0) updates.renderedFontSize = fs;
                      // pdfjs loads embedded PDF fonts with internal names — capture this
                      if (cs.fontFamily) updates.renderedFontFamily = cs.fontFamily;
                      if (cs.fontWeight) updates.renderedFontWeight = cs.fontWeight;
                      if (cs.fontStyle) updates.renderedFontStyle = cs.fontStyle;
                    }
                    
                    // Sample color from the canvas at the text's position
                    if (ctx && item.str && item.str.trim()) {
                      const screenFontSize = (item.fontSize || 12) * scale;
                      const screenX = item.x * scale;
                      const screenW = item.w * scale;
                      
                      // In PDF coords, y is baseline from bottom. Convert to top-left:
                      const screenBaselineY = (existing.size.height - item.y) * scale;
                      
                      // Characters mostly live between 0.1x to 0.7x font-size ABOVE the baseline.
                      // Sampling exactly here prevents overshooting into the line above.
                      const safeY1 = screenBaselineY - screenFontSize * 0.3;
                      const safeY2 = screenBaselineY - screenFontSize * 0.6;
                      
                      // Sample several points across the text to find the darkest pixel
                      // (anti-aliasing can make single samples too light)
                      const samplePoints = [
                        { x: screenX + screenW * 0.2, y: safeY1 },
                        { x: screenX + screenW * 0.5, y: safeY1 },
                        { x: screenX + screenW * 0.3, y: safeY2 },
                        { x: screenX + screenW * 0.7, y: safeY2 },
                      ];
                      
                      let darkestPixel = null;
                      let darkestLum = 999;
                      
                      for (const pt of samplePoints) {
                        const px = Math.round(pt.x * pixelRatioX);
                        const py = Math.round(pt.y * pixelRatioY);
                        if (px < 0 || px >= canvasW || py < 0 || py >= canvasH) continue;
                        try {
                          const d = ctx.getImageData(px, py, 1, 1).data;
                          // Skip transparent canvas pixels
                          if (d[3] === 0) continue; 
                          
                          const lum = d[0] * 0.299 + d[1] * 0.587 + d[2] * 0.114;
                          // If canvas drew transparency over white, it looks white
                          if (lum < darkestLum) {
                            darkestLum = lum;
                            darkestPixel = d;
                          }
                        } catch(e) {}
                      }
                      
                      // Use the sampled color if it's materially darker than white
                      if (darkestPixel && darkestLum < 240) {
                        updates.color = `rgb(${darkestPixel[0]}, ${darkestPixel[1]}, ${darkestPixel[2]})`;
                      }
                    }
                    
                    return Object.keys(updates).length > 0 ? { ...item, ...updates } : item;
                  });
                  return { ...prev, [index + 1]: { ...existing, items: updatedItems } };
                });
              }}
            />

            
            {/* Phase 1 & 2 Text Hit-Testing & Editing */}
            { pageMetadata[index + 1]?.items && pageMetadata[index + 1]?.size && (
              <>
                <TextOverlay 
                  items={pageMetadata[index + 1].items} 
                  pageHeight={pageMetadata[index + 1].size.height} 
                  scale={pageMetadata[index + 1].size.renderedScale} 
                  selectedIdx={activePageNum === index + 1 ? selectedTextIdx : null}
                  edits={edits.filter(e => e.pageNum === index + 1)}
                  onSelect={(idx) => {
                    setSelectedTextIdx(idx);
                    setActivePageNum(index + 1);
                  }}
                />
                
                {activePageNum === index + 1 && selectedTextIdx !== null && pageMetadata[index + 1].items[selectedTextIdx] && (
                  <InlineEditor 
                    item={pageMetadata[index + 1].items[selectedTextIdx]}
                    pageHeight={pageMetadata[index + 1].size.height}
                    scale={pageMetadata[index + 1].size.renderedScale}
                    onCommit={(newVal, formatOptions) => {
                       const origItem = pageMetadata[index + 1].items[selectedTextIdx];
                       pdfEditStore.commitEdit(activeFileId, {
                          pageNum: index + 1,
                          origStr: origItem.str,
                          newStr: newVal,
                          rect: {
                             x: origItem.x,
                             y: origItem.y,
                             w: origItem.w,
                             h: origItem.h
                          },
                          origFontSize: origItem.fontSize,
                          fontSizeAdj: formatOptions.fontSizeAdj,
                          fontName: origItem.fontName,
                          color: formatOptions.color,
                          customFontFamily: formatOptions.fontFamily,
                          isBold: formatOptions.isBold,
                          isItalic: formatOptions.isItalic,
                          nodeIndex: selectedTextIdx
                       });
                       setSelectedTextIdx(null);
                    }}
                    onCancel={() => setSelectedTextIdx(null)}
                  />
                )}
              </>
            )}
            
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
