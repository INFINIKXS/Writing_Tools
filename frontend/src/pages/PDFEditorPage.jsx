import React, { useState, useCallback } from 'react';
import Toolbar from '../components/PDFEditor/Toolbar';
import PDFViewer from '../components/PDFEditor/Viewer';
import { applyTextAnnotations } from '../utils/pdfModifier';

export default function PDFEditorPage() {
  const [currentFile, setCurrentFile] = useState(null);
  const [fileBytes, setFileBytes] = useState(null);
  const [scale, setScale] = useState(1.0);
  
  const [annotations, setAnnotations] = useState([]);
  
  const [isWandActive, setIsWandActive] = useState(false);
  const [defaultStyle, setDefaultStyle] = useState({ font: 'Helvetica', size: 16 });

  const handleUpload = (file) => {
    if (!file) return;
    setCurrentFile(file);
    const reader = new FileReader();
    reader.onload = () => {
      setFileBytes(reader.result);
    };
    reader.readAsArrayBuffer(file);
    setAnnotations([]);
  };

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
    if (!fileBytes) return;
    try {
      const editedDocBytes = await applyTextAnnotations(fileBytes, annotations);
      const blob = new Blob([editedDocBytes], { type: "application/pdf" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `edited_${currentFile.name}`;
      link.click();
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
      <div className="flex-1 overflow-hidden p-6 relative">
         <PDFViewer 
           file={currentFile} 
           scale={scale} 
           annotations={annotations}
           onUpdateAnnotation={updateAnnotation}
           onDeleteAnnotation={deleteAnnotation}
           onCanvasClick={handleCanvasClick}
           isWandActive={isWandActive}
         />
      </div>
    </div>
  );
}
