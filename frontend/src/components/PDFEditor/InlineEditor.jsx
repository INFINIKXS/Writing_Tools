import React, { useState, useEffect, useRef } from 'react';
import { blockToScreen } from '../../utils/pdfCoords';

const rgbToHex = (colorStr) => {
  if (!colorStr) return '#000000';
  if (colorStr.startsWith('#')) return colorStr;
  const match = colorStr.match(/\d+/g);
  if (!match || match.length < 3) return '#000000';
  return '#' + match.slice(0, 3).map(x => parseInt(x).toString(16).padStart(2, '0')).join('');
};

const FONTS = ['Original', 'Arial', 'Times New Roman', 'Courier', 'Verdana', 'Georgia'];

export function InlineEditor({ block, scale, existingEdit, onCommit, onCancel }) {
  const [val, setVal] = useState(existingEdit ? existingEdit.newStr : block.text);
  
  // Existing formatting
  const [fontSizeAdj, setFontSizeAdj] = useState(existingEdit ? existingEdit.fontSizeAdj : 0);
  
  // New rich formatting
  const [color, setColor] = useState(() => existingEdit && existingEdit.color ? existingEdit.color : rgbToHex(block.color));
  const [fontFamily, setFontFamily] = useState(existingEdit && existingEdit.customFontFamily ? existingEdit.customFontFamily : 'Original');
  const [isBold, setIsBold] = useState(() => {
    if (existingEdit) return existingEdit.isBold;
    return false;
  });
  const [isItalic, setIsItalic] = useState(() => {
    if (existingEdit) return existingEdit.isItalic;
    return false;
  });
  
  const [keyboardOffset, setKeyboardOffset] = useState(0);
  
  const r = blockToScreen(block, scale);
  const fsize = Math.max(8, Math.round(block.fontSize * scale) + fontSizeAdj);

  const editorRef = useRef(null);

  // Auto focus and place cursor at end
  useEffect(() => {
    if (editorRef.current) {
      editorRef.current.focus();
      try {
        const range = document.createRange();
        const sel = window.getSelection();
        range.selectNodeContents(editorRef.current);
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
    onCommit(val, {
      fontSizeAdj,
      color,
      fontFamily,
      isBold,
      isItalic
    });
  };

  const currentFontFamily = fontFamily === 'Original' ? `"${block.fontName}", sans-serif` : fontFamily;

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
          <span>Orig: {block.fontName || 'Unknown'}</span>
          <span>{Math.round(block.fontSize)}px</span>
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
      
      {/* Block-level contentEditable div with fixed width for reflow */}
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        onInput={e => setVal(e.currentTarget.innerText)}
        onKeyDown={e => { 
          e.stopPropagation();
          if(e.key === 'Escape') onCancel();
          // Ctrl+Enter or Cmd+Enter to commit (plain Enter inserts line break)
          if(e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
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
          top: r.y,
          left: r.x,
          width: `${r.w}px`,
          minHeight: `${r.h}px`,
          transform: keyboardOffset ? `translateY(${-keyboardOffset}px)` : undefined,
          transformOrigin: '0% 0%',
          fontFamily: currentFontFamily,
          fontSize: `${fsize}px`,
          fontWeight: isBold ? 'bold' : 'normal',
          fontStyle: isItalic ? 'italic' : 'normal',
          color: color,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          outline: 'none',
          background: 'rgba(255,255,255,0.95)',
          cursor: 'text',
          zIndex: 100,
          lineHeight: 1.2,
          padding: '2px',
          boxSizing: 'border-box',
          textDecoration: 'underline',           
          textDecorationStyle: 'dashed',         
          textDecorationColor: '#3b82f6',        
          textUnderlineOffset: '4px',            
        }}
      >
        {existingEdit ? existingEdit.newStr : block.text}
      </div>
    </>
  );
}
