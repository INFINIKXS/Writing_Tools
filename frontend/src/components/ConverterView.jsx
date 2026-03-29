import React, { useState, useCallback, useRef } from 'react';
import {
  ArrowLeft, FileText, FileType2, Type, ImageIcon, Images,
  Layers, Minimize2, Upload, Download, CheckCircle2, AlertCircle,
  Loader2, X, Plus, GripVertical
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

// ─── Tool Definitions ───────────────────────────────────────────────────────
const TOOLS = [
  {
    id: 'pdf-to-word',
    title: 'PDF to Word',
    description: 'Convert PDF documents to editable DOCX files with layout preservation. OCR support for scanned PDFs.',
    icon: FileText,
    color: '#3B82F6',
    colorLight: 'rgba(59, 130, 246, 0.12)',
    accept: '.pdf',
    acceptLabel: 'PDF',
    endpoint: '/api/convert/pdf-to-word',
    multiple: false,
    outputExt: '.docx',
  },
  {
    id: 'word-to-pdf',
    title: 'Word to PDF',
    description: 'Convert Word documents to high-quality PDF files using LibreOffice.',
    icon: FileType2,
    color: '#10B981',
    colorLight: 'rgba(16, 185, 129, 0.12)',
    accept: '.docx,.doc,.odt,.rtf',
    acceptLabel: 'DOCX, DOC, ODT, RTF',
    endpoint: '/api/convert/word-to-pdf',
    multiple: false,
    outputExt: '.pdf',
  },
  {
    id: 'pdf-to-text',
    title: 'PDF to Text',
    description: 'Extract all text content from PDF files. Uses OCR for scanned documents.',
    icon: Type,
    color: '#F59E0B',
    colorLight: 'rgba(245, 158, 11, 0.12)',
    accept: '.pdf',
    acceptLabel: 'PDF',
    endpoint: '/api/convert/pdf-to-text',
    multiple: false,
    outputExt: '.txt',
  },
  {
    id: 'image-to-pdf',
    title: 'Image to PDF',
    description: 'Convert JPG, PNG, or other images into a single PDF document.',
    icon: ImageIcon,
    color: '#8B5CF6',
    colorLight: 'rgba(139, 92, 246, 0.12)',
    accept: '.jpg,.jpeg,.png,.bmp,.tiff,.tif,.webp',
    acceptLabel: 'JPG, PNG, BMP, TIFF, WebP',
    endpoint: '/api/convert/image-to-pdf',
    multiple: true,
    outputExt: '.pdf',
  },
  {
    id: 'pdf-to-images',
    title: 'PDF to Images',
    description: 'Convert each page of a PDF to high-quality JPG images. Downloads as ZIP.',
    icon: Images,
    color: '#EC4899',
    colorLight: 'rgba(236, 72, 153, 0.12)',
    accept: '.pdf',
    acceptLabel: 'PDF',
    endpoint: '/api/convert/pdf-to-images',
    multiple: false,
    outputExt: '.zip',
  },
  {
    id: 'merge-pdf',
    title: 'Merge PDF',
    description: 'Combine multiple PDF files into a single document in your desired order.',
    icon: Layers,
    color: '#06B6D4',
    colorLight: 'rgba(6, 182, 212, 0.12)',
    accept: '.pdf',
    acceptLabel: 'PDF',
    endpoint: '/api/convert/merge-pdf',
    multiple: true,
    minFiles: 2,
    outputExt: '.pdf',
  },
  {
    id: 'compress-pdf',
    title: 'Compress PDF',
    description: 'Reduce PDF file size by compressing content streams and removing metadata.',
    icon: Minimize2,
    color: '#F97316',
    colorLight: 'rgba(249, 115, 22, 0.12)',
    accept: '.pdf',
    acceptLabel: 'PDF',
    endpoint: '/api/convert/compress-pdf',
    multiple: false,
    outputExt: '.pdf',
  },
];


// ─── Tool Card Component ────────────────────────────────────────────────────
function ToolCard({ tool, onClick }) {
  const Icon = tool.icon;
  return (
    <button
      onClick={onClick}
      className="glass-card p-6 flex flex-col items-start gap-4 group cursor-pointer text-left transition-all duration-300 hover:scale-[1.02]"
      id={`tool-card-${tool.id}`}
    >
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center transition-transform duration-300 group-hover:scale-110"
        style={{ background: tool.colorLight, border: `1px solid ${tool.color}30` }}
      >
        <Icon size={26} style={{ color: tool.color }} />
      </div>
      <div>
        <h3 className="text-base font-bold text-white mb-1.5">{tool.title}</h3>
        <p className="text-xs text-neutral-500 leading-relaxed">{tool.description}</p>
      </div>
      <div className="flex items-center gap-2 mt-auto">
        <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full"
          style={{ background: tool.colorLight, color: tool.color, border: `1px solid ${tool.color}25` }}>
          {tool.acceptLabel}
        </span>
      </div>
    </button>
  );
}


// ─── File Drop Zone ─────────────────────────────────────────────────────────
function FileDropZone({ tool, files, setFiles, onConvert, status, error, resultBlob, resultInfo }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(false);
    const dropped = Array.from(e.dataTransfer.files);
    if (tool.multiple) {
      setFiles(prev => [...prev, ...dropped]);
    } else {
      setFiles(dropped.slice(0, 1));
    }
  }, [tool, setFiles]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleFileSelect = useCallback((e) => {
    const selected = Array.from(e.target.files);
    if (tool.multiple) {
      setFiles(prev => [...prev, ...selected]);
    } else {
      setFiles(selected.slice(0, 1));
    }
    e.target.value = '';
  }, [tool, setFiles]);

  const removeFile = useCallback((index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  }, [setFiles]);

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const handleDownload = useCallback(() => {
    if (!resultBlob) return;
    const url = URL.createObjectURL(resultBlob.blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = resultBlob.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [resultBlob]);

  const canConvert = files.length >= (tool.minFiles || 1) && status !== 'converting';

  return (
    <div className="flex flex-col gap-4 flex-1 min-h-0">
      {/* Drop Zone */}
      {status !== 'done' && (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={`
            glass-card p-8 flex flex-col items-center justify-center text-center cursor-pointer
            transition-all duration-300 min-h-[220px]
            ${isDragOver ? 'border-2' : 'border border-dashed'}
          `}
          style={{
            borderColor: isDragOver ? tool.color : 'rgba(255,255,255,0.1)',
            background: isDragOver ? `${tool.colorLight}` : undefined
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={tool.accept}
            multiple={tool.multiple}
            onChange={handleFileSelect}
            className="hidden"
          />
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center mb-5 transition-transform duration-300"
            style={{
              background: tool.colorLight,
              border: `1.5px solid ${tool.color}30`,
              transform: isDragOver ? 'scale(1.1)' : 'scale(1)'
            }}
          >
            <Upload size={36} style={{ color: tool.color }} />
          </div>
          <h3 className="text-lg font-bold text-white mb-2">
            {isDragOver ? 'Drop files here' : `Select ${tool.acceptLabel} file${tool.multiple ? 's' : ''}`}
          </h3>
          <p className="text-sm text-neutral-500 mb-4">or drag and drop {tool.multiple ? 'files' : 'a file'} here</p>
          <button
            className="py-2.5 px-8 rounded-xl font-bold text-sm transition-all duration-300 hover:scale-105"
            style={{ background: tool.color, color: '#fff' }}
            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
          >
            Browse Files
          </button>
          <p className="text-[10px] text-neutral-600 mt-3">
            Accepts: {tool.acceptLabel} {tool.minFiles ? `(min ${tool.minFiles} files)` : ''}
          </p>
        </div>
      )}

      {/* File List */}
      {files.length > 0 && status !== 'done' && (
        <div className="glass-card-static p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-widest text-neutral-500">
              {files.length} file{files.length > 1 ? 's' : ''} selected
            </span>
            {tool.multiple && (
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-1 text-xs font-semibold transition-colors"
                style={{ color: tool.color }}
              >
                <Plus size={14} /> Add more
              </button>
            )}
          </div>
          <div className="space-y-2 max-h-[180px] overflow-y-auto">
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-3 glass-inner p-3">
                {tool.multiple && <GripVertical size={14} className="text-neutral-600 shrink-0" />}
                <FileText size={16} className="text-neutral-400 shrink-0" />
                <span className="text-sm text-neutral-300 font-medium truncate flex-1">{f.name}</span>
                <span className="text-[10px] text-neutral-600 shrink-0">{formatSize(f.size)}</span>
                <button onClick={() => removeFile(i)} className="text-neutral-600 hover:text-red-400 transition-colors shrink-0">
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Convert Button */}
      {files.length > 0 && status !== 'done' && (
        <button
          disabled={!canConvert}
          onClick={onConvert}
          className="py-4 px-8 rounded-xl font-bold text-base transition-all duration-300 flex items-center justify-center gap-3 hover:scale-[1.01] disabled:opacity-40 disabled:cursor-not-allowed"
          style={{
            background: canConvert ? tool.color : 'rgba(255,255,255,0.05)',
            color: '#fff',
            boxShadow: canConvert ? `0 8px 30px ${tool.color}40` : 'none'
          }}
        >
          {status === 'converting' ? (
            <>
              <Loader2 size={20} className="animate-spin" />
              Converting...
            </>
          ) : (
            <>Convert {tool.title.split(' ').pop()}</>
          )}
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="glass-card-static p-4 border border-red-500/20">
          <div className="flex items-center gap-3">
            <AlertCircle size={20} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-300">{error}</p>
          </div>
        </div>
      )}

      {/* Success + Download */}
      {status === 'done' && resultBlob && (
        <div className="glass-card p-8 flex flex-col items-center text-center animate-fade-in-up">
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center mb-5"
            style={{ background: 'rgba(16, 185, 129, 0.12)', border: '1.5px solid rgba(16, 185, 129, 0.3)' }}
          >
            <CheckCircle2 size={36} className="text-emerald-400" />
          </div>
          <h3 className="text-xl font-bold text-white mb-2">Conversion Complete!</h3>
          {resultInfo && (
            <p className="text-sm text-neutral-400 mb-1">{resultInfo}</p>
          )}
          <p className="text-sm text-neutral-500 mb-6">{resultBlob.filename} — {formatSize(resultBlob.blob.size)}</p>
          <button
            onClick={handleDownload}
            className="py-3.5 px-10 rounded-xl font-bold text-base transition-all duration-300 flex items-center gap-3 hover:scale-105"
            style={{ background: tool.color, color: '#fff', boxShadow: `0 8px 30px ${tool.color}40` }}
          >
            <Download size={20} />
            Download File
          </button>
        </div>
      )}
    </div>
  );
}


// ─── Main Converter View ────────────────────────────────────────────────────
export default function ConverterView() {
  const [selectedTool, setSelectedTool] = useState(null);
  const [files, setFiles] = useState([]);
  const [status, setStatus] = useState('idle'); // idle | converting | done | error
  const [error, setError] = useState(null);
  const [resultBlob, setResultBlob] = useState(null);
  const [resultInfo, setResultInfo] = useState(null);

  const handleBack = useCallback(() => {
    setSelectedTool(null);
    setFiles([]);
    setStatus('idle');
    setError(null);
    setResultBlob(null);
    setResultInfo(null);
  }, []);

  const handleConvert = useCallback(async () => {
    if (!selectedTool || files.length === 0) return;

    setStatus('converting');
    setError(null);
    setResultBlob(null);
    setResultInfo(null);

    try {
      const formData = new FormData();
      if (selectedTool.multiple) {
        files.forEach(f => formData.append('files', f));
      } else {
        formData.append('file', files[0]);
      }

      const response = await fetch(`${API_BASE}${selectedTool.endpoint}`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        throw new Error(errData?.detail || `Conversion failed (${response.status})`);
      }

      const blob = await response.blob();
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = `converted${selectedTool.outputExt}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^"]+)"?/);
        if (match) filename = match[1];
      }

      // For compress — show ratio
      let info = null;
      if (selectedTool.id === 'compress-pdf') {
        const origSize = response.headers.get('X-Original-Size');
        const compSize = response.headers.get('X-Compressed-Size');
        const ratio = response.headers.get('X-Compression-Ratio');
        if (origSize && compSize) {
          const formatBytes = (b) => {
            b = parseInt(b);
            if (b < 1024) return b + ' B';
            if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
            return (b/(1024*1024)).toFixed(1) + ' MB';
          };
          info = `${formatBytes(origSize)} → ${formatBytes(compSize)} (${ratio} reduced)`;
        }
      }

      setResultBlob({ blob, filename });
      setResultInfo(info);
      setStatus('done');
    } catch (err) {
      setError(err.message);
      setStatus('error');
    }
  }, [selectedTool, files]);

  // ─── Tool Selection Grid ──────────────────────────────────────────────
  if (!selectedTool) {
    return (
      <div className="space-y-5 overflow-y-auto flex-1 min-h-0">
        {/* Header */}
        <div className="glass-card-static p-6">
          <h2 className="text-xl font-bold text-white mb-2">Document Converter</h2>
          <p className="text-sm text-neutral-500">
            Convert between PDF, Word, Text, and Image formats. All processing happens locally on this server.
          </p>
        </div>

        {/* Tool Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {TOOLS.map(tool => (
            <ToolCard
              key={tool.id}
              tool={tool}
              onClick={() => setSelectedTool(tool)}
            />
          ))}
        </div>
      </div>
    );
  }

  // ─── Individual Tool Interface ────────────────────────────────────────
  const Icon = selectedTool.icon;
  return (
    <div className="flex flex-col gap-4 flex-1 min-h-0 overflow-y-auto">
      {/* Toolbar */}
      <div className="glass-card-static p-5 flex items-center gap-4">
        <button
          onClick={handleBack}
          className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors shrink-0"
        >
          <ArrowLeft size={18} className="text-neutral-300" />
        </button>
        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0"
          style={{ background: selectedTool.colorLight, border: `1px solid ${selectedTool.color}30` }}
        >
          <Icon size={24} style={{ color: selectedTool.color }} />
        </div>
        <div>
          <h2 className="text-lg font-bold text-white">{selectedTool.title}</h2>
          <p className="text-xs text-neutral-500">{selectedTool.description}</p>
        </div>

        {/* Convert again button (shown after completion) */}
        {status === 'done' && (
          <button
            onClick={() => {
              setFiles([]);
              setStatus('idle');
              setError(null);
              setResultBlob(null);
              setResultInfo(null);
            }}
            className="ml-auto py-2 px-5 rounded-xl text-sm font-bold transition-all duration-300 hover:scale-105"
            style={{ background: selectedTool.colorLight, color: selectedTool.color, border: `1px solid ${selectedTool.color}25` }}
          >
            Convert Another
          </button>
        )}
      </div>

      {/* Conversion Area */}
      <FileDropZone
        tool={selectedTool}
        files={files}
        setFiles={setFiles}
        onConvert={handleConvert}
        status={status}
        error={error}
        resultBlob={resultBlob}
        resultInfo={resultInfo}
      />
    </div>
  );
}
