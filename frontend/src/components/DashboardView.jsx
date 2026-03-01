import React from 'react';
import { UploadCloud, FileText, CheckCircle, ArrowRight } from 'lucide-react';

// Simple SVG sparkline component
function Sparkline({ data, color = 'rgba(255,255,255,0.4)', width = 100, height = 32 }) {
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;
    const points = data.map((v, i) =>
        `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`
    ).join(' ');
    return (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="opacity-60">
            <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={points} />
        </svg>
    );
}

export default function DashboardView({ onNavigate }) {
    const recentFiles = [
        { name: 'Novel_Draft.docx', status: 'Uploaded', badge: 'badge-green', progress: '32%' },
        { name: 'Essay_final.pdf', status: 'Analyzed', badge: 'badge-blue', progress: '100%' },
        { name: 'Outline_v3', status: 'Progress', badge: 'badge-purple', progress: '65%' },
        { name: 'Chapter_1_notes', status: 'Draft', badge: 'badge-amber', progress: '10%' },
    ];

    return (
        <div className="space-y-3">
            {/* ─── Bento Grid ─── */}
            <div className="grid grid-cols-12 gap-3 auto-rows-auto">

                {/* ── Project Overview ── */}
                <div className="col-span-12 md:col-span-5 glass-card p-6">
                    <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500 mb-5">Project Overview</h3>
                    <div className="flex gap-10">
                        <div>
                            <div className="stat-value">3</div>
                            <div className="text-xs uppercase tracking-widest text-neutral-600 mt-1 font-semibold">Current</div>
                        </div>
                        <div>
                            <div className="stat-value">12</div>
                            <div className="text-xs uppercase tracking-widest text-neutral-600 mt-1 font-semibold">Completed</div>
                        </div>
                    </div>
                </div>

                {/* ── Drag & Drop Upload ── */}
                <div className="col-span-12 md:col-span-4 glass-card p-6 flex flex-col items-center justify-center text-center group cursor-pointer transition-all"
                    onClick={() => onNavigate('verifier')}
                >
                    <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                        <UploadCloud size={32} className="text-neutral-400" />
                    </div>
                    <h3 className="text-base font-bold text-white mb-1">DRAG & DROP YOUR FILES</h3>
                    <button className="btn-accent text-xs py-2 px-5 mt-3 rounded-lg">UPLOAD FILES</button>
                    <p className="text-[10px] text-neutral-600 mt-2">Supports DOCX, PDF, TXT (Max 50MB)</p>
                </div>

                {/* ── Words Analyzed ── */}
                <div className="col-span-6 md:col-span-3 glass-card p-5 flex flex-col justify-between">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Words Analyzed</div>
                    <div className="flex items-end justify-between mt-3">
                        <div className="stat-value text-3xl">1.4M</div>
                        <Sparkline data={[30, 45, 38, 60, 55, 70, 65, 80, 75, 90]} width={70} height={28} />
                    </div>
                </div>

                {/* ── Document Status ── */}
                <div className="col-span-12 md:col-span-5 glass-card p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500">Document Status</h3>
                        <span className="text-xs text-neutral-600">{recentFiles.length} files</span>
                    </div>
                    <div className="space-y-3">
                        {recentFiles.map((file, i) => (
                            <div key={i} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <FileText size={16} className="text-neutral-500" />
                                    <span className="text-sm text-neutral-300 font-medium">{file.name}</span>
                                </div>
                                <span className={`badge ${file.badge}`}>{file.status}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* ── Revisions Made ── */}
                <div className="col-span-6 md:col-span-4 glass-card p-5">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-3">Revisions Made</div>
                    <div className="flex items-end justify-between">
                        <div className="stat-value text-3xl">412</div>
                        <Sparkline data={[20, 35, 30, 50, 45, 55, 60, 48, 70, 65]} width={70} height={28} />
                    </div>
                </div>

                {/* ── Insights Generated ── */}
                <div className="col-span-6 md:col-span-3 glass-card p-5">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-3">Insights Generated</div>
                    <div className="flex items-end justify-between">
                        <div className="stat-value text-3xl">98</div>
                        <Sparkline data={[10, 25, 20, 40, 35, 50, 45, 55, 60, 70]} width={70} height={28} />
                    </div>
                </div>

                {/* ── Recent Writing ── */}
                <div className="col-span-12 lg:col-span-8 glass-card p-6">
                    <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500 mb-5">Recent Writing</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {recentFiles.map((file, i) => (
                            <div key={i} className="glass-inner p-4 hover:bg-white/5 transition-colors cursor-pointer">
                                <div className="flex items-center gap-2 mb-3">
                                    <FileText size={14} className="text-neutral-400" />
                                    <span className="text-xs font-bold text-white truncate">{file.name.split('.')[0]}</span>
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className={`badge ${file.badge} !text-[8px] !px-2 !py-0.5`}>{file.status}</span>
                                    <span className="text-[10px] text-neutral-600">{file.progress}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* ── Writing Progress Chart ── */}
                <div className="col-span-12 lg:col-span-4 glass-card p-6">
                    <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500 mb-5">Writing Progress</h3>
                    <div className="flex items-end justify-center h-24">
                        <svg viewBox="0 0 200 80" className="w-full h-full">
                            <defs>
                                <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="rgba(255,255,255,0.15)" />
                                    <stop offset="100%" stopColor="rgba(255,255,255,0)" />
                                </linearGradient>
                            </defs>
                            <path d="M0,70 L30,55 L60,60 L90,40 L120,45 L150,25 L180,30 L200,15 L200,80 L0,80 Z" fill="url(#lineGrad)" />
                            <polyline fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                                points="0,70 30,55 60,60 90,40 120,45 150,25 180,30 200,15" />
                            {[[0, 70], [30, 55], [60, 60], [90, 40], [120, 45], [150, 25], [180, 30], [200, 15]].map(([x, y], i) => (
                                <circle key={i} cx={x} cy={y} r="3" fill="#000" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5" />
                            ))}
                        </svg>
                    </div>
                    <div className="flex justify-between mt-4 text-[10px] text-neutral-600 font-medium">
                        <span>Jan</span><span>Feb</span><span>Mar</span><span>Apr</span><span>May</span>
                    </div>
                </div>

            </div>

            {/* Quick Action Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <button onClick={() => onNavigate('verifier')} className="glass-card p-6 flex items-center gap-5 group cursor-pointer text-left">
                    <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform">
                        <CheckCircle size={24} className="text-neutral-400" />
                    </div>
                    <div className="flex-1">
                        <h3 className="text-base font-bold text-white mb-1">Citation Verifier</h3>
                        <p className="text-xs text-neutral-500 leading-relaxed">Upload a document and verify citations against references</p>
                    </div>
                    <ArrowRight size={18} className="text-neutral-700 group-hover:text-white transition-colors" />
                </button>

                <button onClick={() => onNavigate('formatter')} className="glass-card p-6 flex items-center gap-5 group cursor-pointer text-left">
                    <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform">
                        <FileText size={24} className="text-neutral-400" />
                    </div>
                    <div className="flex-1">
                        <h3 className="text-base font-bold text-white mb-1">Reference Formatter</h3>
                        <p className="text-xs text-neutral-500 leading-relaxed">Format raw references into Harvard style instantly</p>
                    </div>
                    <ArrowRight size={18} className="text-neutral-700 group-hover:text-white transition-colors" />
                </button>
            </div>
        </div>
    );
}
