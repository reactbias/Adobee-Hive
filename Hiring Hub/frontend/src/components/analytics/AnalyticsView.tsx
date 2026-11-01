import React, { useState } from 'react';
import { useAnalytics } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { KpiSummaryGrid } from './KpiSummaryGrid';
import { FunnelProgression } from './FunnelProgression';
import { DepartmentDistribution } from './DepartmentDistribution';
import { SourcingDonut } from './SourcingDonut';
import { QueryLogsTable } from './QueryLogsTable';

export const AnalyticsView: React.FC = () => {
  const { data: analytics, isLoading } = useAnalytics();
  const [timeRange, setTimeRange] = useState<'30d' | 'qtd' | 'ytd'>('30d');
  const { showToast } = useToast();

  if (isLoading || !analytics) {
    return (
      <div className="py-20 flex flex-col items-center justify-center space-y-3 min-h-screen">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span className="font-mono text-xs text-on-surface-variant">
          Calculating pipeline conversion velocity...
        </span>
      </div>
    );
  }

  const { kpis, funnelStages, departmentQualities, sourcingChannels, queryLogs } = analytics;

  return (
    <div className="w-full min-h-screen bg-background px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header Context & Controls */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="flex flex-col">
          <div className="flex items-center gap-2 mb-1 font-mono text-xs text-on-surface-variant">
            <span className="text-primary font-semibold uppercase tracking-wider">
              Executive Overview
            </span>
            <span>•</span>
            <span>Q3 Performance Snapshot</span>
          </div>
          <h1 className="font-headline text-2xl sm:text-3xl text-on-surface font-bold tracking-tight">
            Talent Pipeline Intelligence
          </h1>
          <p className="text-xs sm:text-sm text-on-surface-variant max-w-2xl mt-1 leading-relaxed">
            Real-time candidate conversion velocity, autonomous sourcing telemetry, and multi-department algorithmic screening metrics.
          </p>
        </div>

        {/* Date Selector & Export */}
        <div className="flex items-center gap-2 self-start md:self-auto">
          <div className="bg-surface-container-low p-1 rounded-xl flex items-center border border-white/5 shadow-inner">
            <button
              onClick={() => setTimeRange('30d')}
              className={`px-3 py-1 rounded-lg font-mono text-xs transition-all ${
                timeRange === '30d'
                  ? 'bg-surface-container text-primary font-semibold shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Last 30 Days
            </button>
            <button
              onClick={() => setTimeRange('qtd')}
              className={`px-3 py-1 rounded-lg font-mono text-xs transition-all ${
                timeRange === 'qtd'
                  ? 'bg-surface-container text-primary font-semibold shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Quarter-to-Date
            </button>
            <button
              onClick={() => setTimeRange('ytd')}
              className={`px-3 py-1 rounded-lg font-mono text-xs transition-all ${
                timeRange === 'ytd'
                  ? 'bg-surface-container text-primary font-semibold shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Year-to-Date
            </button>
          </div>

          <button
            onClick={() => showToast('Exporting Talent Intelligence Executive Summary (PDF/XLSX)...', 'info')}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-black font-semibold font-mono text-xs hover:bg-amber-400 transition-all shadow-md active:scale-95"
          >
            <span className="material-symbols-outlined text-[18px]">ios_share</span>
            <span>Export Report</span>
          </button>
        </div>
      </div>

      {/* Top 4 KPI Summary Cards */}
      <KpiSummaryGrid kpis={kpis} />

      {/* Primary Analytics: Funnel & Quality Mosaic */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <FunnelProgression funnelStages={funnelStages} totalPipeline={kpis.totalPipeline} />
        <DepartmentDistribution departmentQualities={departmentQualities} />
      </div>

      {/* Sourcing Breakdown & AI Query Logs Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <SourcingDonut sourcingChannels={sourcingChannels} totalPipeline={kpis.totalPipeline} />
        <QueryLogsTable queryLogs={queryLogs} />
      </div>
    </div>
  );
};
