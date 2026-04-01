import React, { useState, useRef, useCallback } from 'react';
import { GitCompareArrows, Upload, FileText, Loader2, AlertCircle, CheckCircle2, XCircle, ChevronRight, Trash2, FileSearch, BookOpen, FileX, X } from 'lucide-react';

const STAGE_ICONS = {
    parsing: FileSearch,
    splitting: BookOpen,
    parsing_refs: FileText,
    extracting_pdfs: FileSearch,
    matching: GitCompareArrows,
    complete: CheckCircle2,
    error: AlertCircle,
};

export default function MatcherView() {
    // ─── State ───
    const [refMode, setRefMode] = useState('paste');       // 'paste' | 'upload'
    const [refText, setRefText] = useState('');
    const [refFile, setRefFile] = useState(null);
    const [pdfFiles, setPdfFiles] = useState([]);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState('');
    const [progressStage, setProgressStage] = useState('');
    const [progressMessage, setProgressMessage] = useState('');
    const [progressLog, setProgressLog] = useState([]);
    const [isDragging, setIsDragging] = useState(false);
    const [expandedMatches, setExpandedMatches] = useState({});

    const pdfInputRef = useRef(null);
    const refFileInputRef = useRef(null);

    // ─── PDF file handling ───
    const addPdfFiles = useCallback((files) => {
        const valid = Array.from(files).filter(f =>
            ['pdf', 'docx', 'doc'].includes(f.name.split('.').pop().toLowerCase())
        );
        if (valid.length === 0) return;
        setPdfFiles(prev => {
            const existingNames = new Set(prev.map(f => f.name));
            const unique = valid.filter(f => !existingNames.has(f.name));
            return [...prev, ...unique];
        });
    }, []);

    const removePdf = useCallback((idx) => {
        setPdfFiles(prev => prev.filter((_, i) => i !== idx));
    }, []);

    const onDrop = useCallback((e) => {
        e.preventDefault(); setIsDragging(false);
        addPdfFiles(e.dataTransfer?.files);
    }, [addPdfFiles]);

    const toggleMatchDetail = useCallback((idx) => {
        setExpandedMatches(prev => ({ ...prev, [idx]: !prev[idx] }));
    }, []);

    // ─── Run matching ───
    const runMatch = useCallback(async () => {
        if (pdfFiles.length === 0) { setError('Please upload at least one PDF.'); return; }
        if (refMode === 'paste' && !refText.trim()) { setError('Please paste your reference list.'); return; }
        if (refMode === 'upload' && !refFile) { setError('Please upload a reference list file.'); return; }

        setLoading(true); setResults(null); setError('');
        setProgressStage(''); setProgressMessage(''); setProgressLog([]);

        const formData = new FormData();
        if (refMode === 'paste') {
            formData.append('reference_text', refText);
        } else {
            formData.append('reference_file', refFile);
        }
        pdfFiles.forEach(f => formData.append('pdf_files', f));

        try {
            const res = await fetch('/api/match-references', { method: 'POST', body: formData });
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const event = JSON.parse(line.slice(6));
                            setProgressStage(event.stage);
                            setProgressMessage(event.message);
                            setProgressLog(prev => [...prev, { stage: event.stage, message: event.message }]);

                            if (event.stage === 'complete' && event.data) {
                                setResults(event.data);
                                setLoading(false);
                            } else if (event.stage === 'error') {
                                setError(event.message);
                                setLoading(false);
                            }
                        } catch { /* skip malformed */ }
                    }
                }
            }
        } catch (err) {
            setError(err.message || 'Connection failed.');
            setLoading(false);
        }
    }, [refMode, refText, refFile, pdfFiles]);

    const reset = () => {
        setResults(null); setError(''); setRefText(''); setRefFile(null);
        setPdfFiles([]); setProgressLog([]); setExpandedMatches({});
    };

    // ─── Derived ───
    const canRun = pdfFiles.length > 0 && (refMode === 'paste' ? refText.trim().length > 0 : !!refFile);
    const matchCount = results?.matched?.length || 0;
    const missingCount = results?.missing?.length || 0;

    // ─── Render ───
    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">Reference Matcher</h1>
                <p className="text-sm text-neutral-500">Upload your reference list and PDFs to find which sources you have and which are missing.</p>
            </header>

            {/* ─── Input Phase ─── */}
            {!results && !loading && (
                <div className="flex gap-3 flex-1 min-h-0 overflow-hidden">

                    {/* ── Left: Reference List Input ── */}
                    <div className="glass-card flex flex-col overflow-hidden w-[400px] shrink-0 self-start border-l-4 border-l-purple-500/50 max-w-[45vw]">
                        <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <BookOpen size={16} className="text-neutral-400" />
                                <h3 className="text-sm font-bold text-white">Reference List</h3>
                            </div>
                            <div className="flex items-center gap-1 bg-white/5 rounded-lg p-0.5">
                                <button
                                    onClick={() => setRefMode('paste')}
                                    className={`text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-md transition-all ${refMode === 'paste' ? 'bg-white/10 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
                                >Paste</button>
                                <button
                                    onClick={() => setRefMode('upload')}
                                    className={`text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-md transition-all ${refMode === 'upload' ? 'bg-white/10 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
                                >Upload</button>
                            </div>
                        </div>

                        <div className="p-4 flex flex-col gap-3">
                            <p className="text-xs text-neutral-600 bg-white/3 p-2.5 rounded-lg border border-white/5">
                                {refMode === 'paste'
                                    ? <>Paste your <strong className="text-neutral-400">full reference list</strong> below. Supports numbered, bulleted, or paragraph-separated formats.</>
                                    : <>Upload a <strong className="text-neutral-400">DOCX</strong>, <strong className="text-neutral-400">PDF</strong>, or <strong className="text-neutral-400">TXT</strong> file containing your reference list.</>
                                }
                            </p>

                            {refMode === 'paste' ? (
                                <textarea
                                    value={refText}
                                    onChange={e => setRefText(e.target.value)}
                                    placeholder={"1. Smith, J. (2020). Example article title. Journal Name, 10(2), 45-60.\n2. Jones, A. & Brown, B. (2019). Another reference. Publisher.\n..."}
                                    className="w-full h-[260px] bg-white/[0.03] border border-white/8 rounded-xl p-3 text-sm text-neutral-300 placeholder-neutral-700 resize-none outline-none focus:border-white/15 transition-colors font-mono leading-relaxed"
                                />
                            ) : (
                                <div className="flex flex-col items-center gap-3">
                                    {refFile ? (
                                        <div className="w-full bg-white/3 border border-white/5 rounded-xl p-4 flex items-center gap-3">
                                            <FileText size={20} className="text-neutral-400 shrink-0" />
                                            <span className="truncate flex-1 text-sm font-medium text-neutral-200">{refFile.name}</span>
                                            <button onClick={() => setRefFile(null)} className="p-1.5 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-red-400 transition-colors">
                                                <XCircle size={18} />
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            onClick={() => refFileInputRef.current?.click()}
                                            className="w-full h-[120px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04] cursor-pointer transition-all"
                                        >
                                            <Upload size={24} className="text-neutral-600 mb-2" />
                                            <span className="text-sm text-neutral-500">Click to upload reference file</span>
                                            <span className="text-xs text-neutral-700 mt-1">PDF, DOCX, DOC, or TXT</span>
                                        </button>
                                    )}
                                    <input
                                        ref={refFileInputRef}
                                        type="file"
                                        accept=".pdf,.docx,.doc,.txt"
                                        className="hidden"
                                        onChange={e => { if (e.target.files?.[0]) setRefFile(e.target.files[0]); e.target.value = ''; }}
                                    />
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── Right: PDF Upload + Action ── */}
                    <div className="flex-1 flex flex-col min-w-0 gap-3 self-start">
                        <div className="glass-card flex flex-col overflow-hidden border-l-4 border-l-sky-500/50">
                            <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <FileSearch size={16} className="text-neutral-400" />
                                    <h3 className="text-sm font-bold text-white">Source PDFs</h3>
                                    {pdfFiles.length > 0 && <span className="text-[10px] font-bold text-neutral-500 bg-white/5 px-2 py-0.5 rounded-full">{pdfFiles.length}</span>}
                                </div>
                                {pdfFiles.length > 0 && (
                                    <button
                                        onClick={() => setPdfFiles([])}
                                        className="text-[10px] text-neutral-600 hover:text-red-400 flex items-center gap-1 transition-colors"
                                    >
                                        <Trash2 size={10} /> Clear all
                                    </button>
                                )}
                            </div>

                            <div className="p-4 flex flex-col gap-3">
                                <p className="text-xs text-neutral-600 bg-white/3 p-2.5 rounded-lg border border-white/5">
                                    Upload the <strong className="text-neutral-400">PDF source files</strong> you have. The system will match them against your reference list.
                                </p>

                                {/* Drop zone */}
                                <div
                                    onDrop={onDrop}
                                    onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                                    onDragLeave={() => setIsDragging(false)}
                                    onClick={() => pdfInputRef.current?.click()}
                                    className={`h-[160px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging
                                        ? 'border-sky-400 bg-sky-500/10 scale-[1.01]'
                                        : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
                                        }`}
                                >
                                    <input
                                        ref={pdfInputRef}
                                        type="file"
                                        accept=".pdf,.docx,.doc"
                                        multiple
                                        className="hidden"
                                        onChange={e => { addPdfFiles(e.target.files); e.target.value = ''; }}
                                    />
                                    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-3 transition-all ${isDragging ? 'bg-sky-500/20 border border-sky-400/30 scale-110' : 'bg-white/5 border border-white/10'}`}>
                                        <Upload size={22} className={isDragging ? 'text-sky-400' : 'text-neutral-600'} />
                                    </div>
                                    <p className="text-sm text-neutral-400 font-medium">{isDragging ? 'Drop PDFs here' : 'Drag & drop PDF files'}</p>
                                    <p className="text-xs text-neutral-600 mt-1">or click to browse</p>
                                </div>

                                {/* File list */}
                                {pdfFiles.length > 0 && (
                                    <div className="space-y-1 max-h-[200px] overflow-y-auto">
                                        {pdfFiles.map((f, i) => (
                                            <div key={i} className="flex items-center gap-2 text-xs px-3 py-1.5 bg-white/[0.03] rounded-lg border border-white/5">
                                                <FileText size={12} className="text-sky-400 shrink-0" />
                                                <span className="truncate flex-1 text-neutral-400">{f.name}</span>
                                                <span className="text-neutral-700 text-[10px]">{(f.size / 1024).toFixed(0)} KB</span>
                                                <button onClick={() => removePdf(i)} className="text-neutral-600 hover:text-red-400 transition-colors">
                                                    <X size={12} />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Match button */}
                        <button
                            onClick={runMatch}
                            disabled={!canRun}
                            className="btn-accent w-full py-3.5 text-base rounded-xl flex items-center justify-center gap-2"
                        >
                            <GitCompareArrows size={20} />
                            Match References to PDFs
                        </button>

                        {error && (
                            <div className="flex items-center gap-3 bg-red-500/10 text-red-300 px-5 py-3.5 rounded-xl border border-red-500/20">
                                <AlertCircle size={18} className="text-red-400 shrink-0" />
                                <p className="text-sm font-medium">{error}</p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ─── Progress Phase ─── */}
            {loading && (() => {
                const STAGE_ORDER = { parsing: 1, splitting: 2, parsing_refs: 3, extracting_pdfs: 4, matching: 5, complete: 6 };
                const currentStep = STAGE_ORDER[progressStage] || 0;
                const totalSteps = 5;
                const STAGE_LABELS = {
                    parsing: 'Parsing Reference List',
                    splitting: 'Splitting References',
                    parsing_refs: 'Parsing Reference Metadata',
                    extracting_pdfs: 'Extracting PDF Metadata',
                    matching: 'Running Matcher',
                };
                const Icon = STAGE_ICONS[progressStage] || Loader2;

                return (
                    <div className="glass-card flex flex-col items-center justify-center p-8 animate-fade-in-up flex-1 min-h-0">
                        {/* Progress Bar */}
                        <div className="w-full max-w-md mb-8">
                            <div className="flex justify-between mb-2">
                                <span className="text-xs font-semibold text-neutral-400">Progress</span>
                                <span className="text-xs font-semibold text-white">Step {Math.min(currentStep, totalSteps)} of {totalSteps}</span>
                            </div>
                            <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-gradient-to-r from-white/40 to-white/70 rounded-full transition-all duration-700 ease-out"
                                    style={{ width: `${(currentStep / totalSteps) * 100}%` }}
                                />
                            </div>
                        </div>

                        {/* Current Stage Icon */}
                        <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-5">
                            <Icon size={32} className={`text-white ${['parsing_refs', 'extracting_pdfs'].includes(progressStage) ? 'animate-spin' : ''}`} />
                        </div>

                        <h3 className="text-xl font-bold text-white mb-2">
                            {STAGE_LABELS[progressStage] || 'Initializing…'}
                        </h3>
                        <p className="text-sm text-neutral-400 mb-8 text-center max-w-md">{progressMessage}</p>

                        {/* Activity Log — constrained + scrollable */}
                        <div className="w-full max-w-md max-h-[180px] overflow-y-auto space-y-2 scrollbar-thin">
                            {progressLog.map((entry, i) => {
                                const EntryIcon = STAGE_ICONS[entry.stage] || Loader2;
                                const isLatest = i === progressLog.length - 1;
                                return (
                                    <div key={i} className={`flex items-center gap-3 text-xs py-1.5 transition-opacity ${isLatest ? 'text-white opacity-100' : 'text-neutral-600 opacity-60'}`}>
                                        <EntryIcon size={14} className={isLatest ? 'text-white' : 'text-neutral-600'} />
                                        <span className="font-medium truncate">{entry.message}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                );
            })()}

            {/* ─── Results Phase ─── */}
            {results && !loading && (
                <div className="space-y-3 animate-fade-in-up overflow-y-auto flex-1 min-h-0">
                    {/* Header */}
                    <div className="glass-card-static flex items-center justify-between px-5 py-3 sticky top-0 z-20">
                        <div className="flex items-center gap-3">
                            <GitCompareArrows size={20} className="text-white" />
                            <h2 className="text-base font-bold text-white">Matching Results</h2>
                        </div>
                        <button onClick={reset} className="text-xs font-semibold text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-lg transition-colors">
                            New Match
                        </button>
                    </div>

                    {/* Stats */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {[
                            { label: 'References', value: results.total_references || 0, border: 'border-l-white/20' },
                            { label: 'PDFs Uploaded', value: results.total_pdfs || 0, border: 'border-l-sky-500/50' },
                            { label: 'Matched', value: matchCount, border: 'border-l-emerald-500/50' },
                            { label: 'Missing', value: missingCount, border: 'border-l-red-500/50' },
                        ].map((stat, i) => (
                            <div key={i} className={`glass-card p-5 border-l-4 ${stat.border}`}>
                                <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 mb-2">{stat.label}</div>
                                <div className="text-4xl font-extrabold text-white">{stat.value}</div>
                            </div>
                        ))}
                    </div>

                    {/* Matched + Missing panels */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        {/* ── Matched ── */}
                        <div className="glass-card overflow-hidden">
                            <div className="bg-white/3 border-b border-white/5 px-5 py-3 flex items-center gap-2">
                                <CheckCircle2 size={16} className="text-emerald-400" />
                                <h3 className="text-sm font-bold text-emerald-200">Matched ({matchCount})</h3>
                            </div>
                            <div className="p-4 max-h-[500px] overflow-y-auto space-y-2">
                                {matchCount === 0 ? (
                                    <div className="text-xs text-neutral-500 text-center py-6">No matches found.</div>
                                ) : results.matched.map((m, i) => (
                                    <div key={i} className="bg-white/[0.02] rounded-xl border border-white/5 border-l-4 border-l-emerald-500/40 overflow-hidden">
                                        <button
                                            onClick={() => toggleMatchDetail(i)}
                                            className="w-full flex items-center gap-3 p-3 text-left hover:bg-white/[0.02] transition-colors"
                                        >
                                            <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <div className="text-xs text-neutral-300 truncate leading-relaxed">{m.ref_text}</div>
                                            </div>
                                            <div className="flex items-center gap-2 shrink-0">
                                                <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                                                    {Math.round(m.confidence * 100)}%
                                                </span>
                                                <ChevronRight size={12} className={`text-neutral-600 transition-transform duration-200 ${expandedMatches[i] ? 'rotate-90' : ''}`} />
                                            </div>
                                        </button>

                                        {expandedMatches[i] && (
                                            <div className="px-3 pb-3 space-y-2 animate-fade-in-up">
                                                <div className="bg-emerald-500/5 border border-emerald-500/15 rounded-lg px-3 py-2">
                                                    <div className="text-[9px] font-bold uppercase tracking-widest text-emerald-400/70 mb-1">Matched PDF</div>
                                                    <div className="text-sm text-emerald-300 font-medium flex items-center gap-2">
                                                        <FileText size={14} className="shrink-0" />
                                                        {m.pdf_filename}
                                                    </div>
                                                </div>
                                                <div className="bg-white/[0.03] border border-white/5 rounded-lg px-3 py-2">
                                                    <div className="text-[9px] font-bold uppercase tracking-widest text-neutral-600 mb-1">Match Reason</div>
                                                    <div className="text-xs text-neutral-400">{m.match_reason}</div>
                                                </div>
                                                <div className="bg-white/[0.03] border border-white/5 rounded-lg px-3 py-2">
                                                    <div className="text-[9px] font-bold uppercase tracking-widest text-neutral-600 mb-1">Full Reference</div>
                                                    <div className="text-xs text-neutral-300 leading-relaxed">{m.ref_text}</div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* ── Missing ── */}
                        <div className="glass-card overflow-hidden border border-red-500/15">
                            <div className="bg-red-500/5 border-b border-red-500/10 px-5 py-3 flex items-center gap-2">
                                <FileX size={16} className="text-red-400" />
                                <h3 className="text-sm font-bold text-red-200">Missing PDFs ({missingCount})</h3>
                            </div>
                            <div className="p-4 max-h-[500px] overflow-y-auto space-y-2">
                                {missingCount === 0 ? (
                                    <div className="text-xs text-emerald-500 text-center py-6 flex flex-col items-center gap-2">
                                        <CheckCircle2 size={20} />
                                        <span>All references have matching PDFs!</span>
                                    </div>
                                ) : results.missing.map((m, i) => (
                                    <div key={i} className="bg-white/[0.02] p-3 rounded-xl border border-red-500/15 border-l-4 border-l-red-500/40">
                                        <div className="flex items-start gap-2">
                                            <AlertCircle size={14} className="text-red-400 shrink-0 mt-0.5" />
                                            <div className="flex-1 min-w-0">
                                                <div className="text-xs text-red-200 leading-relaxed mb-1.5">{m.ref_text}</div>
                                                {m.best_candidate && m.best_score > 0.2 && (
                                                    <div className="text-[10px] text-neutral-600 bg-white/3 border border-white/5 rounded px-2 py-1">
                                                        Closest match: <span className="text-neutral-400">{m.best_candidate}</span>
                                                        <span className="ml-1 text-amber-500/70">({Math.round(m.best_score * 100)}% — too low)</span>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
