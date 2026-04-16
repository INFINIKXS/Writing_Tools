import React, { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import Toolbar from '../components/PDFEditor/Toolbar';
import PDFViewer from '../components/PDFEditor/Viewer';
import { applyTextAnnotations } from '../utils/pdfModifier';
import { pdfEditStore, activeFileId } from '../stores/pdfEditStore';

// ─── Error Boundary ──────────────────────────────────────────────────────────
// Catches any React render crash inside the PDF viewer and displays a
// recoverable fallback instead of unmounting to the black body background.
class PDFErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('PDF render error caught by boundary:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-full text-slate-400">
          <div className="text-center p-8">
            <div className="text-5xl mb-4 opacity-30">⚠️</div>
            <p className="text-lg font-semibold mb-2 text-slate-300">PDF failed to render</p>
            <p className="text-sm text-slate-500 mb-6">An unexpected error occurred in the PDF viewer.</p>
            <button
              className="text-sm underline text-blue-400 hover:text-blue-300 transition-colors"
              onClick={() => this.setState({ hasError: false })}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function PDFEditorPage() {
  const [currentFile, setCurrentFile] = useState(null);
  const [fileBytes, setFileBytes] = useState(null);
  const [scale, setScale] = useState(1.0);
  
  const [spacingData, setSpacingData] = useState(null);
  const [annotations, setAnnotations] = useState([]);
  
  const [isWandActive, setIsWandActive] = useState(false);
  const [defaultStyle, setDefaultStyle] = useState({ font: 'Helvetica', size: 16 });

  // Live preview: stable object URL of the most recently baked PDF.
  // We store the URL in a ref so we can revoke the old one before creating a
  // new one, preventing memory leaks.  We also keep it in state so the viewer
  // re-renders when it changes.
  const [livePreviewUrl, setLivePreviewUrl] = useState(null);
  const [isLiveBaking, setIsLiveBaking] = useState(false);
  // objectUrlRef tracks the *current* blob URL so we can revoke it on the
  // next bake or on unmount.  prevLiveUrlRef is kept for the upload-clear path.
  const objectUrlRef = useRef(null);
  const prevLiveUrlRef = useRef(null);

  // Revoke any outstanding object URL when the component unmounts.
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
      }
    };
  }, []);

  // Stable file reference — only changes when livePreviewUrl or currentFile actually changes.
  // Without useMemo, { url: livePreviewUrl } creates a new object every render,
  // making react-pdf think the file changed and killing the pdf.js workers unnecessarily.
  const viewerFile = useMemo(
    () => livePreviewUrl ? { url: livePreviewUrl } : currentFile,
    [livePreviewUrl, currentFile]
  );

  const handleUpload = async (file) => {
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

    // Fetch authoritative spacing + column data from the backend
    try {
      const fd = new FormData();
      fd.append('file', file, 'document.pdf');
      const res = await fetch('http://localhost:8000/api/pdf/extract-spacing', {
        method: 'POST', body: fd,
      });
      if (res.ok) {
        const payload = await res.json();
        setSpacingData(payload);
      } else {
        console.error('Failed to extract spacing data');
      }
    } catch (e) {
      console.error('extract-spacing error:', e);
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
      // Always bake from the ORIGINAL upload so edits don't compound each other.
      // If currentFile is already a string URL (from a previous bake), we need
      // to fetch it back into a Blob first before re-uploading.
      let sourceFile;
      if (typeof currentFile === 'string') {
        // currentFile is an object URL from a previous bake — fetch it locally
        const localRes = await fetch(currentFile);
        const localBlob = await localRes.blob();
        sourceFile = new File([localBlob], 'document.pdf', { type: 'application/pdf' });
      } else {
        sourceFile = currentFile;
      }
      fd.append('file', sourceFile, 'document.pdf');
      fd.append('edits', JSON.stringify(inlineEdits));

      const res = await fetch('http://localhost:8000/api/pdf/apply-edits', { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`Live bake failed: ${res.status}`);

      const warningsHeader = res.headers.get('X-Font-Warnings');
      if (warningsHeader) {
        try {
          const parsedWarnings = JSON.parse(decodeURIComponent(warningsHeader));
          if (parsedWarnings && parsedWarnings.length > 0) {
            setFontWarnings(parsedWarnings);
            // Auto-dismiss toast after 8 s
            setTimeout(() => setFontWarnings([]), 8000);
          }
        } catch (e) {
          console.error('Failed to parse font warnings', e);
        }
      }

      const blob = await res.blob();
      const bakedBytes = await blob.arrayBuffer();

      // ── Stable URL strategy ──────────────────────────────────────────────
      // Instead of wrapping the blob in a new File object (which creates a new
      // reference, causing react-pdf to fully re-initialize the document),
      // we pass a string object URL.  react-pdf compares string file props by
      // value — the same URL string on a re-render does NOT trigger a reload,
      // and a new string URL (different value) triggers a smooth transition.
      //
      // We revoke the *previous* URL right before creating the new one so that
      // the old blob is freed from memory without any gap in display.
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
      }
      const newUrl = URL.createObjectURL(blob);
      objectUrlRef.current = newUrl;

      pdfEditStore.clear(activeFileId); // edits are now baked-in; remove CSS overlays

      // Clear stale spacingData so items don't briefly render at old coordinates
      // against the new baked PDF while we wait for fresh data from the backend.
      setSpacingData(null);

      // Re-extract ground-truth spacing + columns from the freshly baked PDF
      try {
        const spacingFd = new FormData();
        spacingFd.append('file', blob, 'document.pdf');
        const spacingRes = await fetch(
          'http://localhost:8000/api/pdf/extract-spacing',
          { method: 'POST', body: spacingFd },
        );
        if (spacingRes.ok) {
          const payload = await spacingRes.json();
          setSpacingData(payload);
        }
      } catch (e) {
        console.error('Failed to re-extract spacing after bake:', e);
      }

      setCurrentFile(newUrl);           // ✅ stable string ref — no full remount
      setFileBytes(bakedBytes);
      setLivePreviewUrl(null);          // clear any legacy preview URL
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
        <PDFErrorBoundary>
          <PDFViewer 
            file={viewerFile} 
            scale={scale} 
            annotations={annotations}
            spacingData={spacingData}
            onUpdateAnnotation={updateAnnotation}
            onDeleteAnnotation={deleteAnnotation}
            onCanvasClick={handleCanvasClick}
            isWandActive={isWandActive}
            onLivePreview={handleLivePreview}
          />
        </PDFErrorBoundary>
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
