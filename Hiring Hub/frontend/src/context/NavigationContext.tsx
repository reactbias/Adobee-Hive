import React, { createContext, useContext, useState } from 'react';
import { ActiveView } from '../types';

interface NavigationContextType {
  currentView: ActiveView;
  setCurrentView: (view: ActiveView) => void;
  selectedRequisitionId: string;
  setSelectedRequisitionId: (id: string) => void;
  selectedCandidateId: string;
  setSelectedCandidateId: (id: string) => void;
  globalSearchQuery: string;
  setGlobalSearchQuery: (query: string) => void;
  openCandidateDossier: (candidateId: string) => void;
  openApplicantPool: (requisitionId: string) => void;
  isMobileMenuOpen: boolean;
  setIsMobileMenuOpen: (open: boolean) => void;
}

const NavigationContext = createContext<NavigationContextType | undefined>(undefined);

export const NavigationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentView, setCurrentView] = useState<ActiveView>('job-postings');
  const [selectedRequisitionId, setSelectedRequisitionId] = useState<string>('');
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>('');
  const [globalSearchQuery, setGlobalSearchQuery] = useState<string>('');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);

  const openCandidateDossier = (candidateId: string) => {
    setSelectedCandidateId(candidateId);
    setCurrentView('candidate-dossier');
  };

  const openApplicantPool = (requisitionId: string) => {
    setSelectedRequisitionId(requisitionId);
    setCurrentView('candidate-search');
  };

  return (
    <NavigationContext.Provider
      value={{
        currentView,
        setCurrentView,
        selectedRequisitionId,
        setSelectedRequisitionId,
        selectedCandidateId,
        setSelectedCandidateId,
        globalSearchQuery,
        setGlobalSearchQuery,
        openCandidateDossier,
        openApplicantPool,
        isMobileMenuOpen,
        setIsMobileMenuOpen,
      }}
    >
      {children}
    </NavigationContext.Provider>
  );
};

export const useNavigation = () => {
  const context = useContext(NavigationContext);
  if (!context) {
    throw new Error('useNavigation must be used within a NavigationProvider');
  }
  return context;
};
