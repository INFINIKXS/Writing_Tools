import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, Copy, Check, BookOpen, ChevronDown, FileText, Loader2, AlertCircle, X, ChevronRight, Trash2, ShieldCheck, ShieldAlert, ClipboardCheck, Send, Sparkles, ChevronUp, RefreshCw, StopCircle } from 'lucide-react';
import FormatterView from './FormatterView';

const STYLES = [
    { id: 'harvard', label: 'Harvard', desc: 'Cite Them Right (10th ed.)' },
    { id: 'apa', label: 'APA 7th', desc: 'Publication Manual (7th ed.)' },
    { id: 'vancouver', label: 'Vancouver', desc: 'ICMJE / Citing Medicine' },
];

function ReferenceCard({ r, copiedId, copyRich, removeResult, expandedMeta, toggleMeta, onAiRetry }) {
    const vStatus = r.data.metadata?.verification_status;
    const vBadge = (() => {
        if (!vStatus) return null;
        if (vStatus.startsWith('verified_')) return { icon: '✓', label: 'Verified (DOI found)', cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20', tooltip: 'Paper identity confirmed via PubMed/CrossRef with title match.' };
        if (vStatus === 'partial') return { icon: '~', label: 'Partial', cls: 'text-amber-400 bg-amber-500/10 border-amber-500/20', tooltip: 'API found the paper, but some metadata fields were filled by AI. Review recommended.' };
        if (vStatus === 'unverified' || vStatus === 'not_found') return { icon: '!', label: 'Unverified', cls: 'text-red-400 bg-red-500/10 border-red-500/20', tooltip: 'Could not confirm paper identity via external database. Metadata may be inaccurate.' };
        return null;
    })();

    let apiSource = r.data.metadata?.api_source;
    if (!apiSource && vStatus) {
        if (vStatus.startsWith('verified_pubmed')) apiSource = 'PubMed';
        else if (vStatus.startsWith('verified_crossref')) apiSource = 'CrossRef';
    }

    return (
        <div className="glass-card p-4 border-l-4 border-l-purple-500/50 overflow-hidden">
            <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                    <span className="badge badge-green">{r.data.type || 'Reference'}</span>
                    {apiSource && (
                        <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border text-cyan-400 bg-cyan-500/10 border-cyan-500/20 flex items-center">
                            {apiSource}
                        </span>
                    )}
                    {vBadge && (
                        <span title={vBadge.tooltip} className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border cursor-help flex items-center gap-1 ${vBadge.cls}`}>
                            <span className="text-[10px]">{vBadge.icon}</span>
                            {vBadge.label}
                        </span>
                    )}
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

            {(!r.data.metadata?.doi && (vStatus === 'unverified' || vStatus === 'not_found')) && (
                <div className="mt-2 flex flex-col sm:flex-row sm:items-center gap-2 bg-amber-500/5 border border-amber-500/15 rounded-lg p-2.5">
                    <div className="flex items-start gap-2 flex-1">
                        <span className="text-amber-400 text-[10px] mt-0.5">⚠</span>
                        <p className="text-[10px] text-amber-400/80 leading-relaxed">
                            <strong>No DOI found.</strong> Standard extraction failed to find a valid DOI for this document.
                        </p>
                    </div>
                    {onAiRetry && r.file && (
                        <button 
                            onClick={() => onAiRetry(r.id)}
                            disabled={r.aiRetrying}
                            className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/30 rounded-md text-indigo-300 hover:text-indigo-200 text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                        >
                            {r.aiRetrying ? (
                                <>
                                    <Loader2 size={12} className="animate-spin" />
                                    <span>Extracting...</span>
                                </>
                            ) : (
                                <>
                                    <Sparkles size={12} />
                                    <span>Retry DOI Search with Advanced Method</span>
                                </>
                            )}
                        </button>
                    )}
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

            {r.data.metadata?.crossref_failed && (
                <div className="mt-2 flex items-start gap-2 bg-purple-500/5 border border-purple-500/15 rounded-lg px-3 py-1.5">
                    <span className="text-purple-400 text-[10px] mt-0.5">⚠</span>
                    <p className="text-[10px] text-purple-400/80 leading-relaxed">
                        <strong>API lookup failed.</strong> Metadata was extracted using AI/Regex and may be inaccurate. Please review.
                    </p>
                </div>
            )}

            {r.data.metadata?.ai_filled_fields && Object.keys(r.data.metadata.ai_filled_fields).length > 0 && (
                <div className="mt-2 bg-violet-500/5 border border-violet-500/15 rounded-lg px-3 py-2">
                    <div className="flex items-center gap-1.5 mb-1.5">
                        <span className="text-violet-400 text-[10px]">🤖</span>
                        <span className="text-[10px] font-bold text-violet-400 uppercase tracking-wider">AI-Generated Fields</span>
                        <span className="text-[9px] text-violet-400/60 ml-1">— verify these values</span>
                    </div>
                    <div className="space-y-1">
                        {Object.entries(r.data.metadata.ai_filled_fields).map(([key, info]) => (
                            <div key={key} className="flex items-start gap-2">
                                <span className="text-[9px] font-bold uppercase tracking-widest text-violet-500/70 w-16 shrink-0 pt-0.5">{key}</span>
                                <span className="text-[10px] text-violet-300 font-mono break-all flex-1">{info.value}</span>
                                <span className="text-[8px] font-bold uppercase tracking-wider px-1 py-0.5 rounded border text-amber-400 bg-amber-500/10 border-amber-500/20 shrink-0">
                                    {info.source === 'ai_verified' ? 'AI ✓' : info.source === 'ai_inferred' ? 'AI ~' : 'AI'}
                                </span>
                            </div>
                        ))}
                    </div>
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
                        const srcLabel = { pubmed: 'PubMed', crossref: 'CrossRef', ai_verified: 'AI ✓', ai: 'AI', text_parsing: 'Regex', pdf_metadata: 'PDF' }[src];
                        const srcColor = { pubmed: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20', crossref: 'text-blue-400 bg-blue-500/10 border-blue-500/20', ai_verified: 'text-green-400 bg-green-500/10 border-green-500/20', ai: 'text-amber-400 bg-amber-500/10 border-amber-500/20', text_parsing: 'text-neutral-400 bg-white/5 border-white/10', pdf_metadata: 'text-neutral-400 bg-white/5 border-white/10' }[src] || '';
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


// ─── Verifier Result Card ────────────────────────────────────────────────────

const STATUS_CONFIG = {
    verified: { icon: '✓', label: 'Verified', cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20', borderCls: 'border-l-emerald-500/50' },
    issues_found: { icon: '⚠', label: 'Issues Found', cls: 'text-amber-400 bg-amber-500/10 border-amber-500/20', borderCls: 'border-l-amber-500/50' },
    unverifiable: { icon: '✗', label: 'Unverifiable', cls: 'text-red-400 bg-red-500/10 border-red-500/20', borderCls: 'border-l-red-500/50' },
};

const FIELD_LABELS = { authors: 'Authors', title: 'Title', year: 'Year', source: 'Source', volume: 'Volume', issue: 'Issue', pages: 'Pages' };

function VerifierResultCard({ result, index, copiedId, onCopy, expanded, onToggle }) {
    const status = STATUS_CONFIG[result.overall_status] || STATUS_CONFIG.unverifiable;
    const hasMetaIssues = result.metadata_issues?.some(i => i.status !== 'correct' && i.status !== 'skipped');
    const hasMeta = result.metadata_issues?.length > 0;
    const hasFormatIssues = result.formatting_issues?.length > 0;

    return (
        <div className={`glass-card p-4 border-l-4 ${status.borderCls} overflow-hidden`}>
            {/* Header */}
            <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] font-bold text-neutral-500 bg-white/5 px-1.5 py-0.5 rounded">#{index + 1}</span>
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border flex items-center gap-1 ${status.cls}`}>
                        <span className="text-[10px]">{status.icon}</span>
                        {status.label}
                    </span>
                    {result.api_source && (
                        <span className="text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border text-cyan-400 bg-cyan-500/10 border-cyan-500/20">
                            {result.api_source}
                        </span>
                    )}
                    {result.doi && (
                        <span className="text-[9px] text-neutral-500 font-mono truncate max-w-[200px]">
                            {result.doi}
                        </span>
                    )}
                    {result.accuracy_score > 0 && (
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                            result.accuracy_score >= 0.9 ? 'text-emerald-400 bg-emerald-500/10' :
                            result.accuracy_score >= 0.6 ? 'text-amber-400 bg-amber-500/10' :
                            'text-red-400 bg-red-500/10'
                        }`}>
                            {Math.round(result.accuracy_score * 100)}% accurate
                        </span>
                    )}
                </div>
                {result.corrected_reference && (
                    <button
                        onClick={() => onCopy(result.corrected_reference_html || result.corrected_reference, index)}
                        className="p-1.5 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all active:scale-90 flex items-center gap-1.5 shrink-0"
                    >
                        {copiedId === index ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                        <span className="text-[10px] font-bold uppercase tracking-wider">
                            {copiedId === index ? 'Copied!' : 'Copy Corrected'}
                        </span>
                    </button>
                )}
            </div>

            {/* Original reference */}
            <div className="text-[11px] text-neutral-400 bg-white/[0.03] p-3 rounded-lg border border-white/5 leading-relaxed break-words mb-2 font-mono">
                {result.original}
            </div>

            {/* Corrected reference (if different / available) */}
            {result.corrected_reference && result.overall_status !== 'verified' && (
                <div className="mb-2">
                    <div className="flex items-center gap-1.5 mb-1">
                        <Sparkles size={10} className="text-emerald-400" />
                        <span className="text-[9px] font-bold text-emerald-400 uppercase tracking-wider">Corrected Reference</span>
                    </div>
                    <div
                        className="text-sm text-white bg-emerald-500/5 p-3 rounded-lg border border-emerald-500/15 leading-relaxed font-medium break-words"
                        dangerouslySetInnerHTML={{ __html: (result.corrected_reference_html || result.corrected_reference).replace(/<(?!\/?(?:i|em)\b)[^>]*>/gi, '') }}
                    />
                </div>
            )}

            {/* Unverifiable notice */}
            {result.overall_status === 'unverifiable' && (
                <div className="flex items-start gap-2 bg-red-500/5 border border-red-500/15 rounded-lg px-3 py-2 mb-2">
                    <AlertCircle size={12} className="text-red-400 shrink-0 mt-0.5" />
                    <p className="text-[10px] text-red-400/80 leading-relaxed">
                        <strong>Could not verify.</strong> No DOI was found and title search did not match. Check the reference manually.
                    </p>
                </div>
            )}

            {/* Expandable details */}
            {(hasMeta || hasFormatIssues) && (
                <button
                    onClick={() => onToggle(index)}
                    className="w-full flex items-center justify-between text-[10px] font-semibold text-neutral-600 hover:text-neutral-400 transition-colors"
                >
                    <span className="flex items-center gap-1.5">
                        Details
                        {hasMetaIssues && <span className="text-[8px] px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">Metadata Issue</span>}
                        {hasFormatIssues && <span className="text-[8px] px-1 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20">Format Issue</span>}
                    </span>
                    <ChevronRight size={10} className={`transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`} />
                </button>
            )}

            {expanded && (
                <div className="mt-2 space-y-2 animate-fade-in-up">
                    {/* Metadata issues */}
                    {hasMeta && (
                        <div className="bg-white/[0.02] border border-white/5 rounded-lg p-3">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-1.5">
                                    <span className="text-[9px] font-bold text-neutral-400 uppercase tracking-wider">Metadata Accuracy</span>
                                </div>
                                {result.api_source && (
                                    <span className="text-[9px] text-cyan-400/80 italic font-medium">Source: {result.api_source}</span>
                                )}
                            </div>
                            <div className="space-y-1.5">
                                {result.metadata_issues.filter(i => i.status !== 'skipped').map((issue, idx) => (
                                    <div key={idx} className="flex items-start gap-2">
                                        <span className={`text-[10px] shrink-0 mt-0.5 ${
                                            issue.status === 'correct' ? 'text-emerald-400' :
                                            issue.status === 'missing' ? 'text-amber-400' :
                                            issue.status === 'unavailable' ? 'text-neutral-600' : 'text-red-400'
                                        }`}>
                                            {issue.status === 'correct' ? '✓' : issue.status === 'missing' ? '○' : issue.status === 'unavailable' ? '?' : '✗'}
                                        </span>
                                        <span className="text-[9px] font-bold uppercase tracking-widest text-neutral-500 w-14 shrink-0 pt-0.5">
                                            {FIELD_LABELS[issue.field] || issue.field}
                                        </span>
                                        <div className="flex-1 min-w-0">
                                            {issue.status === 'incorrect' && (
                                                <>
                                                    <div className="text-[10px] text-red-400/80 line-through break-all">{issue.user_value}</div>
                                                    <div className="text-[10px] text-emerald-400 break-all">{issue.correct_value}</div>
                                                </>
                                            )}
                                            {issue.status === 'missing' && (
                                                <div className="text-[10px] text-amber-400 break-all">Missing — should be: {issue.correct_value}</div>
                                            )}
                                            {issue.status === 'correct' && (
                                                <div className="text-[10px] text-neutral-500 break-all">{issue.user_value || issue.correct_value}</div>
                                            )}
                                            {issue.status === 'unavailable' && (
                                                <div className="text-[10px] text-neutral-600 italic break-all">Unable to verify — not available from API</div>
                                            )}
                                            {issue.detail && issue.status !== 'correct' && (
                                                <div className="text-[9px] text-neutral-600 mt-0.5">{issue.detail}</div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Formatting issues */}
                    {hasFormatIssues && (
                        <div className="bg-violet-500/5 border border-violet-500/15 rounded-lg p-3">
                            <div className="flex items-center gap-1.5 mb-2">
                                <span className="text-[9px] font-bold text-violet-400 uppercase tracking-wider">Formatting Issues</span>
                            </div>
                            <div className="space-y-1.5">
                                {result.formatting_issues.map((issue, idx) => (
                                    <div key={idx} className="flex items-start gap-2">
                                        <span className="text-violet-400 text-[10px] mt-0.5">→</span>
                                        <div className="flex-1">
                                            <span className="text-[9px] font-bold text-violet-400/80 uppercase tracking-wider mr-1.5">
                                                {issue.issue.replace(/_/g, ' ')}
                                            </span>
                                            <span className="text-[10px] text-neutral-400">{issue.detail}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}


// ─── Verifier Sub-View ───────────────────────────────────────────────────────

function VerifierSubView() {
    const [refsText, setRefsText] = useState('');
    const [style, setStyle] = useState('auto');
    const [isVerifying, setIsVerifying] = useState(false);
    const [progress, setProgress] = useState([]);
    const [results, setResults] = useState(null);
    const [expandedCards, setExpandedCards] = useState({});
    const [copiedId, setCopiedId] = useState(null);
    const [copiedAll, setCopiedAll] = useState(false);
    const abortRef = useRef(null);

    const toggleCard = (idx) => setExpandedCards(prev => ({ ...prev, [idx]: !prev[idx] }));

    const stripHtml = (html) => html.replace(/<\/?[^>]*>/g, '');
    const sanitizeHtml = (html) => html.replace(/<(?!\/?(?:i|em)\b)[^>]*>/gi, '');

    const copyRich = (htmlText, id) => {
        const html = sanitizeHtml(htmlText);
        const plain = stripHtml(htmlText);
        navigator.clipboard.write([new ClipboardItem({
            'text/html': new Blob([html], { type: 'text/html' }),
            'text/plain': new Blob([plain], { type: 'text/plain' }),
        })]).then(() => {
            setCopiedId(id);
            setTimeout(() => setCopiedId(null), 2000);
        });
    };

    const copyAllCorrected = () => {
        if (!results?.results) return;
        const corrected = results.results.filter(r => r.corrected_reference);
        if (corrected.length === 0) return;
        const allHtml = corrected.map(r => sanitizeHtml(r.corrected_reference_html || r.corrected_reference)).join('<br/>\n');
        const allPlain = corrected.map(r => stripHtml(r.corrected_reference_html || r.corrected_reference)).join('\n');
        navigator.clipboard.write([new ClipboardItem({
            'text/html': new Blob([allHtml], { type: 'text/html' }),
            'text/plain': new Blob([allPlain], { type: 'text/plain' }),
        })]).then(() => {
            setCopiedAll(true);
            setTimeout(() => setCopiedAll(false), 2000);
        });
    };

    const handleVerify = async () => {
        if (!refsText.trim() || isVerifying) return;
        setIsVerifying(true);
        setResults({ results: [], style_info: null, summary: null });
        setProgress([]);
        setExpandedCards({});

        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const res = await fetch('/api/verify-reference-list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    references_text: refsText.trim(),
                    style: style === 'auto' ? null : style,
                }),
                signal: controller.signal,
            });

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
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        setProgress(prev => [...prev, event]);

                        // Style detected — show style badge immediately
                        if (event.stage === 'style_detected' && event.data?.style_info) {
                            setResults(prev => ({ ...prev, style_info: event.data.style_info }));
                        }

                        // Individual reference result — append to results array immediately
                        if (event.stage === 'ref_result' && event.data?.result) {
                            const refResult = event.data.result;
                            const idx = event.data.index;
                            setResults(prev => ({
                                ...prev,
                                results: [...(prev?.results || []), refResult],
                            }));
                            // Auto-expand cards with issues
                            if (refResult.overall_status === 'issues_found') {
                                setExpandedCards(prev => ({ ...prev, [idx]: true }));
                            }
                        }

                        // Final summary
                        if (event.stage === 'complete' && event.data?.summary) {
                            setResults(prev => ({ ...prev, summary: event.data.summary }));
                        }
                    } catch {}
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                setProgress(prev => [...prev, { stage: 'error', message: `Connection error: ${err.message}` }]);
            }
        } finally {
            setIsVerifying(false);
            abortRef.current = null;
        }
    };

    const styleInfo = results?.style_info;
    const summary = results?.summary;
    const correctedCount = results?.results?.filter(r => r.corrected_reference).length || 0;

    return (
        <div className="flex gap-3 flex-1 min-h-0 min-w-0 w-full overflow-hidden">
            {/* Input Panel */}
            <div className="glass-card flex flex-col overflow-hidden w-[380px] shrink-0 self-start border-l-4 border-l-cyan-500/50 max-w-[40vw]">
                <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ClipboardCheck size={16} className="text-neutral-400" />
                        <h3 className="text-sm font-bold text-white">Verify References</h3>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="relative">
                            <select
                                value={style}
                                onChange={(e) => setStyle(e.target.value)}
                                className="appearance-none bg-white/5 border border-white/10 text-xs font-semibold text-neutral-300 px-3 py-1.5 pr-7 rounded-lg cursor-pointer hover:bg-white/10 transition-colors outline-none focus:border-white/20"
                            >
                                <option value="auto" className="bg-neutral-900 text-white">Auto-detect</option>
                                {STYLES.map(s => (
                                    <option key={s.id} value={s.id} className="bg-neutral-900 text-white">{s.label}</option>
                                ))}
                            </select>
                            <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500 pointer-events-none" />
                        </div>
                        <span className="badge badge-green">Input</span>
                    </div>
                </div>

                <div className="p-4 flex flex-col gap-3 flex-1 overflow-y-auto">
                    <p className="text-xs text-neutral-600 bg-white/3 p-2.5 rounded-lg border border-white/5 shrink-0">
                        Paste your reference list below. Each reference should be separated by a <strong className="text-neutral-400">blank line</strong> or <strong className="text-neutral-400">numbered</strong> (1. / [1]).
                        DOIs will be used for verification via <strong className="text-cyan-400/70">CrossRef</strong> & <strong className="text-cyan-400/70">PubMed</strong>.
                    </p>

                    <textarea
                        value={refsText}
                        onChange={(e) => setRefsText(e.target.value)}
                        placeholder={'1. Smith, J. (2020). Title of article. Journal Name, 10(2), 45-67. https://doi.org/10.1234/example\n\n2. Jones, A. & Brown, B. (2019). Another title. Publisher.\n\nOr paste without numbers, separated by blank lines...'}
                        className="w-full flex-1 min-h-[150px] shrink-0 bg-white/[0.03] border border-white/10 rounded-xl p-3 text-xs text-neutral-300 placeholder-neutral-700 outline-none resize-none focus:border-cyan-500/30 transition-colors font-mono leading-relaxed"
                    />

                    <div className="flex gap-2 shrink-0">
                        <button
                            onClick={handleVerify}
                            disabled={!refsText.trim() || isVerifying}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-bold text-sm transition-all duration-300 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/20"
                        >
                            {isVerifying ? (
                                <>
                                    <Loader2 size={16} className="animate-spin" />
                                    Verifying…
                                </>
                            ) : (
                                <>
                                    <Send size={16} />
                                    Verify References
                                </>
                            )}
                        </button>
                        {isVerifying && (
                            <button
                                onClick={() => { abortRef.current?.abort(); }}
                                className="px-3 py-3 rounded-xl font-bold text-sm bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-400 hover:text-red-300 transition-all active:scale-95"
                                title="Stop verification"
                            >
                                <StopCircle size={16} />
                            </button>
                        )}
                    </div>

                    {/* Progress feed */}
                    {progress.length > 0 && (
                        <div className="space-y-1 shrink-0 overflow-y-auto max-h-[150px]">
                            {progress.map((p, i) => {
                                const isCurrent = isVerifying && i === progress.length - 1;
                                return (
                                    <div key={i} className="flex items-center gap-2 text-[10px] px-2 py-1 bg-white/[0.02] rounded">
                                        {p.stage === 'error' ? (
                                            <AlertCircle size={10} className="text-red-400 shrink-0" />
                                        ) : isCurrent ? (
                                            <Loader2 size={10} className="text-cyan-400 animate-spin shrink-0" />
                                        ) : (
                                            <Check size={10} className="text-cyan-600 shrink-0" />
                                        )}
                                        <span className={`truncate ${p.stage === 'error' ? 'text-red-400' : isCurrent ? 'text-cyan-400' : 'text-neutral-500'}`}>
                                            {p.message}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>

            {/* Results Panel */}
            <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
                {/* Header */}
                <div className="glass-card px-5 py-3 flex items-center justify-between mb-3 shrink-0">
                    <div className="flex items-center gap-2">
                        <ShieldCheck size={16} className="text-neutral-400" />
                        <h3 className="text-sm font-bold text-white">Verification Results</h3>
                        {summary && (
                            <div className="flex items-center gap-1.5 ml-2">
                                {summary.verified > 0 && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded text-emerald-400 bg-emerald-500/10">{summary.verified} ✓</span>}
                                {summary.issues_found > 0 && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded text-amber-400 bg-amber-500/10">{summary.issues_found} ⚠</span>}
                                {summary.unverifiable > 0 && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded text-red-400 bg-red-500/10">{summary.unverifiable} ✗</span>}
                            </div>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        {correctedCount > 1 && (
                            <button onClick={copyAllCorrected} className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-neutral-400 hover:text-white transition-all active:scale-95">
                                {copiedAll ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                                {copiedAll ? 'Copied!' : 'Copy All Corrected'}
                            </button>
                        )}
                        <span className="badge badge-blue">Result</span>
                    </div>
                </div>

                {/* Style detection badge */}
                {styleInfo && (
                    <div className="glass-card px-4 py-2 mb-3 flex items-center gap-3 shrink-0">
                        <Sparkles size={14} className="text-cyan-400" />
                        <span className="text-xs text-neutral-400">
                            {styleInfo.auto_detected ? 'Detected' : 'Selected'} style:
                        </span>
                        <span className="text-xs font-bold text-white uppercase">{styleInfo.style}</span>
                        {styleInfo.auto_detected && (
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                                styleInfo.confidence >= 70 ? 'text-emerald-400 bg-emerald-500/10' :
                                styleInfo.confidence >= 40 ? 'text-amber-400 bg-amber-500/10' :
                                'text-red-400 bg-red-500/10'
                            }`}>
                                {styleInfo.confidence}% confidence
                            </span>
                        )}
                        {styleInfo.evidence?.length > 0 && (
                            <span className="text-[9px] text-neutral-600 truncate max-w-[300px]" title={styleInfo.evidence.join('; ')}>
                                {styleInfo.evidence[0]}
                            </span>
                        )}
                    </div>
                )}

                {/* Results content */}
                <div className="flex-1 overflow-y-auto min-h-0">
                    {!results && !isVerifying && (
                        <div className="h-full flex flex-col items-center justify-center text-neutral-700 space-y-3">
                            <ClipboardCheck size={40} />
                            <p className="text-sm font-medium">Paste references and click Verify</p>
                            <p className="text-xs text-neutral-600 max-w-sm text-center">Each reference will be checked against CrossRef & PubMed for metadata accuracy, and validated against your selected referencing style.</p>
                        </div>
                    )}

                    {isVerifying && !results && (
                        <div className="glass-card p-4 animate-pulse mb-3">
                            <div className="h-3 bg-white/5 rounded w-24 mb-3"></div>
                            <div className="h-2.5 bg-white/3 rounded w-full mb-1.5"></div>
                            <div className="h-2.5 bg-white/3 rounded w-3/4"></div>
                        </div>
                    )}

                    {results?.results && (
                        <div className="space-y-3">
                            {results.results.map((r, i) => (
                                <VerifierResultCard
                                    key={i}
                                    result={r}
                                    index={i}
                                    copiedId={copiedId}
                                    onCopy={copyRich}
                                    expanded={!!expandedCards[i]}
                                    onToggle={toggleCard}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}


// ─── Main Library View ───────────────────────────────────────────────────────

export default function LibraryView() {
    const [activeSubTab, setActiveSubTab] = useState('generator');
    const [style, setStyle] = useState('harvard');
    const [results, setResults] = useState([]);
    const [isDragging, setIsDragging] = useState(false);
    const [copiedId, setCopiedId] = useState(null);
    const [copiedAll, setCopiedAll] = useState(false);
    const [copiedWithDoi, setCopiedWithDoi] = useState(false);
    const [copiedWithoutDoi, setCopiedWithoutDoi] = useState(false);
    const [expandedMeta, setExpandedMeta] = useState({});
    const fileInputRef = useRef(null);
    const idCounter = useRef(0);
    const abortRef = useRef(null);
    const styleRef = useRef('harvard');
    const uploadPanelRef = useRef(null);
    const [inputHeight, setInputHeight] = useState(null);

    useEffect(() => {
        if (!uploadPanelRef.current) return;
        const ro = new ResizeObserver(([entry]) => setInputHeight(entry.contentRect.height + 32));
        ro.observe(uploadPanelRef.current);
        return () => ro.disconnect();
    }, []);

    const currentStyle = STYLES.find(s => s.id === style);
    useEffect(() => { styleRef.current = style; }, [style]);

    const processFile = useCallback(async (file, entryId, styleOverride, signal) => {
        const useStyle = styleOverride || style;
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch(`/api/extract-reference?style=${useStyle}`, { method: 'POST', body: formData, signal });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to extract reference');
            }
            const data = await res.json();
            // If style changed during extraction, reformat with current style
            const curStyle = styleRef.current;
            if (curStyle !== useStyle && data.metadata) {
                try {
                    const reformatRes = await fetch(`/api/reformat-reference?style=${curStyle}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ metadata: data.metadata }),
                        signal,
                    });
                    if (reformatRes.ok) {
                        const reformatted = await reformatRes.json();
                        setResults(prev => prev.map(r => r.id === entryId ? { ...r, loading: false, data: { ...data, ...reformatted, metadata: { ...data.metadata, ...reformatted.metadata } }, error: null } : r));
                        return;
                    }
                } catch (e) { if (e.name === 'AbortError') throw e; }
            }
            setResults(prev => prev.map(r => r.id === entryId ? { ...r, loading: false, data, error: null } : r));
        } catch (err) {
            if (err.name === 'AbortError') {
                setResults(prev => prev.map(r => r.id === entryId && r.loading ? { ...r, loading: false, error: 'Cancelled' } : r));
                return;
            }
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
        const controller = new AbortController();
        abortRef.current = controller;
        await Promise.allSettled(
            newEntries.map(entry => processFile(entry.file, entry.id, null, controller.signal))
        );
        abortRef.current = null;
    }, [processFile]);

    const handleStop = useCallback(() => {
        abortRef.current?.abort();
        abortRef.current = null;
    }, []);

    const handleAiRetry = useCallback(async (id) => {
        const target = results.find(r => r.id === id);
        if (!target || !target.file || !target.data?.metadata) return;

        setResults(prev => prev.map(r => r.id === id ? { ...r, aiRetrying: true, error: null } : r));

        try {
            const formData = new FormData();
            formData.append('file', target.file);
            formData.append('metadata', JSON.stringify(target.data.metadata));
            formData.append('style', styleRef.current);

            const res = await fetch('/api/retry-ai-doi', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'AI extraction failed');
            }

            const updatedData = await res.json();
            
            setResults(prev => prev.map(r => r.id === id ? { 
                ...r, 
                aiRetrying: false, 
                data: { ...r.data, ...updatedData, metadata: { ...r.data.metadata, ...updatedData.metadata } },
                error: null
            } : r));

        } catch (err) {
            setResults(prev => prev.map(r => r.id === id ? { ...r, aiRetrying: false, error: err.message } : r));
        }
    }, [results]);

    const handleAiRetryAll = useCallback(() => {
        const toRetry = results.filter(r => r.data && !r.data.metadata?.doi && !r.aiRetrying);
        for (const r of toRetry) {
            handleAiRetry(r.id);
        }
    }, [results, handleAiRetry]);

    const handleStyleChange = useCallback(async (newStyle) => {
        setStyle(newStyle);
        // Reformat completed results using lightweight endpoint (no re-extraction)
        const toReformat = results.filter(r => r.data?.metadata);
        if (toReformat.length === 0) return;

        // Light loading state — keeps cards visible, just shows a subtle indicator
        setResults(prev => prev.map(r => r.data?.metadata ? { ...r, _reformatting: true } : r));

        // Reformat all in parallel (fast, no re-extraction)
        const updates = await Promise.all(toReformat.map(async (entry) => {
            try {
                const res = await fetch(`/api/reformat-reference?style=${newStyle}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ metadata: entry.data.metadata }),
                });
                if (!res.ok) throw new Error('Reformat failed');
                const data = await res.json();
                return { id: entry.id, data: { ...entry.data, ...data, metadata: { ...entry.data.metadata, ...data.metadata } }, ok: true };
            } catch {
                return { id: entry.id, ok: false };
            }
        }));

        setResults(prev => prev.map(r => {
            const u = updates.find(x => x.id === r.id);
            if (u?.ok) return { ...r, data: u.data, _reformatting: false };
            if (u) return { ...r, _reformatting: false };
            return r;
        }));
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

    const copyGroup = (items, setCopiedState) => {
        if (!items || items.length === 0) return;
        const allHtml = items.map(r => sanitizeHtml(r.data.formatted_html || r.data.formatted)).join('<br/>\n');
        const allPlain = items.map(r => stripHtml(r.data.formatted_html || r.data.formatted)).join('\n');
        navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([allHtml], { type: 'text/html' }), 'text/plain': new Blob([allPlain], { type: 'text/plain' }) })]).then(() => {
            setCopiedState(true);
            setTimeout(() => setCopiedState(false), 2000);
        });
    };

    const copyAll = () => {
        const completed = results.filter(r => r.data);
        copyGroup(completed, setCopiedAll);
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
    const cardProps = { copiedId, copyRich, removeResult, expandedMeta, toggleMeta, onAiRetry: handleAiRetry };
    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <header className="mb-4">
                <h1 className="text-3xl font-extrabold text-white mb-1">Reference Library</h1>
                <p className="text-sm text-neutral-500">Generate references from PDFs, verify an existing reference list, or format raw references.</p>
            </header>

            {/* Tab Toggle */}
            <div className="flex items-center gap-1 mb-4 bg-white/[0.03] p-1 rounded-xl w-fit border border-white/5">
                <button
                    onClick={() => setActiveSubTab('generator')}
                    className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-2 ${
                        activeSubTab === 'generator'
                            ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30 shadow-lg shadow-purple-500/10'
                            : 'text-neutral-500 hover:text-neutral-300 hover:bg-white/5 border border-transparent'
                    }`}
                >
                    <Upload size={14} />
                    Generator
                </button>
                <button
                    onClick={() => setActiveSubTab('verifier')}
                    className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-2 ${
                        activeSubTab === 'verifier'
                            ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-lg shadow-cyan-500/10'
                            : 'text-neutral-500 hover:text-neutral-300 hover:bg-white/5 border border-transparent'
                    }`}
                >
                    <ClipboardCheck size={14} />
                    Verifier
                </button>
                <button
                    onClick={() => setActiveSubTab('formatter')}
                    className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-2 ${
                        activeSubTab === 'formatter'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-lg shadow-emerald-500/10'
                            : 'text-neutral-500 hover:text-neutral-300 hover:bg-white/5 border border-transparent'
                    }`}
                >
                    <FileText size={14} />
                    Formatter
                </button>
            </div>

            {/* Generator Sub-View */}
            <div style={activeSubTab !== 'generator' ? { display: 'none' } : undefined} className="flex gap-3 flex-1 min-h-0 min-w-0 w-full">
                    {/* Upload Panel — fills height */}
                    <div ref={uploadPanelRef} className="glass-card flex flex-col overflow-hidden w-[340px] shrink-0 h-full border-l-4 border-l-purple-500/50 max-w-[40vw]">
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

                        <div className="p-4 flex flex-col flex-1 min-h-0">
                            <p className="text-xs text-neutral-600 mb-3 bg-white/3 p-2.5 rounded-lg border border-white/5 shrink-0">
                                Upload <strong className="text-neutral-400">PDF</strong>, <strong className="text-neutral-400">DOCX</strong>, or <strong className="text-neutral-400">DOC</strong> files.
                                Style: <strong className="text-neutral-400">{currentStyle.label}</strong>
                            </p>

                            {/* Drop Zone — fixed height */}
                            <div
                                onDrop={onDrop}
                                onDragOver={onDragOver}
                                onDragLeave={onDragLeave}
                                onClick={() => fileInputRef.current?.click()}
                                className={`shrink-0 h-[200px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging
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
                                <div className="flex flex-col flex-1 min-h-0 mt-4">
                                    <div className="space-y-1 flex-1 min-h-0 overflow-y-auto pr-1">
                                        {results.map(r => (
                                            <div key={r.id} className="flex items-center gap-2 text-xs px-3 py-1.5 bg-white/[0.03] rounded-lg border border-white/5">
                                                {r.loading ? <Loader2 size={12} className="text-purple-400 animate-spin shrink-0" /> : r._reformatting ? <Loader2 size={12} className="text-cyan-400 animate-spin shrink-0" /> :
                                                    r.error ? <AlertCircle size={12} className="text-red-400 shrink-0" /> :
                                                        <Check size={12} className="text-green-400 shrink-0" />}
                                                <span className={`truncate flex-1 ${r.error ? 'text-red-400' : 'text-neutral-400'}`}>{r.fileName}</span>
                                                <button onClick={(e) => { e.stopPropagation(); removeResult(r.id); }} className="text-neutral-600 hover:text-red-400 transition-colors shrink-0">
                                                    <X size={12} />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                    <div className="mt-3 flex items-center justify-between shrink-0">
                                        {loadingCount > 0 && (
                                            <button onClick={handleStop} className="text-[10px] font-bold uppercase tracking-wider text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 px-2.5 py-1.5 rounded-lg flex items-center gap-1.5 transition-all active:scale-95">
                                                <StopCircle size={12} /> Stop All
                                            </button>
                                        )}
                                        <button onClick={clearAll} className="text-[10px] text-neutral-600 hover:text-red-400 ml-auto flex items-center gap-1 transition-colors">
                                            <Trash2 size={10} /> Clear all
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Results Panel — expands to fill remaining width */}
                    <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
                        {/* Header */}
                        <div className="glass-card px-5 py-3 flex items-center justify-between mb-3 shrink-0">
                            <div className="flex items-center gap-2">
                                <BookOpen size={16} className="text-neutral-400" />
                                <h3 className="text-sm font-bold text-white">Generated References</h3>
                                {completed.length > 0 && <span className="text-[10px] font-bold text-neutral-500 bg-white/5 px-2 py-0.5 rounded-full">{completed.length}</span>}
                            </div>
                            <div className="flex items-center gap-2">
                                {errors.length > 0 && (
                                    <button
                                        onClick={() => {
                                            for (const r of errors) {
                                                setResults(prev => prev.map(x => x.id === r.id ? { ...x, loading: true, error: null } : x));
                                                processFile(r.file, r.id);
                                            }
                                        }}
                                        className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-lg text-red-400 hover:text-red-300 transition-all active:scale-95"
                                    >
                                        <RefreshCw size={12} />
                                        Retry {errors.length > 1 ? `All (${errors.length})` : 'Failed'}
                                    </button>
                                )}
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
                                    <div className="flex items-center gap-1.5 shrink-0">
                                        <button
                                            onClick={() => {
                                                setResults(prev => prev.map(x => x.id === r.id ? { ...x, loading: true, error: null } : x));
                                                processFile(r.file, r.id);
                                            }}
                                            className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-neutral-400 hover:text-white transition-all active:scale-95"
                                            title="Retry extraction"
                                        >
                                            <RefreshCw size={10} />
                                            Retry
                                        </button>
                                        <button onClick={() => removeResult(r.id)} className="text-red-400/50 hover:text-red-300 p-1"><X size={12} /></button>
                                    </div>
                                </div>
                            ))}

                            {/* Single list or split view */}
                            {!shouldSplit ? (
                                <div className="space-y-3">
                                    {completed.map(r => <ReferenceCard key={r.id} r={r} {...cardProps} />)}
                                </div>
                            ) : (
                                <div className="flex gap-3 h-full min-h-0 pb-2">
                                    {/* With DOI — single panel */}
                                    <div className="flex-1 min-w-0 glass-card border-l-4 border-l-green-500/50 flex flex-col overflow-hidden">
                                        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0">
                                            <div className="flex items-center gap-2">
                                                <ShieldCheck size={14} className="text-green-400" />
                                                <h4 className="text-xs font-bold text-green-400 uppercase tracking-wider">Verified (DOI found)</h4>
                                                <span className="text-[10px] text-neutral-600 bg-white/5 px-1.5 py-0.5 rounded">{withDoi.length}</span>
                                            </div>
                                            <button onClick={() => copyGroup(withDoi, setCopiedWithDoi)} className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2 py-1 hover:bg-white/5 rounded text-neutral-500 hover:text-white transition-all">
                                                {copiedWithDoi ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                                                {copiedWithDoi ? 'Copied' : 'Copy'}
                                            </button>
                                        </div>
                                        <div className="flex-1 overflow-y-auto p-3 space-y-3">
                                            {withDoi.map(r => <ReferenceCard key={r.id} r={r} {...cardProps} />)}
                                        </div>
                                    </div>

                                    {/* Without DOI — single panel */}
                                    <div className="flex-1 min-w-0 glass-card border-l-4 border-l-amber-500/50 flex flex-col overflow-hidden">
                                        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0">
                                            <div className="flex items-center gap-2">
                                                <ShieldAlert size={14} className="text-amber-400" />
                                                <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wider">Needs Review (No DOI)</h4>
                                                <span className="text-[10px] text-neutral-600 bg-white/5 px-1.5 py-0.5 rounded">{withoutDoi.length}</span>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <button onClick={handleAiRetryAll} className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2 py-1 bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/30 rounded text-indigo-300 hover:text-indigo-200 transition-all">
                                                    <Sparkles size={12} />
                                                    Retry All with Advanced Method
                                                </button>
                                                <button onClick={() => copyGroup(withoutDoi, setCopiedWithoutDoi)} className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2 py-1 hover:bg-white/5 rounded text-neutral-500 hover:text-white transition-all">
                                                    {copiedWithoutDoi ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                                                    {copiedWithoutDoi ? 'Copied' : 'Copy'}
                                                </button>
                                            </div>
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


            {/* Verifier Sub-View */}
            <div style={activeSubTab !== 'verifier' ? { display: 'none' } : undefined} className="flex-1 min-h-0 flex flex-col">
                <VerifierSubView />
            </div>

            {/* Formatter Sub-View */}
            <div style={activeSubTab !== 'formatter' ? { display: 'none' } : undefined} className="flex-1 min-h-0 flex flex-col">
                <FormatterView />
            </div>
        </div>
    );
}
