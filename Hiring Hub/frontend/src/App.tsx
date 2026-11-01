import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NavigationProvider, useNavigation } from './context/NavigationContext';
import { ToastProvider } from './context/ToastContext';
import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import { JobPostingsView } from './components/jobPostings/JobPostingsView';
import { CandidatePoolView } from './components/candidatePool/CandidatePoolView';
import { DossierView } from './components/dossier/DossierView';
import { AnalyticsView } from './components/analytics/AnalyticsView';
import { SettingsView } from './components/settings/SettingsView';
import { CVUploaderView } from './components/cvUploader/CVUploaderView';
import { ChatSessionsView } from './components/chatSessions/ChatSessionsView';
import { ensureOrganization } from './services/api';
import { useEffect, useState } from 'react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 1000 * 60 * 5,
    },
  },
});

const MainContent: React.FC = () => {
  const { currentView } = useNavigation();

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <Sidebar />
      <main className="lg:pl-64 pl-0 pt-16">
        {currentView === 'job-postings' && <JobPostingsView />}
        {currentView === 'cv-uploader' && <CVUploaderView />}
        {currentView === 'candidate-search' && <CandidatePoolView />}
        {currentView === 'candidate-dossier' && <DossierView />}
        {currentView === 'chat-sessions' && <ChatSessionsView />}
        {currentView === 'analytics-pipelines' && <AnalyticsView />}
        {currentView === 'settings-team' && <SettingsView />}
      </main>
    </div>
  );
};

export const App: React.FC = () => {
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    ensureOrganization()
      .catch((error) => console.error('Unable to initialize the organization:', error))
      .finally(() => setAuthReady(true));
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <ToastProvider>
          {authReady ? <MainContent /> : (
            <div className="min-h-screen bg-background flex items-center justify-center text-on-surface">
              Connecting to CV Analyzer...
            </div>
          )}
        </ToastProvider>
      </NavigationProvider>
    </QueryClientProvider>
  );
};

export default App;
