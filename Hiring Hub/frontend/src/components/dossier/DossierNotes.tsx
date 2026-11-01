import React, { useState } from 'react';
import { CandidateTelemetry } from '../../types';

interface DossierNotesProps {
  telemetry?: CandidateTelemetry;
  notesList: string[];
  onAddNote: (note: string) => void;
}

export const DossierNotes: React.FC<DossierNotesProps> = ({
  telemetry,
  notesList,
  onAddNote,
}) => {
  const [internalNote, setInternalNote] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!internalNote.trim()) return;
    onAddNote(internalNote.trim());
    setInternalNote('');
  };

  return (
    <div className="bg-surface-container-low rounded-xl p-6 shadow-lg border border-white/5 space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[22px]">database</span>
          <span className="font-headline text-lg text-on-surface font-semibold">
            Backend ATS Metadata & Candidate Logs
          </span>
        </div>
        <span className="font-mono text-xs text-on-surface-variant">
          {telemetry?.atsMetadata?.source || 'CV Ingestion System'}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-surface-container p-4 rounded-xl border border-white/5 space-y-2">
          <div className="flex items-center justify-between font-mono text-[10px] uppercase">
            <span className="text-on-surface-variant">Application Ingestion</span>
            <span className="text-tertiary font-bold">DOCUMENT PARSER</span>
          </div>
          <div className="text-sm font-semibold text-on-surface">
            {telemetry?.atsMetadata?.ingestedAt || 'Processed'}
          </div>
          <div className="text-xs text-on-surface-variant leading-relaxed">
            Source: {telemetry?.atsMetadata?.source || 'CV Upload'} • ID: {telemetry?.atsMetadata?.candidateId || 'N/A'}
          </div>
        </div>

        <div className="bg-surface-container p-4 rounded-xl border border-white/5 space-y-2">
          <div className="flex items-center justify-between font-mono text-[10px] uppercase">
            <span className="text-on-surface-variant">Compensation Alignment</span>
            <span className="text-tertiary bg-tertiary/10 border border-tertiary/20 px-1.5 py-0.5 rounded font-bold">
              Standard
            </span>
          </div>
          <div className="text-sm font-bold text-primary font-mono">
            {telemetry?.atsMetadata?.compensationBand || 'Not specified'}
          </div>
          <div className="text-xs text-on-surface-variant leading-relaxed">
            {telemetry?.atsMetadata?.approvedBudget || 'In Review'}
          </div>
        </div>
      </div>

      {/* Internal Recruiter Dispatch Notes Form */}
      <div className="bg-surface-container p-4 rounded-xl border border-white/5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-on-surface font-semibold">
            Hiring Manager Screening Notes & Feedback
          </span>
          <span className="font-mono text-[10px] text-tertiary">
            {telemetry?.atsMetadata?.checkrTier || 'Verified Profile'}
          </span>
        </div>

        <div className="space-y-2">
          {notesList.map((note, idx) => (
            <div
              key={idx}
              className="p-3 bg-surface-container-low rounded-lg text-xs text-on-surface leading-relaxed border border-white/5 font-mono"
            >
              {note}
            </div>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="flex gap-2 pt-2">
          <input
            type="text"
            value={internalNote}
            onChange={(e) => setInternalNote(e.target.value)}
            placeholder="Dispatch review note to Greenhouse ATS..."
            className="flex-1 bg-surface-container-lowest text-xs text-on-surface placeholder:text-on-surface-variant/50 px-3 py-2 rounded-lg border border-white/10 focus:outline-none focus:border-primary"
          />
          <button
            type="submit"
            className="bg-surface-container-high hover:bg-surface-bright text-primary font-mono text-xs px-4 py-2 rounded-lg border border-white/5 transition-all"
          >
            Post Note
          </button>
        </form>
      </div>
    </div>
  );
};
