import React, { useEffect, useState } from 'react';
import { mapBackendCandidateToCandidate, useCandidates, useRequisition, useRequisitions } from '../../services/api';
import { useNavigation } from '../../context/NavigationContext';
import { useToast } from '../../context/ToastContext';
import { CopilotChat } from './CopilotChat';
import { CandidateCard } from './CandidateCard';
import { BackendCandidateBrief } from '../../types';

export const CandidatePoolView: React.FC = () => {
  const { selectedRequisitionId, setSelectedRequisitionId, setCurrentView } = useNavigation();
  const { data: requisitions = [] } = useRequisitions();

  useEffect(() => {
    if (!selectedRequisitionId && requisitions.length > 0) {
      setSelectedRequisitionId(requisitions[0].id);
    }
  }, [requisitions, selectedRequisitionId, setSelectedRequisitionId]);

  const { data: requisition } = useRequisition(selectedRequisitionId);
  const { showToast } = useToast();

  const [activeTokens, setActiveTokens] = useState<string[]>([]);
  const [filteredCandidates, setFilteredCandidates] = useState<BackendCandidateBrief[] | null>(null);

  const { data: candidates = [], isLoading } = useCandidates(
    selectedRequisitionId,
    activeTokens
  );
  const visibleCandidates = filteredCandidates
    ? filteredCandidates.map((candidate, index) =>
        mapBackendCandidateToCandidate(candidate, selectedRequisitionId, index))
    : candidates;

  const handleAddToken = (token: string) => {
    if (!activeTokens.includes(token)) {
      setActiveTokens((prev) => [...prev, token]);
    }
  };

  const handleRemoveToken = (token: string) => {
    setActiveTokens((prev) => prev.filter((t) => t !== token));
  };

  const handleResetTokens = () => {
    setActiveTokens([]);
    setFilteredCandidates(null);
  };

  const heroCandidate = visibleCandidates[0];

  return (
    <div className="w-full h-screen pt-16 flex flex-col overflow-hidden bg-background">
      {/* Top Breadcrumb & Metadata Banner */}
      <div className="px-4 sm:px-6 py-3 shrink-0 border-b border-white/5 bg-surface-container-low/60 backdrop-blur-md">
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2 font-mono text-xs text-on-surface-variant uppercase tracking-wider">
              <button
                onClick={() => setCurrentView('job-postings')}
                className="hover:text-primary transition-colors flex items-center gap-1 font-medium"
              >
                <span className="material-symbols-outlined text-[14px]">arrow_back</span>
                Job Postings
              </button>
              <span>/</span>
              <span className="text-on-surface-variant font-semibold">
                {requisition?.reqCode || 'Position'}
              </span>
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary" />
              <span className="text-tertiary font-semibold">Active Intake</span>
            </div>

            <div className="flex flex-wrap items-center gap-3 mt-1">
              <h1 className="font-headline text-xl sm:text-2xl text-on-surface font-bold tracking-tight">
                {requisition?.title || 'Selected position'}
              </h1>
              <div className="bg-surface-container-high px-2 py-0.5 rounded text-on-surface-variant font-mono text-xs flex items-center gap-1 border border-white/5">
                <span className="material-symbols-outlined text-[14px] text-primary">location_on</span>
                {requisition?.location || 'Location not specified'}
              </div>
              <div className="bg-primary/10 text-primary border border-primary/20 px-2.5 py-0.5 rounded font-mono text-xs font-semibold">
                {requisition?.department || 'Department not specified'}
              </div>
            </div>

            <div className="flex items-center gap-3 mt-1 text-xs text-on-surface-variant">
              <span>
                Target: <strong className="text-on-surface font-mono">{requisition?.salaryBand || 'Not specified'}</strong>
              </span>
              <span>•</span>
              <span>
                Hiring Lead: <strong className="text-on-surface font-semibold">{requisition?.hiringLead?.name || 'Unassigned'}</strong>
              </span>
              <span>•</span>
              <span>
                Posted: <span className="font-mono">Not specified</span>
              </span>
            </div>
          </div>

          {/* Action cluster */}
          <div className="flex items-center gap-2 self-start xl:self-center shrink-0">
            <div className="bg-surface-container px-3 py-1.5 rounded-lg flex items-center gap-2 border border-white/5 shadow-inner">
              <span className="material-symbols-outlined text-primary text-[18px]">group</span>
              <span className="font-mono text-sm text-on-surface font-bold">
                {requisition?.applicantsCount || 0}
              </span>
              <span className="text-xs text-on-surface-variant">Total Applicants</span>
            </div>
            <button 
              onClick={() => showToast('Exporting candidate talent pool CSV/JSON...', 'info')}
              className="bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs px-3 py-2 rounded-lg flex items-center gap-1.5 border border-white/5 transition-all"
            >
              <span className="material-symbols-outlined text-[18px]">file_download</span>
              <span>Export Pool</span>
            </button>
            <button 
              onClick={() => showToast('Batch screening actions panel ready.', 'info')}
              className="bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs px-3 py-2 rounded-lg flex items-center gap-1.5 border border-white/5 transition-all"
            >
              <span className="material-symbols-outlined text-[18px]">checklist</span>
              <span>Batch Actions</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Two-Column 100vh Locked Workbench */}
      <div className="flex-1 min-h-0 px-4 sm:px-6 py-4 grid grid-cols-1 xl:grid-cols-12 gap-6 overflow-hidden">
        {/* Left Column (5 cols): AI Co-pilot & Filter Engine */}
        <div className="xl:col-span-5 h-full overflow-y-auto">
          <CopilotChat
            activeTokens={activeTokens}
            onAddToken={handleAddToken}
            onRemoveToken={handleRemoveToken}
            onResetTokens={handleResetTokens}
            onFilterResult={setFilteredCandidates}
            positionTitle={requisition?.title || ''}
          />
        </div>

        {/* Right Column (7 cols): Filtered Candidate Pool */}
        <div className="xl:col-span-7 h-full flex flex-col space-y-4 overflow-y-auto pr-1">
          {/* Pool Header Bar with Filter Metric */}
          <div className="bg-surface-container-low rounded-xl px-4 py-2.5 shadow-sm border border-white/5 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3">
              <span className="font-headline text-base text-on-surface font-semibold">
                Filtered Pool
              </span>
              <span className="bg-primary/20 text-primary font-mono text-xs font-bold px-2 py-0.5 rounded border border-primary/30">
                {visibleCandidates.length} Candidates
              </span>
              <span className="text-on-surface-variant text-xs hidden sm:inline">
                from {requisition?.applicantsCount || 0} total applications
              </span>
            </div>

            <div className="flex items-center gap-2 text-on-surface-variant text-xs">
              <span className="font-mono text-[10px] uppercase">Sort by:</span>
              <button className="bg-surface-container hover:bg-surface-container-high text-on-surface font-mono text-xs px-2.5 py-1 rounded border border-white/5 flex items-center gap-1 transition-colors">
                <span>Match Vector (High → Low)</span>
                <span className="material-symbols-outlined text-[16px]">arrow_drop_down</span>
              </button>
            </div>
          </div>

          {/* Candidates Roster */}
          {isLoading ? (
            <div className="py-20 flex flex-col items-center justify-center space-y-3">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span className="font-mono text-xs text-on-surface-variant">
                Synthesizing semantic embeddings...
              </span>
            </div>
          ) : visibleCandidates.length === 0 ? (
            <div className="bg-surface-container-low rounded-xl p-8 text-center space-y-3 border border-white/5">
              <span className="material-symbols-outlined text-4xl text-on-surface-variant">
                person_search
              </span>
              <p className="text-sm text-on-surface-variant">
                No candidates match the selected criteria tokens.
              </p>
              <button
                onClick={handleResetTokens}
                className="bg-primary text-black font-semibold text-xs px-4 py-2 rounded-lg hover:bg-amber-400"
              >
                Reset All Filters
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Highlight Hero Card */}
              {heroCandidate && (
                <CandidateCard candidate={heroCandidate} isHero />
              )}

              {/* Remaining Candidate Roster Cards */}
              {visibleCandidates.slice(1).map((candidate) => (
                <CandidateCard key={candidate.id} candidate={candidate} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
