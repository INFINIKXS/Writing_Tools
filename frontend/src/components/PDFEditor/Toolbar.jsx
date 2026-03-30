import React from 'react';
import { ZoomIn, ZoomOut, Save, Type, Upload, Eraser, Wand2 } from 'lucide-react';

export default function Toolbar({ onZoomIn, onZoomOut, onAddText, onAddRedaction, onToggleWand, isWandActive, onSave, onUpload }) {
  const btnClass = "p-2 hover:bg-gray-100 rounded text-gray-700 transition-colors flex items-center justify-center";
  
  return (
    <div className="bg-white/80 backdrop-blur-md border-b shadow-sm sticky top-0 z-50 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <h2 className="font-bold text-lg text-gray-800 tracking-tight mr-4">Web PDF Editor</h2>
        <label className={`px-4 py-2 rounded-lg text-blue-700 bg-blue-50 hover:bg-blue-100 cursor-pointer font-semibold shadow-sm transition-all hover:shadow flex items-center`}>
          <Upload size={18} className="mr-2"/> Open Local PDF
          <input type="file" accept="application/pdf" className="hidden" onChange={(e) => { if(e.target.files[0]) onUpload(e.target.files[0])} } />
        </label>
      </div>
      
      <div className="flex items-center gap-1 bg-gray-50 p-1 rounded-lg border shadow-inner">
        <button onClick={onZoomOut} className={btnClass} title="Zoom Out"><ZoomOut size={18} /></button>
        <button onClick={onZoomIn} className={btnClass} title="Zoom In"><ZoomIn size={18} /></button>
        <div className="w-px h-6 bg-gray-300 mx-2" />
        <button onClick={onAddText} className={btnClass} title="Add Text Annotation"><Type size={18} /></button>
        <button onClick={onAddRedaction} className={btnClass} title="Add Correction Tape (Whiteout)"><Eraser size={18} /></button>
        <div className="w-px h-6 bg-gray-300 mx-2" />
        <button 
          onClick={onToggleWand} 
          className={`p-2 transition-colors flex items-center justify-center rounded border ${isWandActive ? 'bg-indigo-100 text-indigo-700 border-indigo-300 shadow-inner' : 'hover:bg-gray-100 text-gray-700 border-transparent'}`} 
          title="Auto-Detect Font (Magic Wand)"
        >
          <Wand2 size={18} />
        </button>
      </div>

      <div>
        <button onClick={onSave} className={`px-4 py-2 rounded-lg text-emerald-700 bg-emerald-50 hover:bg-emerald-100 font-semibold shadow-sm transition-all hover:shadow flex items-center`}>
          <Save size={18} className="mr-2"/> Export File
        </button>
      </div>
    </div>
  );
}
