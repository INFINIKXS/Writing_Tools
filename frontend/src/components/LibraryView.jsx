import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, Copy, Check, BookOpen, ChevronDown, FileText, Loader2, AlertCircle, X, ChevronRight, Trash2, ShieldCheck, ShieldAlert } from 'lucide-react';

const STYLES = [
    { id: 'harvard', label: 'Harvard', desc: 'Cite Them Right (10th ed.)' },
    { id: 'apa', label: 'APA 7th', desc: 'Publication Manual (7th ed.)' },
];

function ReferenceCard({ r, copiedId, copyRich, removeResult, expandedMeta, toggleMeta }) {
    return (
        <div className="glass-card p-4 border-l-4 border-l-purple-500/50 overflow-hidden">
            <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                    <span className="badge badge-green">{r.data.type || 'Reference'}</span>
                    <span className="text-[10px] text-neutral-600 truncate max-w-[150px]">{r.fileName}</span>
                </div>
                <button
                    onClick={() => copyRich(r.data.formatted_html || r.data.formatted, r.id)}
                    className="p-1.5 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all active:scale-90 flex items-center gap-1.5"
                >
                    {copiedId === r.id ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                    <span className="text-[10px] font-bold uppercase tracking-wider">
                        {copiedId === r.id ? 'Copied!' : 'Copy'}
                    </span>
                </button>
            </div>

            <div className="text-sm text-white bg-white/[0.04] p-3 rounded-lg border border-white/8 leading-relaxed font-medium break-words overflow-hidden"
                dangerouslySetInnerHTML={{ __html: (r.data.formatted_html || r.data.formatted).replace(/<(?!\/?(?:i|em)\b)[^>]*>/gi, '') }}
            />

            {!r.data.metadata?.doi && (
                <div className="mt-2 flex items-start gap-2 bg-amber-500/5 border border-amber-500/15 rounded-lg px-3 py-1.5">
                    <span className="text-amber-400 text-[10px] mt-0.5">⚠</span>
                    <p className="text-[10px] text-amber-400/80 leading-relaxed">
                        <strong>No DOI found.</strong> Verify the URL/link is correct and attach your source link after copying.
                    </p>
                </div>
            )}

            {r.data.metadata?.ai_warning && (
                <div className="mt-2 flex items-start gap-2 bg-red-500/5 border border-red-500/15 rounded-lg px-3 py-1.5">
                    <span className="text-red-400 text-[10px] mt-0.5">⚠</span>
                    <p className="text-[10px] text-red-400/80 leading-relaxed">
                        <strong>AI verification failed.</strong> Metadata may be inaccurate — please verify manually.
                    </p>
                </div>
            )}

            <button
                onClick={() => toggleMeta(r.id)}
                className="mt-2 w-full flex items-center justify-between text-[10px] font-semibold text-neutral-600 hover:text-neutral-400 transition-colors"
            >
                <span>Metadata</span>
                <ChevronRight size={10} className={`transition-transform duration-200 ${expandedMeta[r.id] ? 'rotate-90' : ''}`} />
            </button>

            {expandedMeta[r.id] && r.data.metadata && (
                <div className="mt-2 bg-white/[0.02] border border-white/5 rounded-lg p-3 space-y-1.5 animate-fade-in-up">
                    {[
                        ['Author(s)', 'authors', Array.isArray(r.data.metadata.authors) ? r.data.metadata.authors.join('; ') : r.data.metadata.authors],
                        ['Title', 'title', r.data.metadata.title],
                        ['Year', 'year', r.data.metadata.year],
                        ['Source', 'source', r.data.metadata.source],
                        ['Volume', 'volume', r.data.metadata.volume],
                        ['Issue', 'issue', r.data.metadata.issue],
                        ['Pages', 'pages', r.data.metadata.pages],
                        ['DOI', 'doi', r.data.metadata.doi],
                        ['Publisher', 'publisher', r.data.metadata.publisher],
                        ['URL', 'url', r.data.metadata.url],
                    ].filter(([, , val]) => val).map(([label, key, value]) => {
                        const src = r.data.metadata.field_sources?.[key];
                        const srcLabel = { crossref: 'CrossRef', ai_verified: 'AI ✓', ai: 'AI', text_parsing: 'Regex', pdf_metadata: 'PDF' }[src];
                        const srcColor = { crossref: 'text-blue-400 bg-blue-500/10 border-blue-500/20', ai_verified: 'text-green-400 bg-green-500/10 border-green-500/20', ai: 'text-amber-400 bg-amber-500/10 border-amber-500/20', text_parsing: 'text-neutral-400 bg-white/5 border-white/10', pdf_metadata: 'text-neutral-400 bg-white/5 border-white/10' }[src] || '';
                        return (
                            <div key={label} className="flex items-start gap-2">
                                <span className="text-[9px] font-bold uppercase tracking-widest text-neutral-600 w-16 shrink-0 pt-0.5">{label}</span>
                                <span className="text-[11px] text-neutral-300 font-mono break-all flex-1">{value}</span>
                                {srcLabel && <span className={`text-[8px] font-bold uppercase tracking-wider px-1 py-0.5 rounded border shrink-0 ${srcColor}`}>{srcLabel}</span>}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

export default function LibraryView() {
    const [style, setStyle] = useState('harvard');
    const [results, setResults] = useState([]);
    const [isDragging, setIsDragging] = useState(false);
    const [copiedId, setCopiedId] = useState(null);
    const [copiedAll, setCopiedAll] = useState(false);
    const [expandedMeta, setExpandedMeta] = useState({});
    const fileInputRef = useRef(null);
    const idCounter = useRef(0);
    const uploadPanelRef = useRef(null);
    const [inputHeight, setInputHeight] = useState(null);

    useEffect(() => {
        if (!uploadPanelRef.current) return;
        const ro = new ResizeObserver(([entry]) => setInputHeight(entry.contentRect.height + 32));
        ro.observe(uploadPanelRef.current);
        return () => ro.disconnect();
    }, []);

    const currentStyle = STYLES.find(s => s.id === style);

    const processFile = useCallback(async (file, entryId, styleOverride) => {
        const useStyle = styleOverride || style;
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch(`/api/extract-reference?style=${useStyle}`, { method: 'POST', body: formData });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to extract reference');
            }
            const data = await res.json();
            setResults(prev => prev.map(r => r.id === entryId ? { ...r, loading: false, data, error: null } : r));
        } catch (err) {
            setResults(prev => prev.map(r => r.id === entryId ? { ...r, loading: false, error: err.message } : r));
        }
    }, [style]);

    const handleUpload = useCallback(async (files) => {
        if (!files || files.length === 0) return;
        const newEntries = Array.from(files)
            .filter(f => ['pdf', 'docx', 'doc'].includes(f.name.split('.').pop().toLowerCase()))
            .map(f => ({ id: ++idCounter.current, fileName: f.name, loading: true, error: null, data: null, file: f }));
        if (newEntries.length === 0) return;
        setResults(prev => [...prev, ...newEntries]);
        for (const entry of newEntries) processFile(entry.file, entry.id);
    }, [processFile]);

    const handleStyleChange = useCallback(async (newStyle) => {
        setStyle(newStyle);
        // Reformat completed results using lightweight endpoint (no re-extraction)
        const toReformat = results.filter(r => r.data?.metadata);
        if (toReformat.length === 0) return;

        // Mark as loading
        setResults(prev => prev.map(r => r.data?.metadata ? { ...r, loading: true } : r));

        // Reformat each result with the new style
        for (const entry of toReformat) {
            try {
                const res = await fetch(`/api/reformat-reference?style=${newStyle}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ metadata: entry.data.metadata }),
                });
                if (!res.ok) throw new Error('Reformat failed');
                const data = await res.json();
                setResults(prev => prev.map(r => r.id === entry.id ? { ...r, loading: false, data } : r));
            } catch {
                // On failure, keep old data
                setResults(prev => prev.map(r => r.id === entry.id ? { ...r, loading: false } : r));
            }
        }
    }, [results]);

    const onDrop = useCallback((e) => { e.preventDefault(); setIsDragging(false); handleUpload(e.dataTransfer?.files); }, [handleUpload]);
    const onDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
    const onDragLeave = () => setIsDragging(false);

    const stripHtml = (html) => html.replace(/<\/?[^>]*>/g, '');
    const sanitizeHtml = (html) => html.replace(/<(?!\/?(?:i|em)\b)[^>]*>/gi, '');

    const copyRich = (htmlText, id) => {
        const html = sanitizeHtml(htmlText);
        const plain = stripHtml(htmlText);
        navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([plain], { type: 'text/plain' }) })]).then(() => {
            setCopiedId(id);
            setTimeout(() => setCopiedId(null), 2000);
        });
    };

    const copyAll = () => {
        const completed = results.filter(r => r.data);
        if (completed.length === 0) return;
        const allHtml = completed.map(r => sanitizeHtml(r.data.formatted_html || r.data.formatted)).join('<br/>\n');
        const allPlain = completed.map(r => stripHtml(r.data.formatted_html || r.data.formatted)).join('\n');
        navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([allHtml], { type: 'text/html' }), 'text/plain': new Blob([allPlain], { type: 'text/plain' }) })]).then(() => {
            setCopiedAll(true);
            setTimeout(() => setCopiedAll(false), 2000);
        });
    };

    const removeResult = (id) => { setResults(prev => prev.filter(r => r.id !== id)); };
    const clearAll = () => { setResults([]); setExpandedMeta({}); if (fileInputRef.current) fileInputRef.current.value = ''; };
    const toggleMeta = (id) => { setExpandedMeta(prev => ({ ...prev, [id]: !prev[id] })); };

    const completed = results.filter(r => r.data);
    const errors = results.filter(r => r.error);
    const loadingCount = results.filter(r => r.loading).length;

    // Split results by DOI presence — only when both groups exist
    const withDoi = completed.filter(r => r.data.metadata?.doi);
    const withoutDoi = completed.filter(r => !r.data.metadata?.doi);
    const shouldSplit = withDoi.length > 0 && withoutDoi.length > 0;

    const cardProps = { copiedId, copyRich, removeResult, expandedMeta, toggleMeta };

    return (
        <div className="animate-fade-in-up h-full flex flex-col w-full overflow-hidden">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">Reference Generator</h1>
                <p className="text-sm text-neutral-500">Upload PDFs and get properly formatted references for your bibliography.</p>
            </header>

            <div className="flex gap-3 flex-1 min-h-0 min-w-0 w-full">
                {/* Upload Panel — fills height */}
                <div ref={uploadPanelRef} className="glass-card flex flex-col overflow-hidden w-[340px] shrink-0 self-start border-l-4 border-l-purple-500/50 max-w-[40vw]">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Upload size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Upload</h3>
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

                    <div className="p-4 flex flex-col">
                        <p className="text-xs text-neutral-600 mb-3 bg-white/3 p-2.5 rounded-lg border border-white/5">
                            Upload <strong className="text-neutral-400">PDF</strong>, <strong className="text-neutral-400">DOCX</strong>, or <strong className="text-neutral-400">DOC</strong> files.
                            Style: <strong className="text-neutral-400">{currentStyle.label}</strong>
                        </p>

                        {/* Drop Zone — fixed height */}
                        <div
                            onDrop={onDrop}
                            onDragOver={onDragOver}
                            onDragLeave={onDragLeave}
                            onClick={() => fileInputRef.current?.click()}
                            className={`h-[200px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging
                                ? 'border-purple-400 bg-purple-500/10 scale-[1.02]'
                                : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
                                }`}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".pdf,.docx,.doc"
                                multiple
                                className="hidden"
                                onChange={(e) => { handleUpload(e.target.files); e.target.value = ''; }}
                            />
                            <div className="flex flex-col items-center gap-3">
                                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-300 ${isDragging ? 'bg-purple-500/20 border border-purple-400/30 scale-110' : 'bg-white/5 border border-white/10'
                                    }`}>
                                    <FileText size={24} className={isDragging ? 'text-purple-400' : 'text-neutral-600'} />
                                </div>
                                <div className="text-center">
                                    <p className="text-sm text-neutral-400 font-medium">
                                        {isDragging ? 'Drop files here' : 'Drag & drop files'}
                                    </p>
                                    <p className="text-xs text-neutral-600 mt-1">or click to browse</p>
                                </div>
                            </div>
                        </div>

                        {/* File list */}
                        {results.length > 0 && (
                            <>
                                <div className="mt-3 space-y-1 max-h-[200px] overflow-y-auto">
                                    {results.map(r => (
                                        <div key={r.id} className="flex items-center gap-2 text-xs px-3 py-1.5 bg-white/[0.03] rounded-lg border border-white/5">
                                            {r.loading ? <Loader2 size={12} className="text-purple-400 animate-spin shrink-0" /> :
                                                r.error ? <AlertCircle size={12} className="text-red-400 shrink-0" /> :
                                                    <Check size={12} className="text-green-400 shrink-0" />}
                                            <span className={`truncate flex-1 ${r.error ? 'text-red-400' : 'text-neutral-400'}`}>{r.fileName}</span>
                                            <button onClick={(e) => { e.stopPropagation(); removeResult(r.id); }} className="text-neutral-600 hover:text-red-400 transition-colors">
                                                <X size={12} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                                <button onClick={clearAll} className="mt-2 text-[10px] text-neutral-600 hover:text-red-400 self-end flex items-center gap-1 transition-colors">
                                    <Trash2 size={10} /> Clear all
                                </button>
                            </>
                        )}
                    </div>
                </div>

                {/* Results Panel — expands to fill remaining width */}
                <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">
                    {/* Header */}
                    <div className="glass-card px-5 py-3 flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                            <BookOpen size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Generated References</h3>
                            {completed.length > 0 && <span className="text-[10px] font-bold text-neutral-500 bg-white/5 px-2 py-0.5 rounded-full">{completed.length}</span>}
                        </div>
                        <div className="flex items-center gap-2">
                            {completed.length > 1 && (
                                <button onClick={copyAll} className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-neutral-400 hover:text-white transition-all active:scale-95">
                                    {copiedAll ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                                    {copiedAll ? 'Copied!' : 'Copy All'}
                                </button>
                            )}
                            <span className="badge badge-blue">Result</span>
                        </div>
                    </div>

                    {/* Results content */}
                    <div className="flex-1 overflow-y-auto min-h-0">
                        {results.length === 0 && (
                            <div className="h-full flex flex-col items-center justify-center text-neutral-700 space-y-3">
                                <BookOpen size={40} />
                                <p className="text-sm font-medium">Upload documents to generate references</p>
                            </div>
                        )}

                        {loadingCount > 0 && completed.length === 0 && (
                            <div className="glass-card p-4 animate-pulse mb-3">
                                <div className="h-3 bg-white/5 rounded w-24 mb-3"></div>
                                <div className="h-2.5 bg-white/3 rounded w-full mb-1.5"></div>
                                <div className="h-2.5 bg-white/3 rounded w-3/4"></div>
                            </div>
                        )}

                        {/* Errors */}
                        {errors.map(r => (
                            <div key={r.id} className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-3">
                                <AlertCircle size={14} className="text-red-400 shrink-0 mt-0.5" />
                                <div className="flex-1">
                                    <p className="text-xs text-red-400 font-medium">{r.fileName}</p>
                                    <p className="text-[10px] text-red-400/70 mt-0.5">{r.error}</p>
                                </div>
                                <button onClick={() => removeResult(r.id)} className="text-red-400/50 hover:text-red-300"><X size={12} /></button>
                            </div>
                        ))}

                        {/* Single list or split view */}
                        {!shouldSplit ? (
                            <div className="space-y-3">
                                {completed.map(r => <ReferenceCard key={r.id} r={r} {...cardProps} />)}
                            </div>
                        ) : (
                            <div className="flex gap-3 items-start">
                                {/* With DOI — single panel */}
                                <div className="flex-1 min-w-0 glass-card border-l-4 border-l-green-500/50 flex flex-col overflow-hidden" style={inputHeight ? { height: inputHeight } : { maxHeight: '60vh' }}>
                                    <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 shrink-0">
                                        <ShieldCheck size={14} className="text-green-400" />
                                        <h4 className="text-xs font-bold text-green-400 uppercase tracking-wider">Verified (DOI found)</h4>
                                        <span className="text-[10px] text-neutral-600 bg-white/5 px-1.5 py-0.5 rounded">{withDoi.length}</span>
                                    </div>
                                    <div className="flex-1 overflow-y-auto p-3 space-y-3">
                                        {withDoi.map(r => <ReferenceCard key={r.id} r={r} {...cardProps} />)}
                                    </div>
                                </div>

                                {/* Without DOI — single panel */}
                                <div className="flex-1 min-w-0 glass-card border-l-4 border-l-amber-500/50 flex flex-col overflow-hidden" style={inputHeight ? { height: inputHeight } : { maxHeight: '60vh' }}>
                                    <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 shrink-0">
                                        <ShieldAlert size={14} className="text-amber-400" />
                                        <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wider">Needs Review (No DOI)</h4>
                                        <span className="text-[10px] text-neutral-600 bg-white/5 px-1.5 py-0.5 rounded">{withoutDoi.length}</span>
                                    </div>
                                    <div className="flex-1 overflow-y-auto p-3 space-y-3">
                                        {withoutDoi.map(r => <ReferenceCard key={r.id} r={r} {...cardProps} />)}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
