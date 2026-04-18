import React, { useState, useEffect, useRef } from 'react';
import { pdfToScreen } from '../../utils/pdfCoords';

const rgbToHex = (colorStr) => {
  if (!colorStr) return '#000000';
  if (colorStr.startsWith('#')) return colorStr;
  const match = colorStr.match(/\d+/g);
  if (!match || match.length < 3) return '#000000';
  return '#' + match.slice(0, 3).map(x => parseInt(x).toString(16).padStart(2, '0')).join('');
};

const FONTS = ['Original', 'Arial', 'Times New Roman', 'Courier', 'Verdana', 'Georgia'];

/**
 * Build the initial DOM for the contentEditable span.
 * Splits `str` based on `superscriptRanges` — chars inside a range become
 * children of a <sup> or <sub> element, everything else is normal text.
 * Returns an array of React children.
 */
function buildInitialChildren(str, superscriptRanges) {
  if (!superscriptRanges || superscriptRanges.length === 0) {
    return [str];
  }
  // Sort ranges by charStart so we can walk left-to-right
  const sorted = [...superscriptRanges].sort((a, b) => a.charStart - b.charStart);
  const children = [];
  let cursor = 0;
  sorted.forEach((r, idx) => {
    if (r.charStart > cursor) {
      children.push(str.slice(cursor, r.charStart));
    }
    const chunk = str.slice(r.charStart, r.charEnd);
    if (r.kind === 'super') {
      children.push(
        <sup key={`sup-${idx}`} style={{ fontSize: '0.7em', lineHeight: 0 }}>
          {chunk}
        </sup>,
      );
    } else {
      children.push(
        <sub key={`sub-${idx}`} style={{ fontSize: '0.7em', lineHeight: 0 }}>
          {chunk}
        </sub>,
      );
    }
    cursor = r.charEnd;
  });
  if (cursor < str.length) {
    children.push(str.slice(cursor));
  }
  return children;
}

/**
 * Walk the contentEditable DOM and extract plain text + the character
 * ranges that are inside <sup>/<sub> elements.
 * Returns { text, ranges: [{kind, charStart, charEnd}] }.
 */
function extractTextAndRanges(rootEl) {
  let text = '';
  const ranges = [];

  function walk(node, inSup, inSub) {
    if (node.nodeType === Node.TEXT_NODE) {
      const chunk = node.textContent || '';
      if (chunk.length === 0) return;
      const start = text.length;
      text += chunk;
      if (inSup) {
        ranges.push({ kind: 'super', charStart: start, charEnd: text.length });
      } else if (inSub) {
        ranges.push({ kind: 'sub', charStart: start, charEnd: text.length });
      }
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = node.tagName ? node.tagName.toLowerCase() : '';
    const newInSup = inSup || tag === 'sup';
    const newInSub = inSub || tag === 'sub';
    for (const child of node.childNodes) {
      walk(child, newInSup, newInSub);
    }
  }

  walk(rootEl, false, false);

  // Merge adjacent same-kind ranges
  const merged = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && last.kind === r.kind && last.charEnd === r.charStart) {
      last.charEnd = r.charEnd;
    } else {
      merged.push({ ...r });
    }
  }
  return { text, ranges: merged };
}

/**
 * Enrich newly-extracted ranges with metadata (font size, baseline Y) from
 * the original ranges. We match by ORDER and KIND — if the Nth super in
 * the new text corresponds to the Nth super in the original text, copy
 * its fontSize/pdfY_top so the backend can render it at the same scale
 * and elevation as the original.
 *
 * Brand-new ranges (no corresponding original) get null metadata, and
 * the backend falls back to defaults.
 */
