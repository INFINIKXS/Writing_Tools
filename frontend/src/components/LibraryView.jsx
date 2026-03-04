import React, { useState, useRef, useCallback } from 'react';
import { Upload, Copy, Check, BookOpen, ChevronDown, FileText, Loader2, AlertCircle, X, ChevronRight } from 'lucide-react';

const STYLES = [
    { id: 'harvard', label: 'Harvard', desc: 'Cite Them Right (10th ed.)' },
    { id: 'apa', label: 'APA 7th', desc: 'Publication Manual (7th ed.)' },
];

export default function LibraryView() {
    const [style, setStyle] = useState('harvard');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [fileName, setFileName] = useState(null);
    const [isDragging, setIsDragging] = useState(false);
    const [copied, setCopied] = useState(false);
    const [showMeta, setShowMeta] = useState(false);
    const fileInputRef = useRef(null);

    const currentStyle = STYLES.find(s => s.id === style);

    const handleUpload = useCallback(async (file) => {
        if (!file) return;
        const ext = file.name.split('.').pop().toLowerCase();
        if (!['pdf', 'docx', 'doc'].includes(ext)) {
            setError('Unsupported file type. Please upload a PDF, DOCX, or DOC file.');
            return;
        }

        setFileName(file.name);
        setLoading(true);
        setResult(null);
        setError(null);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const res = await fetch(`/api/extract-reference?style=${style}`, {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to extract reference');
            }

            const data = await res.json();
            setResult(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [style]);

    const onDrop = useCallback((e) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer?.files?.[0];
        if (file) handleUpload(file);
    }, [handleUpload]);

    const onDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
    const onDragLeave = () => setIsDragging(false);

    const sanitizeHtml = (html) => html.replace(/<(?!\/?(?:i|em)\b)[^>]*>/gi, '');
    const stripHtml = (html) => html.replace(/<\/?[^>]*>/g, '');

    const copyRich = (htmlText) => {
        const html = sanitizeHtml(htmlText);
        const plain = stripHtml(htmlText);
        const htmlBlob = new Blob([html], { type: 'text/html' });
        const textBlob = new Blob([plain], { type: 'text/plain' });
        navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })]).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    const reset = () => {
        setResult(null);
        setError(null);
        setFileName(null);
        setShowMeta(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    // Re-fetch with new style when changed
    const handleStyleChange = async (newStyle) => {
        setStyle(newStyle);
        if (result && result.metadata) {
            // We have metadata, just re-upload with new style on next file
            // For now, user needs to re-upload after style change
        }
    };

    return (
        <div className="animate-fade-in-up h-full flex flex-col">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">Reference Generator</h1>
                <p className="text-sm text-neutral-500">Upload a PDF and get a properly formatted reference for your bibliography.</p>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 flex-1 min-h-[500px]">
                {/* Upload Panel */}
                <div className="glass-card flex flex-col overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Upload size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Upload Document</h3>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="relative">
                                <select
                                    value={style}
                                    onChange={(e) => handleStyleChange(e.target.value)}
                                    className="appearance-none bg-white/5 border border-white/10 text-xs font-semibold text-neutral-300 px-3 py-1.5 pr-7 rounded-lg cursor-pointer hover:bg-white/10 transition-colors outline-none focus:border-white/20"
                                >
                                    {STYLES.map(s => (
                                        <option key={s.id} value={s.id} className="bg-neutral-900 text-white">{s.label}</option>
                                    ))}
                                </select>
                                <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 pointer-events-none" />
                            </div>
                            <span className="badge badge-green">Input</span>
                        </div>
                    </div>

                    <div className="p-4 flex-1 flex flex-col">
                        <p className="text-xs text-neutral-600 mb-3 bg-white/3 p-2.5 rounded-lg border border-white/5">
                            Upload a <strong className="text-neutral-400">PDF</strong>, <strong className="text-neutral-400">DOCX</strong>, or <strong className="text-neutral-400">DOC</strong> file.
                            Style: <strong className="text-neutral-400">{currentStyle.label}</strong> ({currentStyle.desc})
                        </p>

                        {/* Drop Zone */}
                        <div
                            onDrop={onDrop}
                            onDragOver={onDragOver}
                            onDragLeave={onDragLeave}
                            onClick={() => fileInputRef.current?.click()}
                            className={`flex-1 min-h-[220px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging
                                ? 'border-purple-400 bg-purple-500/10 scale-[1.02]'
                                : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
                                }`}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".pdf,.docx,.doc"
                                className="hidden"
                                onChange={(e) => handleUpload(e.target.files?.[0])}
                            />

                            {loading ? (
                                <div className="flex flex-col items-center gap-3">
                                    <Loader2 size={36} className="text-purple-400 animate-spin" />
                                    <p className="text-sm text-neutral-400 font-medium">Extracting metadata...</p>
                                    <p className="text-xs text-neutral-600">{fileName}</p>
                                </div>
                            ) : fileName && !error ? (
                                <div className="flex flex-col items-center gap-3">
                                    <div className="w-14 h-14 rounded-2xl bg-green-500/10 border border-green-500/20 flex items-center justify-center">
                                        <Check size={28} className="text-green-400" />
                                    </div>
                                    <p className="text-sm text-neutral-300 font-medium">{fileName}</p>
                                    <button
                                        onClick={(e) => { e.stopPropagation(); reset(); }}
                                        className="text-xs text-neutral-500 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-colors"
                                    >
                                        <X size={12} /> Upload Different File
                                    </button>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-3">
                                    <div className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300 ${isDragging
                                        ? 'bg-purple-500/20 border border-purple-400/30 scale-110'
                                        : 'bg-white/5 border border-white/10'
                                        }`}>
                                        <FileText size={28} className={isDragging ? 'text-purple-400' : 'text-neutral-600'} />
                                    </div>
                                    <div className="text-center">
                                        <p className="text-sm text-neutral-400 font-medium">
                                            {isDragging ? 'Drop your file here' : 'Drag & drop a PDF here'}
                                        </p>
                                        <p className="text-xs text-neutral-600 mt-1">or click to browse</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {error && (
                            <div className="mt-3 flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                                <AlertCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
                                <div>
                                    <p className="text-xs text-red-400 font-medium">{error}</p>
                                    <button
                                        onClick={reset}
                                        className="text-[10px] text-red-400/70 hover:text-red-300 mt-1 underline"
                                    >
                                        Try again
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Result Panel */}
                <div className="glass-card flex flex-col overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between bg-white/[0.01]">
                        <div className="flex items-center gap-2">
                            <BookOpen size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Generated Reference</h3>
                        </div>
                        <span className="badge badge-blue">Result</span>
                    </div>

                    <div className="p-4 flex-1 overflow-y-auto">
                        {!result && !loading && (
                            <div className="h-full flex flex-col items-center justify-center text-neutral-700 space-y-3">
                                <BookOpen size={40} />
                                <p className="text-sm font-medium">Upload a document to generate its reference</p>
                            </div>
                        )}

                        {loading && (
                            <div className="space-y-3">
                                <div className="bg-white/3 p-4 rounded-xl border border-white/5 animate-pulse">
                                    <div className="h-3 bg-white/5 rounded w-24 mb-3"></div>
                                    <div className="h-2.5 bg-white/3 rounded w-full mb-1.5"></div>
                                    <div className="h-2.5 bg-white/3 rounded w-3/4"></div>
                                </div>
                            </div>
                        )}

                        {result && (
                            <div className="space-y-4">
                                {/* Reference Card */}
                                <div className="glass-card p-5 border-l-4 border-l-purple-500/50 group relative overflow-hidden">
                                    <div className="flex justify-between items-start mb-3">
                                        <span className="badge badge-green">{result.type || 'Reference'}</span>
                                        <button
                                            onClick={() => copyRich(result.formatted_html || result.formatted)}
                                            className="p-1.5 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all active:scale-90 flex items-center gap-1.5"
                                        >
                                            {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                                            <span className="text-[10px] font-bold uppercase tracking-wider">
                                                {copied ? 'Copied!' : 'Copy'}
                                            </span>
                                        </button>
                                    </div>

                                    <div className="text-sm text-white bg-white/[0.04] p-4 rounded-lg border border-white/8 leading-relaxed font-medium"
                                        dangerouslySetInnerHTML={{ __html: sanitizeHtml(result.formatted_html || result.formatted) }}
                                    />

                                    <p className="text-[10px] text-neutral-600 mt-3">
                                        {currentStyle.label} style — {currentStyle.desc}
                                    </p>
                                </div>

                                {/* Metadata Accordion */}
                                <button
                                    onClick={() => setShowMeta(!showMeta)}
                                    className="w-full flex items-center justify-between text-xs font-semibold text-neutral-500 hover:text-neutral-300 bg-white/3 hover:bg-white/5 border border-white/5 rounded-lg px-4 py-2.5 transition-colors"
                                >
                                    <span>Extracted Metadata</span>
                                    <ChevronRight size={14} className={`transition-transform duration-200 ${showMeta ? 'rotate-90' : ''}`} />
                                </button>

                                {showMeta && result.metadata && (
                                    <div className="bg-white/[0.02] border border-white/5 rounded-lg p-4 space-y-2 animate-fade-in-up">
                                        {[
                                            ['Author(s)', 'authors', Array.isArray(result.metadata.authors) ? result.metadata.authors.join('; ') : result.metadata.authors],
                                            ['Title', 'title', result.metadata.title],
                                            ['Year', 'year', result.metadata.year],
                                            ['Source', 'source', result.metadata.source],
                                            ['Volume', 'volume', result.metadata.volume],
                                            ['Issue', 'issue', result.metadata.issue],
                                            ['Pages', 'pages', result.metadata.pages],
                                            ['DOI', 'doi', result.metadata.doi],
                                            ['Publisher', 'publisher', result.metadata.publisher],
                                            ['URL', 'url', result.metadata.url],
                                            ['Type', 'type', result.metadata.type],
                                        ].filter(([, , val]) => val).map(([label, key, value]) => {
                                            const src = result.metadata.field_sources?.[key];
                                            const srcLabel = { crossref: 'CrossRef', ai_verified: 'AI Verified', ai: 'AI', text_parsing: 'Regex', pdf_metadata: 'PDF Meta' }[src];
                                            const srcColor = { crossref: 'text-blue-400 bg-blue-500/10 border-blue-500/20', ai_verified: 'text-green-400 bg-green-500/10 border-green-500/20', ai: 'text-amber-400 bg-amber-500/10 border-amber-500/20', text_parsing: 'text-neutral-400 bg-white/5 border-white/10', pdf_metadata: 'text-neutral-400 bg-white/5 border-white/10' }[src] || '';
                                            return (
                                                <div key={label} className="flex items-start gap-3">
                                                    <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 w-20 shrink-0 pt-0.5">{label}</span>
                                                    <span className="text-xs text-neutral-300 font-mono break-all flex-1">{value}</span>
                                                    {srcLabel && <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border shrink-0 ${srcColor}`}>{srcLabel}</span>}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
