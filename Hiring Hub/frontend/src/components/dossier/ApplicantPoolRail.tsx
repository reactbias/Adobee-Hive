import React from 'react';
import { Candidate } from '../../types';

interface ApplicantPoolRailProps {
  candidates: Candidate[];
  selectedCandidateId: string;
  onSelectCandidate: (id: string) => void;
  cosineFit?: number;
}

export const ApplicantPoolRail: React.FC<ApplicantPoolRailProps> = ({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  cosineFit = 0.984,
}) => {
  return (
    <div className="col-span-12 xl:col-span-4 flex flex-col gap-5">
      {/* Pool Roster */}
      <div className="bg-surface-container-low rounded-xl p-4 shadow-xl border border-white/5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-on-surface-variant uppercase tracking-wider font-semibold">
              Applicant Pool
            </span>
            <span className="font-mono text-[11px] text-primary bg-primary/10 px-2 py-0.5 rounded font-bold">
              {candidates.length} in Pool
            </span>
          </div>
          <span className="font-mono text-xs text-on-surface-variant">
            Ranked by Fit
          </span>
        </div>

        <div className="space-y-2">
          {candidates.map((cand) => {
            const isSelected = cand.id === selectedCandidateId;
            return (
              <button
                key={cand.id}
                onClick={() => onSelectCandidate(cand.id)}
                className={`w-full text-left p-3 rounded-lg transition-all flex items-start gap-3 border ${
                  isSelected
                    ? 'bg-surface-container-high border-primary/40 shadow-md ring-1 ring-primary/20'
                    : 'bg-surface-container border-white/5 hover:bg-surface-container-high hover:border-white/10'
                }`}
              >
                <div className="relative shrink-0">
                  <img
                    src={cand.avatarUrl}
                    alt={cand.name}
                    className="w-11 h-11 rounded-lg object-cover"
                  />
                  <span className="absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full bg-surface-container-lowest flex items-center justify-center">
                    <span className="w-2 h-2 rounded-full bg-tertiary" />
                  </span>
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className={`font-headline text-sm font-semibold truncate ${isSelected ? 'text-primary' : 'text-on-surface'}`}>
                      {cand.name}
                    </span>
                    <span className="font-mono text-xs text-primary bg-primary/10 px-1.5 py-0.2 rounded font-semibold">
                      {cand.fitScore}%
                    </span>
                  </div>
                  <div className="text-xs text-on-surface truncate mt-0.5">
                    {cand.title}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1.5 font-mono text-[10px]">
                    <span className="text-on-surface-variant bg-surface-container-high px-1 py-0.5 rounded uppercase">
                      {cand.education.split('(')[0]}
                    </span>
                    <span className="text-tertiary bg-tertiary/10 px-1 py-0.5 rounded uppercase font-semibold">
                      Active
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Mini Benchmark Card */}
      <div className="bg-surface-container-low rounded-xl p-4 shadow-lg border border-white/5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-on-surface-variant uppercase tracking-wider font-semibold">
            Applicant Vector Index
          </span>
          <span className="material-symbols-outlined text-[18px] text-tertiary">hub</span>
        </div>
        <p className="text-xs text-on-surface-variant leading-relaxed">
          Applicant matches are cross-referenced across 42 distinct architectural, systems latency, and production scaling vectors against team benchmark.
        </p>
        <div className="flex items-center justify-between pt-2 bg-surface-container-lowest p-3 rounded-lg border border-white/5">
          <div>
            <div className="font-mono text-sm text-primary font-bold">
              Cosine Fit: {cosineFit}
            </div>
            <div className="font-mono text-[10px] text-on-surface-variant uppercase">
              Target Embedding Matrix
            </div>
          </div>
          <span className="material-symbols-outlined text-primary text-[24px]">insights</span>
        </div>
      </div>
    </div>
  );
};
