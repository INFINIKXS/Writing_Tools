import React, { useState, useRef } from 'react';
import { UploadCloud, File, AlertCircle, CheckCircle2, XCircle, FileX, BarChart3, Loader2, FileSearch, Brain, ShieldCheck, BookOpen, Copy, ClipboardCheck, ScanSearch, GitCompare } from 'lucide-react';

const STAGE_CONFIG = {
    parsing: { icon: FileSearch, label: 'Parsing Document', step: 1 },
    extracted: { icon: BookOpen, label: 'Text Extracted', step: 2 },
    scanning: { icon: ScanSearch, label: 'Python Regex Scan', step: 3 },
    analyzing: { icon: Brain, label: 'AI Matching', step: 4 },
    processing: { icon: Loader2, label: 'Processing', step: 4 },
    validating: { icon: GitCompare, label: 'Cross-Validation', step: 5 },
    verifying: { icon: ShieldCheck, label: 'String Verification', step: 6 },
    extracting: { icon: BookOpen, label: 'Source Extraction', step: 7 },
    complete: { icon: CheckCircle2, label: 'Complete', step: 8 },
    error: { icon: AlertCircle, label: 'Error', step: 0 },
};

export default function VerifierView() {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState('');
    const [isDragActive, setIsDragActive] = useState(false);
    const [progressStage, setProgressStage] = useState('');
    const [progressMessage, setProgressMessage] = useState('');
    const [progressLog, setProgressLog] = useState([]);
    const fileInputRef = useRef(null);

    const handleDragOver = (e) => { e.preventDefault(); setIsDragActive(true); };
    const handleDragLeave = (e) => { e.preventDefault(); setIsDragActive(false); };
    const handleDrop = (e) => {
        e.preventDefault(); setIsDragActive(false);
        if (e.dataTransfer.files?.[0]) handleFileSelected(e.dataTransfer.files[0]);
    };
    const handleFileChange = (e) => { if (e.target.files?.[0]) handleFileSelected(e.target.files[0]); };
    const handleFileSelected = (f) => {
        if (f.name.toLowerCase().endsWith('.pdf') || f.name.toLowerCase().endsWith('.docx') || f.name.toLowerCase().endsWith('.doc')) { setFile(f); setError(''); }
        else { setError('Please upload a PDF, DOCX, or DOC file.'); setFile(null); }
    };

    const verifyFile = async () => {
        if (!file) return;
        setLoading(true); setResults(null); setError('');
        setProgressStage(''); setProgressMessage(''); setProgressLog([]);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/verify', { method: 'POST', body: formData });

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line in buffer

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
                        } catch (parseErr) { /* skip malformed events */ }
                    }
                }
            }
        } catch (err) {
            setError(err.message || 'Connection failed');
            setLoading(false);
        }
    };

    const currentStep = STAGE_CONFIG[progressStage]?.step || 0;
    const totalSteps = 7;

    const [copiedIdx, setCopiedIdx] = useState(null);
    const sanitizeHtml = (html) => html.replace(/<(?!\/?(?:i|em)\b)[^>]*>/gi, '');
    const copyRichText = (plainText, htmlText, idx) => {
        if (htmlText) {
            const htmlBlob = new Blob([htmlText], { type: 'text/html' });
            const textBlob = new Blob([plainText], { type: 'text/plain' });
            navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })]).then(() => {
                setCopiedIdx(idx);
                setTimeout(() => setCopiedIdx(null), 2000);
            });
        } else {
            navigator.clipboard.writeText(plainText).then(() => {
                setCopiedIdx(idx);
                setTimeout(() => setCopiedIdx(null), 2000);
            });
        }
    };

    return (
        <div className="space-y-4 animate-fade-in-up overflow-y-auto flex-1 min-h-0">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">Citation Verifier</h1>
                <p className="text-sm text-neutral-500">Cross-check inline citations against your reference list using Gemini AI.</p>
            </header>

            {/* Upload Zone */}
            {!results && !loading && (
                <>
                    <div
                        className={`glass-card p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[320px] group
              ${isDragActive ? 'border-white/20 bg-white/[0.06]' : ''}`}
                        onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
                        onClick={() => !file && fileInputRef.current?.click()}
                    >
                        {!file ? (
                            <>
                                <div className={`w-20 h-20 rounded-full border border-white/10 bg-white/5 flex items-center justify-center mb-6 transition-transform ${isDragActive ? 'scale-110' : 'group-hover:scale-105'}`}>
                                    <UploadCloud size={40} className="text-neutral-400" />
                                </div>
                                <h3 className="text-xl font-bold text-white mb-2">DRAG & DROP YOUR FILES</h3>
                                <p className="text-sm text-neutral-600 mb-4">Supports <strong className="text-neutral-400">PDF</strong>, <strong className="text-neutral-400">DOCX</strong>, and <strong className="text-neutral-400">DOC</strong> (Max 50MB)</p>
                                <button className="btn-accent text-sm py-2.5 px-8 rounded-lg">UPLOAD FILES</button>
                            </>
                        ) : (
                            <div className="w-full max-w-md flex flex-col items-center">
                                <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-5">
                                    <CheckCircle2 size={32} className="text-white" />
                                </div>
                                <div className="w-full bg-white/3 border border-white/5 rounded-xl p-4 flex items-center gap-3 mb-6">
                                    <File size={20} className="text-neutral-400 shrink-0" />
                                    <span className="truncate flex-1 text-sm font-medium text-neutral-200">{file.name}</span>
                                    <button onClick={(e) => { e.stopPropagation(); setFile(null); }} className="p-1.5 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-red-400 transition-colors">
                                        <XCircle size={18} />
                                    </button>
                                </div>
                                <button onClick={(e) => { e.stopPropagation(); verifyFile(); }} className="btn-accent w-full py-3.5 text-base rounded-xl">
                                    Run Citation Verification
                                </button>
                            </div>
                        )}
                        <input type="file" ref={fileInputRef} onChange={handleFileChange} accept=".pdf,.docx,.doc" className="hidden" />
                    </div>

                    {error && (
                        <div className="flex items-center gap-3 bg-red-500/10 text-red-300 px-5 py-3.5 rounded-xl border border-red-500/20">
                            <AlertCircle size={18} className="text-red-400 shrink-0" /> <p className="text-sm font-medium">{error}</p>
                        </div>
                    )}
                </>
            )}

            {/* Progress Tracker */}
            {loading && (
                <div className="glass-card min-h-[400px] flex flex-col items-center justify-center p-8">
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
                    {(() => {
                        const StageIcon = STAGE_CONFIG[progressStage]?.icon || Loader2;
                        return (
                            <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-5">
                                <StageIcon size={32} className={`text-white ${progressStage === 'analyzing' || progressStage === 'processing' ? 'animate-spin' : ''}`} />
                            </div>
                        );
                    })()}

                    <h3 className="text-xl font-bold text-white mb-2">
                        {STAGE_CONFIG[progressStage]?.label || 'Initializing...'}
                    </h3>
                    <p className="text-sm text-neutral-400 mb-8 text-center max-w-md">{progressMessage}</p>

                    {/* Activity Log */}
                    <div className="w-full max-w-md space-y-2">
                        {progressLog.map((entry, i) => {
                            const EntryIcon = STAGE_CONFIG[entry.stage]?.icon || Loader2;
                            const isLatest = i === progressLog.length - 1;
                            return (
                                <div key={i} className={`flex items-center gap-3 text-xs py-1.5 transition-opacity ${isLatest ? 'text-white opacity-100' : 'text-neutral-600 opacity-60'}`}>
                                    <EntryIcon size={14} className={isLatest ? 'text-white' : 'text-neutral-600'} />
                                    <span className="font-medium">{entry.message}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Results */}
            {results && !loading && (
                <div className="space-y-3 animate-fade-in-up">
                    <div className="glass-card-static flex items-center justify-between px-5 py-3 sticky top-0 z-20">
                        <div className="flex items-center gap-3">
                            <BarChart3 size={20} className="text-white" />
                            <h2 className="text-base font-bold text-white">Analysis Report</h2>
                        </div>
                        <button onClick={() => { setResults(null); setFile(null); }} className="text-xs font-semibold text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-lg transition-colors">
                            New Scan
                        </button>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                        {[
                            { label: 'Citations', value: results.num_unique_citations || 0 },
                            { label: 'Unique Citations', value: new Set(results.string_verification?.confirmed_matches?.map(m => m.canonical_ref_id || m.matched_ref)).size || 0 },
                            { label: 'References', value: results.num_references || 0 },
                            { label: 'Missing Refs', value: results.missing_references_for_citations?.length || 0 },
                            { label: 'Unused Refs', value: results.unused_references?.length || 0 },
                        ].map((stat, i) => (
                            <div key={i} className="glass-card p-5 border-l-4 border-l-white/20">
                                <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 mb-2">{stat.label}</div>
                                <div className="text-4xl font-extrabold text-white">{stat.value}</div>
                            </div>
                        ))}
                    </div>

                    {(results.missing_references_for_citations?.length > 0 || results.unused_references?.length > 0) && (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                            {results.missing_references_for_citations?.length > 0 && (
                                <div className="glass-card overflow-hidden">
                                    <div className="bg-white/3 border-b border-white/5 px-5 py-3 flex items-center gap-2">
                                        <FileX size={16} className="text-red-400" />
                                        <h3 className="text-sm font-bold text-red-200">Citations Missing References</h3>
                                    </div>
                                    <div className="p-4 max-h-[250px] overflow-y-auto space-y-2">
                                        {results.missing_references_for_citations.map((c, i) => (
                                            <div key={i} className="bg-white/3 p-3 rounded-lg border border-white/5 text-sm text-red-200 font-mono">{c}</div>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {results.unused_references?.length > 0 && (
                                <div className="glass-card overflow-hidden">
                                    <div className="bg-white/3 border-b border-white/5 px-5 py-3 flex items-center gap-2">
                                        <AlertCircle size={16} className="text-amber-400" />
                                        <h3 className="text-sm font-bold text-amber-200">Unused References</h3>
                                    </div>
                                    <div className="p-4 max-h-[250px] overflow-y-auto space-y-2">
                                        {results.unused_references.map((r, i) => (
                                            <div key={i} className="bg-white/3 p-3 rounded-lg border border-white/5 text-sm text-neutral-300 leading-relaxed">{r}</div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {results.duplicate_reference_groups?.length > 0 && (
                        <div className="glass-card overflow-hidden border border-amber-500/20 mb-3">
                            <div className="bg-amber-500/5 border-b border-amber-500/10 px-5 py-3 flex items-center gap-2">
                                <AlertCircle size={16} className="text-amber-400" />
                                <h3 className="text-sm font-bold text-amber-200">
                                    {results.duplicate_reference_groups.length} Duplicate Reference Group{results.duplicate_reference_groups.length !== 1 ? 's' : ''} Detected and Merged
                                </h3>
                            </div>
                            <div className="p-4 max-h-[350px] overflow-y-auto space-y-4">
                                {results.duplicate_reference_groups.map((group, i) => {
                                    const canonical = group[0];
                                    const duplicates = group.slice(1);
                                    
                                    const orderedEntry = results.ordered_references?.find(r => r.ref === canonical);
                                    const badge = orderedEntry?.display_number ? `[${orderedEntry.display_number}] ` : '';

                                    return (
                                        <div key={i} className="space-y-2">
                                            <div className="bg-white/5 p-3 rounded-lg border border-white/5 text-sm text-neutral-300">
                                                <span className="text-amber-400 font-bold mr-2">{badge}</span>
                                                {canonical} <span className="text-emerald-400 text-xs ml-2 font-semibold">(kept)</span>
                                            </div>
                                            {duplicates.map((dup, j) => (
                                                <div key={j} className="flex gap-2 pl-4 text-xs text-neutral-500">
                                                    <span className="text-neutral-600 mt-1">└─</span>
                                                    <div className="bg-white/3 p-2 rounded border border-white/5 flex-1 break-words">
                                                        <span className="text-amber-400/70 mr-1">Merged duplicate:</span> {dup}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {results.cross_validation && (
                        <div className="glass-card overflow-hidden">
                            <div className="bg-white/3 border-b border-white/5 px-5 py-3 flex items-center gap-2">
                                <GitCompare size={16} className="text-sky-400" />
                                <h3 className="text-sm font-bold text-sky-200">Cross-Validation (Python vs AI)</h3>
                            </div>
                            <div className="p-4 space-y-3">
                                <div className="grid grid-cols-3 gap-3">
                                    <div className="bg-white/[0.03] p-3 rounded-lg border border-white/5 text-center">
                                        <div className="text-lg font-bold text-emerald-400">{results.cross_validation.confirmed_by_both?.length || 0}</div>
                                        <div className="text-[10px] uppercase tracking-widest text-neutral-500">Confirmed</div>
                                    </div>
                                    <div className="bg-white/[0.03] p-3 rounded-lg border border-white/5 text-center">
                                        <div className="text-lg font-bold text-sky-400">{results.cross_validation.python_only?.length || 0}</div>
                                        <div className="text-[10px] uppercase tracking-widest text-neutral-500">Python Only</div>
                                    </div>
                                    <div className="bg-white/[0.03] p-3 rounded-lg border border-white/5 text-center">
                                        <div className="text-lg font-bold text-red-400">{results.cross_validation.ai_only_potential_hallucination?.length || 0}</div>
                                        <div className="text-[10px] uppercase tracking-widest text-neutral-500">AI Only ⚠</div>
                                    </div>
                                </div>
                                {results.cross_validation.python_only?.length > 0 && (
                                    <div className="bg-sky-500/5 p-3 rounded-lg border border-sky-500/20">
                                        <div className="text-[10px] font-bold uppercase tracking-widest text-sky-400 mb-2">Found by Python regex only (AI missed these)</div>
                                        {results.cross_validation.python_only.map((c, i) => (
                                            <div key={i} className="text-xs text-neutral-300 font-mono bg-white/[0.02] px-2 py-1 rounded mb-1">{c}</div>
                                        ))}
                                    </div>
                                )}
                                {results.cross_validation.ai_only_potential_hallucination?.length > 0 && (
                                    <div className="bg-red-500/5 p-3 rounded-lg border border-red-500/20">
                                        <div className="text-[10px] font-bold uppercase tracking-widest text-red-400 mb-2">⚠ AI-only citations (not found in document by Python — possible hallucination)</div>
                                        {results.cross_validation.ai_only_potential_hallucination.map((c, i) => (
                                            <div key={i} className="text-xs text-neutral-300 font-mono bg-white/[0.02] px-2 py-1 rounded mb-1">{c}</div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {results.ai_additional_citations?.length > 0 && (
                        <div className="glass-card overflow-hidden border border-amber-500/20">
                            <div className="bg-amber-500/5 border-b border-amber-500/10 px-5 py-3 flex items-center gap-2">
                                <ScanSearch size={16} className="text-amber-400" />
                                <h3 className="text-sm font-bold text-amber-200">AI Found Additional Citations ({results.ai_additional_citations.length})</h3>
                                <span className="ml-auto text-[9px] uppercase tracking-widest text-amber-400/60 bg-amber-500/10 px-2 py-0.5 rounded-full">Review Required</span>
                            </div>
                            <div className="p-4 space-y-2">
                                <p className="text-xs text-neutral-400 mb-3">These citations were found by AI but not by Python regex. They may be valid citations in an unusual format, or they may be false positives. Please review each one.</p>
                                {results.ai_additional_citations.map((c, i) => (
                                    <div key={i} className="bg-white/[0.02] p-3 rounded-lg border border-amber-500/10 text-sm text-neutral-300 font-mono">{c}</div>
                                ))}
                            </div>
                        </div>
                    )}

                    {results.irregularities?.length > 0 && (
                        <div className="glass-card overflow-hidden">
                            <div className="bg-white/3 border-b border-white/5 px-5 py-3 flex items-center gap-2">
                                <AlertCircle size={16} className="text-purple-400" />
                                <h3 className="text-sm font-bold text-purple-200">Irregularities ({results.irregularities.length})</h3>
                            </div>
                            <div className="p-4 max-h-[350px] overflow-y-auto space-y-3">
                                {results.irregularities.map((irr, i) => (
                                    <div key={i} className="bg-white/[0.02] p-4 rounded-xl border border-white/5 border-l-4 border-l-white/15">
                                        <span className="badge badge-purple mb-3 inline-block">{irr.type}</span>
                                        <p className="text-sm text-neutral-300 mb-3">{irr.details}</p>
                                        <div className="grid md:grid-cols-2 gap-3">
                                            <div className="bg-white/3 p-3 rounded-lg border border-white/5">
                                                <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 mb-1">Citation</div>
                                                <div className="font-mono text-xs text-neutral-300">{irr.citation}</div>
                                            </div>
                                            <div className="bg-white/3 p-3 rounded-lg border border-white/5">
                                                <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 mb-1">Reference</div>
                                                <div className="font-mono text-xs text-neutral-300">{irr.ref}</div>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {results.string_verification?.confirmed_matches?.length > 0 && (() => {
                        const detectedStyle = results.detected_style || 'apa';
                        const isVancouver = detectedStyle === 'vancouver';
                        const styleLabel = {
                            vancouver: 'Vancouver',
                            apa: 'APA',
                            mla: 'MLA',
                            chicago: 'Chicago',
                            harvard: 'Harvard',
                        }[detectedStyle] || detectedStyle.toUpperCase();

                        // Group citations by canonical_ref_id to avoid duplicate cards for the same reference
                        const uniqueMatchesMap = {};
                        results.string_verification.confirmed_matches.forEach(m => {
                            const refKey = m.canonical_ref_id || m.matched_ref;
                            if (!uniqueMatchesMap[refKey]) {
                                uniqueMatchesMap[refKey] = {
                                    ...m,
                                    citations: [m.citation]
                                };
                            } else if (!uniqueMatchesMap[refKey].citations.includes(m.citation)) {
                                uniqueMatchesMap[refKey].citations.push(m.citation);
                            }
                        });
                        const allMatches = Object.values(uniqueMatchesMap);

                        // Use ordered_references from backend to reorder matched refs
                        const orderedRefs = results.ordered_references || [];
                        const orderedRefTexts = orderedRefs.map(r => r.ref);

                        // Partition into good & problem, then sort each by the ordered_references sequence
                        const orderIndex = {};
                        orderedRefTexts.forEach((ref, idx) => { orderIndex[ref] = idx; });

                        const sortByOrder = (a, b) => {
                            const idxA = orderIndex[a.matched_ref] ?? 999;
                            const idxB = orderIndex[b.matched_ref] ?? 999;
                            return idxA - idxB;
                        };

                        const goodMatches = allMatches.filter(m => {
                            const conf = results.verbatim_references?.[m.matched_ref]?.confidence || 0;
                            return conf >= 0.75;
                        }).sort(sortByOrder);

                        const problemMatches = allMatches.filter(m => {
                            const conf = results.verbatim_references?.[m.matched_ref]?.confidence || 0;
                            return conf < 0.75;
                        }).sort(sortByOrder);

                        // Lookup helper: find ordered ref entry for a match
                        const getOrderedEntry = (matchedRef) => orderedRefs.find(r => r.ref === matchedRef);

                        const renderMatch = (m, i, isProblem) => {
                            const verbatimData = results.verbatim_references?.[m.matched_ref];
                            const verbatimText = verbatimData?.verbatim || m.matched_ref;
                            const verbatimHtml = verbatimData?.verbatim_html ? sanitizeHtml(verbatimData.verbatim_html) : null;
                            const confidence = verbatimData?.confidence || 0;
                            const conflict = verbatimData?.conflict;
                            const borderClass = isProblem ? 'border-l-amber-500/50' : conflict ? 'border-l-amber-500/50' : 'border-l-white/15';

                            const orderedEntry = getOrderedEntry(m.matched_ref);
                            const displayNumber = orderedEntry?.display_number;
                            const firstCitedAs = orderedEntry?.first_cited_as;

                            return (
                                <div key={i} className={`bg-white/[0.02] p-3 rounded-lg border border-white/5 border-l-4 ${borderClass}`}>
                                    <div className="flex items-start gap-3 mb-2">
                                        {isVancouver && displayNumber != null && (
                                            <span className="shrink-0 w-7 h-7 rounded-full bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-xs font-bold text-sky-400">
                                                {displayNumber}
                                            </span>
                                        )}
                                        <div className="flex-1">
                                            <div className="font-mono text-xs text-neutral-300 bg-white/3 px-3 py-2 rounded-lg mb-2">
                                                {m.citations ? m.citations.join(' | ') : m.citation}
                                            </div>
                                            <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 mb-1 flex items-center gap-2">
                                                Source Reference
                                                {confidence >= 0.8 && <span className="text-emerald-500">(✓ exact match)</span>}
                                                {confidence > 0 && confidence < 0.8 && <span className="text-amber-500">(~{Math.round(confidence * 100)}% match)</span>}
                                            </div>
                                            {verbatimHtml ? (
                                                <div className="text-xs text-neutral-300 leading-relaxed bg-white/[0.03] p-3 rounded-lg border border-white/5" dangerouslySetInnerHTML={{ __html: verbatimHtml }} />
                                            ) : (
                                                <div className="text-xs text-neutral-300 leading-relaxed bg-white/[0.03] p-3 rounded-lg border border-white/5">{verbatimText}</div>
                                            )}
                                            {isVancouver && firstCitedAs && (
                                                <div className="text-[10px] text-neutral-600 mt-1.5">
                                                    First cited as: <span className="font-mono text-neutral-500">{firstCitedAs}</span>
                                                </div>
                                            )}
                                            {isProblem && (
                                                <div className="mt-2 text-[10px] text-amber-400 bg-amber-500/10 px-3 py-2 rounded-lg border border-amber-500/20 space-y-1">
                                                    <div className="font-bold uppercase tracking-widest">⚠ Why this match is flagged:</div>
                                                    {confidence < 0.6 && <div>• Very low similarity ({Math.round(confidence * 100)}%) — source text may contain merged references</div>}
                                                    {confidence >= 0.6 && confidence < 0.75 && <div>• Moderate similarity ({Math.round(confidence * 100)}%) — possible formatting differences or partial extraction</div>}
                                                    {verbatimText.length > 400 && <div>• Unusually long source text ({verbatimText.length} chars) — may contain multiple merged references</div>}
                                                    {conflict && <div>• Conflict: {conflict}</div>}
                                                </div>
                                            )}
                                            {!isProblem && conflict && (
                                                <div className="mt-2 flex items-center gap-2 text-[10px] text-amber-400 bg-amber-500/10 px-3 py-2 rounded-lg border border-amber-500/20">
                                                    <AlertCircle size={12} className="shrink-0" />
                                                    <span>{conflict}</span>
                                                </div>
                                            )}
                                        </div>
                                        <button
                                            onClick={() => copyRichText(verbatimText, verbatimHtml, `${isProblem ? 'p' : 'g'}-${i}`)}
                                            className="shrink-0 p-2 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-colors"
                                            title="Copy reference with formatting"
                                        >
                                            {copiedIdx === `${isProblem ? 'p' : 'g'}-${i}` ? <ClipboardCheck size={16} className="text-emerald-400" /> : <Copy size={16} />}
                                        </button>
                                    </div>
                                </div>
                            );
                        };

                        return (
                            <>
                                {results.style_detection_confidence > 0 && (
                                    <div className="glass-card mb-3 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 border-l-4 border-l-purple-500/50">
                                        <div>
                                            <div className="text-[10px] font-bold uppercase tracking-widest text-purple-400 mb-1">Detected Style</div>
                                            <div className="flex items-center gap-3">
                                                <h3 className="text-xl font-bold text-white">{styleLabel}</h3>
                                                <span className="bg-purple-500/10 text-purple-300 border border-purple-500/20 px-2 py-0.5 rounded text-xs font-semibold">
                                                    {Math.round(results.style_detection_confidence * 100)}% Confidence
                                                </span>
                                            </div>
                                        </div>
                                        {results.style_detection_evidence?.length > 0 && (
                                            <div className="md:w-1/2 bg-white/[0.02] p-3 rounded-lg border border-white/5 text-xs text-neutral-300 space-y-1">
                                                <div className="font-semibold text-neutral-400 mb-1">Key Evidence:</div>
                                                {results.style_detection_evidence.slice(0, 3).map((ev, idx) => (
                                                    <div key={idx} className="flex gap-2">
                                                        <span className="text-purple-400 shrink-0">•</span>
                                                        <span>{ev}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                    {/* Left panel — Good Matches (ordered) */}
                                <div className="glass-card overflow-hidden">
                                    <div className="bg-white/3 border-b border-white/5 px-5 py-3 flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <CheckCircle2 size={16} className="text-emerald-400" />
                                            <h3 className="text-sm font-bold text-emerald-200">{styleLabel} Reference Order ({goodMatches.length})</h3>
                                        </div>
                                        <button
                                            onClick={() => {
                                                const copyList = goodMatches.map((m, idx) => {
                                                    const text = results.verbatim_references?.[m.matched_ref]?.verbatim || m.matched_ref;
                                                    const entry = getOrderedEntry(m.matched_ref);
                                                    if (isVancouver && entry?.display_number != null) {
                                                        return `${entry.display_number}. ${text}`;
                                                    }
                                                    return text;
                                                });
                                                const allPlain = copyList.join('\n\n');
                                                const allHtml = goodMatches
                                                    .map(m => results.verbatim_references?.[m.matched_ref]?.verbatim_html)
                                                    .filter(Boolean)
                                                    .map(h => sanitizeHtml(h));
                                                copyRichText(allPlain, allHtml.length > 0 ? allHtml.join('<br><br>') : null, 'all-good');
                                            }}
                                            className="flex items-center gap-1.5 text-xs font-semibold text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-1.5 rounded-lg transition-colors"
                                        >
                                            {copiedIdx === 'all-good' ? <ClipboardCheck size={13} /> : <Copy size={13} />}
                                            {copiedIdx === 'all-good' ? 'Copied!' : 'Copy All'}
                                        </button>
                                    </div>
                                    <div className="p-4 max-h-[500px] overflow-y-auto space-y-2">
                                        {goodMatches.length > 0 ? goodMatches.map((m, i) => renderMatch(m, i, false)) : (
                                            <div className="text-xs text-neutral-500 text-center py-4">No high-confidence matches</div>
                                        )}
                                    </div>
                                </div>

                                {/* Right panel — Problematic Matches */}
                                <div className="glass-card overflow-hidden border border-amber-500/15">
                                    <div className="bg-amber-500/5 border-b border-amber-500/10 px-5 py-3 flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <AlertCircle size={16} className="text-amber-400" />
                                            <h3 className="text-sm font-bold text-amber-200">Needs Review ({problemMatches.length})</h3>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {problemMatches.length > 0 && (
                                                <button
                                                    onClick={() => {
                                                        const allPlain = problemMatches
                                                            .map(m => results.verbatim_references?.[m.matched_ref]?.verbatim || m.matched_ref)
                                                            .join('\n\n');
                                                        const allHtml = problemMatches
                                                            .map(m => results.verbatim_references?.[m.matched_ref]?.verbatim_html)
                                                            .filter(Boolean)
                                                            .map(h => sanitizeHtml(h));
                                                        copyRichText(allPlain, allHtml.length > 0 ? allHtml.join('<br><br>') : null, 'all-review');
                                                    }}
                                                    className="flex items-center gap-1.5 text-xs font-semibold text-amber-400/70 hover:text-amber-200 bg-amber-500/5 hover:bg-amber-500/15 border border-amber-500/15 px-3 py-1.5 rounded-lg transition-colors"
                                                >
                                                    {copiedIdx === 'all-review' ? <ClipboardCheck size={14} className="text-amber-300" /> : <Copy size={14} />}
                                                    {copiedIdx === 'all-review' ? 'Copied!' : 'Copy All'}
                                                </button>
                                            )}
                                            {problemMatches.length > 0 && (
                                                <span className="text-[9px] uppercase tracking-widest text-amber-400/60 bg-amber-500/10 px-2 py-0.5 rounded-full">Low Confidence</span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="p-4 max-h-[500px] overflow-y-auto space-y-2">
                                        {problemMatches.length > 0 ? problemMatches.map((m, i) => renderMatch(m, i, true)) : (
                                            <div className="text-xs text-emerald-500 text-center py-4">✓ All matches are high confidence</div>
                                        )}
                                    </div>
                                </div>
                            </div>
                            </>
                        );
                    })()}
                </div>
            )}
        </div>
    );
}
