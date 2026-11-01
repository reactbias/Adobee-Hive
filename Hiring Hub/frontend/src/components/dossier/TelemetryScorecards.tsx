import React from 'react';
import { CandidateTelemetry } from '../../types';

interface TelemetryScorecardsProps {
  telemetry?: CandidateTelemetry;
  fallbackFitScore: number;
}

export const TelemetryScorecards: React.FC<TelemetryScorecardsProps> = ({
  telemetry,
  fallbackFitScore,
}) => {
  const overallScore = telemetry?.overallScore || fallbackFitScore;

  return (
    <div className="bg-surface-container-low rounded-xl p-6 shadow-lg border border-white/5 space-y-6">
      <div className="flex items-center justify-between pb-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[22px]">neurology</span>
          <span className="font-headline text-lg text-on-surface font-semibold">
            Backend Requisition Telemetry & Scorecards
          </span>
        </div>
        <span className="font-mono text-xs text-tertiary bg-tertiary/10 border border-tertiary/20 px-2 py-0.5 rounded font-semibold">
          Hash: {telemetry?.telemetryHash || '0x9b4a11c882e'}
        </span>
      </div>

      {/* Scorecard Bento */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
        {/* Dial Card */}
        <div className="md:col-span-4 bg-surface-container p-4 rounded-xl flex flex-col justify-between border border-white/5 shadow-md">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider">
              Overall Hive Match
            </span>
            <span className="material-symbols-outlined text-primary text-[18px]">verified</span>
          </div>
          <div className="flex items-baseline gap-1 my-2">
            <span className="font-headline text-4xl text-primary font-bold">
              {overallScore}
            </span>
            <span className="text-on-surface-variant font-headline text-lg">/ 100</span>
          </div>
          <div className="w-full bg-surface-container-highest rounded-full h-1.5 overflow-hidden mb-2">
            <div
              className="bg-primary h-full rounded-full"
              style={{ width: `${overallScore}%` }}
            />
          </div>
          <div className="font-mono text-xs text-tertiary flex items-center gap-1 font-semibold">
            <span className="material-symbols-outlined text-[14px]">trending_up</span>
            <span>{telemetry?.percentile || '99th percentile of pool'}</span>
          </div>
        </div>

        {/* Technical Competencies Bars */}
        <div className="md:col-span-8 bg-surface-container p-4 rounded-xl flex flex-col justify-between border border-white/5 shadow-md">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold">
              Technical Competency Evaluation (Algorithmic & Panel)
            </span>
            <span className="font-mono text-xs text-on-surface-variant">
              Calibrated N=1,420
            </span>
          </div>
          <div className="space-y-3">
            {(telemetry?.competencies || [
              { name: 'System Architecture & Distributed Scaling', score: 9.8, maxScore: 10 },
              { name: 'LLM / RAG Engineering & Retrieval Pipelines', score: 9.9, maxScore: 10 },
              { name: 'Production TypeScript / Python Async Core', score: 9.6, maxScore: 10 },
            ]).map((comp) => (
              <div key={comp.name}>
                <div className="flex justify-between items-center mb-1 text-xs">
                  <span className="text-on-surface font-medium">{comp.name}</span>
                  <span className="font-mono text-primary font-bold">
                    {comp.score} / {comp.maxScore}
                  </span>
                </div>
                <div className="w-full bg-surface-container-highest rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-amber-500 to-primary h-full rounded-full"
                    style={{ width: `${(comp.score / comp.maxScore) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
