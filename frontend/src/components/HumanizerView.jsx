import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Wand2, Upload, FileText, Loader2, Trash2, Copy, Check, ChevronDown, ChevronUp, Sparkles, ArrowRight, BookOpen, AlertCircle, Zap } from 'lucide-react';

export default function HumanizerView() {
    const [documents, setDocuments] = useState([]);
    const [stats, setStats] = useState({ total_documents: 0, total_sentences: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [inputText, setInputText] = useState('');
    const [processing, setProcessing] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [copied, setCopied] = useState(false);
    const [expandedSentences, setExpandedSentences] = useState({});
    const fileInputRef = useRef(null);

    useEffect(() => {
        fetchDocuments();
        fetchStats();
    }, []);

    const fetchDocuments = async () => {
        try {
            const res = await fetch('/api/humanizer/documents');
            if (res.ok) {
                const data = await res.json();
                setDocuments(data.documents || []);
            }
        } catch { /* silent */ }
    };

    const fetchStats = async () => {
        try {
            const res = await fetch('/api/humanizer/stats');
            if (res.ok) {
                const data = await res.json();
                setStats(data);
            }
        } catch { /* silent */ }
    };

    const handleUpload = useCallback(async (files) => {
        if (!files || files.length === 0) return;
        const pdfs = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfs.length === 0) return;

        setUploading(true);
        setError(null);
        try {
            const formData = new FormData();
            pdfs.forEach(f => formData.append('files', f));
            const res = await fetch('/api/humanizer/upload', { method: 'POST', body: formData });
            if (!res.ok) throw new Error('Upload failed');
            await fetchDocuments();
            await fetchStats();
        } catch (err) {
            setError('Failed to upload and index documents.');
            console.error('Upload error:', err);
        } finally {
            setUploading(false);
        }
    }, []);

    const handleDelete = async (docId) => {
        try {
            const res = await fetch(`/api/humanizer/document/${docId}`, { method: 'DELETE' });
            if (res.ok) {
                setDocuments(prev => prev.filter(d => d.doc_id !== docId));
                await fetchStats();
            }
        } catch { /* silent */ }
    };

    const handleHumanize = async () => {
        if (!inputText.trim()) return;
        setProcessing(true);
        setResult(null);
        setError(null);
        try {
            const res = await fetch('/api/humanizer/humanize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: inputText.trim() }),
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Humanization failed');
            }
            const data = await res.json();
            setResult(data);
        } catch (err) {
            setError(err.message || 'Failed to humanize text.');
        } finally {
            setProcessing(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            handleHumanize();
        }
    };

    const copyResult = () => {
        if (!result?.humanized_text) return;
        navigator.clipboard.writeText(result.humanized_text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    const toggleSentence = (idx) => {
        setExpandedSentences(prev => ({ ...prev, [idx]: !prev[idx] }));
    };

    const onDrop = useCallback((e) => { e.preventDefault(); setIsDragging(false); handleUpload(e.dataTransfer?.files); }, [handleUpload]);
    const onDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
    const onDragLeave = () => setIsDragging(false);

    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">AI Humanizer</h1>
                <p className="text-sm text-neutral-500">Transform AI-generated text by mapping it onto real human sentence structures from your PDFs.</p>
            </header>

            <div className="flex gap-3 flex-1 min-h-0 min-w-0 w-full">
                {/* Left Panel — Human Library */}
                <div className="glass-card flex flex-col overflow-hidden w-[320px] shrink-0 self-start border-l-4 border-l-purple-500/50 max-w-[35vw]">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <BookOpen size={16} className="text-purple-400" />
                            <h3 className="text-sm font-bold text-white">Human Library</h3>
                        </div>
                        {stats.total_sentences > 0 && (
                            <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full border border-purple-500/20">
                                {stats.total_sentences.toLocaleString()} sentences
                            </span>
                        )}
                    </div>

                    <div className="p-4 flex flex-col">
                        <p className="text-xs text-neutral-600 mb-3 bg-white/3 p-2.5 rounded-lg border border-white/5">
                            Upload <strong className="text-neutral-400">PDF</strong> files written by real humans (textbooks, papers, articles). Their sentence structures will be used as templates.
                        </p>

                        {/* Drop Zone */}
                        <div
                            onDrop={onDrop}
                            onDragOver={onDragOver}
                            onDragLeave={onDragLeave}
                            onClick={() => fileInputRef.current?.click()}
                            className={`h-[140px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging
                                ? 'border-purple-400 bg-purple-500/10 scale-[1.02]'
                                : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
                                }`}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".pdf"
                                multiple
                                className="hidden"
                                onChange={(e) => { handleUpload(e.target.files); e.target.value = ''; }}
                            />
                            {uploading ? (
                                <div className="flex flex-col items-center gap-2">
                                    <Loader2 size={24} className="text-purple-400 animate-spin" />
                                    <p className="text-sm text-purple-400 font-medium">Indexing sentences...</p>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-3">
                                    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-all duration-300 ${isDragging ? 'bg-purple-500/20 border border-purple-400/30 scale-110' : 'bg-white/5 border border-white/10'}`}>
                                        <Upload size={20} className={isDragging ? 'text-purple-400' : 'text-neutral-600'} />
                                    </div>
                                    <div className="text-center">
                                        <p className="text-sm text-neutral-400 font-medium">
                                            {isDragging ? 'Drop files here' : 'Drag & drop PDFs'}
                                        </p>
                                        <p className="text-xs text-neutral-600 mt-1">or click to browse</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Document List */}
                        {documents.length > 0 && (
                            <div className="mt-3 space-y-1 max-h-[280px] overflow-y-auto">
                                {documents.map(doc => (
                                    <div key={doc.doc_id} className="flex items-center gap-2 text-xs px-3 py-2 bg-white/[0.03] rounded-lg border border-white/5 group">
                                        <FileText size={12} className="text-purple-400 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-neutral-300 truncate">{doc.filename}</p>
                                            <p className="text-[10px] text-neutral-600">{doc.sentence_count} sentences indexed</p>
                                        </div>
                                        <button
                                            onClick={() => handleDelete(doc.doc_id)}
                                            className="text-neutral-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                                        >
                                            <Trash2 size={12} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {documents.length === 0 && !uploading && (
                            <div className="mt-4 text-center py-6">
                                <BookOpen size={28} className="text-neutral-700 mx-auto mb-2" />
                                <p className="text-xs text-neutral-600">No documents yet</p>
                                <p className="text-[10px] text-neutral-700 mt-1">Upload human-written PDFs to get started</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right Panel — Input & Output */}
                <div className="flex-1 flex flex-col min-w-0 gap-3 min-h-0 overflow-y-auto">
                    {/* Input Card */}
                    <div className="glass-card p-5 shrink-0">
                        <div className="flex items-center gap-2 mb-3">
                            <Zap size={16} className="text-amber-400" />
                            <h3 className="text-sm font-bold text-white">AI Text Input</h3>
                        </div>
                        <textarea
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder={"Paste AI-generated text here...\n\nThe pipeline will decompose each sentence, find matching human structures from your library, and reconstruct the text using real human phrasing.\n\nPress Ctrl+Enter to humanize."}
                            className="w-full bg-white/[0.02] border border-white/8 rounded-xl p-4 text-sm text-neutral-200 leading-relaxed resize-none outline-none focus:border-white/20 focus:ring-1 focus:ring-white/10 transition-colors placeholder-neutral-700 h-[140px]"
                            spellCheck="false"
                        />
                        <div className="flex items-center justify-between mt-3">
                            <div className="flex items-center gap-2">
                                {stats.total_sentences === 0 && (
                                    <p className="text-[10px] text-amber-400/70 flex items-center gap-1">
                                        <AlertCircle size={10} />
                                        Upload human PDFs first to enable humanization.
                                    </p>
                                )}
                            </div>
                            <button
                                onClick={handleHumanize}
                                disabled={processing || !inputText.trim() || stats.total_sentences === 0}
                                className="btn-accent px-6 rounded-xl text-sm font-semibold flex items-center gap-2"
                            >
                                {processing ? (
                                    <><Loader2 size={16} className="animate-spin" /> Processing...</>
                                ) : (
                                    <><Wand2 size={16} /> Humanize</>
                                )}
                            </button>
                        </div>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="glass-card p-4 border-l-4 border-l-red-500/50 shrink-0">
                            <div className="flex items-center gap-2">
                                <AlertCircle size={16} className="text-red-400" />
                                <p className="text-sm text-red-300">{error}</p>
                            </div>
                        </div>
                    )}

                    {/* Processing State */}
                    {processing && (
                        <div className="glass-card p-8 flex flex-col items-center justify-center gap-4 shrink-0">
                            <div className="relative">
                                <div className="w-16 h-16 rounded-full border-2 border-purple-500/20 flex items-center justify-center">
                                    <Wand2 size={24} className="text-purple-400 animate-pulse" />
                                </div>
                                <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-purple-400 animate-spin" />
                            </div>
                            <div className="text-center">
                                <p className="text-sm font-semibold text-white mb-1">Style Transfer in Progress</p>
                                <p className="text-xs text-neutral-500">Deconstructing → Retrieving → Reconstructing → Polishing</p>
                            </div>
                        </div>
                    )}

                    {/* Result */}
                    {result && !processing && (
                        <div className="flex flex-col gap-3">
                            {/* Summary Stats */}
                            <div className="glass-card p-4 flex items-center justify-between shrink-0">
                                <div className="flex items-center gap-4">
                                    <div className="flex items-center gap-2">
                                        <Sparkles size={16} className="text-green-400" />
                                        <span className="text-sm font-bold text-white">Humanized Output</span>
                                    </div>
                                    <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-wider">
                                        <span className="text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full border border-green-500/20">
                                            {result.stats.humanized_count} transformed
                                        </span>
                                        {result.stats.skipped_count > 0 && (
                                            <span className="text-neutral-500 bg-white/5 px-2 py-0.5 rounded-full">
                                                {result.stats.skipped_count} skipped
                                            </span>
                                        )}
                                    </div>
                                </div>
                                <button
                                    onClick={copyResult}
                                    className="p-2 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all active:scale-90 flex items-center gap-1.5"
                                >
                                    {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                                    <span className="text-[10px] font-bold uppercase tracking-wider">
                                        {copied ? 'Copied!' : 'Copy All'}
                                    </span>
                                </button>
                            </div>

                            {/* Full Humanized Text */}
                            <div className="glass-card p-5 border-l-4 border-l-green-500/50 shrink-0">
                                <p className="text-sm text-neutral-200 leading-relaxed whitespace-pre-wrap">
                                    {result.humanized_text}
                                </p>
                            </div>

                            {/* Per-Sentence Breakdown */}
                            <div className="space-y-2">
                                <p className="text-[10px] font-bold text-neutral-600 uppercase tracking-wider px-1">
                                    Sentence-by-Sentence Breakdown
                                </p>
                                {result.sentences.map((sent, idx) => (
                                    <div key={idx} className="glass-card overflow-hidden">
                                        {/* Sentence Header */}
                                        <button
                                            onClick={() => toggleSentence(idx)}
                                            className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
                                        >
                                            <div className="flex items-center gap-3 min-w-0 flex-1">
                                                <span className="text-[10px] font-bold text-neutral-600 shrink-0">#{idx + 1}</span>
                                                {sent.skipped ? (
                                                    <span className="badge text-neutral-500 bg-white/5 border border-white/10">Skipped</span>
                                                ) : (
                                                    <span className="badge text-green-400 bg-green-500/10 border border-green-500/20">Transformed</span>
                                                )}
                                                <p className="text-xs text-neutral-400 truncate">{sent.humanized}</p>
                                            </div>
                                            {!sent.skipped && (
                                                expandedSentences[idx]
                                                    ? <ChevronUp size={14} className="text-neutral-600 shrink-0" />
                                                    : <ChevronDown size={14} className="text-neutral-600 shrink-0" />
                                            )}
                                        </button>

                                        {/* Expanded Details */}
                                        {expandedSentences[idx] && !sent.skipped && sent.steps && (
                                            <div className="px-4 pb-4 space-y-3 border-t border-white/5">
                                                {/* Step 1: Deconstruct */}
                                                {sent.steps.deconstruct && (
                                                    <div className="mt-3">
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 text-[10px] font-bold flex items-center justify-center">1</span>
                                                            <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">Deconstruct</span>
                                                        </div>
                                                        <div className="bg-white/[0.02] rounded-lg p-3 border border-white/5 space-y-2">
                                                            <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider">Original</p>
                                                            <p className="text-xs text-neutral-400 font-mono">{sent.original}</p>
                                                            <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider mt-2">Masked Skeleton</p>
                                                            <p className="text-xs text-blue-300 font-mono">{sent.steps.deconstruct.masked}</p>
                                                            <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider mt-2">Extracted Variables</p>
                                                            <div className="flex flex-wrap gap-1.5">
                                                                {Object.entries(sent.steps.deconstruct.variables).map(([key, val]) => (
                                                                    <span key={key} className="text-[10px] bg-blue-500/10 text-blue-300 px-2 py-1 rounded-md border border-blue-500/20 font-mono">
                                                                        [{key}] = {val}
                                                                    </span>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Step 2: Retrieve */}
                                                {sent.steps.retrieve && (
                                                    <div>
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="w-5 h-5 rounded-full bg-purple-500/20 text-purple-400 text-[10px] font-bold flex items-center justify-center">2</span>
                                                            <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">Retrieve Human Skeleton</span>
                                                            <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded border border-purple-500/20">
                                                                {(sent.steps.retrieve.similarity * 100).toFixed(1)}% match
                                                            </span>
                                                        </div>
                                                        <div className="bg-white/[0.02] rounded-lg p-3 border border-white/5 space-y-2">
                                                            <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider">Original Human Sentence</p>
                                                            <p className="text-xs text-neutral-400 font-mono italic">{sent.steps.retrieve.original_human}</p>
                                                            <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider mt-2">Human Skeleton</p>
                                                            <p className="text-xs text-purple-300 font-mono">{sent.steps.retrieve.human_skeleton}</p>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Step 3: Reconstruct */}
                                                {sent.steps.reconstruct && (
                                                    <div>
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 text-[10px] font-bold flex items-center justify-center">3</span>
                                                            <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">Reconstruct</span>
                                                        </div>
                                                        <div className="bg-white/[0.02] rounded-lg p-3 border border-white/5">
                                                            <p className="text-xs text-amber-300 font-mono">{sent.steps.reconstruct.raw_output}</p>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Step 4: Polish */}
                                                {sent.steps.polish && (
                                                    <div>
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="w-5 h-5 rounded-full bg-green-500/20 text-green-400 text-[10px] font-bold flex items-center justify-center">4</span>
                                                            <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">Polish (Final)</span>
                                                        </div>
                                                        <div className="bg-white/[0.02] rounded-lg p-3 border border-white/5 border-l-2 border-l-green-500/40">
                                                            <p className="text-xs text-green-300 font-mono">{sent.steps.polish.final_output}</p>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Before → After */}
                                                <div className="flex items-center gap-3 mt-2 pt-3 border-t border-white/5">
                                                    <div className="flex-1 bg-red-500/5 rounded-lg p-2.5 border border-red-500/10">
                                                        <p className="text-[10px] text-red-400 font-bold uppercase tracking-wider mb-1">Before (AI)</p>
                                                        <p className="text-xs text-neutral-400">{sent.original}</p>
                                                    </div>
                                                    <ArrowRight size={16} className="text-neutral-600 shrink-0" />
                                                    <div className="flex-1 bg-green-500/5 rounded-lg p-2.5 border border-green-500/10">
                                                        <p className="text-[10px] text-green-400 font-bold uppercase tracking-wider mb-1">After (Human)</p>
                                                        <p className="text-xs text-neutral-200">{sent.humanized}</p>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Empty State */}
                    {!result && !processing && !error && (
                        <div className="flex-1 flex flex-col items-center justify-center text-neutral-700 space-y-3 py-12">
                            <Wand2 size={40} />
                            <p className="text-sm font-medium">Humanized output will appear here</p>
                            <p className="text-xs text-neutral-700 max-w-md text-center">
                                The 4-step pipeline: Deconstruct AI text → Find matching human structures → Reconstruct with human phrasing → Polish grammar
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
