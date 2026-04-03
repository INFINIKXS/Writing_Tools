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
      className={`rounded min-w-[30px] ${annotation.isEditing ? 'ring-2 ring-blue-500 bg-blue-50/20' : 'hover:ring-2 hover:ring-blue-300'}`}
      onClick={(e) => { e.stopPropagation(); onUpdate({ ...annotation, isEditing: true }); }}
    >
      {annotation.isEditing && annotation.type !== 'redact' && (
        <div
          className="absolute -top-[44px] left-0 flex items-center bg-white border border-gray-200 shadow-lg rounded-md px-2 py-1.5 gap-2 z-[60]"
          onPointerDown={e => e.stopPropagation()}
        >
          <select
            value={annotation.font || "Helvetica"}
            onChange={e => onUpdate({ ...annotation, font: e.target.value })}
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
            onChange={e => onUpdate({ ...annotation, size: Number(e.target.value) })}
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
            <span
              contentEditable
              suppressContentEditableWarning
              onBlur={() => onUpdate({ ...annotation, isEditing: false })}
              onInput={(e) => onUpdate({ ...annotation, text: e.currentTarget.textContent })}
              style={{ 
                display: 'block',
                fontSize: `${(annotation.size || 16) * scale}px`, 
                fontFamily: annotation.font || 'sans-serif', 
                minWidth: '2ch',
                outline: 'none',
                whiteSpace: 'pre',
                // -- Box Model Fixes --
                lineHeight: 1, 
                padding: 0,
                margin: 0,
                textDecoration: 'underline',
                textDecorationStyle: 'dashed',
                textDecorationColor: '#60a5fa',
                textUnderlineOffset: '4px'
              }}
            >
              {annotation.text || ""}
            </span>
          ) : (
            <div 
              style={{ 
                fontSize: `${(annotation.size || 16) * scale}px`, 
                fontFamily: annotation.font || 'sans-serif', 
                whiteSpace: 'nowrap',
                // -- Box Model Fixes --
                lineHeight: 1, // Crucial: Prevents default 1.2 line-height from pushing text down
                padding: 0,
                margin: 0
              }} 
              className="text-gray-900 select-none tabular-nums"
            >
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

export default function PDFViewer({ file, scale = 1.0, annotations = [], onUpdateAnnotation, onDeleteAnnotation, onCanvasClick, isWandActive, onLivePreview }) {
  const [numPages, setNumPages] = useState(null);

  const [pageMetadata, setPageMetadata] = useState({});
  const [selectedTextIdx, setSelectedTextIdx] = useState(null);
  const [activePageNum, setActivePageNum] = useState(null);

  // Refs to page container divs — needed for DOM color sampling and span measurement
  const pageContainerRefs = useRef({});

  // FIX: Use a ref (not state) to track which pages have been extracted.
  // State-based guards suffer from stale closures inside onLoadSuccess callbacks —
  // the callback captures the pageMetadata value from the render it was created in,
  // not the current value. A ref is always current regardless of render timing.
  const pageItemsExtracted = useRef({});

  const edits = useSyncExternalStore(pdfEditStore.subscribe, () => pdfEditStore.getEdits(activeFileId));

  // ─── Color sampling + span width measurement useEffect ────────────────────
  // This runs AFTER render, so the canvas and text layer spans are guaranteed
  // to exist in the DOM. It sets _colorsApplied=true so it only runs once per
  // page load (cleared on zoom change by onLoadSuccess).
  useEffect(() => {
    Object.entries(pageMetadata).forEach(([pageNumStr, meta]) => {
      if (!meta?.items || meta._colorsApplied) return;
      const pageNum = parseInt(pageNumStr);
      const container = pageContainerRefs.current[pageNum];
      if (!container) return;
      const canvas = container.querySelector('canvas');
      if (!canvas) return;

      let ctx = null;
      try { ctx = canvas.getContext('2d', { willReadFrequently: true }); } catch (e) { }
      if (!ctx) return;

      const canvasW = canvas.width;
      const canvasH = canvas.height;
      const displayW = canvas.clientWidth || 1;
      const displayH = canvas.clientHeight || 1;
      const pixelRatioX = canvasW / displayW;
      const pixelRatioY = canvasH / displayH;
      const currentScale = scale;

      // Collect pdfjs text spans from the DOM text layer
      const textLayerDiv = container.querySelector('.react-pdf__Page__textContent');
      const allSpans = textLayerDiv ? Array.from(textLayerDiv.querySelectorAll('span')) : [];

      // Build lookup: text content → array of {span, used}
      // We mark spans as used so duplicate strings get distinct spans
      const spansByText = {};
      for (const span of allSpans) {
        const txt = span.textContent || '';
        if (!spansByText[txt]) spansByText[txt] = [];
        spansByText[txt].push({ span, used: false });
      }

      const updatedItems = meta.items.map((item) => {
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

        if (matchedSpan) {
          const cs = window.getComputedStyle(matchedSpan);
          const fs = parseFloat(cs.fontSize);
          if (fs > 0) updates.renderedFontSize = fs;
          if (cs.fontFamily) updates.renderedFontFamily = cs.fontFamily;
          if (cs.fontWeight) updates.renderedFontWeight = cs.fontWeight;
          if (cs.fontStyle) updates.renderedFontStyle = cs.fontStyle;

          // FIX: Capture the actual rendered span width in PDF points.
          // item.width from getTextContent() is the glyph-advance width only —
          // it does NOT include justified spacing gaps that PDF.js adds between
          // words. getBoundingClientRect().width is the true rendered width.
          // Dividing by scale converts screen pixels → PDF points.
          const spanRect = matchedSpan.getBoundingClientRect();
          const renderedW = spanRect.width / currentScale;
          if (renderedW > 0) updates.pdfW = renderedW;

          updates.transform = matchedSpan.style.transform;
          updates.top = matchedSpan.style.top;
          updates.left = matchedSpan.style.left;
          updates.lineHeight = cs.lineHeight;
        }

        // Sample the text color from the canvas pixels
        if (ctx && item.str && item.str.trim()) {
          const screenFontSize = (item.fontSize || 12) * currentScale;
          const screenX = item.pdfX * currentScale;
          const screenW = item.pdfW * currentScale;
          const screenBaselineY = item.pdfY_base * currentScale;

          // ── THE DENSE GRID EYEDROPPER ──
          // Instead of 4 random dots, grab a 10x10 pixel chunk directly from 
          // the visual center of the word.
          const midX = Math.round((screenX + screenW * 0.5) * pixelRatioX) - 5;
          const midY = Math.round((screenBaselineY - screenFontSize * 0.3) * pixelRatioY) - 5;

          let purestColor = null;
          let maxDistance = 0; // We want the pixel that is furthest away from White

          try {
            // Extract the RGBA data for all 100 pixels in this 10x10 grid
            const imgData = ctx.getImageData(midX, midY, 10, 10).data;
            
            // Loop through all pixels (data is an array of [r,g,b,a, r,g,b,a...])
            for (let i = 0; i < imgData.length; i += 4) {
              const r = imgData[i];
              const g = imgData[i+1];
              const b = imgData[i+2];
              const a = imgData[i+3];

              if (a < 100) continue; // Ignore transparent or highly blended pixels

              // Calculate how "dark/colorful" this pixel is compared to pure white (255,255,255)
              const distanceFromWhite = (255 - r) + (255 - g) + (255 - b);

              // If this is the strongest ink we've seen so far, save it
              if (distanceFromWhite > maxDistance) {
                maxDistance = distanceFromWhite;
                purestColor = [r, g, b];
              }
            }
          } catch (e) {
             // CORS or canvas taint issues
          }

          // If we found a solid color (distance > 30 ensures we aren't just picking off-white paper noise)
          if (purestColor && maxDistance > 30) {
            updates.color = `rgb(${purestColor[0]}, ${purestColor[1]}, ${purestColor[2]})`;
          }
        }

        return Object.keys(updates).length > 0 ? { ...item, ...updates } : item;
      });

      setPageMetadata(prev => ({
        ...prev,
        [pageNum]: { ...prev[pageNum], items: updatedItems, _colorsApplied: true }
      }));
    });
  }, [pageMetadata, scale]);

  // ─── Keyboard shortcuts (undo/redo) ──────────────────────────────────────
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

  // ─── Document load ────────────────────────────────────────────────────────
  function onDocumentLoadSuccess({ numPages }) {
    setNumPages(numPages);
    // FIX: Reset both state and the extraction ref when a new file loads.
    // Without this, uploading a second PDF reuses stale items from the first.
    setPageMetadata({});
    pageItemsExtracted.current = {};
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
      onClick={() => {
        annotations.forEach(a => { if (a.isEditing) onUpdateAnnotation({ ...a, isEditing: false }) });
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
            className={`relative bg-white shadow-2xl transition-shadow duration-300 ease-in-out ${isWandActive ? 'hover:shadow-indigo-200' : 'hover:shadow-cyan-100/50'}`}
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
                // FIX: Use the ref to guard re-extraction, not pageMetadata state.
                // pageMetadata inside this callback is a stale closure — it holds
                // whatever value pageMetadata had when this render cycle ran.
                // pageItemsExtracted.current is a ref and is always current.
                if (pageItemsExtracted.current[index + 1]) {
                  // Page already extracted. On zoom, just clear _colorsApplied
                  // so the useEffect re-samples colors and span widths at the new scale.
                  setPageMetadata(prev => ({
                    ...prev,
                    [index + 1]: { ...prev[index + 1], _colorsApplied: false }
                  }));
                  return;
                }

                // Mark as extracted immediately (sync) before the async work below,
                // so concurrent calls for the same page don't double-extract.
                pageItemsExtracted.current[index + 1] = true;

                const newSize = {
                  height: page.originalHeight || page.view[3],
                };

                try {
                  const textContent = await page.getTextContent();

                  // Always use scale=1 viewport so coordinates are in raw PDF points.
                  // Util.transform with this viewport flips Y from PDF bottom-left
                  // to screen/MuPDF top-left — the same space PyMuPDF uses.
                  // No further Y conversion is needed anywhere downstream.
                  const viewport1 = page.getViewport({ scale: 1.0 });

                  const items = textContent.items
                    .filter(item => item.str.trim() !== '')
                    // Exclude pure digit strings (footnote superscripts like ¹ ² ³)
                    // These have aggressively shifted baselines and confuse hit-testing
                    .filter(item => !item.str.match(/^\d+$/))
                    .map(item => {
                      const tx = pdfjs.Util.transform(viewport1.transform, item.transform);

                      // tx[4] = x in PDF points from left edge (MuPDF space)
                      // tx[5] = baseline Y in PDF points from top of page (MuPDF space)

                      // Rotation-safe font size: Math.hypot works for all /Rotate values.
                      // For upright pages: tx[0]=fontSize, tx[1]=0 → hypot=fontSize.
                      // For 90° rotated: tx[0]=0, tx[1]=fontSize → hypot=fontSize.
                      const fontSize = Math.hypot(tx[0], tx[1]);
                      const lineHeight = fontSize * 1.2;

                      // Guard against unreliable item.height values.
                      // Some PDFs (especially LaTeX/InDesign exports) multiply item.height
                      // by a near-zero textAdvanceScale, producing garbage like 0.54
                      // when the visual height is 18. We cross-check against lineHeight.
                      const ascenderH = (item.height > 0 && item.height < lineHeight)
                        ? item.height
                        : fontSize * 0.8;

                      const descenderH = lineHeight - ascenderH;

                      const pdfY_base = tx[5];           // baseline from top of page
                      const pdfY_top = pdfY_base - ascenderH;  // top of cap-height
                      const pdfH = ascenderH + descenderH; // full visual height

                      return {
                        str: item.str,
                        fontName: item.fontName,
                        fontSize,
                        pdfX: tx[4],
                        pdfY_base,
                        pdfY_top,
                        pdfH,
                        // pdfW starts as glyph-advance width from PDF.js.
                        // The color-sampling useEffect will overwrite this with
                        // the true rendered span width (includes justified spacing).
                        pdfW: item.width,
                        ascender_h: ascenderH,
                        descender_h: descenderH,
                        color: 'black'
                      };
                    });

                  setPageMetadata(prev => ({
                    ...prev,
                    [index + 1]: { size: newSize, items }
                    // _colorsApplied is intentionally absent here so the useEffect runs
                  }));
                } catch (err) {
                  console.error(`Error extracting text layer for page ${index + 1}:`, err);
                  // Store size even on failure so the page container renders correctly
                  setPageMetadata(prev => ({
                    ...prev,
                    [index + 1]: { ...prev[index + 1], size: newSize }
                  }));
                }
              }}
              onRenderSuccess={() => {
                // Intentionally empty.
                // Color sampling is handled by the pageMetadata useEffect above,
                // which runs after React has committed the DOM — guaranteeing the
                // canvas and text layer spans are present before we read them.
              }}
            />

            {/* Text hit-testing overlay and inline editor */}
            {pageMetadata[index + 1]?.items && pageMetadata[index + 1]?.size && (
              <>
                <TextOverlay
                  items={pageMetadata[index + 1].items}
                  scale={scale}
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
                    scale={scale}
                    existingEdit={edits.find(e => e.pageNum === index + 1 && e.nodeIndex === selectedTextIdx)}
                    onCommit={(newVal, formatOptions) => {
                      const origItem = pageMetadata[index + 1].items[selectedTextIdx];
                      pdfEditStore.commitEdit(activeFileId, {
                        pageNum: index + 1,
                        origStr: origItem.str,
                        newStr: newVal,
                        origin_y: origItem.pdfY_base,
                        ascender_h: origItem.ascender_h,
                        descender_h: origItem.descender_h,
                        rect: {
                          x: origItem.pdfX,
                          y: origItem.pdfY_top,
                          w: origItem.pdfW,
                          h: origItem.pdfH
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
                      // Trigger live backend bake after the store has been updated
                      if (onLivePreview) setTimeout(onLivePreview, 0);
                    }}
                    onCancel={() => setSelectedTextIdx(null)}
                  />
                )}
              </>
            )}

            {/* Draggable free-form annotations */}
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