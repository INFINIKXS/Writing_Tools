import React, { useState } from 'react';
import { Sparkles, Copy, Check, ArrowRightLeft, Quote, Loader2 } from 'lucide-react';

export default function FormatterView() {
    const [inputText, setInputText] = useState('');
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState([]);
    const [copiedIndex, setCopiedIndex] = useState(null);

    const handleFormat = async () => {
        if (!inputText.trim()) return;
        const refs = inputText.split('\n').filter(l => l.trim());
        if (!refs.length) return;
        setLoading(true); setResults([]);
        try {
            const res = await fetch('/api/format', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ references: refs }) });
            if (!res.ok) throw new Error('Formatting failed');
            const data = await res.json();
            setResults(data.formatted_references || []);
        } catch (err) { alert(err.message); } finally { setLoading(false); }
    };

    const copy = (text, idx) => { navigator.clipboard.writeText(text); setCopiedIndex(idx); setTimeout(() => setCopiedIndex(null), 2000); };
    const copyAll = () => { copy(results.map(r => r.formatted || r.original).join('\n\n'), 'all'); };

    return (
        <div className="animate-fade-in-up h-full flex flex-col">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">Harvard Formatter</h1>
                <p className="text-sm text-neutral-500">Transform messy bibliographies into perfect Harvard style using AI.</p>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 flex-1 min-h-[500px]">
                {/* Input */}
                <div className="glass-card flex flex-col overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Quote size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Raw References</h3>
                        </div>
                        <span className="badge badge-green">Input</span>
                    </div>
                    <div className="p-4 flex-1 flex flex-col">
                        <p className="text-xs text-neutral-600 mb-3 bg-white/3 p-2.5 rounded-lg border border-white/5">
                            Paste one reference per line for optimal results.
                        </p>
                        <textarea
                            className="flex-1 w-full bg-white/[0.02] border border-white/8 rounded-xl p-4 text-sm text-neutral-200 font-mono leading-relaxed resize-none outline-none focus:border-white/20 focus:ring-1 focus:ring-white/10 transition-colors placeholder-neutral-700"
                            placeholder="Smith, J. 2020. The history of science. London: Penguin.&#10;Bloggs, Joe (2019) 'Why I love science', Science Monthly, 14(2), pp.1-10."
                            spellCheck="false"
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                        />
                        <button onClick={handleFormat} disabled={loading || !inputText.trim()} className="btn-accent mt-4 w-full py-3.5 flex items-center justify-center gap-2 rounded-xl text-sm">
                            {loading ? (
                                <><Loader2 size={18} className="animate-spin" /> Formatting...</>
                            ) : (
                                <><Sparkles size={18} /> Format to Harvard Style</>
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
                            {results.length > 0 && (
                                <button onClick={copyAll} className="text-[10px] font-bold uppercase tracking-wider text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-colors">
                                    {copiedIndex === 'all' ? <Check size={12} className="text-white" /> : <Copy size={12} />}
                                    {copiedIndex === 'all' ? 'Copied' : 'Copy All'}
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="p-4 flex-1 overflow-y-auto">
                        {results.length === 0 && !loading && (
                            <div className="h-full flex flex-col items-center justify-center text-neutral-700 space-y-3">
                                <ArrowRightLeft size={40} />
                                <p className="text-sm font-medium">Awaiting input references...</p>
                            </div>
                        )}

                        {loading && (
                            <div className="space-y-3">
                                {[1, 2, 3].map(i => (
                                    <div key={i} className="bg-white/3 p-4 rounded-xl border border-white/5 animate-pulse">
                                        <div className="h-3 bg-white/5 rounded w-20 mb-3"></div>
                                        <div className="h-2.5 bg-white/3 rounded w-full mb-1.5"></div>
                                        <div className="h-2.5 bg-white/3 rounded w-3/4"></div>
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className="space-y-3">
                            {!loading && results.map((r, i) => (
                                <div key={i} className="glass-card p-4 border-l-4 border-l-white/15 group relative overflow-hidden">
                                    <div className="flex justify-between items-start mb-3">
                                        <span className="badge badge-green">{r.type || 'Processed'}</span>
                                        <button onClick={() => copy(r.formatted || r.original, i)} className="p-1.5 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all active:scale-90">
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
                                                <div className="text-[9px] font-bold uppercase tracking-widest text-neutral-500 mb-1">Harvard Style</div>
                                                <p className="text-sm text-white bg-white/[0.04] p-3 rounded-lg border border-white/8 leading-relaxed font-medium">{r.formatted}</p>
                                            </div>
                                        </>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
