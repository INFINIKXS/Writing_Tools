import React, { useState, useCallback, useRef, useMemo } from 'react';
import Toolbar from '../components/PDFEditor/Toolbar';
import PDFViewer from '../components/PDFEditor/Viewer';
import { applyTextAnnotations } from '../utils/pdfModifier';
import { pdfEditStore, activeFileId } from '../stores/pdfEditStore';

export default function PDFEditorPage() {
  const [currentFile, setCurrentFile] = useState(null);
  const [fileBytes, setFileBytes] = useState(null);
  const [scale, setScale] = useState(1.0);
  
  const [annotations, setAnnotations] = useState([]);
  
  const [isWandActive, setIsWandActive] = useState(false);
  const [defaultStyle, setDefaultStyle] = useState({ font: 'Helvetica', size: 16 });

  // Live preview: blob URL of the most recently baked PDF from the backend.
  // When set, the viewer displays this instead of the raw upload.
  const [livePreviewUrl, setLivePreviewUrl] = useState(null);
  const [isLiveBaking, setIsLiveBaking] = useState(false);
  const prevLiveUrlRef = useRef(null);

  // Stable file reference — only changes when livePreviewUrl or currentFile actually changes.
  // Without useMemo, { url: livePreviewUrl } creates a new object every render,
  // making react-pdf think the file changed and killing the pdf.js workers unnecessarily.
  const viewerFile = useMemo(
    () => livePreviewUrl ? { url: livePreviewUrl } : currentFile,
    [livePreviewUrl, currentFile]
  );

  const handleUpload = (file) => {
    if (!file) return;
    setCurrentFile(file);
    const reader = new FileReader();
    reader.onload = () => {
      setFileBytes(reader.result);
    };
    reader.readAsArrayBuffer(file);
    setAnnotations([]);
    // Clear any live preview from a previous document
    setLivePreviewUrl(null);
    if (prevLiveUrlRef.current) {
      URL.revokeObjectURL(prevLiveUrlRef.current);
      prevLiveUrlRef.current = null;
    }
  };

  const [fontWarnings, setFontWarnings] = useState([]);

  /**
   * Called after every inline edit commit.
   * Immediately sends the original file + ALL accumulated edits to the backend
   * and reloads the viewer with the freshly baked PDF blob.
   */
  const handleLivePreview = useCallback(async () => {
    if (!currentFile) return;
    const inlineEdits = pdfEditStore.getEdits(activeFileId);
    if (inlineEdits.length === 0) return;

    setIsLiveBaking(true);
    try {
      const fd = new FormData();
      // Always bake from the ORIGINAL upload so edits don't compound each other
      fd.append('file', currentFile, 'document.pdf');
      fd.append('edits', JSON.stringify(inlineEdits));

      const res = await fetch('http://localhost:8000/api/pdf/apply-edits', { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`Live bake failed: ${res.status}`);
      
      const warningsHeader = res.headers.get('X-Font-Warnings');
      if (warningsHeader) {
        try {
          const parsedWarnings = JSON.parse(decodeURIComponent(warningsHeader));
          if (parsedWarnings && parsedWarnings.length > 0) {
            setFontWarnings(parsedWarnings);
            // Auto dismiss toast after 8s
            setTimeout(() => setFontWarnings([]), 8000);
          }
        } catch (e) {
          console.error("Failed to parse font warnings", e);
        }
      }

      const blob = await res.blob();

      // ── Make the baked PDF the new editing baseline ──
      // Converting the blob to a File + ArrayBuffer means the next bake sends
      // this already-baked version as the source, naturally compounding edits.
      // Clearing the store removes CSS overlays that would otherwise double-render
      // on top of the already-baked canvas content.
      const bakedFile = new File([blob], currentFile.name || 'document.pdf', { type: 'application/pdf' });
      const bakedBytes = await blob.arrayBuffer();

      pdfEditStore.clear(activeFileId);   // edits are now baked-in, overlays no longer needed
      setCurrentFile(bakedFile);           // triggers viewer to load the baked PDF
      setFileBytes(bakedBytes);

      // No blob URL needed — currentFile IS the baked PDF now
      if (prevLiveUrlRef.current) URL.revokeObjectURL(prevLiveUrlRef.current);
      prevLiveUrlRef.current = null;
      setLivePreviewUrl(null);
    } catch (err) {
      console.error('Live preview error:', err);
    } finally {
      setIsLiveBaking(false);
    }
  }, [currentFile, fileBytes]);

  const handleAddText = () => {
    const newId = Date.now().toString() + Math.random().toString().slice(2, 6);
    const newAnn = { 
      id: newId, 
      type: "text",
      text: "New Text Box", 
      x: 50, 
      y: 50, 
      pageIndex: 0, 
      size: defaultStyle.size, 
      font: defaultStyle.font,
      isEditing: true
    };
    setAnnotations(prev => [...prev, newAnn]);
  };

  const handleAddRedaction = () => {
    const newId = Date.now().toString() + Math.random().toString().slice(2, 6);
    const newAnn = { 
      id: newId, 
      type: "redact", 
      x: 50, 
      y: 100, 
      width: 150, 
      height: 24,
      pageIndex: 0, 
    };
    setAnnotations(prev => [...prev, newAnn]);
  };

  const updateAnnotation = useCallback((updated) => {
    setAnnotations(prev => prev.map(a => a.id === updated.id ? updated : a));
  }, []);

  const deleteAnnotation = useCallback((idToDelete) => {
    setAnnotations(prev => prev.filter(a => a.id !== idToDelete));
  }, []);

  const handleCanvasClick = async (pageIndex, unscaledX, unscaledY) => {
    if (!isWandActive || !currentFile) return;
    setIsWandActive(false); // consume wand click
    
    // We send to backend!
    const formData = new FormData();
    formData.append("file", currentFile);
    formData.append("page_index", pageIndex);
    formData.append("x", unscaledX);
    formData.append("y", unscaledY);
    
    try {
      const resp = await fetch(`http://localhost:8000/api/pdf/detect_font`, {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      if (data && data.font) {
        
        // Very basic mapping from common PDF native fonts to standard 14 fonts
        let matchedFont = "Helvetica";
        const fLow = data.font.toLowerCase();
        if (fLow.includes("time") || fLow.includes("serif")) matchedFont = "Times-Roman";
        else if (fLow.includes("courier") || fLow.includes("mono")) matchedFont = "Courier";
        
        // Override
        setDefaultStyle({ font: matchedFont, size: data.size });
        alert(`Detected PDF native font: ${data.font}\nDetected size: ${data.size}pt\n\nText formater automatically calibrated to match (${matchedFont}, ${data.size}pt)!`);
      }
    } catch (err) {
      console.error(err);
      alert("Error reaching Python font analyzer: " + err.message);
    }
  };

  const handleSave = async () => {
    if (!currentFile || !fileBytes) return;
    
    const inlineEdits = pdfEditStore.getEdits(activeFileId);

    try {
      // 1. Process any legacy overlay annotations via frontend pdf-lib first
      let fileToSend = currentFile;
      if (annotations.length > 0) {
        const editedDocBytes = await applyTextAnnotations(fileBytes, annotations);
        fileToSend = new Blob([editedDocBytes], { type: "application/pdf" });
      }

      // 2. If no inline edits, just download the pdf-lib version directly
      if (inlineEdits.length === 0) {
        if (annotations.length === 0) return; // Nothing changed
        const blob = fileToSend instanceof Blob ? fileToSend : new Blob([fileBytes], { type: "application/pdf" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `edited_${currentFile.name}`;
        link.click();
        return;
      }

      // 3. Process deep inplace text replacements via Python backend
      const fd = new FormData();
      fd.append('file', fileToSend, 'document.pdf');
      fd.append('edits', JSON.stringify(inlineEdits));

      const res = await fetch('http://localhost:8000/api/pdf/apply-edits', { method: 'POST', body: fd });
      if (!res.ok) throw new Error("Backend edit failed");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `edited_${currentFile.name}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Error saving PDF", err);
      alert("Failed to modify the PDF backend array.");
    }
  };

  return (
    <div className={`flex flex-col h-full bg-gray-50 font-sans ${isWandActive ? 'cursor-crosshair' : ''}`}>
      <Toolbar 
        onZoomIn={() => setScale(s => s + 0.2)} 
        onZoomOut={() => setScale(s => Math.max(0.4, s - 0.2))}
        onUpload={handleUpload}
        onAddText={handleAddText}
        onAddRedaction={handleAddRedaction}
        onToggleWand={() => setIsWandActive(!isWandActive)}
        isWandActive={isWandActive}
        onSave={handleSave}
      />
      {/* Live baking indicator */}
      {isLiveBaking && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-[200] flex items-center gap-2 bg-white/90 border border-blue-200 shadow-md rounded-full px-4 py-1.5 text-xs text-blue-600 font-semibold backdrop-blur-sm">
          <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
          </svg>
          Baking preview…
        </div>
      )}
      <div className="flex-1 overflow-hidden p-6 relative">
         <PDFViewer 
           file={viewerFile} 
           scale={scale} 
           annotations={annotations}
           onUpdateAnnotation={updateAnnotation}
           onDeleteAnnotation={deleteAnnotation}
           onCanvasClick={handleCanvasClick}
           isWandActive={isWandActive}
           onLivePreview={handleLivePreview}
         />
      </div>

      {/* Font Fallback Warnings Toast */}
      {fontWarnings.length > 0 && (
        <div className="absolute bottom-6 right-8 z-[300] flex flex-col gap-3 max-w-md w-full">
          {fontWarnings.map((warn, idx) => (
            <div key={idx} className="bg-amber-50 border-l-4 border-amber-500 shadow-xl rounded-r-lg p-4 animate-in slide-in-from-bottom-5 fade-in duration-300">
              <div className="flex justify-between items-start gap-3">
                <div className="flex-1">
                  <h3 className="text-amber-800 font-semibold text-sm">Font Fallback Used (Page {warn.pageNum})</h3>
                  <p className="text-amber-700 text-xs mt-1.5 leading-relaxed">{warn.reason}</p>
                  {warn.missingGlyphs && warn.missingGlyphs.length > 0 && (
                     <p className="text-amber-600 font-mono text-[10px] mt-2 bg-amber-100/50 p-1 rounded">
                       Missing: {warn.missingGlyphs.join(", ")}
                     </p>
                  )}
                </div>
                <button 
                  onClick={() => setFontWarnings(prev => prev.filter((_, i) => i !== idx))}
                  className="text-amber-400 hover:text-amber-700 transition-colors shrink-0"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

    </div>
  );
}
