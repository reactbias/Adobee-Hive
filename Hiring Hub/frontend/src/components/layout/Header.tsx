import React, { useState } from 'react';
import { useNavigation } from '../../context/NavigationContext';

export const Header: React.FC = () => {
  const { setCurrentView, isMobileMenuOpen, setIsMobileMenuOpen } = useNavigation();
  const [isDark, setIsDark] = useState<boolean>(() => {
    return document.documentElement.classList.contains('dark');
  });

  const toggleTheme = () => {
    const nextDark = !isDark;
    setIsDark(nextDark);
    if (nextDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('hive_theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('hive_theme', 'light');
    }
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-surface-container-lowest/90 backdrop-blur-xl border-b border-surface-container-highest/60">
      <div className="h-16 w-full px-4 sm:px-6 flex items-center justify-between gap-4">
        {/* Left Section: Mobile Toggle & Brand */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="lg:hidden p-2 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors"
            title="Toggle Menu"
          >
            <span className="material-symbols-outlined text-[24px]">
              {isMobileMenuOpen ? 'close' : 'menu'}
            </span>
          </button>

          <div 
            className="flex items-center gap-3 cursor-pointer"
            onClick={() => setCurrentView('job-postings')}
          >
            <div className="w-9 h-9 flex items-center justify-center shrink-0">
              <img
                src="/brand/logo.svg"
                alt="Adobee Hive"
                className="w-8 h-8"
              />
            </div>
            <div className="flex flex-col">
              <span className="font-headline text-lg font-bold text-on-surface tracking-tight leading-none">
                adobee hive
              </span>
              <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider mt-1">
                Talent Intelligence
              </span>
            </div>
          </div>
        </div>

        {/* Header Right Cluster */}
        <div className="flex items-center gap-2 sm:gap-4 justify-end">
          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="flex items-center justify-center p-2 rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors"
            title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            <span className="material-symbols-outlined text-[20px]">
              {isDark ? 'light_mode' : 'dark_mode'}
            </span>
          </button>

          {/* User Profile */}
          <div className="flex items-center gap-2.5 pl-1 border-l border-surface-container-highest/60 sm:pl-3">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-semibold text-on-surface leading-tight">
                Recruiting Lead
              </div>
              <div className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider">
                Talent Operations
              </div>
            </div>
            <div className="w-8 h-8 rounded-full bg-primary/20 text-primary border border-primary/40 flex items-center justify-center font-bold text-xs shadow-sm">
              RL
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
