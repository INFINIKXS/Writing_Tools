import React, { useState, useRef, useCallback, useEffect } from 'react';
import { BookOpen, AlertCircle, Wand2, Loader2, ArrowRight, Check, Upload, FileText, Trash2 } from 'lucide-react';

export default function PhrasebankView() {
    const [documents, setDocuments] = useState([]);
    const [stats, setStats] = useState({ total_documents: 0, total_phrases: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);

    const [inputText, setInputText] = useState('');
    const [processing, setProcessing] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [copiedOption, setCopiedOption] = useState(null);
    const fileInputRef = useRef(null);

    useEffect(() => { fetchDocuments(); fetchStats(); }, []);

    const fetchDocuments = async () => {
        try {
            const res = await fetch('/api/phrasebank/documents');
            if (res.ok) { const d = await res.json(); setDocuments(d.documents || []); }
        } catch { }
    };

    const fetchStats = async () => {
        try {
            const res = await fetch('/api/phrasebank/stats');
            if (res.ok) { const d = await res.json(); setStats(d); }
        } catch { }
    };

    const handleUpload = useCallback(async (files) => {
        if (!files || files.length === 0) return;
        const pdfs = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfs.length === 0) return;
        setUploading(true); setError(null);
        try {
            const formData = new FormData();
            pdfs.forEach(f => formData.append('files', f));
            const res = await fetch('/api/phrasebank/upload', { method: 'POST', body: formData });
            if (!res.ok) throw new Error('Upload failed');
            await fetchDocuments(); await fetchStats();
        } catch (err) { setError('Failed to upload and mine Phrasebank documents.'); }
        finally { setUploading(false); }
    }, []);

    const handleDelete = async (docId) => {
        try {
            const res = await fetch(`/api/phrasebank/document/${docId}`, { method: 'DELETE' });
            if (res.ok) { setDocuments(prev => prev.filter(d => d.doc_id !== docId)); await fetchStats(); }
        } catch { }
    };

    const onDrop = useCallback((e) => { e.preventDefault(); setIsDragging(false); handleUpload(e.dataTransfer?.files); }, [handleUpload]);

    const handleRewrite = async () => {
        if (!inputText.trim()) return;
        setProcessing(true);
        setResult(null);
        setError(null);

        try {
            const res = await fetch('/api/phrasebank/rewrite', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: inputText.trim() }),
            });
            if (!res.ok) {
                const e = await res.json().catch(() => ({}));
                throw new Error(e.detail || 'Failed to rewrite text.');
            }
            setResult(await res.json());
        } catch (err) {
            setError(err.message || 'Failed to rewrite text with Phrasebank.');
        } finally {
            setProcessing(false);
        }
    };

    const copyOption = (text, optionName) => {
        navigator.clipboard.writeText(text).then(() => {
            setCopiedOption(optionName);
            setTimeout(() => setCopiedOption(null), 2000);
        });
    };

    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1 flex items-center gap-2">
                    <BookOpen size={28} className="text-blue-400" />
                    Academic Phrasebank
                </h1>
                <p className="text-sm text-neutral-500">
                    Restructure dense, nominalisation-heavy sentences into clearer, active formats using established academic templates.
                </p>
            </header>

            <div className="flex gap-3 flex-1 min-h-0 min-w-0 w-full">
                {/* Left: Phrase Bank */}
                <div className="glass-card flex flex-col overflow-hidden w-[300px] shrink-0 self-start border-l-4 border-l-blue-500/50 max-w-[33vw]">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <BookOpen size={16} className="text-blue-400" />
                            <h3 className="text-sm font-bold text-white">Phrase Bank</h3>
                        </div>
                        {stats.total_phrases > 0 && (
                            <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/20">
                                {stats.total_phrases.toLocaleString()} templates
                            </span>
                        )}
                    </div>
                    <div className="p-4 flex flex-col gap-3">
                        <p className="text-xs text-neutral-600 bg-white/3 p-2.5 rounded-lg border border-white/5">
                            Upload <strong className="text-neutral-400">academic PDFs</strong>. The AI will extract and categorize highly reusable phrasing templates for rewriting.
                        </p>

                        <div
                            onDrop={onDrop}
                            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                            onDragLeave={() => setIsDragging(false)}
                            onClick={() => fileInputRef.current?.click()}
                            className={`h-[130px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging ? 'border-blue-400 bg-blue-500/10 scale-[1.02]' : 'border-white/10 bg-white/[0.02] hover:border-white/20'}`}
                        >
                            <input ref={fileInputRef} type="file" accept=".pdf" multiple className="hidden" onChange={(e) => { handleUpload(e.target.files); e.target.value = ''; }} />
                            {uploading ? (
                                <div className="flex flex-col items-center gap-2">
                                    <Loader2 size={22} className="text-blue-400 animate-spin" />
                                    <p className="text-sm text-blue-400 font-medium">Mining academic phrases...</p>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-2">
                                    <Upload size={20} className={isDragging ? 'text-blue-400' : 'text-neutral-600'} />
                                    <p className="text-sm text-neutral-500">{isDragging ? 'Drop here' : 'Drag & drop PDFs'}</p>
                                    <p className="text-xs text-neutral-700">or click to browse</p>
                                </div>
                            )}
                        </div>

                        {documents.length > 0 && (
                            <div className="space-y-1 max-h-[260px] overflow-y-auto">
                                {documents.map(doc => (
                                    <div key={doc.doc_id} className="flex items-center gap-2 text-xs px-3 py-2 bg-white/[0.03] rounded-lg border border-white/5 group">
                                        <FileText size={12} className="text-blue-400 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-neutral-300 truncate">{doc.filename}</p>
                                            <p className="text-[10px] text-neutral-600">{doc.phrase_count} templates extracted</p>
                                        </div>
                                        <button onClick={() => handleDelete(doc.doc_id)} className="text-neutral-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100">
                                            <Trash2 size={12} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Main Editor */}
                <div className="flex-1 flex flex-col min-w-0 gap-4 min-h-0 overflow-y-auto">
                    {/* Input Area */}
                    <div className="glass-card p-5 shrink-0">
                        <div className="flex items-center gap-2 mb-3">
                            <Wand2 size={16} className="text-blue-400" />
                            <h3 className="text-sm font-bold text-white">Dense Sentence Input</h3>
                        </div>
                        <textarea
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); handleRewrite(); } }}
                            placeholder={"Paste a dense academic sentence here...\n\ne.g., 'Health management is a methodical approach that generates structural predictability and directs routine service delivery.'\n\nCtrl+Enter to restructure."}
                            className="w-full bg-white/[0.02] border border-white/8 rounded-xl p-4 text-sm text-neutral-200 leading-relaxed resize-none outline-none focus:border-white/20 transition-colors placeholder-neutral-700 h-[110px]"
                            spellCheck="false"
                        />
                        <div className="flex justify-end mt-3">
                            <button
                                onClick={handleRewrite}
                                disabled={processing || !inputText.trim()}
                                className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {processing ? <><Loader2 size={16} className="animate-spin" /> Analyzing...</> : <><Wand2 size={16} /> Phrasebank Rewrite</>}
                            </button>
                        </div>
                    </div>

                    {/* Error State */}
                    {error && (
                        <div className="glass-card p-4 border-l-4 border-l-red-500/50 shrink-0">
                            <div className="flex items-center gap-2">
                                <AlertCircle size={16} className="text-red-400" />
                                <p className="text-sm text-red-300">{error}</p>
                            </div>
                        </div>
                    )}

                    {/* Results Area */}
                    {result && !processing && (
                        <div className="space-y-4">
                            {/* Analysis & Templates */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 shrink-0">
                                {/* Structural Analysis */}
                                <div className="glass-card p-5 border-l-4 border-l-purple-500/50">
                                    <p className="text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-2">Structural Analysis</p>
                                    <div className="space-y-3">
                                        <div>
                                            <p className="text-xs text-neutral-400 mb-1">Core Concept:</p>
                                            <p className="text-sm text-white font-medium">{result.analysis?.core_concept}</p>
                                        </div>
                                        {result.analysis?.nominalisations_found?.length > 0 && (
                                            <div>
                                                <p className="text-xs text-neutral-400 mb-1">Nominalisations (Noun Stacks) Detected:</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {result.analysis.nominalisations_found.map((n, i) => (
                                                        <span key={i} className="text-xs bg-red-500/10 text-red-300 px-2 py-1 rounded-md border border-red-500/20">
                                                            {n}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Templates Applied */}
                                <div className="glass-card p-5 border-l-4 border-l-blue-500/50">
                                    <p className="text-[10px] font-bold text-blue-400 uppercase tracking-wider mb-2">Templates Applied</p>
                                    <div className="space-y-2">
                                        {result.templates_applied?.map((t, i) => (
                                            <div key={i} className="flex items-start gap-2">
                                                <Wand2 size={14} className="text-blue-400 shrink-0 mt-0.5" />
                                                <p className="text-sm text-neutral-300 italic">"{t}"</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Options */}
                            <div className="glass-card p-5 border-l-4 border-l-green-500/50 shrink-0 space-y-4">
                                <p className="text-[10px] font-bold text-green-400 uppercase tracking-wider mb-2">Restructured Options</p>

                                {result.options?.map((opt, i) => (
                                    <div key={i} className="bg-white/[0.02] p-4 rounded-xl border border-white/5 relative group">
                                        <div className="flex justify-between items-center mb-2">
                                            <p className="text-xs font-bold text-neutral-400">{opt.name}</p>
                                            <button
                                                onClick={() => copyOption(opt.text, opt.name)}
                                                className="text-xs flex items-center gap-1 text-neutral-500 hover:text-green-400 transition-colors bg-white/5 px-2 py-1 rounded"
                                            >
                                                {copiedOption === opt.name ? <><Check size={12} className="text-green-400" /> Copied</> : 'Copy'}
                                            </button>
                                        </div>
                                        <p className="text-sm text-neutral-200 leading-relaxed">{opt.text}</p>
                                    </div>
                                ))}
                            </div>

                            {/* Follow up flow suggestion */}
                            {result.follow_up && (
                                <div className="glass-card p-4 bg-blue-500/5 border border-blue-500/10 shrink-0 flex items-start gap-3">
                                    <ArrowRight size={18} className="text-blue-400 shrink-0 mt-0.5" />
                                    <div>
                                        <p className="text-[10px] font-bold text-blue-400 uppercase tracking-wider mb-1">Paragraph Flow</p>
                                        <p className="text-xs text-blue-200/80 leading-relaxed">{result.follow_up}</p>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
