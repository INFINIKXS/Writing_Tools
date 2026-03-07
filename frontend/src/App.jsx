import React, { useState, useMemo } from 'react';
import { LayoutDashboard, CheckCircle, FileText, BookOpen, Search, Settings } from 'lucide-react';
import Logo from './components/Logo';
import DashboardView from './components/DashboardView';
import VerifierView from './components/VerifierView';
import FormatterView from './components/FormatterView';
import LibraryView from './components/LibraryView';
import SearchView from './components/SearchView';
import SettingsView from './components/SettingsView';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'verifier', label: 'Verifier', icon: CheckCircle },
  { id: 'formatter', label: 'Formatter', icon: FileText },
  { id: 'library', label: 'Library', icon: BookOpen },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'settings', label: 'Settings', icon: Settings },
];

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

  // All views that should stay mounted (state persists, processes run in background)
  const PERSISTENT_VIEWS = useMemo(() => [
    { id: 'dashboard', component: <DashboardView onNavigate={setActiveTab} /> },
    { id: 'verifier', component: <VerifierView /> },
    { id: 'formatter', component: <FormatterView /> },
    { id: 'library', component: <LibraryView /> },
    { id: 'search', component: <SearchView /> },
    { id: 'settings', component: <SettingsView /> },
  ], []);

  const isKnownView = PERSISTENT_VIEWS.some(v => v.id === activeTab);

  return (
    <div className="flex h-screen">

      {/* ─── Icon Sidebar ─── */}
      <aside className="hidden md:flex flex-col items-center w-[88px] py-6 px-2 m-3 mr-0 glass-card-static shrink-0">
        {/* Logo */}
        <div className="mb-8">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center">
            <Logo size={36} />
          </div>
        </div>

        {/* Nav Items */}
        <nav className="flex-1 flex flex-col gap-1 w-full">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            >
              <item.icon size={20} />
              <span className="text-[10px] font-semibold tracking-wide">{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* ─── Main Area ─── */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">

        {/* ─── Top Bar ─── */}
        <header className="flex items-center justify-between px-6 py-4 m-3 mb-0 ml-3 glass-card-static shrink-0">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <Logo size={28} />
            <h1 className="text-xl font-bold text-white tracking-wide">
              WritingTools
            </h1>
          </div>

          {/* Search */}
          <div className="hidden sm:flex items-center gap-3 bg-white/3 border border-white/5 rounded-xl px-4 py-2.5 w-full max-w-md mx-8">
            <Search size={16} className="text-neutral-600" />
            <input
              type="text"
              placeholder="Search..."
              className="bg-transparent text-sm text-neutral-300 placeholder-neutral-600 outline-none w-full"
            />
          </div>

          {/* User Avatar */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-neutral-600 to-neutral-800 p-[2px] cursor-pointer">
              <div className="w-full h-full rounded-full bg-black flex items-center justify-center text-xs font-bold text-neutral-300">
                PL
              </div>
            </div>
            <span className="hidden lg:block text-sm font-semibold text-neutral-300">Paradox Labs</span>
          </div>
        </header>

        {/* ─── Mobile Bottom Nav ─── */}
        <div className="md:hidden fixed bottom-0 left-0 right-0 z-50 glass-card-static rounded-none border-t border-white/5 flex justify-around py-2">
          {NAV_ITEMS.slice(0, 4).map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`nav-item !py-2 ${activeTab === item.id ? 'active' : ''}`}
            >
              <item.icon size={20} />
              <span className="text-[9px] font-semibold">{item.label}</span>
            </button>
          ))}
        </div>

        {/* ─── Content ─── */}
        <main className="flex-1 overflow-hidden p-3 pt-3 flex flex-col min-h-0">
          {/* Persistent views — always mounted, hidden when inactive */}
          {PERSISTENT_VIEWS.map(({ id, component }) => (
            <div
              key={id}
              className={activeTab === id ? 'animate-fade-in-up flex-1 min-h-0 flex flex-col overflow-hidden' : ''}
              style={activeTab !== id ? { display: 'none' } : undefined}
            >
              {component}
            </div>
          ))}

          {/* Fallback for unknown tabs (e.g. "collab") */}
          {!isKnownView && (
            <div className="animate-fade-in-up flex-1 min-h-0 flex flex-col overflow-hidden">
              <div className="flex items-center justify-center h-full">
                <div className="glass-card-static p-12 text-center">
                  <div className="text-6xl mb-4 opacity-30">🚧</div>
                  <h2 className="text-2xl font-bold text-white mb-2">Coming Soon</h2>
                  <p className="text-neutral-500">This feature is under development.</p>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
