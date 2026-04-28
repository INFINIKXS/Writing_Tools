import React from 'react';
import { ZoomIn, ZoomOut, Save, Type, Upload, Eraser, Wand2 } from 'lucide-react';

export default function Toolbar({ onZoomIn, onZoomOut, onAddText, onAddRedaction, onToggleWand, isWandActive, onSave, onUpload }) {
  const btnClass = "p-2 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10 transition-colors flex items-center justify-center";
  
  return (
    <div className="glass-card-static sticky top-0 z-50 px-6 py-3 flex items-center justify-between mx-4 mt-4 mb-2">
      <div className="flex items-center gap-4">
        <h2 className="font-extrabold text-lg text-white tracking-tight mr-4">Web PDF Editor</h2>
        <label className={`px-4 py-2 rounded-lg text-white bg-white/5 hover:bg-white/10 border border-white/10 cursor-pointer font-semibold shadow-sm transition-all hover:shadow flex items-center`}>
          <Upload size={18} className="mr-2 text-neutral-400"/> Open Local PDF
          <input type="file" accept="application/pdf" className="hidden" onChange={(e) => { if(e.target.files[0]) onUpload(e.target.files[0])} } />
        </label>
      </div>
      
      <div className="flex items-center gap-1 bg-[#050505] p-1.5 rounded-xl border border-white/10 shadow-inner">
        <button onClick={onZoomOut} className={btnClass} title="Zoom Out"><ZoomOut size={18} /></button>
        <button onClick={onZoomIn} className={btnClass} title="Zoom In"><ZoomIn size={18} /></button>
        <div className="w-px h-5 bg-white/10 mx-1" />
        <button onClick={onAddText} className={btnClass} title="Add Text Annotation"><Type size={18} /></button>
        <button onClick={onAddRedaction} className={btnClass} title="Add Correction Tape (Whiteout)"><Eraser size={18} /></button>
        <div className="w-px h-5 bg-white/10 mx-1" />
        <button 
          onClick={onToggleWand} 
          className={`p-2 transition-all flex items-center justify-center rounded-lg border ${isWandActive ? 'bg-purple-500/20 text-purple-400 border-purple-500/30 shadow-[0_0_15px_rgba(168,85,247,0.2)]' : 'hover:bg-white/10 text-neutral-400 hover:text-white border-transparent'}`} 
          title="Auto-Detect Font (Magic Wand)"
        >
          <Wand2 size={18} />
        </button>
      </div>

      <div>
        <button onClick={onSave} className="btn-accent text-sm py-2 px-6 flex items-center">
          <Save size={18} className="mr-2"/> Export File
        </button>
      </div>
    </div>
  );
}
