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

/**
 * Groups adjacent TextItems into single logical line-items.
 *
 * After redaction + re-insertion, a single original sentence-line becomes
 * multiple TextItems because each insert_text() call creates a separate
 * content stream object. PDF.js getTextContent() then returns one TextItem
 * per content stream object instead of one per visual line.
 *
 * This post-processing step merges items that share the same baseline,
 * same font, and are horizontally adjacent (gap < fontSize * 0.5).
 *
 * Adapted from the community algorithm in mozilla/pdf.js#10154:
 *   - Group by Y (baseline), sort by X within each group
 *   - Merge when (next.x - (current.x + current.width)) < delta
 *
 * Also informed by pdf-text-reader (npm) which inserts spaces when
 * distance-between-text exceeds a font-proportional threshold.
 */
// ── Median helper for word-boundary detection ──
function getMedian(arr) {
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Group per-character rawdict data into words using inter-character gaps.
 * A gap > 2.5× the median gap on the line signals a word boundary.
 */
function groupCharsIntoWords(lineData) {
  const { chars, gaps } = lineData;
  if (!chars || chars.length === 0) return [];

  const medianGap = gaps.length > 0 ? getMedian(gaps) : 0;
  const wordBoundaryThreshold = Math.max(medianGap * 2.5, 1.0);

  const words = [];
  let currentWord = [];

  if (chars[0].c !== ' ' && chars[0].c !== '\u00A0') {
    currentWord.push(chars[0]);
  }

  for (let i = 0; i < gaps.length; i++) {
    const isBoundary =
      gaps[i] > wordBoundaryThreshold ||
      chars[i + 1].c === ' ' ||
      chars[i + 1].c === '\u00A0';
    if (isBoundary && currentWord.length > 0) {
      words.push(currentWord);
      currentWord = [];
    }
    if (chars[i + 1].c !== ' ' && chars[i + 1].c !== '\u00A0') {
      currentWord.push(chars[i + 1]);
    }
  }

  if (currentWord.length > 0) words.push(currentWord);
  return words;
}

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

export default function PDFViewer({ file, scale = 1.0, annotations = [], spacingData = null, onUpdateAnnotation, onDeleteAnnotation, onCanvasClick, isWandActive, onLivePreview }) {
  const [numPages, setNumPages] = useState(null);

  // ─── Dual-document pattern (eliminates the white-flash on bake) ─────────────
  // When a new `file` prop arrives we keep the previous document rendered as
  // a fully-opaque backdrop while the new one loads invisibly underneath it.
  // Once the new document fires onLoadSuccess we hide the backdrop.
  // This means there is never a moment of blank canvas for the user.
  const [previousFile, setPreviousFile] = useState(null);
  const [isNewDocLoading, setIsNewDocLoading] = useState(false);
  // Separate page count for the backdrop so it renders the right number of pages
  const [previousNumPages, setPreviousNumPages] = useState(null);

  const [fileGeneration, setFileGeneration] = useState(0);
  const scrollContainerRef = useRef(null);

  useEffect(() => {
    // When the file prop changes (new bake arrived), start the loading transition.
    // Guard against the very first load where previousFile is still null.
    if (file && file !== previousFile) {
      if (previousFile !== null) {
        setIsNewDocLoading(true);
      }
    }
  // previousFile is intentionally NOT in the dep array — we only want to fire
  // when `file` changes, and we read previousFile as a live ref via the callback.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

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

  // Extract items for each page when spacingData is available.
  // This runs whenever spacingData changes (first load, or after a bake)
  // OR when a page reports its size via onLoadSuccess.
  // Only pages that have a known size AND haven't been extracted yet will
  // be processed, so this naturally handles all timing scenarios:
  //   - spacingData arrives before pages load: waits for sizes, then extracts
  //   - pages load before spacingData arrives: waits for spacingData, then extracts
  //   - both already ready (zoom change, etc.): skipped due to extraction guard
  useEffect(() => {
    if (!spacingData) return;

    Object.entries(pageMetadata).forEach(([pageNumStr, meta]) => {
      const pageNum = parseInt(pageNumStr);
      const index = pageNum - 1;
      if (!meta?.size) return;
      if (pageItemsExtracted.current[pageNum]) return;

      const pageData = spacingData.find((p) => p.page === index);
      if (!pageData || !pageData.blocks) return;

      pageItemsExtracted.current[pageNum] = true;

      // ── Step 1: Build one item per line AND index words by baseline ──
      const lineItems = [];
      const allWordsByBaseline = {};

      pageData.blocks.forEach((blockData) => {
        if (!blockData.lines) return;
        blockData.lines.forEach((lineData) => {
          const words = groupCharsIntoWords(lineData);
          if (words.length === 0) return;

          const baselineKey = Math.round(words[0][0].origin_y * 2) / 2;
          if (!allWordsByBaseline[baselineKey]) allWordsByBaseline[baselineKey] = [];
          words.forEach((w) => allWordsByBaseline[baselineKey].push(w));

          const allCharsInLine = words.flat();
          const lineStr = words.map((wc) => wc.map((c) => c.c).join('')).join(' ');
          const lineX0 = allCharsInLine[0].x0;
          const lineX1 = allCharsInLine[allCharsInLine.length - 1].x1;
          const lineY_base = allCharsInLine[0].origin_y;
          const lineY_top = Math.min(...allCharsInLine.map((c) => c.y0));
          const lineH = Math.max(...allCharsInLine.map((c) => c.y1 - c.y0));
          const lineFontSize = allCharsInLine[0].size;
          const lineFontName = allCharsInLine[0].font;
          let hasSuperscript = false;
          for (const ch of allCharsInLine) {
            if (ch.is_superscript) hasSuperscript = true;
          }
          const ascenderH = Math.max(0, lineY_base - lineY_top);
          const descenderH = Math.max(0, lineY_top + lineH - lineY_base);

          lineItems.push({
            str: lineStr,
            pdfX: lineX0,
            pdfY_base: lineY_base,
            pdfY_top: lineY_top,
            pdfW: lineX1 - lineX0,
            pdfH: lineH,
            fontSize: lineFontSize,
            fontName: lineFontName,
            hasSuperscript,
            ascender_h: ascenderH,
            descender_h: descenderH,
            color: 'black',
            _baselineKey: baselineKey,
          });
        });
      });

      // ── Step 2: Find baselines that need regrouping ──
      const blockCountPerBaseline = {};
      pageData.blocks.forEach((blockData, bi) => {
        if (!blockData.lines) return;
        blockData.lines.forEach((lineData) => {
          const words = groupCharsIntoWords(lineData);
          if (words.length === 0) return;
          const baselineKey = Math.round(words[0][0].origin_y * 2) / 2;
          if (!blockCountPerBaseline[baselineKey]) blockCountPerBaseline[baselineKey] = new Set();
          blockCountPerBaseline[baselineKey].add(bi);
        });
      });

      const baselinesNeedingRegroup = new Set();
      for (const [baseline, blockSet] of Object.entries(blockCountPerBaseline)) {
        if (blockSet.size > 1) baselinesNeedingRegroup.add(parseFloat(baseline));
      }

      // ── Step 3: Column index helper ──
      const columns = pageData.columns || null;
      const getColumnIndex = (x) => {
        if (!columns || columns.length <= 1) return 0;
        const splitX = (columns[0][1] + columns[1][0]) / 2;
        return x < splitX ? 0 : 1;
      };

      // ── Step 4: Start with ALL line items from untouched baselines ──
      const finalItems = [];
      for (const li of lineItems) {
        if (baselinesNeedingRegroup.has(li._baselineKey)) continue;
        finalItems.push(li);
      }

      // ── Step 5: Regroup only the affected baselines ──
      for (const baseline of baselinesNeedingRegroup) {
        const wordsOnLine = allWordsByBaseline[baseline] || [];
        if (wordsOnLine.length === 0) continue;
        wordsOnLine.sort((a, b) => a[0].x0 - b[0].x0);

        let currentItem = null;
        let currentCol = -1;

        for (const wordChars of wordsOnLine) {
          const wordStr = wordChars.map((c) => c.c).join('');
          const wordX0 = wordChars[0].x0;
          const wordY_base = wordChars[0].origin_y;
          const wordY_top = Math.min(...wordChars.map((c) => c.y0));
          const wordW = wordChars[wordChars.length - 1].x1 - wordChars[0].x0;
          const wordH = Math.max(...wordChars.map((c) => c.y1 - c.y0));
          const wordFontSize = wordChars[0].size;
          const wordFontName = wordChars[0].font;
          let wordHasSuperscript = false;
          for (const ch of wordChars) {
            if (ch.is_superscript) wordHasSuperscript = true;
          }
          const ascenderH = Math.max(0, wordY_base - wordY_top);
          const descenderH = Math.max(0, wordY_top + wordH - wordY_base);
          const wordCol = getColumnIndex(wordX0);

          if (!currentItem) {
            currentItem = {
              str: wordStr, pdfX: wordX0, pdfY_base: wordY_base, pdfY_top: wordY_top,
              pdfW: wordW, pdfH: wordH, fontSize: wordFontSize, fontName: wordFontName,
              hasSuperscript: wordHasSuperscript, ascender_h: ascenderH, descender_h: descenderH,
              color: 'black',
            };
            currentCol = wordCol;
          } else {
            const sameColumn = wordCol === currentCol;
            const gap = wordX0 - (currentItem.pdfX + currentItem.pdfW);
            if (sameColumn && gap <= currentItem.fontSize * 1.5) {
              const needsSpace = gap > currentItem.fontSize * 0.12;
              currentItem.str += (needsSpace ? ' ' : '') + wordStr;
              currentItem.pdfW = wordX0 + wordW - currentItem.pdfX;
              currentItem.pdfH = Math.max(currentItem.pdfH, wordH);
              currentItem.pdfY_top = Math.min(currentItem.pdfY_top, wordY_top);
              if (wordHasSuperscript) currentItem.hasSuperscript = true;
              if (ascenderH > currentItem.ascender_h) currentItem.ascender_h = ascenderH;
              if (descenderH > currentItem.descender_h) currentItem.descender_h = descenderH;
            } else {
              finalItems.push(currentItem);
              currentItem = {
                str: wordStr, pdfX: wordX0, pdfY_base: wordY_base, pdfY_top: wordY_top,
                pdfW: wordW, pdfH: wordH, fontSize: wordFontSize, fontName: wordFontName,
                hasSuperscript: wordHasSuperscript, ascender_h: ascenderH, descender_h: descenderH,
                color: 'black',
              };
              currentCol = wordCol;
            }
          }
        }
        if (currentItem) finalItems.push(currentItem);
      }

      // ── Sort final items in reading order ──
      finalItems.sort((a, b) => {
        const yDiff = a.pdfY_base - b.pdfY_base;
        if (Math.abs(yDiff) > 1.5) return yDiff;
        return a.pdfX - b.pdfX;
      });

      setPageMetadata((prev) => ({
        ...prev,
        [pageNum]: { ...prev[pageNum], items: finalItems },
      }));
    });
  }, [spacingData, pageMetadata]);

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

  // ─── Document load ──────────────────────────────────────────────────────────
  function onDocumentLoadSuccess({ numPages: n }) {
    const savedScrollPos = scrollContainerRef.current ? scrollContainerRef.current.scrollTop : 0;

    setNumPages(n);
    
    // ALL of these must happen in the SAME React batch:
    setPageMetadata({});
    pageItemsExtracted.current = {};
    pdfEditStore.clearEdits(activeFileId);
    setFileGeneration(prev => prev + 1);  // ← SYNCHRONOUS, not in setTimeout
    
    setPreviousNumPages(n);
    setPreviousFile(file);
    setIsNewDocLoading(false);

    // Restore scroll after React commits the new DOM
    requestAnimationFrame(() => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollTop = savedScrollPos;
        }
    });
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
      ref={scrollContainerRef}
      className="flex flex-col items-center overflow-auto bg-gray-200 p-8 border rounded-xl shadow-inner h-full relative"
      onClick={() => {
        annotations.forEach(a => { if (a.isEditing) onUpdateAnnotation({ ...a, isEditing: false }) });
        setSelectedTextIdx(null);
      }}
    >
      {/*
        DUAL-DOCUMENT PATTERN
        ────────────────────────────────────────────────────────────────
        While a new baked PDF is loading we render the OLD document as a static
        backdrop (position:absolute, z-index:0, opacity:1) so the user never
        sees a blank white or black canvas.  The incoming Document is rendered
        on top but invisible (opacity:0).  The instant onLoadSuccess fires we
        flip isNewDocLoading=false, the backdrop disappears, and the new
        document fades in.  Net result: zero flash.
      */}
      {isNewDocLoading && previousFile && (
        <Document
          file={previousFile}
          className="flex flex-col gap-6"
          style={{ position: 'absolute', top: 0, left: 0, right: 0, zIndex: 0, pointerEvents: 'none' }}
          loading={null}
        >
          {Array.from(new Array(previousNumPages || numPages), (_, index) => (
            <Page
              key={`prev_page_${index + 1}`}
              pageNumber={index + 1}
              scale={scale}
              renderTextLayer={false}
              renderAnnotationLayer={false}
              loading={null}
            />
          ))}
        </Document>
      )}

      {/* The active / incoming document */}
      <Document
        file={file}
        onLoadSuccess={onDocumentLoadSuccess}
        onLoadError={(error) => {
          console.error('PDFViewer: document load error', error);
          // Safety: always clear the loading overlay so the UI doesn't get stuck
          setIsNewDocLoading(false);
        }}
        className="flex flex-col gap-6"
        style={{
          opacity: isNewDocLoading ? 0 : 1,
          transition: 'opacity 0.15s ease',
          position: 'relative',
          zIndex: 1,
        }}
        loading={<div className="font-semibold text-blue-500 animate-pulse">Loading document...</div>}
      >
        {Array.from(new Array(numPages), (el, index) => (
          <div
            key={`page_${fileGeneration}_${index + 1}`}
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
              onLoadSuccess={(page) => {
                // Just store the page size here. Item extraction happens in a
                // separate useEffect that waits for spacingData to be available.
                // We don't extract items in this handler because onLoadSuccess
                // can fire before spacingData arrives — and we don't want to
                // produce "placeholder" items that get rendered and then have
                // to be replaced.
                const newSize = {
                  height: page.originalHeight || page.view[3],
                };
                setPageMetadata((prev) => ({
                  ...prev,
                  [index + 1]: { ...(prev[index + 1] || {}), size: newSize },
                }));
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

                {activePageNum === index + 1 && selectedTextIdx !== null && pageMetadata[index + 1].items[selectedTextIdx] && (() => {
                  const item = pageMetadata[index + 1].items[selectedTextIdx];
                  return (
                    <InlineEditor
                      key={`${activePageNum}-${selectedTextIdx}-${item.str}`}
                      item={item}
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
                  );
                })()}
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