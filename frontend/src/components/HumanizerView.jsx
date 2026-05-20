import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Wand2, Upload, FileText, Loader2, Trash2, Copy, Check, ChevronDown, ChevronUp, Sparkles, ArrowRight, BookOpen, AlertCircle, Zap, Brain, Shield, ShieldAlert } from 'lucide-react';

export default function HumanizerView() {
    const [documents, setDocuments] = useState([]);
    const [stats, setStats] = useState({ total_documents: 0, total_skeletons: 0, total_sentences: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [inputText, setInputText] = useState('');
    const [processing, setProcessing] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [copied, setCopied] = useState(false);
    const [expandedSentences, setExpandedSentences] = useState({});
    const [selectedRewrites, setSelectedRewrites] = useState({});
    const fileInputRef = useRef(null);

    useEffect(() => { fetchDocuments(); fetchStats(); }, []);

    const fetchDocuments = async () => {
        try {
            const res = await fetch('/api/humanizer/documents');
            if (res.ok) { const d = await res.json(); setDocuments(d.documents || []); }
        } catch { }
    };

    const fetchStats = async () => {
        try {
            const res = await fetch('/api/humanizer/stats');
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
            const res = await fetch('/api/humanizer/upload', { method: 'POST', body: formData });
            if (!res.ok) throw new Error('Upload failed');
            await fetchDocuments(); await fetchStats();
        } catch (err) { setError('Failed to upload and mine documents.'); }
        finally { setUploading(false); }
    }, []);

    const handleDelete = async (docId) => {
        try {
            const res = await fetch(`/api/humanizer/document/${docId}`, { method: 'DELETE' });
            if (res.ok) { setDocuments(prev => prev.filter(d => d.doc_id !== docId)); await fetchStats(); }
        } catch { }
    };

    const handleHumanize = async () => {
        if (!inputText.trim()) return;
        setProcessing(true); setResult(null); setError(null); setSelectedRewrites({});
        try {
            const res = await fetch('/api/humanizer/humanize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: inputText.trim() }),
            });
            if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
            setResult(await res.json());
        } catch (err) { setError(err.message || 'Failed to humanize text.'); }
        finally { setProcessing(false); }
    };

    const copyResult = () => {
        if (!result?.humanized_text) return;
        navigator.clipboard.writeText(result.humanized_text).then(() => {
            setCopied(true); setTimeout(() => setCopied(false), 2000);
        });
    };

    const skeletonCount = stats.total_skeletons || stats.total_sentences || 0;
    const onDrop = useCallback((e) => { e.preventDefault(); setIsDragging(false); handleUpload(e.dataTransfer?.files); }, [handleUpload]);

    const getSelectedRewrite = (sentIdx, rewrites) => {
        const sel = selectedRewrites[sentIdx];
        if (sel !== undefined && rewrites[sel]) return rewrites[sel].text;
        return rewrites[0]?.text || '';
    };

    const buildFinalText = () => {
        if (!result) return '';
        return result.sentences.map((sent, idx) => {
            if (sent.skipped) return sent.original;
            const rewrites = sent.steps?.rewrite?.rewrites || [];
            return getSelectedRewrite(idx, rewrites) || sent.humanized;
        }).join(' ');
    };

    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">Advanced Humanizer</h1>
                <p className="text-sm text-neutral-500">Retrieval-Augmented Style Transfer — imitates real human writing style from your PDFs while preserving the original meaning.</p>
            </header>

            <div className="flex gap-3 flex-1 min-h-0 min-w-0 w-full">
                {/* Left: Style Bank */}
                <div className="glass-card flex flex-col overflow-hidden w-[300px] shrink-0 self-start border-l-4 border-l-purple-500/50 max-w-[33vw]">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <BookOpen size={16} className="text-purple-400" />
                            <h3 className="text-sm font-bold text-white">Style Bank</h3>
                        </div>
                        {skeletonCount > 0 && (
                            <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full border border-purple-500/20">
                                {skeletonCount.toLocaleString()} examples
                            </span>
                        )}
                    </div>
                    <div className="p-4 flex flex-col gap-3">
                        <p className="text-xs text-neutral-600 bg-white/3 p-2.5 rounded-lg border border-white/5">
                            Upload <strong className="text-neutral-400">human-written PDFs</strong>. The system imitates their sentence rhythm, connectors, and vocabulary when rewriting.
                        </p>
                        <div
                            onDrop={onDrop}
                            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                            onDragLeave={() => setIsDragging(false)}
                            onClick={() => fileInputRef.current?.click()}
                            className={`h-[130px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging ? 'border-purple-400 bg-purple-500/10 scale-[1.02]' : 'border-white/10 bg-white/[0.02] hover:border-white/20'}`}
                        >
                            <input ref={fileInputRef} type="file" accept=".pdf" multiple className="hidden" onChange={(e) => { handleUpload(e.target.files); e.target.value = ''; }} />
                            {uploading ? (
                                <div className="flex flex-col items-center gap-2">
                                    <Loader2 size={22} className="text-purple-400 animate-spin" />
                                    <p className="text-sm text-purple-400 font-medium">Mining style examples...</p>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-2">
                                    <Upload size={20} className={isDragging ? 'text-purple-400' : 'text-neutral-600'} />
                                    <p className="text-sm text-neutral-500">{isDragging ? 'Drop here' : 'Drag & drop PDFs'}</p>
                                    <p className="text-xs text-neutral-700">or click to browse</p>
                                </div>
                            )}
                        </div>
                        {documents.length > 0 && (
                            <div className="space-y-1 max-h-[260px] overflow-y-auto">
                                {documents.map(doc => (
                                    <div key={doc.doc_id} className="flex items-center gap-2 text-xs px-3 py-2 bg-white/[0.03] rounded-lg border border-white/5 group">
                                        <FileText size={12} className="text-purple-400 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-neutral-300 truncate">{doc.filename}</p>
                                            <p className="text-[10px] text-neutral-600">{doc.skeleton_count || doc.sentence_count} style examples</p>
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

                {/* Right: Main */}
                <div className="flex-1 flex flex-col min-w-0 gap-3 min-h-0 overflow-y-auto">
                    {/* Input */}
                    <div className="glass-card p-5 shrink-0">
                        <div className="flex items-center gap-2 mb-3">
                            <Zap size={16} className="text-amber-400" />
                            <h3 className="text-sm font-bold text-white">Draft Text Input</h3>
                        </div>
                        <textarea
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); handleHumanize(); } }}
                            placeholder={"Paste draft text here...\n\nCtrl+Enter to humanize."}
                            className="w-full bg-white/[0.02] border border-white/8 rounded-xl p-4 text-sm text-neutral-200 leading-relaxed resize-none outline-none focus:border-white/20 transition-colors placeholder-neutral-700 h-[110px]"
                            spellCheck="false"
                        />
                        <div className="flex items-center justify-between mt-3">
                            <div>
                                {skeletonCount === 0 && <p className="text-[10px] text-amber-400/70 flex items-center gap-1"><AlertCircle size={10} /> Upload human PDFs first.</p>}
                            </div>
                            <button
                                onClick={handleHumanize}
                                disabled={processing || !inputText.trim() || skeletonCount === 0}
                                className="btn-accent px-6 rounded-xl text-sm font-semibold flex items-center gap-2"
                            >
                                {processing ? <><Loader2 size={16} className="animate-spin" /> Processing...</> : <><Wand2 size={16} /> Humanize</>}
                            </button>
                        </div>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="glass-card p-4 border-l-4 border-l-red-500/50 shrink-0">
                            <div className="flex items-center gap-2"><AlertCircle size={16} className="text-red-400" /><p className="text-sm text-red-300">{error}</p></div>
                        </div>
                    )}

                    {/* Processing */}
                    {processing && (
                        <div className="glass-card p-8 flex flex-col items-center gap-4 shrink-0">
                            <div className="relative">
                                <div className="w-16 h-16 rounded-full border-2 border-purple-500/20 flex items-center justify-center">
                                    <Brain size={24} className="text-purple-400 animate-pulse" />
                                </div>
                                <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-purple-400 animate-spin" />
                            </div>
                            <div className="text-center">
                                <p className="text-sm font-semibold text-white mb-1">Style Transfer in Progress</p>
                                <p className="text-xs text-neutral-500">Extract meaning → Retrieve style palette → Generate 3 rewrites</p>
                            </div>
                        </div>
                    )}

                    {/* Result */}
                    {result && !processing && (
                        <div className="flex flex-col gap-3">
                            {/* Stats bar */}
                            <div className="glass-card p-4 flex items-center justify-between shrink-0">
                                <div className="flex items-center gap-3">
                                    <div className="flex items-center gap-2"><Sparkles size={16} className="text-green-400" /><span className="text-sm font-bold text-white">Humanized Output</span></div>
                                    <span className="text-[10px] font-bold text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full border border-green-500/20">{result.stats.humanized_count} transformed</span>
                                    {result.stats.skipped_count > 0 && <span className="text-[10px] font-bold text-neutral-500 bg-white/5 px-2 py-0.5 rounded-full">{result.stats.skipped_count} skipped</span>}
                                </div>
                                <button onClick={copyResult} className="p-2 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all flex items-center gap-1.5">
                                    {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                                    <span className="text-[10px] font-bold uppercase tracking-wider">{copied ? 'Copied!' : 'Copy All'}</span>
                                </button>
                            </div>

                            {/* Final assembled output */}
                            <div className="glass-card p-5 border-l-4 border-l-green-500/50 shrink-0">
                                <p className="text-[10px] font-bold text-green-400 uppercase tracking-wider mb-2">Final Output</p>
                                <p className="text-sm text-neutral-200 leading-relaxed whitespace-pre-wrap">{buildFinalText()}</p>
                            </div>

                            {/* Per-sentence breakdown */}
                            <div className="space-y-2">
                                <p className="text-[10px] font-bold text-neutral-600 uppercase tracking-wider px-1">Sentence-by-Sentence Breakdown</p>
                                {result.sentences.map((sent, idx) => (
                                    <div key={idx} className="glass-card overflow-hidden">
                                        <button
                                            onClick={() => setExpandedSentences(prev => ({ ...prev, [idx]: !prev[idx] }))}
                                            className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
                                        >
                                            <div className="flex items-center gap-3 min-w-0 flex-1">
                                                <span className="text-[10px] font-bold text-neutral-600 shrink-0">#{idx + 1}</span>
                                                {sent.skipped
                                                    ? <span className="badge text-neutral-500 bg-white/5 border border-white/10">Skipped</span>
                                                    : <span className="badge text-green-400 bg-green-500/10 border border-green-500/20">Transformed</span>
                                                }
                                                {sent.steps?.extract?.intent && !sent.skipped && (
                                                    <span className="badge text-purple-400 bg-purple-500/10 border border-purple-500/20 text-[9px]">
                                                        {sent.steps.extract.intent.replace(/_/g, ' ')}
                                                    </span>
                                                )}
                                                <p className="text-xs text-neutral-400 truncate">
                                                    {getSelectedRewrite(idx, sent.steps?.rewrite?.rewrites || []) || sent.humanized}
                                                </p>
                                            </div>
                                            {!sent.skipped && (expandedSentences[idx] ? <ChevronUp size={14} className="text-neutral-600 shrink-0" /> : <ChevronDown size={14} className="text-neutral-600 shrink-0" />)}
                                        </button>

                                        {expandedSentences[idx] && !sent.skipped && sent.steps && (
                                            <div className="px-4 pb-4 space-y-4 border-t border-white/5 mt-0">

                                                {/* Step 1: Extraction */}
                                                {sent.steps.extract && (
                                                    <div className="mt-3">
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 text-[10px] font-bold flex items-center justify-center shrink-0">1</span>
                                                            <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">Semantic Extraction</span>
                                                            <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20">
                                                                {sent.steps.extract.intent?.replace(/_/g, ' ')}
                                                            </span>
                                                        </div>
                                                        <div className="bg-white/[0.02] rounded-lg p-3 border border-white/5 space-y-2">
                                                            <div>
                                                                <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider mb-0.5">Original</p>
                                                                <p className="text-xs text-neutral-400 font-mono">{sent.original}</p>
                                                            </div>
                                                            <div>
                                                                <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider mb-0.5">Core Meaning (oracle)</p>
                                                                <p className="text-xs text-amber-200/80 italic">{sent.steps.extract.core_meaning}</p>
                                                            </div>
                                                            {Object.keys(sent.steps.extract.variables || {}).length > 0 && (
                                                                <div>
                                                                    <p className="text-[10px] text-neutral-600 font-bold uppercase tracking-wider mb-1">Extracted Facts</p>
                                                                    <div className="flex flex-wrap gap-1.5">
                                                                        {Object.entries(sent.steps.extract.variables).map(([k, v]) => (
                                                                            <span key={k} className="text-[10px] bg-blue-500/10 text-blue-300 px-2 py-1 rounded-md border border-blue-500/20 font-mono">{k} = {v}</span>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Step 2: Style palette */}
                                                {sent.steps.retrieve && (
                                                    <div>
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="w-5 h-5 rounded-full bg-purple-500/20 text-purple-400 text-[10px] font-bold flex items-center justify-center shrink-0">2</span>
                                                            <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">Style Palette Retrieved</span>
                                                            <span className="text-[10px] font-bold text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded border border-purple-500/20">
                                                                {sent.steps.retrieve.example_count} human sentences
                                                            </span>
                                                        </div>
                                                        <div className="space-y-1">
                                                            {(sent.steps.retrieve.examples || []).map((ex, ei) => (
                                                                <div key={ei} className="bg-white/[0.02] rounded-md px-3 py-1.5 border border-white/5">
                                                                    <p className="text-xs text-neutral-500 italic">{ex}</p>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Step 3: 3 rewrites to choose from */}
                                                {sent.steps.rewrite && (
                                                    <div>
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="w-5 h-5 rounded-full bg-green-500/20 text-green-400 text-[10px] font-bold flex items-center justify-center shrink-0">3</span>
                                                            <span className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider">3 Style-Guided Rewrites</span>
                                                            <span className="text-[10px] text-neutral-600">click one to select it</span>
                                                        </div>
                                                        <div className="space-y-2">
                                                            {(sent.steps.rewrite.rewrites || []).map((rw, ri) => {
                                                                const selected = (selectedRewrites[idx] ?? 0) === ri;
                                                                return (
                                                                    <button
                                                                        key={ri}
                                                                        onClick={() => setSelectedRewrites(prev => ({ ...prev, [idx]: ri }))}
                                                                        className={`w-full text-left rounded-lg p-3 border transition-all ${selected
                                                                            ? 'border-green-500/40 bg-green-500/[0.05]'
                                                                            : 'border-white/5 bg-white/[0.02] hover:border-white/15'}`}
                                                                    >
                                                                        <div className="flex items-start gap-2">
                                                                            <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
                                                                                {selected
                                                                                    ? <span className="text-[9px] font-bold text-green-400 bg-green-500/10 px-1.5 py-0.5 rounded border border-green-500/20 uppercase">Selected</span>
                                                                                    : <span className="text-[9px] font-bold text-neutral-600 bg-white/5 px-1.5 py-0.5 rounded border border-white/10 uppercase">Option {ri + 1}</span>
                                                                                }
                                                                                {!rw.containment_passed
                                                                                    ? <ShieldAlert size={12} className="text-amber-400" title={rw.warning} />
                                                                                    : <Shield size={12} className="text-green-500/50" />
                                                                                }
                                                                                <span className="text-[9px] text-neutral-700">{(rw.containment_score * 100).toFixed(0)}%</span>
                                                                            </div>
                                                                            <p className={`text-xs leading-relaxed ${selected ? 'text-neutral-200' : 'text-neutral-400'}`}>{rw.text}</p>
                                                                        </div>
                                                                        {!rw.containment_passed && (
                                                                            <p className="text-[9px] text-amber-400/70 mt-1 ml-1">⚠ {rw.warning}</p>
                                                                        )}
                                                                    </button>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Before → After */}
                                                <div className="flex items-center gap-3 pt-3 border-t border-white/5">
                                                    <div className="flex-1 bg-red-500/5 rounded-lg p-2.5 border border-red-500/10">
                                                        <p className="text-[10px] text-red-400 font-bold uppercase tracking-wider mb-1">Before (Draft)</p>
                                                        <p className="text-xs text-neutral-400">{sent.original}</p>
                                                    </div>
                                                    <ArrowRight size={16} className="text-neutral-600 shrink-0" />
                                                    <div className="flex-1 bg-green-500/5 rounded-lg p-2.5 border border-green-500/10">
                                                        <p className="text-[10px] text-green-400 font-bold uppercase tracking-wider mb-1">After (RAST)</p>
                                                        <p className="text-xs text-neutral-200">{getSelectedRewrite(idx, sent.steps?.rewrite?.rewrites || []) || sent.humanized}</p>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Empty state */}
                    {!result && !processing && !error && (
                        <div className="flex-1 flex flex-col items-center justify-center text-neutral-700 space-y-3 py-12">
                            <Wand2 size={40} className="text-neutral-700/50" />
                            <p className="text-sm font-medium">Humanized output will appear here</p>
                            <p className="text-xs text-neutral-700 max-w-md text-center">
                                RAST: Extract meaning → Retrieve 8 real human sentences → Generate 3 style-guided rewrites → Pick the best one
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
