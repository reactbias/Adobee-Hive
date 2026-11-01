import React from 'react';
import { FunnelStage } from '../../types';

interface FunnelProgressionProps {
  funnelStages: FunnelStage[];
  totalPipeline: number;
}

export const FunnelProgression: React.FC<FunnelProgressionProps> = ({
  funnelStages,
  totalPipeline,
}) => {
  return (
    <div className="lg:col-span-7 bg-surface-container-low rounded-xl p-6 flex flex-col justify-between shadow-sm border border-white/5">
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[20px]">filter_alt</span>
            <h2 className="font-headline text-base text-on-surface font-semibold">
              Requisition Funnel Progression
            </h2>
          </div>
          <div className="flex items-center gap-2 font-mono text-xs text-on-surface-variant">
            <span className="w-2 h-2 rounded-full bg-tertiary" />
            <span>Global Active ({totalPipeline.toLocaleString()})</span>
          </div>
        </div>
        <p className="text-xs text-on-surface-variant mb-6">
          Dynamic stage drop-off and machine-validated candidate velocity across current open requisitions.
        </p>

        {/* Funnel Steps */}
        <div className="space-y-4">
          {funnelStages.map((stage) => (
            <div key={stage.stageNumber} className="flex flex-col gap-1.5">
              <div className="flex justify-between items-center text-xs">
                <span className="text-on-surface font-medium flex items-center gap-2">
                  <span className="font-mono text-[10px] text-on-surface-variant bg-surface-container px-1.5 py-0.5 rounded border border-white/5">
                    {stage.stageNumber}
                  </span>
                  {stage.name}
                </span>
                <div className="flex items-center gap-4 font-mono">
                  <span className="text-on-surface font-semibold">{stage.count}</span>
                  <span className="text-on-surface-variant w-12 text-right">
                    {stage.percentage}%
                  </span>
                </div>
              </div>
              <div className="w-full h-3 bg-surface-container rounded-full overflow-hidden border border-white/5">
                <div
                  className={`h-full ${stage.colorClass} rounded-full transition-all duration-700`}
                  style={{ width: `${stage.percentage}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 pt-4 bg-surface-container/40 p-3 rounded-lg flex items-center justify-between border border-white/5">
        <div className="flex items-center gap-2 text-xs">
          <span className="material-symbols-outlined text-primary text-[18px]">speed</span>
          <span className="text-on-surface">
            Velocity Index: Screen-to-Offer speed has improved by{' '}
            <strong className="text-primary font-bold">28%</strong> with AI-assisted loops
          </span>
        </div>
        <button className="font-mono text-xs text-primary hover:underline">
          Stage Diagnostics →
        </button>
      </div>
    </div>
  );
};
