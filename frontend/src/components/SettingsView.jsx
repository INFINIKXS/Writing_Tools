import React, { useState, useEffect, useCallback } from 'react';
import { Key, RefreshCw, Clock, Activity, Shield, AlertTriangle } from 'lucide-react';

const BACKEND_URL = 'http://localhost:8000';

export default function SettingsView() {
    const [usage, setUsage] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [countdown, setCountdown] = useState('');

    const fetchUsage = useCallback(async () => {
        try {
            setLoading(true);
            const res = await fetch(`${BACKEND_URL}/api-key-usage`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setUsage(data);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    // Fetch on mount + auto-refresh every 30s
    useEffect(() => {
        fetchUsage();
        const interval = setInterval(fetchUsage, 30000);
        return () => clearInterval(interval);
    }, [fetchUsage]);

    // Countdown to midnight reset
    useEffect(() => {
        const updateCountdown = () => {
            const now = new Date();
            const midnight = new Date(now);
            midnight.setHours(24, 0, 0, 0);
            const diff = midnight - now;
            const h = Math.floor(diff / 3600000);
            const m = Math.floor((diff % 3600000) / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            setCountdown(`${h}h ${m}m ${s}s`);
        };
        updateCountdown();
        const timer = setInterval(updateCountdown, 1000);
        return () => clearInterval(timer);
    }, []);

    const quotaLimit = usage?.quota_limit_per_key || 20;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-white">Settings</h2>
                    <p className="text-neutral-500 text-sm mt-1">API key management & usage monitoring</p>
                </div>
                <button
                    onClick={fetchUsage}
                    disabled={loading}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 hover:text-white transition-all duration-200 text-sm font-medium disabled:opacity-40"
                >
                    <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                    Refresh
                </button>
            </div>

            {/* Error Banner */}
            {error && (
                <div className="glass-card-static p-4 border-amber-500/20 flex items-center gap-3">
                    <AlertTriangle size={18} className="text-amber-400 shrink-0" />
                    <div>
                        <p className="text-amber-400 text-sm font-medium">Connection Error</p>
                        <p className="text-neutral-500 text-xs mt-0.5">Could not fetch API key usage: {error}</p>
                    </div>
                </div>
            )}

            {/* Stats Overview Cards */}
            {usage && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {/* Total Keys */}
                    <div className="glass-card p-5">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                                <Key size={16} className="text-blue-400" />
                            </div>
                            <span className="text-neutral-500 text-xs font-semibold uppercase tracking-wider">Total Keys</span>
                        </div>
                        <p className="text-3xl font-extrabold text-white">{usage.total_keys}</p>
                        <p className="text-neutral-600 text-xs mt-1">{usage.service} API</p>
                    </div>

                    {/* Available */}
                    <div className="glass-card p-5">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <Shield size={16} className="text-emerald-400" />
                            </div>
                            <span className="text-neutral-500 text-xs font-semibold uppercase tracking-wider">Available</span>
                        </div>
                        <p className="text-3xl font-extrabold text-white">{usage.available_keys}</p>
                        <p className="text-neutral-600 text-xs mt-1">Ready to use</p>
                    </div>

                    {/* Requests Today */}
                    <div className="glass-card p-5">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-9 h-9 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                                <Activity size={16} className="text-purple-400" />
                            </div>
                            <span className="text-neutral-500 text-xs font-semibold uppercase tracking-wider">Requests Today</span>
                        </div>
                        <p className="text-3xl font-extrabold text-white">{usage.total_requests_today || 0}</p>
                        <p className="text-neutral-600 text-xs mt-1">Across all keys</p>
                    </div>

                    {/* Reset Countdown */}
                    <div className="glass-card p-5">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                                <Clock size={16} className="text-amber-400" />
                            </div>
                            <span className="text-neutral-500 text-xs font-semibold uppercase tracking-wider">Quota Resets</span>
                        </div>
                        <p className="text-2xl font-extrabold text-white font-mono">{countdown}</p>
                        <p className="text-neutral-600 text-xs mt-1">Until midnight reset</p>
                    </div>
                </div>
            )}

            {/* Per-Key Usage Details */}
            {usage && usage.keys && usage.keys.length > 0 && (
                <div className="glass-card-static p-6">
                    <div className="flex items-center justify-between mb-5">
                        <h3 className="text-lg font-bold text-white">API Key Usage</h3>
                        <span className="badge badge-blue">
                            {quotaLimit} calls/key/model/day
                        </span>
                    </div>

                    <div className="space-y-4">
                        {usage.keys.map((key, idx) => {
                            const totalUsage = key.quota_used || 0;
                            const isActive = usage.current_key === key.key_suffix;
                            const isExhausted = key.exhausted;
                            const exhaustedModels = key.exhausted_models || [];

                            return (
                                <div
                                    key={idx}
                                    className={`glass-inner p-4 transition-all duration-300 ${isActive ? 'border-emerald-500/30 bg-emerald-500/5' : ''
                                        } ${isExhausted ? 'border-red-500/20 bg-red-500/5 opacity-60' : ''}`}
                                >
                                    {/* Key Header */}
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="flex items-center gap-3">
                                            <div className={`w-2.5 h-2.5 rounded-full ${isExhausted ? 'bg-red-500' : isActive ? 'bg-emerald-400 animate-pulse' : 'bg-neutral-600'
                                                }`} />
                                            <span className="text-white font-semibold font-mono text-sm">{key.key_suffix}</span>
                                            {isActive && (
                                                <span className="badge badge-green text-[9px]">Active</span>
                                            )}
                                            {isExhausted && (
                                                <span className="badge badge-amber text-[9px]">Exhausted</span>
                                            )}
                                        </div>
                                        <span className="text-neutral-500 text-xs font-mono">
                                            {totalUsage} total calls
                                        </span>
                                    </div>

                                    {/* Per-Model Usage Bars */}
                                    {key.model_usage && Object.keys(key.model_usage).length > 0 ? (
                                        <div className="space-y-2.5">
                                            {Object.entries(key.model_usage).map(([model, count]) => {
                                                const percent = Math.min((count / quotaLimit) * 100, 100);
                                                const isModelExhausted = exhaustedModels.includes(model);
                                                return (
                                                    <div key={model}>
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-neutral-400 text-xs truncate max-w-[60%]">{model}</span>
                                                            <span className={`text-xs font-mono font-semibold ${isModelExhausted ? 'text-red-400' : percent >= 80 ? 'text-amber-400' : 'text-neutral-300'
                                                                }`}>
                                                                {count}/{quotaLimit}
                                                            </span>
                                                        </div>
                                                        <div className="w-full h-1.5 rounded-full bg-white/5 overflow-hidden">
                                                            <div
                                                                className={`h-full rounded-full transition-all duration-500 ${isModelExhausted
                                                                        ? 'bg-red-500'
                                                                        : percent >= 80
                                                                            ? 'bg-gradient-to-r from-amber-500 to-red-500'
                                                                            : 'bg-gradient-to-r from-emerald-500 to-emerald-400'
                                                                    }`}
                                                                style={{ width: `${percent}%` }}
                                                            />
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    ) : (
                                        <p className="text-neutral-600 text-xs italic">No usage recorded yet</p>
                                    )}

                                    {/* Exhausted Models Tags */}
                                    {exhaustedModels.length > 0 && (
                                        <div className="flex flex-wrap gap-1.5 mt-3">
                                            {exhaustedModels.map((m) => (
                                                <span key={m} className="text-[10px] px-2 py-0.5 rounded-md bg-red-500/10 text-red-400 border border-red-500/20 font-mono">
                                                    {m}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Single Key Mode Notice */}
            {usage && usage.message && (
                <div className="glass-card-static p-5 flex items-start gap-3">
                    <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
                    <div>
                        <p className="text-white text-sm font-medium">Single Key Mode</p>
                        <p className="text-neutral-500 text-xs mt-1">
                            {usage.message}. Add multiple keys in <code className="text-neutral-400 bg-white/5 px-1.5 py-0.5 rounded text-[11px]">GOOGLE_API_KEYS</code> in your <code className="text-neutral-400 bg-white/5 px-1.5 py-0.5 rounded text-[11px]">.env</code> file to enable rotation.
                        </p>
                    </div>
                </div>
            )}

            {/* Empty State */}
            {usage && (!usage.keys || usage.keys.length === 0) && !usage.message && (
                <div className="glass-card-static p-12 text-center">
                    <div className="text-5xl mb-4 opacity-20">🔑</div>
                    <h3 className="text-lg font-bold text-white mb-2">No API Keys Configured</h3>
                    <p className="text-neutral-500 text-sm max-w-md mx-auto">
                        Add your Google API keys to <code className="text-neutral-400 bg-white/5 px-1.5 py-0.5 rounded text-xs">backend/.env</code> as <code className="text-neutral-400 bg-white/5 px-1.5 py-0.5 rounded text-xs">GOOGLE_API_KEYS=key1,key2,key3</code>
                    </p>
                </div>
            )}

            {/* Loading Skeleton */}
            {loading && !usage && (
                <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="glass-card p-5 animate-pulse">
                                <div className="w-20 h-3 bg-white/5 rounded mb-4" />
                                <div className="w-12 h-8 bg-white/5 rounded" />
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
