import React from 'react';
import { CandidateTelemetry } from '../../types';

interface EmploymentTimelineProps {
  telemetry?: CandidateTelemetry;
}

export const EmploymentTimeline: React.FC<EmploymentTimelineProps> = ({ telemetry }) => {
  return (
    <div className="bg-surface-container-low rounded-xl p-6 shadow-lg border border-white/5 space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[22px]">history_edu</span>
          <span className="font-headline text-lg text-on-surface font-semibold">
            Verified Employment History & Backend Records
          </span>
        </div>
        <span className="font-mono text-xs text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded border border-white/5">
          Verified via The Work Number API
        </span>
      </div>

      <div className="space-y-4">
        {(telemetry?.employmentHistory || []).map((job) => (
          <div
            key={job.company}
            className="bg-surface-container p-4 rounded-xl border border-white/5 space-y-2 shadow-md"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
              <div>
                <span className="font-headline text-sm font-semibold text-primary">
                  {job.title}
                </span>
                <span className="text-sm font-semibold text-on-surface ml-1">
                  @ {job.company}
                </span>
              </div>
              <div className="flex items-center gap-2 font-mono text-xs">
                <span className="text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded">
                  {job.period} ({job.duration})
                </span>
                <span className="text-tertiary bg-tertiary/10 border border-tertiary/20 px-2 py-0.5 rounded flex items-center gap-1 font-semibold">
                  <span className="material-symbols-outlined text-[13px]">check_circle</span>
                  Verified
                </span>
              </div>
            </div>
            <p className="text-xs text-on-surface leading-relaxed">
              {job.description}
            </p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {job.skills.map((s) => (
                <span
                  key={s}
                  className="font-mono text-xs text-on-surface-variant bg-surface-container-low px-2 py-0.5 rounded border border-white/5"
                >
                  {s}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
