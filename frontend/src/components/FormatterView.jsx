import React, { useState, useCallback, useRef } from 'react';
import { Sparkles, Copy, Check, ArrowRightLeft, Quote, Loader2, ChevronDown, AlertTriangle, Shield, ShieldCheck, ShieldAlert } from 'lucide-react';

const STYLES = [
    { id: 'harvard', label: 'Harvard', desc: 'Cite Them Right (10th ed.)' },
    { id: 'apa', label: 'APA 7th', desc: 'Publication Manual (7th ed.)' },
    { id: 'vancouver', label: 'Vancouver', desc: 'ICMJE / Citing Medicine' },
];

export default function FormatterView() {
    const [inputText, setInputText] = useState('');
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState([]);
    const [copiedIndex, setCopiedIndex] = useState(null);
    const [style, setStyle] = useState('harvard');
    const [progress, setProgress] = useState(null); // { current, total }
    const abortRef = useRef(null);

    const currentStyle = STYLES.find(s => s.id === style);

    const handleFormat = async () => {
        if (!inputText.trim()) return;
        const refs = inputText.split('\n').filter(l => l.trim());
        if (!refs.length) return;

        setLoading(true);
        setResults([]);
        setProgress({ current: 0, total: refs.length });

        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const res = await fetch('/api/format', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ references: refs, style }),
                signal: controller.signal,
            });

            if (!res.ok) throw new Error('Formatting failed');

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));

                        if (event.stage === 'processing') {
                            setProgress({ current: (event.data?.index ?? 0) + 1, total: refs.length });
                        }

                        if (event.stage === 'ref_result' && event.data?.result) {
                            const result = event.data.result;
                            setResults(prev => {
                                const next = [...prev];
                                next[event.data.index] = result;
                                return next;
                            });
                            setProgress({ current: (event.data.index ?? 0) + 1, total: refs.length });
                        }

                        if (event.stage === 'complete') {
                            setProgress(null);
                        }
                    } catch { /* skip malformed events */ }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                alert(err.message);
            }
        } finally {
            setLoading(false);
            setProgress(null);
            abortRef.current = null;
        }
    };

    const handleStyleChange = useCallback(async (newStyle) => {
        setStyle(newStyle);
        // Reformat existing results instantly via lightweight endpoint (no AI)
        const toReformat = results.filter(r => r.metadata);
        if (toReformat.length === 0) return;
        setResults(prev => prev.map(r => r.metadata ? { ...r, _reformatting: true } : r));
        const updated = await Promise.all(toReformat.map(async (r) => {
            try {
                const res = await fetch(`/api/reformat-reference?style=${newStyle}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ metadata: r.metadata }),
                });
                if (!res.ok) throw new Error('Reformat failed');
                const data = await res.json();
                return { ...r, ...data, original: r.original, _reformatting: false };
            } catch {
                return { ...r, _reformatting: false };
            }
        }));
        setResults(prev => {
            const map = new Map(updated.map((u, i) => [toReformat[i].original, u]));
            return prev.map(r => map.get(r.original) || r);
        });
    }, [results]);

    const sanitizeHtml = (html) => html.replace(/<(?!\/?(?:i|em)\b)[^>]*>/gi, '');
    const stripHtml = (html) => html.replace(/<\/?[^>]*>/g, '');

    const copyRich = (htmlText, idx) => {
        const html = sanitizeHtml(htmlText);
        const plain = stripHtml(htmlText);
        const htmlBlob = new Blob([html], { type: 'text/html' });
        const textBlob = new Blob([plain], { type: 'text/plain' });
        navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })]).then(() => {
            setCopiedIndex(idx);
            setTimeout(() => setCopiedIndex(null), 2000);
        });
    };

    const copyAll = () => {
        const allHtml = results.filter(Boolean).map(r => sanitizeHtml(r.formatted_html || r.formatted || r.original)).join('<br><br>');
        const allPlain = results.filter(Boolean).map(r => stripHtml(r.formatted_html || r.formatted || r.original)).join('\n\n');
        const htmlBlob = new Blob([allHtml], { type: 'text/html' });
        const textBlob = new Blob([allPlain], { type: 'text/plain' });
        navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })]).then(() => {
            setCopiedIndex('all');
            setTimeout(() => setCopiedIndex(null), 2000);
        });
    };

    const completedResults = results.filter(Boolean);

    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 flex-1 min-h-0">
                {/* Input */}
                <div className="glass-card flex flex-col overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Quote size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Raw References</h3>
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
                            Paste one reference per line. Include DOIs for verification. Style: <strong className="text-neutral-400">{currentStyle.label}</strong> ({currentStyle.desc})
                        </p>
                        <textarea
                            className="flex-1 w-full bg-white/[0.02] border border-white/8 rounded-xl p-4 text-sm text-neutral-200 font-mono leading-relaxed resize-none outline-none focus:border-white/20 focus:ring-1 focus:ring-white/10 transition-colors placeholder-neutral-700"
                            placeholder={"Smith, J. 2020. The history of science. London: Penguin.\nBloggs, Joe (2019) 'Why I love science', Science Monthly, 14(2), pp.1-10. doi: 10.1234/example"}
                            spellCheck="false"
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                        />
                        <button onClick={handleFormat} disabled={loading || !inputText.trim()} className="btn-accent mt-4 w-full py-3.5 flex items-center justify-center gap-2 rounded-xl text-sm">
                            {loading ? (
                                <><Loader2 size={18} className="animate-spin" /> {progress ? `Processing ${progress.current}/${progress.total}...` : 'Starting...'}</>
                            ) : (
                                <><Sparkles size={18} /> Format to {currentStyle.label} Style</>
                            )}
                        </button>
                    </div>
                </div>

                {/* Output */}
                <div className="glass-card flex flex-col overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between bg-white/[0.01]">
                        <div className="flex items-center gap-2">
                            <Check size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Formatted Output</h3>
                        </div>
                        <div className="flex gap-2 items-center">
                            <span className="badge badge-blue">Result</span>
                            {completedResults.length > 0 && (
                                <button onClick={copyAll} className="text-[10px] font-bold uppercase tracking-wider text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-colors">
                                    {copiedIndex === 'all' ? <Check size={12} className="text-white" /> : <Copy size={12} />}
                                    {copiedIndex === 'all' ? 'Copied' : 'Copy All'}
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="p-4 flex-1 overflow-y-auto">
                        {completedResults.length === 0 && !loading && (
                            <div className="h-full flex flex-col items-center justify-center text-neutral-700 space-y-3">
                                <ArrowRightLeft size={40} />
                                <p className="text-sm font-medium">Awaiting input references...</p>
                            </div>
                        )}

                        <div className="space-y-3">
                            {results.map((r, i) => {
                                // Slot is null while still loading this index
                                if (!r) {
                                    return (
                                        <div key={i} className="bg-white/3 p-4 rounded-xl border border-white/5 animate-pulse">
                                            <div className="h-3 bg-white/5 rounded w-20 mb-3"></div>
                                            <div className="h-2.5 bg-white/3 rounded w-full mb-1.5"></div>
                                            <div className="h-2.5 bg-white/3 rounded w-3/4"></div>
                                        </div>
                                    );
                                }

                                const corrections = r.corrections || [];
                                const apiVerified = r.api_verified;

                                return (
                                    <div key={i} className={`glass-card p-4 border-l-4 ${apiVerified ? 'border-l-emerald-500/40' : 'border-l-white/15'} group relative overflow-hidden animate-fade-in-up`}>
                                        <div className="flex justify-between items-start mb-3">
                                            <div className="flex items-center gap-2">
                                                <span className="badge badge-green">{r.type || 'Processed'}</span>
                                                {apiVerified && (
                                                    <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-emerald-400/80 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-md">
                                                        <ShieldCheck size={10} /> {r.api_source}
                                                    </span>
                                                )}
                                                {!apiVerified && !r.error && (
                                                    <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-neutral-500 bg-white/5 border border-white/10 px-2 py-0.5 rounded-md">
                                                        <Shield size={10} /> regex only
                                                    </span>
                                                )}
                                            </div>
                                            <button onClick={() => copyRich(r.formatted_html || r.formatted || r.original, i)} className="p-1.5 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all active:scale-90">
                                                {copiedIndex === i ? <Check size={14} className="text-white" /> : <Copy size={14} />}
                                            </button>
                                        </div>
                                        {r.error ? (
                                            <div className="text-red-400 text-xs bg-red-500/10 p-2.5 rounded border border-red-500/20">Error: {r.error}</div>
                                        ) : (
                                            <>
                                                <div className="mb-3">
                                                    <div className="text-[9px] font-bold uppercase tracking-widest text-neutral-600 mb-1">Original</div>
                                                    <p className="text-xs text-neutral-500 font-mono bg-white/3 p-2.5 rounded-lg border border-white/5 line-clamp-2">{r.original}</p>
                                                </div>
                                                <div>
                                                    <div className="text-[9px] font-bold uppercase tracking-widest text-neutral-500 mb-1">{currentStyle.label} Style</div>
                                                    <div className="text-sm text-white bg-white/[0.04] p-3 rounded-lg border border-white/8 leading-relaxed font-medium" dangerouslySetInnerHTML={{ __html: sanitizeHtml(r.formatted_html || r.formatted) }} />
                                                </div>

                                                {/* Corrections */}
                                                {corrections.length > 0 && (
                                                    <div className="mt-3 space-y-1.5">
                                                        {corrections.map((c, ci) => (
                                                            <div key={ci} className="flex items-start gap-2 text-xs bg-amber-500/8 border border-amber-500/15 rounded-lg p-2.5">
                                                                <AlertTriangle size={13} className="text-amber-400 mt-0.5 shrink-0" />
                                                                <div>
                                                                    <span className="font-semibold text-amber-300 capitalize">{c.field}:</span>{' '}
                                                                    <span className="text-neutral-400">{c.detail}</span>
                                                                    {c.user_value && c.correct_value && (
                                                                        <div className="mt-1 text-[10px] font-mono">
                                                                            <span className="text-red-400/70 line-through">{c.user_value}</span>
                                                                            <span className="text-neutral-600 mx-1.5">→</span>
                                                                            <span className="text-emerald-400/80">{c.correct_value}</span>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                );
                            })}

                            {/* Loading placeholders for remaining items */}
                            {loading && progress && Array.from({ length: Math.max(0, progress.total - results.length) }).map((_, i) => (
                                <div key={`loading-${i}`} className="bg-white/3 p-4 rounded-xl border border-white/5 animate-pulse">
                                    <div className="h-3 bg-white/5 rounded w-20 mb-3"></div>
                                    <div className="h-2.5 bg-white/3 rounded w-full mb-1.5"></div>
                                    <div className="h-2.5 bg-white/3 rounded w-3/4"></div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
