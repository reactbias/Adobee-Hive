import React from 'react';
import { DepartmentQuality } from '../../types';

interface DepartmentDistributionProps {
  departmentQualities: DepartmentQuality[];
}

export const DepartmentDistribution: React.FC<DepartmentDistributionProps> = ({
  departmentQualities,
}) => {
  return (
    <div className="lg:col-span-5 bg-surface-container-low rounded-xl p-6 flex flex-col justify-between shadow-sm border border-white/5">
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary text-[20px]">
              stacked_bar_chart
            </span>
            <h2 className="font-headline text-base text-on-surface font-semibold">
              Department Quality Distribution
            </h2>
          </div>
          <span className="font-mono text-[10px] text-on-surface-variant uppercase">
            Percentiles
          </span>
        </div>
        <p className="text-xs text-on-surface-variant mb-5">
          Algorithmic fit score percentiles (P50 / P75 / P90) indexed across operational disciplines.
        </p>

        <div className="space-y-4">
          {departmentQualities.length === 0 ? (
            <div className="text-center py-6 text-xs text-on-surface-variant font-mono">
              No department metrics recorded yet.
            </div>
          ) : (
            departmentQualities.map((item) => (
              <div key={item.department} className="bg-surface-container p-3 rounded-lg border border-white/5 space-y-2">
                <div className="flex justify-between items-center text-xs">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px]" style={{ color: item.accentColor }}>
                      {item.icon}
                    </span>
                    <span className="text-on-surface font-medium">{item.department}</span>
                  </div>
                  <div className="flex items-center gap-1.5 font-mono">
                    <span className="text-on-surface-variant text-[11px]">Top Tier:</span>
                    <span
                      className="px-1.5 py-0.5 rounded text-xs font-semibold"
                      style={{ backgroundColor: `${item.accentColor}20`, color: item.accentColor }}
                    >
                      {item.topTierScore}
                    </span>
                  </div>
                </div>

                <div className="w-full bg-surface-container-high h-2 rounded-full relative overflow-hidden">
                  <div
                    className="absolute left-[45%] right-[10%] h-full rounded-full opacity-70"
                    style={{ backgroundColor: item.accentColor }}
                  />
                  <div
                    className="absolute left-[88%] w-1.5 h-full rounded-full"
                    style={{ backgroundColor: item.accentColor }}
                  />
                </div>

                <div className="flex justify-between items-center font-mono text-[10px] text-on-surface-variant">
                  <span>P50: {item.p50}</span>
                  <span>P75: {item.p75}</span>
                  <span style={{ color: item.accentColor }} className="font-bold">
                    P90: {item.p90}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="mt-5 pt-3 border-t border-white/5 flex items-center justify-between font-mono text-xs text-on-surface-variant">
        <span>Benchmark: Global Engineering Top Decile</span>
        <span className="text-tertiary flex items-center gap-1 font-semibold">
          <span className="w-1.5 h-1.5 rounded-full bg-tertiary" />
          Calibration Calibrated
        </span>
      </div>
    </div>
  );
};
