import React from 'react';
import { useNavigation } from '../../context/NavigationContext';
import { useRequisitions } from '../../services/api';
import { ActiveView } from '../../types';

interface NavItem {
  id: ActiveView;
  label: string;
  icon: string;
  badge?: string;
}

export const Sidebar: React.FC = () => {
  const { currentView, setCurrentView, isMobileMenuOpen, setIsMobileMenuOpen } = useNavigation();
  const { data: requisitions = [] } = useRequisitions();

  const navItems: NavItem[] = [
    {
      id: 'job-postings',
      label: 'Job Postings',
      icon: 'work',
      badge: requisitions.length > 0 ? requisitions.length.toString() : undefined,
    },
    { id: 'cv-uploader', label: 'Upload CVs', icon: 'upload_file' },
    { id: 'candidate-search', label: 'Candidate Search', icon: 'person_search', badge: 'AI' },
    { id: 'candidate-dossier', label: 'Candidate Dossier', icon: 'badge' },
    { id: 'chat-sessions', label: 'Chat Sessions', icon: 'chat' },
    { id: 'analytics-pipelines', label: 'Analytics & Pipelines', icon: 'monitoring' },
    { id: 'settings-team', label: 'Settings & Team', icon: 'settings' },
  ];

  return (
    <>
      {isMobileMenuOpen && (
        <div
          onClick={() => setIsMobileMenuOpen(false)}
          className="fixed inset-0 bg-black/60 z-30 lg:hidden backdrop-blur-[2px] transition-opacity"
        />
      )}
      <aside
        className={`fixed left-0 top-16 bottom-0 w-64 bg-surface-container-lowest z-40 flex flex-col border-r border-surface-container-highest/60 select-none transition-transform duration-200 ease-in-out ${
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
      {/* Workspace Header */}
      <div className="p-4">
        <div className="flex items-center justify-between px-1 mb-1">
          <span className="font-mono text-xs text-on-surface-variant uppercase tracking-wider font-semibold">
            Workspace
          </span>
          <span className="font-mono text-[11px] text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded font-medium">
            Core
          </span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => {
                setCurrentView(item.id);
                setIsMobileMenuOpen(false);
              }}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg transition-all text-sm ${
                isActive
                  ? 'bg-primary text-black font-semibold shadow-md shadow-amber-500/15'
                  : 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface'
              }`}
            >
              <div className="flex items-center gap-3">
                <span className={`material-symbols-outlined text-[20px] ${isActive ? 'text-black' : 'text-on-surface-variant'}`}>
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span
                  className={`text-[11px] font-mono px-1.5 py-0.2 rounded ${
                    isActive
                      ? 'bg-black/20 text-black font-bold'
                      : 'bg-surface-container-high text-on-surface-variant'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Cluster Status Footer */}
      <div className="p-4 border-t border-surface-container-highest/60 bg-surface-container-low/40">
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider">
              Active Cluster
            </span>
            <span className="font-mono text-xs text-on-surface font-semibold">
              Docker Cluster
            </span>
          </div>
          <span className="material-symbols-outlined text-tertiary text-[18px]" title="Operational Cluster">
            verified
          </span>
        </div>
      </div>
    </aside>
    </>
  );
};
