import React from 'react';
import { Candidate } from '../../types';
import { useNavigation } from '../../context/NavigationContext';
import { useToast } from '../../context/ToastContext';

interface CandidateCardProps {
  candidate: Candidate;
  isHero?: boolean;
}

export const CandidateCard: React.FC<CandidateCardProps> = ({
  candidate,
  isHero = false,
}) => {
  const { openCandidateDossier } = useNavigation();
  const { showToast } = useToast();

  if (isHero) {
    return (
      <div 
        onClick={() => openCandidateDossier(candidate.id)}
        className="group relative bg-surface-container-low hover:bg-surface-container transition-all duration-200 rounded-xl p-5 shadow-lg cursor-pointer overflow-hidden border-l-4 border-l-primary border border-white/5"
      >
        {/* Subtle ambient amber gradient overlay on highlight */}
        <div className="absolute inset-0 bg-gradient-to-r from-primary/10 via-transparent to-transparent pointer-events-none" />

        <div className="relative flex flex-col md:flex-row md:items-start justify-between gap-4">
          {/* Left Info: Avatar + Details */}
          <div className="flex items-start gap-4 min-w-0">
            <div className="relative shrink-0">
              <img
                src={candidate.avatarUrl}
                alt={candidate.name}
                className="w-16 h-16 rounded-xl object-cover ring-2 ring-primary shadow-md"
              />
              {candidate.verified && (
                <div
                  className="absolute -bottom-1 -right-1 bg-tertiary text-black w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] shadow"
                  title="Verified AI Architect"
                >
                  <span className="material-symbols-outlined text-[14px]">verified</span>
                </div>
              )}
            </div>

            <div className="flex flex-col min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-headline text-xl text-on-surface font-bold tracking-tight hover:text-primary transition-colors">
                  {candidate.name}
                </h2>
                <span className="bg-surface-container-high px-2 py-0.5 rounded text-on-surface font-mono text-xs border border-white/5">
                  {(candidate.education || 'Education not specified').split('(')[0]}
                </span>
                <span className="bg-tertiary/15 text-tertiary font-mono text-[10px] uppercase px-2 py-0.5 rounded font-bold border border-tertiary/30">
                  {candidate.status}
                </span>
              </div>

              <div className="text-sm text-on-surface-variant mt-0.5">
                {candidate.title} • {candidate.currentCompany}
              </div>

              {/* Metrics micro-row */}
              <div className="flex flex-wrap items-center gap-4 mt-2 font-mono text-xs text-on-surface-variant">
                <span className="flex items-center gap-1 text-on-surface">
                  <span className="material-symbols-outlined text-[15px] text-primary">history_edu</span>
                  <strong>{candidate.experienceYears} yrs</strong> Exp
                </span>
                <span className="flex items-center gap-1 text-on-surface">
                  <span className="material-symbols-outlined text-[15px] text-tertiary">payments</span>
                  <strong>{candidate.expectedSalary}</strong> Expected
                </span>
                <span className="flex items-center gap-1 text-on-surface">
                  <span className="material-symbols-outlined text-[15px] text-secondary">schedule</span>
                  {candidate.noticePeriod}
                </span>
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-[15px] text-on-surface-variant">location_on</span>
                  {candidate.location}
                </span>
              </div>
            </div>
          </div>

          {/* Right Info: Fit Score Badge & Link */}
          <div className="flex flex-row md:flex-col items-center md:items-end justify-between shrink-0 gap-2">
            <div className="bg-primary/10 border border-primary/20 px-3 py-1.5 rounded-lg flex items-center gap-2">
              <div className="flex flex-col text-right">
                <span className="font-mono text-[10px] text-primary uppercase">Overall Fit</span>
                <span className="font-headline text-2xl text-primary font-bold leading-none">
                  {candidate.fitScore}%
                </span>
              </div>
              <div className="w-2.5 h-2.5 rounded-full bg-tertiary animate-pulse" title="High confidence synthesis" />
            </div>

            <div className="flex items-center gap-1 text-primary hover:text-amber-400 font-mono text-xs mt-1 transition-all group-hover:translate-x-1">
              <span>Inspect full dossier</span>
              <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
            </div>
          </div>
        </div>

        {/* Semantic Match Tags & CTAs */}
        <div className="mt-4 pt-3 bg-surface-container/60 -mx-5 px-5 flex flex-col md:flex-row md:items-center justify-between gap-3 border-t border-white/5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase mr-1">
              Semantic Match:
            </span>
            {candidate.skills.slice(0, 4).map((skill) => (
              <span
                key={skill}
                className="bg-surface-container-high px-2 py-0.5 rounded font-mono text-xs text-on-surface border border-white/5"
              >
                {skill}
              </span>
            ))}
          </div>

          <button
            onClick={(e) => {
              e.stopPropagation();
              showToast(`Interview screen scheduled with ${candidate.name}!`, 'success');
            }}
            className="bg-primary text-black font-semibold text-xs px-4 py-2 rounded-lg hover:bg-amber-400 transition-all self-end md:self-auto shrink-0 shadow-md active:scale-95"
          >
            Schedule Screen
          </button>
        </div>
      </div>
    );
  }

  // Standard Candidate Row
  return (
    <div 
      onClick={() => openCandidateDossier(candidate.id)}
      className="bg-surface-container-low hover:bg-surface-container transition-all duration-150 rounded-xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4 border border-white/5 cursor-pointer group"
    >
      <div className="flex items-start gap-4 min-w-0">
        {candidate.avatarUrl ? (
          <img
            src={candidate.avatarUrl}
            alt={candidate.name}
            className="w-12 h-12 rounded-xl object-cover ring-1 ring-white/10 shrink-0"
          />
        ) : (
          <div className="w-12 h-12 rounded-xl bg-surface-container-high border border-white/10 flex items-center justify-center text-on-surface font-headline font-semibold text-sm shrink-0">
            {candidate.initials || candidate.name.slice(0, 2).toUpperCase()}
          </div>
        )}

        <div className="flex flex-col min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-headline text-base text-on-surface font-semibold group-hover:text-primary transition-colors">
              {candidate.name}
            </h3>
            <span className="bg-surface-container-high text-secondary border border-secondary/20 font-mono text-[10px] uppercase px-2 py-0.5 rounded font-medium">
              {candidate.status}
            </span>
          </div>

          <div className="text-xs text-on-surface-variant">
            {candidate.title} • {candidate.currentCompany}
          </div>

          <div className="flex flex-wrap items-center gap-3 mt-1.5 font-mono text-xs text-on-surface-variant">
            <span>{candidate.experienceYears} yrs Exp</span>
            <span>•</span>
            <span>{candidate.skills.slice(0, 2).join(' & ')}</span>
            <span>•</span>
            <span>{candidate.expectedSalary} req</span>
            <span>•</span>
            <span>{candidate.location}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center md:flex-col md:items-end justify-between shrink-0 gap-2">
        <div className="text-right">
          <span className="font-mono text-[10px] text-on-surface-variant block uppercase">
            Fit Index
          </span>
          <span className="font-mono text-lg text-primary font-bold">
            {candidate.fitScore}%
          </span>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            openCandidateDossier(candidate.id);
          }}
          className="bg-surface-container-high hover:bg-surface-bright text-on-surface text-xs px-3 py-1.5 rounded-lg border border-white/5 transition-colors"
        >
          View Profile
        </button>
      </div>
    </div>
  );
};
