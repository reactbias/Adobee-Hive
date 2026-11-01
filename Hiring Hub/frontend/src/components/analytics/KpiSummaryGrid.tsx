import React from 'react';
import { AnalyticsKPIs } from '../../types';

interface KpiSummaryGridProps {
  kpis: AnalyticsKPIs;
}

export const KpiSummaryGrid: React.FC<KpiSummaryGridProps> = ({ kpis }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* KPI 1 */}
      <div className="bg-surface-container-low rounded-xl p-5 relative overflow-hidden shadow-sm border border-white/5 flex flex-col justify-between group hover:border-primary/40 transition-all">
        <div className="absolute -right-4 -top-4 w-24 h-24 bg-primary/5 rounded-full blur-xl pointer-events-none group-hover:bg-primary/10 transition-all" />
        <div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold">
              Total Active Pipeline
            </span>
            <span className="material-symbols-outlined text-primary text-[20px]">groups</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-headline text-3xl text-on-surface font-bold tracking-tight">
              {kpis.totalPipeline.toLocaleString()}
            </span>
            <span className="font-mono text-xs text-on-surface-variant">candidates</span>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between font-mono text-xs">
          <div className="flex items-center gap-1 text-tertiary font-bold">
            <span className="material-symbols-outlined text-[16px]">trending_up</span>
            <span>{kpis.pipelineGrowth}</span>
          </div>
          <span className="text-[11px] text-on-surface-variant">Month-over-Month</span>
        </div>
      </div>

      {/* KPI 2 */}
      <div className="bg-surface-container-low rounded-xl p-5 relative overflow-hidden shadow-sm border border-white/5 flex flex-col justify-between group hover:border-secondary/40 transition-all">
        <div className="absolute -right-4 -top-4 w-24 h-24 bg-secondary/5 rounded-full blur-xl pointer-events-none group-hover:bg-secondary/10 transition-all" />
        <div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold">
              Avg. Time to Fill
            </span>
            <span className="material-symbols-outlined text-secondary text-[20px]">timelapse</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-headline text-3xl text-on-surface font-bold tracking-tight">
              {kpis.avgTimeToFillDays}
            </span>
            <span className="font-mono text-xs text-on-surface-variant">Days</span>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between font-mono text-xs">
          <div className="flex items-center gap-1 text-tertiary font-bold">
            <span className="material-symbols-outlined text-[16px]">arrow_downward</span>
            <span>{kpis.timeToFillDelta}</span>
          </div>
          <span className="text-[11px] text-on-surface-variant">vs 28d benchmark</span>
        </div>
      </div>

      {/* KPI 3 */}
      <div className="bg-surface-container-low rounded-xl p-5 relative overflow-hidden shadow-sm border border-white/5 flex flex-col justify-between group hover:border-tertiary/40 transition-all">
        <div className="absolute -right-4 -top-4 w-24 h-24 bg-tertiary/5 rounded-full blur-xl pointer-events-none group-hover:bg-tertiary/10 transition-all" />
        <div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold">
              AI Screening Accuracy
            </span>
            <span className="material-symbols-outlined text-tertiary text-[20px]">neurology</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-headline text-3xl text-on-surface font-bold tracking-tight">
              {kpis.screeningAccuracyPercent}%
            </span>
            <span className="font-mono text-xs text-tertiary font-semibold">Verified</span>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between font-mono text-xs">
          <div className="flex items-center gap-1 text-on-surface-variant truncate">
            <span className="material-symbols-outlined text-[16px] text-tertiary">verified</span>
            <span>Eng Hiring Managers</span>
          </div>
          <span className="text-[11px] text-on-surface-variant">{kpis.evalsCount} evals</span>
        </div>
      </div>

      {/* KPI 4 */}
      <div className="bg-surface-container-low rounded-xl p-5 relative overflow-hidden shadow-sm border border-white/5 flex flex-col justify-between group hover:border-primary/40 transition-all">
        <div className="absolute -right-4 -top-4 w-24 h-24 bg-primary/5 rounded-full blur-xl pointer-events-none group-hover:bg-primary/10 transition-all" />
        <div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold">
              Offer Acceptance Rate
            </span>
            <span className="material-symbols-outlined text-primary text-[20px]">assignment_turned_in</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-headline text-3xl text-on-surface font-bold tracking-tight">
              {kpis.offerAcceptancePercent}%
            </span>
            <span className="font-mono text-xs text-on-surface-variant">rate</span>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between font-mono text-xs">
          <div className="flex items-center gap-1 text-primary font-bold">
            <span className="material-symbols-outlined text-[16px]">thumb_up</span>
            <span>{kpis.acceptedCount}</span>
          </div>
          <span className="text-[11px] text-on-surface-variant">Accepted Q3</span>
        </div>
      </div>
    </div>
  );
};
