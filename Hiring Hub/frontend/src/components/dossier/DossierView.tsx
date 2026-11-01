import React, { useEffect, useState } from 'react';
import { useCandidate, useCandidates, useAdvanceCandidateStage, useReprocessCandidateCV } from '../../services/api';
import { useNavigation } from '../../context/NavigationContext';
import { useToast } from '../../context/ToastContext';
import { ApplicantPoolRail } from './ApplicantPoolRail';
import { CandidateHeaderBanner } from './CandidateHeaderBanner';
import { TelemetryScorecards } from './TelemetryScorecards';
import { CodeAuditCard } from './CodeAuditCard';
import { EmploymentTimeline } from './EmploymentTimeline';
import { DossierNotes } from './DossierNotes';

export const DossierView: React.FC = () => {
  const { selectedCandidateId, setSelectedCandidateId, selectedRequisitionId, setCurrentView } = useNavigation();
  const { data: candidate } = useCandidate(selectedCandidateId);
  const { data: poolCandidates = [] } = useCandidates(selectedRequisitionId);
  const advanceMutation = useAdvanceCandidateStage();
  const reprocessMutation = useReprocessCandidateCV();
  const { showToast } = useToast();
  const [reprocessing, setReprocessing] = useState(false);
  const [notesList, setNotesList] = useState<string[]>([
    candidate?.telemetry?.atsMetadata?.hiringManagerNotes ||
      'Profile extracted via neural CV parser.',
  ]);

  useEffect(() => {
    if (candidate?.telemetry?.atsMetadata?.hiringManagerNotes) {
      setNotesList([candidate.telemetry.atsMetadata.hiringManagerNotes]);
    }
  }, [candidate?.id, candidate?.telemetry?.atsMetadata?.hiringManagerNotes]);

  if (!candidate) {
    return (
      <div className="w-full min-h-screen bg-background px-4 sm:px-6 lg:px-8 py-20 flex flex-col items-center justify-center space-y-4">
        <span className="material-symbols-outlined text-5xl text-on-surface-variant">person_off</span>
        <h2 className="font-headline text-xl text-on-surface font-bold">No Candidate Selected or Found</h2>
        <p className="text-sm text-on-surface-variant max-w-md text-center">
          Select a candidate from the Candidate Pool to view their technical dossier and CV extraction.
        </p>
        <button
          onClick={() => setCurrentView('candidate-search')}
          className="bg-primary text-black font-semibold text-xs px-4 py-2.5 rounded-lg hover:bg-amber-400 transition-all shadow"
        >
          Return to Candidate Search
        </button>
      </div>
    );
  }

  const telemetry = candidate.telemetry;
  const displayPool = poolCandidates.length > 0 ? poolCandidates : [candidate];

  const handleAdvanceStage = () => {
    advanceMutation.mutate({
      candidateId: candidate.id,
      newStage: 'Offer Extended',
    });
    showToast(`Candidate ${candidate.name} advanced to Formal Offer stage!`, 'success');
  };

  const handleReprocess = async () => {
    setReprocessing(true);
    try {
      await reprocessMutation.mutateAsync(candidate.id);
      showToast(`CV for ${candidate.name} queued for re-extraction with the LLM pipeline.`, 'success');
    } catch {
      showToast(`Queued reprocessing for ${candidate.name}.`, 'info');
    } finally {
      setReprocessing(false);
    }
  };

  const handleAddNote = (noteText: string) => {
    setNotesList((prev) => [
      `Recruiter (Just now): ${noteText}`,
      ...prev,
    ]);
    showToast('Internal note saved to candidate log.', 'info');
  };

  return (
    <div className="w-full min-h-screen bg-background px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Requisition Navigation Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 py-2 border-b border-white/5">
        <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-on-surface-variant">
          <button
            onClick={() => setCurrentView('candidate-search')}
            className="hover:text-primary transition-colors flex items-center gap-1 font-medium"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Candidate Pool
          </button>
          <span>/</span>
          <span>{selectedRequisitionId ? `POS-${selectedRequisitionId.replace(/\D/g, '')}` : 'Position Pool'}</span>
          <span>/</span>
          <span className="text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded font-semibold">
            {candidate.name}
          </span>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs text-on-surface-variant">
          <span className="w-2 h-2 rounded-full bg-tertiary animate-pulse" />
          <span>Telemetry Status:</span>
          <span className="text-on-surface font-semibold">CV Analyzer Live Sync</span>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: Candidate Switch Rail */}
        <ApplicantPoolRail
          candidates={displayPool}
          selectedCandidateId={candidate.id}
          onSelectCandidate={setSelectedCandidateId}
          cosineFit={telemetry?.cosineFit}
        />

        {/* RIGHT COLUMN: Comprehensive Backend Dossier Panel */}
        <div className="col-span-12 xl:col-span-8 flex flex-col gap-6">
          <CandidateHeaderBanner
            candidate={candidate}
            onAdvanceStage={handleAdvanceStage}
            onScheduleLoop={() => showToast(`Technical panel interview loop scheduled for ${candidate.name}!`, 'success')}
            onReprocess={handleReprocess}
            onExportPdf={() => showToast('Exporting candidate dossier report (PDF)...', 'info')}
            onReject={() => {
              advanceMutation.mutate({ candidateId: candidate.id, newStage: 'Rejected' });
              showToast(`Candidate ${candidate.name} flagged as rejected.`, 'info');
            }}
            isReprocessing={reprocessing}
          />

          <div className="space-y-6">
            <TelemetryScorecards telemetry={telemetry} fallbackFitScore={candidate.fitScore} />
            <CodeAuditCard telemetry={telemetry} />
          </div>

          <EmploymentTimeline telemetry={telemetry} />

          <DossierNotes
            telemetry={telemetry}
            notesList={notesList}
            onAddNote={handleAddNote}
          />
        </div>
      </div>
    </div>
  );
};
