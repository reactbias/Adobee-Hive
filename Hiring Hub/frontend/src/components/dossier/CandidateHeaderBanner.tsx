import React from 'react';
import { Candidate } from '../../types';

interface CandidateHeaderBannerProps {
  candidate: Candidate;
  onAdvanceStage: () => void;
  onScheduleLoop: () => void;
  onReprocess: () => void;
  onExportPdf: () => void;
  onReject: () => void;
  isReprocessing: boolean;
}

export const CandidateHeaderBanner: React.FC<CandidateHeaderBannerProps> = ({
  candidate,
  onAdvanceStage,
  onScheduleLoop,
  onReprocess,
  onExportPdf,
  onReject,
  isReprocessing,
}) => {
  return (
    <div className="relative bg-surface-container-low rounded-xl p-6 sm:p-7 shadow-xl overflow-hidden border border-white/5">
      <div className="relative z-10 flex flex-col lg:flex-row lg:items-start justify-between gap-6">
        <div className="flex items-start gap-5">
          <div className="relative shrink-0">
            <img
              src={candidate.avatarUrl}
              alt={candidate.name}
              className="w-20 h-20 rounded-xl object-cover shadow-2xl ring-2 ring-primary/40"
            />
            <span className="absolute -bottom-1 -right-1 bg-tertiary text-black rounded-full p-1 flex items-center justify-center font-bold shadow">
              <span className="material-symbols-outlined text-[14px]">check</span>
            </span>
          </div>

          <div className="flex flex-col">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="font-headline text-2xl text-on-surface font-bold tracking-tight">
                {candidate.name}
              </span>
              <span className="font-mono text-xs text-primary bg-primary/10 border border-primary/20 px-2.5 py-0.5 rounded font-semibold">
                {candidate.education}
              </span>
            </div>

            <div className="text-sm text-on-surface-variant mb-2">
              {candidate.title || 'Candidate'} • {candidate.currentCompany}
            </div>

            <div className="flex flex-wrap items-center gap-y-1 gap-x-4 text-xs text-on-surface-variant">
              <span className="flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px] text-tertiary">verified</span>
                <span>{candidate.email}</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">location_on</span>
                <span>{candidate.location}</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">phone</span>
                <span>{candidate.phone}</span>
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2 mt-3 font-mono text-xs">
              <span className="bg-tertiary-container/30 text-tertiary border border-tertiary/30 px-2 py-0.5 rounded flex items-center gap-1 font-semibold">
                <span className="material-symbols-outlined text-[14px]">badge</span>
                {candidate.citizenship}
              </span>
              <span className="bg-surface-container-high text-on-surface-variant border border-white/5 px-2 py-0.5 rounded flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">schedule</span>
                Notice: {candidate.noticePeriod}
              </span>
              <a
                href={candidate.githubUrl}
                target="_blank"
                rel="noreferrer"
                className="text-secondary hover:underline flex items-center gap-1 bg-surface-container-high px-2 py-0.5 rounded border border-white/5"
              >
                <span className="material-symbols-outlined text-[14px]">code</span>
                {candidate.githubUrl.replace('https://', '')}
              </a>
            </div>
          </div>
        </div>

        {/* Action cluster */}
        <div className="flex flex-wrap lg:flex-col gap-2 shrink-0 items-stretch">
          <button
            onClick={onAdvanceStage}
            className="bg-primary text-black hover:bg-amber-400 font-semibold text-xs px-4 py-2.5 rounded-lg flex items-center justify-center gap-1.5 shadow-lg shadow-amber-500/20 transition-all active:scale-95"
          >
            <span className="material-symbols-outlined text-[18px]">bolt</span>
            <span>Advance to Offer Stage</span>
          </button>
          <button
            onClick={onScheduleLoop}
            className="bg-surface-container-high text-on-surface hover:bg-surface-bright text-xs px-4 py-2 rounded-lg flex items-center justify-center gap-1.5 border border-white/5 transition-all"
          >
            <span className="material-symbols-outlined text-[18px]">calendar_today</span>
            <span>Schedule Technical Loop</span>
          </button>
          <div className="flex gap-2">
            <button
              onClick={onReprocess}
              disabled={isReprocessing}
              className="flex-1 bg-surface-container text-primary hover:text-amber-400 text-xs py-2 rounded-lg flex items-center justify-center gap-1 border border-primary/20 transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">{isReprocessing ? 'sync' : 'auto_fix_high'}</span>
              <span>{isReprocessing ? 'Reprocessing...' : 'Reprocess AI'}</span>
            </button>
            <button
              onClick={onExportPdf}
              className="flex-1 bg-surface-container text-on-surface-variant hover:text-on-surface text-xs py-2 rounded-lg flex items-center justify-center gap-1 border border-white/5"
            >
              <span className="material-symbols-outlined text-[16px]">picture_as_pdf</span>
              <span>Export PDF</span>
            </button>
            <button
              onClick={onReject}
              className="bg-surface-container text-error hover:bg-error-container hover:text-white text-xs px-3 py-2 rounded-lg flex items-center justify-center border border-white/5"
              title="Reject Candidate"
            >
              <span className="material-symbols-outlined text-[18px]">close</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
