import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Search, Upload, FileText, Loader2, X, Check, Trash2, ChevronDown, BookOpen, AlertCircle, Copy } from 'lucide-react';

export default function SearchView() {
    const [documents, setDocuments] = useState([]);
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [query, setQuery] = useState('');
    const [searching, setSearching] = useState(false);
    const [results, setResults] = useState(null);
    const [copiedIdx, setCopiedIdx] = useState(null);
    const fileInputRef = useRef(null);

    // Load indexed documents on mount
    useEffect(() => {
        fetchDocuments();
    }, []);

    const fetchDocuments = async () => {
        try {
            const res = await fetch('/api/search/documents');
            if (res.ok) {
                const data = await res.json();
                setDocuments(data.documents || []);
            }
        } catch { /* silent */ }
    };

    const handleUpload = useCallback(async (files) => {
        if (!files || files.length === 0) return;
        const pdfs = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfs.length === 0) return;

        setUploading(true);
        try {
            const formData = new FormData();
            pdfs.forEach(f => formData.append('files', f));
            const res = await fetch('/api/search/upload', { method: 'POST', body: formData });
            if (!res.ok) throw new Error('Upload failed');
            await fetchDocuments();
        } catch (err) {
            console.error('Upload error:', err);
        } finally {
            setUploading(false);
        }
    }, []);

    const handleDelete = async (docId) => {
        try {
            const res = await fetch(`/api/search/document/${docId}`, { method: 'DELETE' });
            if (res.ok) {
                setDocuments(prev => prev.filter(d => d.doc_id !== docId));
            }
        } catch { /* silent */ }
    };

    // Each non-empty line is a separate query
    const parseQueries = (text) => {
        return text
            .split(/\n/)
            .map(q => q.trim())
            .filter(q => q.length > 0);
    };

    const handleSearch = async () => {
        const queries = parseQueries(query);
        if (queries.length === 0) return;
        setSearching(true);
        setResults(null);
        try {
            const res = await fetch('/api/search/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ queries }),
            });
            if (!res.ok) throw new Error('Search failed');
            const data = await res.json();
            setResults(data);
        } catch (err) {
            console.error('Search error:', err);
        } finally {
            setSearching(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            handleSearch();
        }
    };

    const queryCount = parseQueries(query).length;

    const copySnippet = (text, idx) => {
        navigator.clipboard.writeText(text).then(() => {
            setCopiedIdx(idx);
            setTimeout(() => setCopiedIdx(null), 2000);
        });
    };

    const totalMatches = results?.groups?.reduce((sum, g) => sum + g.total, 0) || 0;

    const onDrop = useCallback((e) => { e.preventDefault(); setIsDragging(false); handleUpload(e.dataTransfer?.files); }, [handleUpload]);
    const onDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
    const onDragLeave = () => setIsDragging(false);

    return (
        <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col w-full overflow-hidden">
            <header className="mb-6">
                <h1 className="text-3xl font-extrabold text-white mb-1">Source Search</h1>
                <p className="text-sm text-neutral-500">Upload source PDFs and search for verbatim sentences across all documents.</p>
            </header>

            <div className="flex gap-3 flex-1 min-h-0 min-w-0 w-full">
                {/* Left Panel — Upload & Documents */}
                <div className="glass-card flex flex-col overflow-hidden w-[340px] shrink-0 self-start border-l-4 border-l-blue-500/50 max-w-[40vw]">
                    <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Upload size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Source Documents</h3>
                        </div>
                        {documents.length > 0 && (
                            <span className="text-[10px] font-bold text-neutral-500 bg-white/5 px-2 py-0.5 rounded-full">{documents.length}</span>
                        )}
                    </div>

                    <div className="p-4 flex flex-col">
                        <p className="text-xs text-neutral-600 mb-3 bg-white/3 p-2.5 rounded-lg border border-white/5">
                            Upload <strong className="text-neutral-400">PDF</strong> files to index for searching.
                        </p>

                        {/* Drop Zone */}
                        <div
                            onDrop={onDrop}
                            onDragOver={onDragOver}
                            onDragLeave={onDragLeave}
                            onClick={() => fileInputRef.current?.click()}
                            className={`h-[160px] flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all duration-300 ${isDragging
                                ? 'border-blue-400 bg-blue-500/10 scale-[1.02]'
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
                                    <Loader2 size={24} className="text-blue-400 animate-spin" />
                                    <p className="text-sm text-blue-400 font-medium">Indexing...</p>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-3">
                                    <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-300 ${isDragging ? 'bg-blue-500/20 border border-blue-400/30 scale-110' : 'bg-white/5 border border-white/10'}`}>
                                        <FileText size={24} className={isDragging ? 'text-blue-400' : 'text-neutral-600'} />
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
                            <div className="mt-3 space-y-1 max-h-[240px] overflow-y-auto">
                                {documents.map(doc => (
                                    <div key={doc.doc_id} className="flex items-center gap-2 text-xs px-3 py-2 bg-white/[0.03] rounded-lg border border-white/5 group">
                                        <FileText size={12} className="text-blue-400 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-neutral-300 truncate">{doc.filename}</p>
                                            <p className="text-[10px] text-neutral-600">{doc.total_pages} pages</p>
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
                    </div>
                </div>

                {/* Right Panel — Search & Results */}
                <div className="flex-1 flex flex-col min-w-0 self-start max-h-[calc(100vh-12rem)]">
                    {/* Search Bar */}
                    <div className="glass-card p-4 mb-3 shrink-0">
                        <div className="flex items-center gap-2 mb-3">
                            <Search size={16} className="text-neutral-400" />
                            <h3 className="text-sm font-bold text-white">Search</h3>
                            {queryCount > 1 && (
                                <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/20">
                                    {queryCount} queries
                                </span>
                            )}
                            {results && (
                                <span className="text-[10px] font-bold text-neutral-500 bg-white/5 px-2 py-0.5 rounded-full">
                                    {totalMatches} {totalMatches === 1 ? 'match' : 'matches'}
                                </span>
                            )}
                        </div>
                        <div className="flex gap-2">
                            <textarea
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder={"Paste sentences to find in your source documents...\n\nEach line is a separate search query.\nPress Ctrl+Enter to search."}
                                className="flex-1 bg-white/[0.02] border border-white/8 rounded-xl p-3 text-sm text-neutral-200 font-mono leading-relaxed resize-none outline-none focus:border-white/20 focus:ring-1 focus:ring-white/10 transition-colors placeholder-neutral-700 h-[100px]"
                                spellCheck="false"
                            />
                            <button
                                onClick={handleSearch}
                                disabled={searching || queryCount === 0 || documents.length === 0}
                                className="btn-accent px-5 rounded-xl text-sm font-semibold flex items-center gap-2 self-end h-[42px] shrink-0"
                            >
                                {searching ? (
                                    <><Loader2 size={16} className="animate-spin" /> Searching...</>
                                ) : (
                                    <><Search size={16} /> Find</>
                                )}
                            </button>
                        </div>
                        {documents.length === 0 && (
                            <p className="text-[10px] text-amber-400/70 mt-2">Upload PDF documents first to enable searching.</p>
                        )}
                    </div>

                    {/* Results */}
                    <div className="flex-1 overflow-y-auto min-h-0">
                        {/* Empty state */}
                        {!results && !searching && (
                            <div className="h-full flex flex-col items-center justify-center text-neutral-700 space-y-3">
                                <Search size={40} />
                                <p className="text-sm font-medium">Search results will appear here</p>
                            </div>
                        )}

                        {/* Loading */}
                        {searching && (
                            <div className="glass-card p-6 flex items-center justify-center gap-3 mb-3">
                                <Loader2 size={20} className="text-blue-400 animate-spin" />
                                <p className="text-sm text-neutral-400">Searching {queryCount} {queryCount === 1 ? 'query' : 'queries'} across {documents.length} documents...</p>
                            </div>
                        )}

                        {/* Grouped results */}
                        {results && results.groups && (
                            <div className="space-y-4">
                                {results.groups.map((group, gi) => (
                                    <div key={gi}>
                                        {/* Query header */}
                                        <div className="flex items-center gap-2 mb-2 px-1">
                                            <span className="text-[10px] font-bold text-neutral-600 uppercase tracking-wider">Query {results.groups.length > 1 ? `${gi + 1}` : ''}</span>
                                            <p className="text-xs text-neutral-400 truncate flex-1 font-mono bg-white/[0.03] px-2 py-1 rounded border border-white/5">
                                                {group.query.length > 120 ? group.query.slice(0, 120) + '...' : group.query}
                                            </p>
                                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${group.total > 0 ? 'text-green-400 bg-green-500/10' : 'text-neutral-600 bg-white/5'}`}>
                                                {group.total} {group.total === 1 ? 'match' : 'matches'}
                                            </span>
                                        </div>

                                        {/* No results for this query */}
                                        {group.total === 0 && (
                                            <div className="glass-card p-4 flex items-center gap-3 mb-2">
                                                <AlertCircle size={16} className="text-neutral-600" />
                                                <p className="text-xs text-neutral-500">No matches found for this query.</p>
                                            </div>
                                        )}

                                        {/* Results for this query */}
                                        {group.results.map((r, ri) => {
                                            const uniqueKey = `${gi}-${ri}`;
                                            return (
                                                <div key={uniqueKey} className="glass-card p-4 border-l-4 border-l-blue-500/50 overflow-hidden mb-2">
                                                    <div className="flex items-center justify-between mb-3">
                                                        <div className="flex items-center gap-2">
                                                            <FileText size={14} className="text-blue-400" />
                                                            <span className="text-sm font-semibold text-white truncate">{r.filename}</span>
                                                            <span className="badge badge-blue">Page {r.page_num}</span>
                                                        </div>
                                                        <button
                                                            onClick={() => copySnippet(r.snippet, uniqueKey)}
                                                            className="p-1.5 bg-white/3 hover:bg-white/10 rounded-lg text-neutral-500 hover:text-white transition-all active:scale-90 flex items-center gap-1"
                                                        >
                                                            {copiedIdx === uniqueKey ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                                                            <span className="text-[10px] font-bold uppercase tracking-wider">
                                                                {copiedIdx === uniqueKey ? 'Copied' : 'Copy'}
                                                            </span>
                                                        </button>
                                                    </div>

                                                    {/* Snippet with highlighted match */}
                                                    <div className="text-sm text-neutral-300 bg-white/[0.03] p-3 rounded-lg border border-white/5 font-mono leading-relaxed break-words">
                                                        {r.match_start >= 0 ? (
                                                            <>
                                                                <span className="text-neutral-500">{r.snippet.slice(0, r.match_start)}</span>
                                                                <mark className="bg-blue-500/30 text-blue-200 rounded px-0.5">{r.snippet.slice(r.match_start, r.match_end)}</mark>
                                                                <span className="text-neutral-500">{r.snippet.slice(r.match_end)}</span>
                                                            </>
                                                        ) : (
                                                            <span className="text-neutral-500">{r.snippet}</span>
                                                        )}
                                                    </div>

                                                    <div className="mt-2 flex items-center gap-2">
                                                        <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border text-green-400 bg-green-500/10 border-green-500/20">
                                                            Match Found
                                                        </span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
