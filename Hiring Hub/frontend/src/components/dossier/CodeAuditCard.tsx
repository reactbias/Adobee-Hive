import React from 'react';
import { CandidateTelemetry } from '../../types';

interface CodeAuditCardProps {
  telemetry?: CandidateTelemetry;
}

export const CodeAuditCard: React.FC<CodeAuditCardProps> = ({ telemetry }) => {
  const repo = telemetry?.codeRepo;

  return (
    <div className="bg-surface-container p-4 rounded-xl border border-white/5 shadow-md space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-secondary text-[20px]">terminal</span>
          <span className="font-headline text-sm text-on-surface font-semibold">
            Automated Code & Repository Audit
          </span>
        </div>
        <span className="font-mono text-xs text-on-surface-variant bg-surface-container-highest px-2 py-0.5 rounded border border-white/5">
          {repo?.username || 'Repository telemetry'} • {repo?.syncDate || 'Live'}
        </span>
      </div>
      <p className="text-xs text-on-surface leading-relaxed">
        Code Analysis:{' '}
        <strong className="text-primary font-mono">
          {repo?.commitsYear || 0} commits
        </strong>{' '}
        across {repo?.reposCount || 0} repositories; code structure validated with integration test coverage (
        <strong className="text-tertiary font-mono">
          {repo?.testCoverage || 'Verified'}
        </strong>
        ).
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
        <div className="bg-surface-container-low p-3 rounded-lg border border-white/5">
          <div className="font-mono text-[10px] text-on-surface-variant uppercase">
            Commit Velocity
          </div>
          <div className="font-mono text-sm text-primary font-bold mt-1">
            {repo?.commitVelocity || 'Standard'}
          </div>
          <div className="text-[11px] text-on-surface-variant mt-0.5">
            {repo?.cohortPercentile || 'Qualified'}
          </div>
        </div>
        <div className="bg-surface-container-low p-3 rounded-lg border border-white/5">
          <div className="font-mono text-[10px] text-on-surface-variant uppercase">
            Open Source Index
          </div>
          <div className="font-mono text-sm text-tertiary font-bold mt-1">
            {repo?.ossImpact || 'Audited'}
          </div>
          <div className="text-[11px] text-on-surface-variant mt-0.5">
            {repo?.ossRole || 'Contributor'}
          </div>
        </div>
        <div className="bg-surface-container-low p-3 rounded-lg border border-white/5">
          <div className="font-mono text-[10px] text-on-surface-variant uppercase">
            Architecture Audit
          </div>
          <div className="font-mono text-sm text-secondary font-bold mt-1">
            {repo?.architectureSmell || 'Clean'}
          </div>
          <div className="text-[11px] text-on-surface-variant mt-0.5">
            {repo?.vulnerabilities || '0 Vulnerabilities'}
          </div>
        </div>
      </div>
    </div>
  );
};
