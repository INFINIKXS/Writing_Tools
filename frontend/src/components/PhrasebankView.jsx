import React, { useState, useEffect, useCallback, useRef } from 'react';
import { BookOpen, Search, AlertCircle, Wand2, Loader2, Check, ChevronRight, Sparkles, ArrowRight, Copy, Tag, Hash } from 'lucide-react';

export default function PhrasebankView() {
    // ── State ────────────────────────────────────────────────────────
    const [categories, setCategories] = useState([]);
    const [selectedCategory, setSelectedCategory] = useState(null);
    const [categoryPhrases, setCategoryPhrases] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState(null);
    const [stats, setStats] = useState({ total_phrases: 0 });

    const [inputText, setInputText] = useState('');
    const [suggesting, setSuggesting] = useState(false);
    const [suggestions, setSuggestions] = useState(null);
    const [fitting, setFitting] = useState(null); // phrase_id being fitted
    const [fitResult, setFitResult] = useState(null);
    const [error, setError] = useState(null);
    const [copiedText, setCopiedText] = useState(null);
    const [loadingCategory, setLoadingCategory] = useState(false);

    const searchTimeout = useRef(null);

    // ── Initial load ─────────────────────────────────────────────────
    useEffect(() => { fetchCategories(); fetchStats(); }, []);

    const fetchCategories = async () => {
        try {
            const res = await fetch('/api/phrasebank/categories');
            if (res.ok) { const d = await res.json(); setCategories(d.categories || []); }
        } catch { }
    };

    const fetchStats = async () => {
        try {
            const res = await fetch('/api/phrasebank/stats');
            if (res.ok) { const d = await res.json(); setStats(d); }
        } catch { }
    };

    // ── Category browsing ────────────────────────────────────────────
    const handleCategoryClick = async (category) => {
        if (selectedCategory === category) { setSelectedCategory(null); setCategoryPhrases([]); return; }
        setSelectedCategory(category);
        setLoadingCategory(true);
        setSearchResults(null);
        setSearchQuery('');
        try {
            const res = await fetch(`/api/phrasebank/by-category?category=${encodeURIComponent(category)}`);
            if (res.ok) { const d = await res.json(); setCategoryPhrases(d.phrases || []); }
        } catch { }
        finally { setLoadingCategory(false); }
    };

    // ── Search (debounced) ───────────────────────────────────────────
    const handleSearchChange = (value) => {
        setSearchQuery(value);
        if (searchTimeout.current) clearTimeout(searchTimeout.current);
        if (!value.trim()) { setSearchResults(null); return; }
        searchTimeout.current = setTimeout(async () => {
            try {
                const res = await fetch(`/api/phrasebank/search?q=${encodeURIComponent(value.trim())}`);
                if (res.ok) { const d = await res.json(); setSearchResults(d.phrases || []); setSelectedCategory(null); }
            } catch { }
        }, 350);
    };

    // ── Suggest phrases ──────────────────────────────────────────────
    const handleSuggest = async () => {
        if (!inputText.trim()) return;
        setSuggesting(true); setSuggestions(null); setFitResult(null); setError(null);
        try {
            const res = await fetch('/api/phrasebank/suggest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: inputText.trim() }),
            });
            if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed to suggest phrases.'); }
            const d = await res.json();
            setSuggestions(d.phrases || []);
        } catch (err) { setError(err.message); }
        finally { setSuggesting(false); }
    };

    // ── Fit a phrase ─────────────────────────────────────────────────
    const handleFit = async (phrase) => {
        if (!inputText.trim()) { setError('Paste your text first, then click "Use This".'); return; }
        setFitting(phrase.id); setFitResult(null); setError(null);
        try {
            const res = await fetch('/api/phrasebank/fit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phrase_id: phrase.id, user_text: inputText.trim() }),
            });
            if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed to fit phrase.'); }
            setFitResult(await res.json());
        } catch (err) { setError(err.message); }
        finally { setFitting(null); }
    };

    // ── Copy helper ──────────────────────────────────────────────────
    const copyText = (text, id) => {
        navigator.clipboard.writeText(text).then(() => {
            setCopiedText(id);
            setTimeout(() => setCopiedText(null), 2000);
        });
    };

    // ── Which phrases to show in the left panel ──────────────────────
    const displayPhrases = searchResults !== null ? searchResults : (selectedCategory ? categoryPhrases : []);
    const displayLabel = searchResults !== null ? `Search: "${searchQuery}"` : selectedCategory || null;

    // ── Category color map ───────────────────────────────────────────
    const catColors = {
        'Stating the Aim': 'blue',
        'Reviewing the Literature': 'purple',
        'Identifying a Gap': 'red',
        'Defining Terms': 'amber',
        'Describing Methodology': 'cyan',
        'Presenting Results': 'green',
        'Discussing Implications': 'orange',
        'Hedging & Qualifying': 'yellow',
        'Comparing & Contrasting': 'pink',
        'Concluding': 'emerald',
        'General Transitions': 'neutral',
    };
    const getColor = (cat) => catColors[cat] || 'blue';

    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <header className="mb-5">
                <h1 className="text-3xl font-extrabold text-white mb-1 flex items-center gap-2">
                    <BookOpen size={28} className="text-blue-400" />
                    Academic Phrasebank
                </h1>
                <p className="text-sm text-neutral-500">
                    Browse {stats.total_phrases?.toLocaleString() || 0} curated academic templates. Search, explore by category, or let AI suggest the best match for your text.
                </p>
            </header>

            <div className="flex gap-3 flex-1 min-h-0 min-w-0 w-full">

                {/* ═══ LEFT: Category Browser + Search ═══ */}
                <div className="glass-card flex flex-col overflow-hidden w-[320px] shrink-0 self-stretch border-l-4 border-l-blue-500/50 max-w-[35vw]">
                    {/* Header */}
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <BookOpen size={16} className="text-blue-400" />
                            <h3 className="text-sm font-bold text-white">Phrase Bank</h3>
                        </div>
                        {stats.total_phrases > 0 && (
                            <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/20">
                                {stats.total_phrases.toLocaleString()} phrases
                            </span>
                        )}
                    </div>

                    {/* Search bar */}
                    <div className="px-4 pt-3 pb-2">
                        <div className="flex items-center gap-2 bg-white/[0.03] border border-white/8 rounded-xl px-3 py-2 focus-within:border-white/20 transition-colors">
                            <Search size={14} className="text-neutral-600 shrink-0" />
                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => handleSearchChange(e.target.value)}
                                placeholder="Search phrases..."
                                className="bg-transparent text-sm text-neutral-300 placeholder-neutral-600 outline-none w-full"
                            />
                        </div>
                    </div>

                    {/* Category list or phrase results */}
                    <div className="flex-1 overflow-y-auto px-3 pb-3">
                        {displayPhrases.length > 0 ? (
                            /* Phrase list */
                            <div className="space-y-1.5 pt-1">
                                {displayLabel && (
                                    <div className="flex items-center justify-between px-2 py-1">
                                        <p className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider truncate">{displayLabel}</p>
                                        <button
                                            onClick={() => { setSearchResults(null); setSelectedCategory(null); setSearchQuery(''); setCategoryPhrases([]); }}
                                            className="text-[10px] text-neutral-600 hover:text-white transition-colors"
                                        >Clear</button>
                                    </div>
                                )}
                                {displayPhrases.map((p) => (
                                    <PhraseCard
                                        key={p.id}
                                        phrase={p}
                                        color={getColor(p.category)}
                                        onFit={() => handleFit(p)}
                                        fitting={fitting === p.id}
                                        compact
                                    />
                                ))}
                            </div>
                        ) : (
                            /* Category browser */
                            <div className="space-y-1 pt-1">
                                {categories.map(({ category, count }) => (
                                    <button
                                        key={category}
                                        onClick={() => handleCategoryClick(category)}
                                        className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-left transition-all duration-200 group
                                            ${selectedCategory === category
                                                ? 'bg-blue-500/10 border border-blue-500/20 text-white'
                                                : 'bg-white/[0.02] border border-transparent hover:bg-white/[0.05] hover:border-white/8 text-neutral-400 hover:text-white'}`}
                                    >
                                        <div className="flex items-center gap-2 min-w-0">
                                            <Tag size={12} className={`shrink-0 ${selectedCategory === category ? 'text-blue-400' : `text-${getColor(category)}-400/60`}`} />
                                            <span className="text-xs font-medium truncate">{category}</span>
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-[10px] font-bold text-neutral-600">{count}</span>
                                            <ChevronRight size={12} className={`text-neutral-700 transition-transform ${selectedCategory === category ? 'rotate-90' : 'group-hover:translate-x-0.5'}`} />
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                        {loadingCategory && (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 size={18} className="text-blue-400 animate-spin" />
                            </div>
                        )}
                    </div>
                </div>

                {/* ═══ RIGHT: Input + Suggestions + Fit Result ═══ */}
                <div className="flex-1 flex flex-col min-w-0 gap-4 min-h-0 overflow-y-auto">
                    {/* Input Area */}
                    <div className="glass-card p-5 shrink-0">
                        <div className="flex items-center gap-2 mb-3">
                            <Wand2 size={16} className="text-blue-400" />
                            <h3 className="text-sm font-bold text-white">Your Text</h3>
                        </div>
                        <textarea
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); handleSuggest(); } }}
                            placeholder={"Paste an academic sentence or paragraph here...\n\ne.g., 'We looked at how social media affects student attention spans in university settings.'\n\nCtrl+Enter to get phrase suggestions."}
                            className="w-full bg-white/[0.02] border border-white/8 rounded-xl p-4 text-sm text-neutral-200 leading-relaxed resize-none outline-none focus:border-white/20 transition-colors placeholder-neutral-700 h-[110px]"
                            spellCheck="false"
                        />
                        <div className="flex justify-end mt-3">
                            <button
                                onClick={handleSuggest}
                                disabled={suggesting || !inputText.trim()}
                                className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {suggesting
                                    ? <><Loader2 size={16} className="animate-spin" /> Finding phrases...</>
                                    : <><Sparkles size={16} /> Suggest Phrases</>}
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

                    {/* Suggestions */}
                    {suggestions && !suggesting && (
                        <div className="glass-card p-5 border-l-4 border-l-purple-500/50 shrink-0">
                            <p className="text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-3">
                                AI-Suggested Phrases ({suggestions.length})
                            </p>
                            {suggestions.length === 0 ? (
                                <p className="text-sm text-neutral-500">No relevant phrases found. Try different text or browse by category.</p>
                            ) : (
                                <div className="space-y-2">
                                    {suggestions.map((p) => (
                                        <PhraseCard
                                            key={p.id}
                                            phrase={p}
                                            color={getColor(p.category)}
                                            onFit={() => handleFit(p)}
                                            fitting={fitting === p.id}
                                            showReason
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Fit Result */}
                    {fitResult && !fitting && (
                        <div className="glass-card p-5 border-l-4 border-l-green-500/50 shrink-0 space-y-4">
                            <div className="flex items-center gap-2">
                                <Check size={16} className="text-green-400" />
                                <p className="text-[10px] font-bold text-green-400 uppercase tracking-wider">Fitted to Your Text</p>
                            </div>

                            {/* Template used */}
                            <div className="bg-white/[0.02] p-3 rounded-lg border border-white/5">
                                <p className="text-[10px] text-neutral-500 mb-1">Template used:</p>
                                <p className="text-xs text-neutral-400 italic">"{fitResult.template_used}"</p>
                            </div>

                            {/* Fitted versions */}
                            {fitResult.fitted_versions?.map((v, i) => (
                                <div key={i} className="bg-white/[0.02] p-4 rounded-xl border border-white/5 group">
                                    <div className="flex justify-between items-center mb-2">
                                        <p className="text-xs font-bold text-neutral-400">{v.name}</p>
                                        <button
                                            onClick={() => copyText(v.text, `fit-${i}`)}
                                            className="text-xs flex items-center gap-1 text-neutral-500 hover:text-green-400 transition-colors bg-white/5 px-2 py-1 rounded"
                                        >
                                            {copiedText === `fit-${i}`
                                                ? <><Check size={12} className="text-green-400" /> Copied</>
                                                : <><Copy size={12} /> Copy</>}
                                        </button>
                                    </div>
                                    <p className="text-sm text-neutral-200 leading-relaxed">{v.text}</p>
                                </div>
                            ))}

                            {/* Content mapping */}
                            {fitResult.content_extracted && (
                                <div className="bg-white/[0.02] p-3 rounded-lg border border-white/5">
                                    <p className="text-[10px] text-neutral-500 mb-2">Content mapped:</p>
                                    <div className="flex flex-wrap gap-2">
                                        {Object.entries(fitResult.content_extracted).map(([key, val]) => (
                                            <div key={key} className="flex items-center gap-1.5">
                                                <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">[{key}]</span>
                                                <span className="text-xs text-neutral-400">{val}</span>
                                            </div>
                                        ))}
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


// ── Phrase Card sub-component ────────────────────────────────────────

function PhraseCard({ phrase, color, onFit, fitting, compact, showReason }) {
    const colorClasses = {
        blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
        purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
        red: 'text-red-400 bg-red-500/10 border-red-500/20',
        amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
        cyan: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
        green: 'text-green-400 bg-green-500/10 border-green-500/20',
        orange: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
        yellow: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
        pink: 'text-pink-400 bg-pink-500/10 border-pink-500/20',
        emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
        neutral: 'text-neutral-400 bg-neutral-500/10 border-neutral-500/20',
    };
    const cc = colorClasses[color] || colorClasses.blue;

    // Highlight [X], [Y], [Z] placeholders
    const highlightTemplate = (text) => {
        return text.replace(/\[([A-Z])\]/g, '<span class="text-blue-400 font-semibold">[$1]</span>');
    };

    return (
        <div className={`bg-white/[0.02] border border-white/5 rounded-xl transition-all duration-200 hover:bg-white/[0.04] hover:border-white/10 ${compact ? 'p-3' : 'p-4'}`}>
            <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                    <p
                        className={`${compact ? 'text-xs' : 'text-sm'} text-neutral-200 leading-relaxed`}
                        dangerouslySetInnerHTML={{ __html: highlightTemplate(phrase.template) }}
                    />
                    {!compact && phrase.example && (
                        <p className="text-xs text-neutral-500 italic mt-1.5 leading-relaxed">e.g., "{phrase.example}"</p>
                    )}
                    {showReason && phrase.relevance_reason && (
                        <p className="text-[11px] text-purple-300/70 mt-1.5 flex items-start gap-1">
                            <Sparkles size={11} className="shrink-0 mt-0.5" />
                            {phrase.relevance_reason}
                        </p>
                    )}
                </div>
                <button
                    onClick={onFit}
                    disabled={fitting}
                    className={`shrink-0 text-[10px] font-bold px-2.5 py-1.5 rounded-lg border transition-all duration-200
                        ${fitting
                            ? 'text-blue-400 bg-blue-500/10 border-blue-500/20 cursor-wait'
                            : 'text-green-400 bg-green-500/10 border-green-500/20 hover:bg-green-500/20 hover:border-green-500/30'}`}
                >
                    {fitting ? <Loader2 size={12} className="animate-spin" /> : 'Use This'}
                </button>
            </div>
            <div className="flex items-center gap-2 mt-2">
                <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${cc}`}>
                    {phrase.category}
                </span>
                {phrase.subcategory && (
                    <span className="text-[9px] text-neutral-600">{phrase.subcategory}</span>
                )}
                {phrase.formality_level && (
                    <span className="text-[9px] text-neutral-700 bg-white/[0.03] px-1.5 py-0.5 rounded">
                        {phrase.formality_level}
                    </span>
                )}
            </div>
        </div>
    );
}
