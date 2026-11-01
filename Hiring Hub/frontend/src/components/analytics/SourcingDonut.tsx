import React from 'react';
import { SourcingChannel } from '../../types';

interface SourcingDonutProps {
  sourcingChannels: SourcingChannel[];
  totalPipeline: number;
}

export const SourcingDonut: React.FC<SourcingDonutProps> = ({
  sourcingChannels,
  totalPipeline,
}) => {
  return (
    <div className="lg:col-span-5 bg-surface-container-low rounded-xl p-6 flex flex-col justify-between shadow-sm border border-white/5">
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[20px]">donut_large</span>
            <h2 className="font-headline text-base text-on-surface font-semibold">
              Candidate Sourcing Channels
            </h2>
          </div>
          <span className="font-mono text-xs text-on-surface-variant">Volume</span>
        </div>
        <p className="text-xs text-on-surface-variant mb-4">
          Channel attribution demonstrating autonomous AI inbound expansion.
        </p>

        {/* Donut SVG Representation */}
        <div className="flex items-center justify-center py-2">
          <div className="relative w-44 h-44 flex items-center justify-center">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
              <circle
                cx="18"
                cy="18"
                fill="none"
                r="15.9155"
                stroke="currentColor"
                strokeWidth="3.5"
                className="text-surface-container"
              />
              {(() => {
                let accumulatedOffset = 0;
                const palette = ['#f59e0b', '#38bdf8', '#10b981', '#a855f7', '#ec4899'];
                return sourcingChannels.map((ch, idx) => {
                  const pct = Math.max(0, Math.min(100, ch.percentage));
                  const strokeDasharray = `${pct} ${100 - pct}`;
                  const strokeDashoffset = -accumulatedOffset;
                  accumulatedOffset += pct;
                  const color = palette[idx % palette.length];
                  return (
                    <circle
                      key={ch.name}
                      cx="18"
                      cy="18"
                      fill="none"
                      r="15.9155"
                      stroke={color}
                      strokeWidth="3.5"
                      strokeDasharray={strokeDasharray}
                      strokeDashoffset={strokeDashoffset}
                    />
                  );
                });
              })()}
            </svg>

            <div className="absolute flex flex-col items-center justify-center text-center">
              <span className="font-headline text-2xl text-on-surface font-bold leading-none">
                {totalPipeline.toLocaleString()}
              </span>
              <span className="font-mono text-[9px] text-on-surface-variant uppercase mt-1">
                Total Sourced
              </span>
            </div>
          </div>
        </div>

        {/* Legend Breakdown */}
        <div className="grid grid-cols-2 gap-2 mt-4">
          {sourcingChannels.length === 0 ? (
            <div className="col-span-2 text-center py-4 text-xs text-on-surface-variant font-mono">
              No sourcing channels recorded.
            </div>
          ) : (
            sourcingChannels.map((ch) => (
              <div
                key={ch.name}
                className="bg-surface-container p-2.5 rounded-lg flex items-center justify-between border border-white/5 text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${ch.dotColor}`} />
                  <span className="text-on-surface">{ch.name}</span>
                </div>
                <span className="font-mono font-bold text-on-surface">{ch.percentage}%</span>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="mt-4 pt-2 text-center text-xs text-on-surface-variant border-t border-white/5">
        AI Sourcing conversion yield is <strong className="text-tertiary">2.4x</strong> higher than cold inbound
      </div>
    </div>
  );
};