function enrichRangesWithOriginalMetadata(newRanges, originalRanges) {
  if (!originalRanges || originalRanges.length === 0) return newRanges;
  // Index originals by kind, in order of appearance
  const origByKind = { super: [], sub: [] };
  for (const o of originalRanges) {
    if (o.kind === 'super' || o.kind === 'sub') {
      origByKind[o.kind].push(o);
    }
  }
  const usedByKind = { super: 0, sub: 0 };
  return newRanges.map((nr) => {
    const pool = origByKind[nr.kind];
    if (!pool || usedByKind[nr.kind] >= pool.length) {
      return { ...nr };
    }
    const orig = pool[usedByKind[nr.kind]];
    usedByKind[nr.kind] += 1;
    return {
      ...nr,
      // Carry forward original super/sub geometry. Backend uses these
      // to render the new chars at the same size and baseline elevation
      // as the original PDF's super/sub.
      fontSize: orig.fontSize,
      pdfY_top: orig.pdfY_top,
      pdfX: orig.pdfX,
      pdfH: orig.pdfH,
      color: orig.color,
    };
  });
}

export function InlineEditor({ item, scale, existingEdit, onCommit, onCancel }) {
  const initialStr = existingEdit ? existingEdit.newStr : item.str;
  const initialRanges = existingEdit
    ? existingEdit.superscriptRanges || []
    : item.superscriptRanges || [];

  // We no longer store text as state — the DOM IS the source of truth.
  // We only read it when the user commits.
  const [fontSizeAdj, setFontSizeAdj] = useState(existingEdit ? existingEdit.fontSizeAdj : 0);
  const [color, setColor] = useState(() => existingEdit && existingEdit.color ? existingEdit.color : rgbToHex(item.color));
  const [fontFamily, setFontFamily] = useState(existingEdit && existingEdit.customFontFamily ? existingEdit.customFontFamily : 'Original');
  // Read bold/italic from the backend's authoritative PyMuPDF font flags
  // (item.isBold / item.isItalic). These are derived from either the
  // font's PDF flag bits or the PostScript name containing "Bold" /
  // "Italic" / "Oblique" — more reliable than PDF.js's text-layer
  // CSS weight heuristics, which often misreport for subsetted fonts.
  //
  // Fall back to PDF.js heuristics only if the backend didn't provide
  // the flags (e.g. regrouped items that skipped the extract-spacing path).
  const [isBold, setIsBold] = useState(() => {
    if (existingEdit) return existingEdit.isBold;
    if (item.isBold !== undefined) return item.isBold;
    return item.renderedFontWeight === 'bold' || parseInt(item.renderedFontWeight) >= 600;
  });
  const [isItalic, setIsItalic] = useState(() => {
    if (existingEdit) return existingEdit.isItalic;
    if (item.isItalic !== undefined) return item.isItalic;
    return item.renderedFontStyle === 'italic';
  });

  const [keyboardOffset, setKeyboardOffset] = useState(0);

  const r = pdfToScreen(item, scale);
  const fsize = Math.max(8, Math.round(item.fontSize * scale) + fontSizeAdj);

  const spanRef = useRef(null);

  // Auto focus and place cursor at end
  useEffect(() => {
    if (spanRef.current) {
      spanRef.current.focus();
      try {
        const range = document.createRange();
        const sel = window.getSelection();
        range.selectNodeContents(spanRef.current);
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);
      } catch (e) {}
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle mobile keyboard
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const reposition = () => {
      const keyboardHeight = window.innerHeight - vv.height;
      setKeyboardOffset(keyboardHeight > 0 ? keyboardHeight : 0);
    };
    vv.addEventListener('resize', reposition);
    return () => vv.removeEventListener('resize', reposition);
  }, []);

  const handleCommit = () => {
    let newText = initialStr;
    let newRanges = initialRanges;
    if (spanRef.current) {
      const extracted = extractTextAndRanges(spanRef.current);
      newText = extracted.text;
      // Carry original super/sub metadata (fontSize, baseline Y) into the
      // new ranges so the backend can render them at the correct size
      // and elevation rather than estimating from parent line metrics.
      newRanges = enrichRangesWithOriginalMetadata(
        extracted.ranges,
        initialRanges,
      );
    }
    onCommit(
      newText,
      { fontSizeAdj, color, fontFamily, isBold, isItalic },
      newRanges,
    );
  };

  const currentFontFamily = fontFamily === 'Original' ? `ForceSpace, "${item.fontName}", sans-serif` : fontFamily;

  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: r.x,
          top: Math.max(0, r.y - 70 - keyboardOffset),
          zIndex: 101,
          width: 'max-content'
        }}
        className="flex flex-col bg-white border border-gray-300 rounded-md shadow-lg pointer-events-auto divide-y divide-gray-200"
        onPointerDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="px-2 py-1 text-[10px] text-gray-500 bg-gray-50 rounded-t-md flex items-center justify-between gap-4">
          <span>Orig: {item.fontName || 'Unknown'}</span>
          <span>{Math.round(item.fontSize)}px</span>
        </div>
        <div className="flex gap-1 p-1 items-center">
          <select
            value={fontFamily}
            onChange={e => setFontFamily(e.target.value)}
            className="text-xs border border-gray-300 rounded px-1 py-1 outline-none hover:border-blue-400"
          >
            {FONTS.map(f => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>

          <input
            type="color"
            value={color}
            onChange={e => setColor(e.target.value)}
            className="w-6 h-6 p-0 border-0 rounded cursor-pointer"
            title="Text Color"
          />

          <div className="w-px h-4 bg-gray-300 mx-1"></div>

          <button onClick={() => setIsBold(!isBold)} className={`w-6 h-6 flex items-center justify-center text-sm font-bold rounded ${isBold ? 'bg-blue-100 text-blue-700' : 'hover:bg-gray-100'}`} title="Bold">B</button>
          <button onClick={() => setIsItalic(!isItalic)} className={`w-6 h-6 flex items-center justify-center text-sm italic rounded ${isItalic ? 'bg-blue-100 text-blue-700' : 'hover:bg-gray-100'}`} title="Italic">I</button>

          <div className="w-px h-4 bg-gray-300 mx-1"></div>

          <button onClick={() => setFontSizeAdj(v => v - 1)} className="px-1.5 py-1 text-xs font-semibold hover:bg-gray-100 rounded" title="Smaller">A-</button>
          <button onClick={() => setFontSizeAdj(v => v + 1)} className="px-1.5 py-1 text-xs font-semibold hover:bg-gray-100 rounded" title="Larger">A+</button>

          <div className="w-px h-4 bg-gray-300 mx-1"></div>

          <button onClick={handleCommit} className="px-2 py-1 text-xs text-blue-600 font-medium hover:bg-blue-50 rounded">Done</button>
          <button onClick={onCancel} className="px-2 py-1 text-xs text-gray-500 hover:bg-red-50 hover:text-red-600 rounded">✕</button>
        </div>
      </div>

      <span
        ref={spanRef}
        contentEditable
        suppressContentEditableWarning
        onKeyDown={e => {
          e.stopPropagation();
          if (e.key === 'Escape') onCancel();
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleCommit();
          }
        }}
        onKeyUp={e => e.stopPropagation()}
        onKeyPress={e => e.stopPropagation()}
        onPointerDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
        onMouseDown={e => e.stopPropagation()}
        onMouseUp={e => e.stopPropagation()}
        className="shadow-xl"
        style={{
          position: 'absolute',
          top: item.top !== undefined ? item.top : r.y,
          left: item.left !== undefined ? item.left : r.x,
          transform: item.transform ? (keyboardOffset ? `translateY(${-keyboardOffset}px) ${item.transform}` : item.transform) : `translateY(${-keyboardOffset}px)`,
          transformOrigin: '0% 0%',
          fontFamily: fontFamily !== 'Original' ? currentFontFamily : (item.renderedFontFamily || 'sans-serif'),
          fontSize: `${(item.renderedFontSize || fsize) + fontSizeAdj}px`,
          fontWeight: isBold ? 'bold' : 'normal',
          fontStyle: isItalic ? 'italic' : 'normal',
          color: color,
          whiteSpace: 'pre',
          outline: 'none',
          background: 'transparent',
          minWidth: '1ch',
          display: 'block',
          cursor: 'text',
          zIndex: 100,
          lineHeight: item.lineHeight || 'normal',
          textDecoration: 'underline',
          textDecorationStyle: 'dashed',
          textDecorationColor: '#3b82f6',
          textUnderlineOffset: '4px',
        }}
      >
        {buildInitialChildren(initialStr, initialRanges)}
      </span>
    </>
  );
}
