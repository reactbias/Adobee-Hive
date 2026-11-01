import React from 'react';
import { Requisition } from '../../types';
import { useNavigation } from '../../context/NavigationContext';

interface RequisitionCardProps {
  requisition: Requisition;
  featured?: boolean;
}

export const RequisitionCard: React.FC<RequisitionCardProps> = ({
  requisition,
  featured = false,
}) => {
  const { openApplicantPool } = useNavigation();

  if (featured) {
    return (
      <div className="col-span-12 bg-surface-container-low rounded-xl p-6 sm:p-7 relative overflow-hidden shadow-xl border border-white/5 hover:border-primary/40 transition-all group">
        {/* Accent Bar */}
        <div className="absolute top-0 left-0 w-2 h-full bg-primary" />
        {/* Ambient Glow */}
        <div className="absolute -right-20 -bottom-20 w-80 h-80 bg-primary/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
          {/* Main Info */}
          <div className="space-y-3 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-primary bg-primary/10 border border-primary/20 px-2.5 py-0.5 rounded font-semibold">
                Req #{requisition.reqCode}
              </span>
              <span className="font-mono text-xs uppercase bg-error/15 text-error border border-error/30 px-2 py-0.5 rounded font-bold tracking-wider">
                {requisition.priorityLabel}
              </span>
              <span className="font-mono text-xs text-on-surface-variant flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">location_on</span>
                {requisition.location}
              </span>
              <span className="font-mono text-xs text-on-surface-variant flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">payments</span>
                {requisition.salaryBand} • {requisition.equity}
              </span>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center gap-4">
              <h2 className="font-headline text-2xl text-on-surface font-bold group-hover:text-primary transition-colors tracking-tight">
                {requisition.title}
              </h2>
              <div className="flex items-center gap-2 bg-surface-container-lowest px-3 py-1 rounded-full border border-white/5 shadow-inner">
                <span className="w-2 h-2 rounded-full bg-tertiary animate-pulse" />
                <span className="font-mono text-xs text-tertiary font-bold">
                  {requisition.aiCohortFit}% AI Cohort Fit
                </span>
              </div>
            </div>

            <p className="text-sm text-on-surface-variant leading-relaxed">
              {requisition.summary}
            </p>

            {/* Skills Badges */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {requisition.skills.map((skill) => (
                <span
                  key={skill}
                  className="font-mono text-xs bg-surface-container-high text-on-surface px-2.5 py-1 rounded flex items-center gap-1.5 border border-white/5"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-tertiary" />
                  {skill}
                </span>
              ))}
            </div>
          </div>

          {/* Hiring Lead Card */}
          <div className="flex flex-col sm:flex-row lg:flex-col items-start sm:items-center lg:items-end justify-between gap-4 min-w-[280px] bg-surface-container-lowest p-4 rounded-xl border border-white/5 shadow-inner">
            <div className="flex items-center gap-3 w-full">
              {requisition.hiringLead.avatarUrl ? (
                <img
                  src={requisition.hiringLead.avatarUrl}
                  alt={requisition.hiringLead.name}
                  className="w-10 h-10 rounded-full object-cover shadow-sm ring-1 ring-primary/30"
                />
              ) : (
                <span className="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center">
                  <span className="material-symbols-outlined text-on-surface-variant">person</span>
                </span>
              )}
              <div className="flex flex-col min-w-0">
                <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider">
                  Hiring Lead
                </span>
                <span className="text-sm text-on-surface font-semibold truncate">
                  {requisition.hiringLead.name}
                </span>
              </div>
              <span className="ml-auto font-mono text-xs text-primary bg-primary/10 px-2 py-0.5 rounded font-bold">
                {requisition.hiringLead.poolsCount} Pools
              </span>
            </div>

            <div className="w-full flex items-center justify-between text-on-surface-variant font-mono text-xs pt-1 border-t border-white/5">
              <span>New Influx:</span>
              <span className="text-tertiary font-bold">
                +{requisition.unreviewedCount} Unreviewed
              </span>
            </div>
          </div>
        </div>

        {/* Pipeline Distribution & CTA */}
        <div className="mt-6 pt-4 grid grid-cols-1 lg:grid-cols-12 gap-4 items-center bg-surface-container-high/40 p-4 rounded-lg border border-white/5">
          <div className="lg:col-span-8 flex flex-wrap items-center gap-3">
            <span className="font-mono text-xs text-on-surface-variant uppercase tracking-wider">
              Pipeline Distribution:
            </span>
            <div className="flex items-center gap-1.5 bg-surface-container px-3 py-1.5 rounded-lg border border-white/5">
              <span className="font-mono text-xs text-on-surface-variant">Review:</span>
              <span className="font-mono text-xs text-on-surface font-bold">
                {requisition.pipeline.review}
              </span>
            </div>
            <div className="flex items-center gap-1.5 bg-surface-container px-3 py-1.5 rounded-lg border border-white/5">
              <span className="font-mono text-xs text-secondary">AI Screened:</span>
              <span className="font-mono text-xs text-secondary font-bold">
                {requisition.pipeline.aiScreened}
              </span>
            </div>
            <div className="flex items-center gap-1.5 bg-surface-container px-3 py-1.5 rounded-lg border border-white/5">
              <span className="font-mono text-xs text-primary">Tech Round:</span>
              <span className="font-mono text-xs text-primary font-bold">
                {requisition.pipeline.techRound}
              </span>
            </div>
            <div className="flex items-center gap-1.5 bg-surface-container px-3 py-1.5 rounded-lg border border-white/5">
              <span className="font-mono text-xs text-tertiary">Offer Stage:</span>
              <span className="font-mono text-xs text-tertiary font-bold">
                {requisition.pipeline.offerStage}
              </span>
            </div>
          </div>

          <div className="lg:col-span-4 flex justify-start lg:justify-end">
            <button
              onClick={() => openApplicantPool(requisition.id)}
              className="inline-flex items-center gap-2 bg-primary text-black font-semibold text-xs px-4 py-2.5 rounded-lg shadow-md hover:bg-amber-400 transition-all active:scale-95"
            >
              <span>View Applicant Pool & AI Filter</span>
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Regular Bento Grid Card
  return (
    <div className="bg-surface-container-low rounded-xl p-5 flex flex-col justify-between shadow-lg border border-white/5 hover:border-primary/30 transition-all group">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded font-semibold">
            Req #{requisition.reqCode}
          </span>
          <span
            className={`font-mono text-xs uppercase px-2 py-0.5 rounded font-bold ${
              requisition.isUrgent
                ? 'bg-error/15 text-error border border-error/30'
                : 'bg-surface-container text-on-surface-variant'
            }`}
          >
            {requisition.priorityLabel}
          </span>
        </div>

        <div>
          <h3 className="font-headline text-lg text-on-surface font-semibold group-hover:text-primary transition-colors">
            {requisition.title}
          </h3>
          <div className="flex flex-wrap items-center gap-2 text-xs text-on-surface-variant mt-1">
            <span>{requisition.location.split('(')[0]}</span>
            <span>•</span>
            <span className="font-mono">{requisition.salaryBand}</span>
          </div>
        </div>

        <p className="text-xs text-on-surface-variant line-clamp-2 leading-relaxed">
          {requisition.summary}
        </p>

        {/* Mini Metric Grid */}
        <div className="grid grid-cols-3 gap-2 pt-1">
          <div className="bg-surface-container p-2 rounded-lg text-center border border-white/5">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase block">
              Applicants
            </span>
            <span className="font-mono text-xs text-on-surface font-bold">
              {requisition.applicantsCount}{' '}
              <span className="text-tertiary text-[10px]">
                (+{requisition.unreviewedCount})
              </span>
            </span>
          </div>
          <div className="bg-surface-container p-2 rounded-lg text-center border border-white/5">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase block">
              AI Match
            </span>
            <span className="font-mono text-xs text-tertiary font-bold">
              {requisition.aiCohortFit}%
            </span>
          </div>
          <div className="bg-surface-container p-2 rounded-lg text-center border border-white/5">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase block">
              Pipeline
            </span>
            <span className="font-mono text-xs text-primary font-bold">
              {requisition.pipeline.techRound + requisition.pipeline.offerStage} Ready
            </span>
          </div>
        </div>

        {requisition.funnelVelocityPercent && (
          <div className="space-y-1 pt-1">
            <div className="flex justify-between font-mono text-[10px] text-on-surface-variant">
              <span>Interview Funnel Velocity</span>
              <span className="text-primary font-bold">
                {requisition.funnelVelocityPercent}% Target
              </span>
            </div>
            <div className="w-full h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500"
                style={{ width: `${requisition.funnelVelocityPercent}%` }}
              />
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img
            src={requisition.hiringLead.avatarUrl}
            alt={requisition.hiringLead.name}
            className="w-7 h-7 rounded-full object-cover ring-1 ring-white/10"
          />
          <span className="text-xs text-on-surface-variant">
            {requisition.hiringLead.name}
          </span>
        </div>
        <button
          onClick={() => openApplicantPool(requisition.id)}
          className="bg-surface-container-high hover:bg-surface-bright text-on-surface font-medium text-xs px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1"
        >
          <span>Manage Req</span>
          <span className="material-symbols-outlined text-[14px]">chevron_right</span>
        </button>
      </div>
    </div>
  );
};
