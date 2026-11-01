import React, { useEffect, useState } from 'react';
import { createPosition, useRequisitions } from '../../services/api';
import { useQueryClient } from '@tanstack/react-query';
import { Department, RequisitionStatus } from '../../types';
import { DepartmentTabs } from './DepartmentTabs';
import { RequisitionCard } from './RequisitionCard';
import { useNavigation } from '../../context/NavigationContext';

export const JobPostingsView: React.FC = () => {
  const [selectedDept, setSelectedDept] = useState<Department>('All Departments');
  const [selectedStatus, setSelectedStatus] = useState<RequisitionStatus | 'All'>('All');
  const [searchInput, setSearchInput] = useState('');
  const { globalSearchQuery, selectedRequisitionId, setSelectedRequisitionId } = useNavigation();
  const queryClient = useQueryClient();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [createError, setCreateError] = useState('');
  const [creating, setCreating] = useState(false);

  const effectiveSearch = searchInput || globalSearchQuery;
  const { data: requisitions = [], isLoading, isError } = useRequisitions(
    selectedDept,
    selectedStatus,
    effectiveSearch
  );

  useEffect(() => {
    const selectedId = Number(selectedRequisitionId.replace(/\D/g, ''));
    if (requisitions.length > 0 &&
        !requisitions.some((requisition) => Number(requisition.id) === selectedId)) {
      setSelectedRequisitionId(requisitions[0].id);
    }
  }, [requisitions, selectedRequisitionId, setSelectedRequisitionId]);

  const submitPosition = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newTitle.trim()) {
      setCreateError('Enter a job title.');
      return;
    }
    setCreating(true);
    setCreateError('');
    try {
      await createPosition(newTitle.trim(), newDescription.trim());
      await queryClient.invalidateQueries({ queryKey: ['requisitions'] });
      setNewTitle('');
      setNewDescription('');
      setShowCreateForm(false);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : 'Unable to create job posting.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-background px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Top Command & Metrics Strip */}
      <div className="relative bg-surface-container-low rounded-xl p-6 sm:p-8 overflow-hidden shadow-2xl border border-white/5">
        <div className="absolute -right-24 -top-24 w-96 h-96 bg-primary/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute right-1/3 bottom-0 w-64 h-32 bg-secondary/5 rounded-full blur-2xl pointer-events-none" />

        <div className="relative z-10 flex flex-col xl:flex-row xl:items-center justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-primary uppercase tracking-widest bg-surface-container-high px-2.5 py-0.5 rounded border border-white/5">
                Requisition Orchestration
              </span>
              <span className="inline-flex items-center gap-1.5 font-mono text-xs text-tertiary">
                <span className="w-2 h-2 rounded-full bg-tertiary" />
                Sync Active
              </span>
            </div>

            <h1 className="font-headline text-2xl sm:text-3xl text-on-surface font-bold tracking-tight">
              Active Job Postings & Requisitions
            </h1>
            <p className="text-sm text-on-surface-variant leading-relaxed">
              Algorithmic sourcing, real-time candidate triage, and predictive conversion vectors across active organizational cohorts.
            </p>
          </div>

          <button
            onClick={() => setShowCreateForm((open) => !open)}
            className="self-start xl:self-center bg-primary text-black font-semibold text-xs px-4 py-2 rounded-lg hover:bg-amber-400 transition-all shadow flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-[16px]">{showCreateForm ? 'close' : 'add'}</span>
            <span>{showCreateForm ? 'Cancel' : 'Add Job Posting'}</span>
          </button>

          {/* Summary Pill Matrix & Sync Status */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-surface-container-lowest p-2 rounded-xl border border-white/5 shadow-inner">
              <div className="flex flex-col px-3 py-1.5">
                <span className="font-mono text-[10px] text-on-surface-variant uppercase">
                  Open Roles
                </span>
                <span className="font-mono text-lg text-primary font-bold">{requisitions.length}</span>
              </div>
              <div className="flex flex-col px-3 py-1.5">
                <span className="font-mono text-[10px] text-on-surface-variant uppercase">
                  Total Talent
                </span>
                <span className="font-mono text-lg text-on-surface font-bold">
                  {requisitions.reduce((acc, r) => acc + r.applicantsCount, 0)}
                </span>
              </div>
              <div className="flex flex-col px-3 py-1.5">
                <span className="font-mono text-[10px] text-on-surface-variant uppercase">
                  Shortlisted
                </span>
                <span className="font-mono text-lg text-secondary font-bold">
                  {requisitions.reduce((acc, r) => acc + r.pipeline.review, 0)}
                </span>
              </div>
              <div className="flex flex-col px-3 py-1.5">
                <span className="font-mono text-[10px] text-on-surface-variant uppercase">
                  In Interview
                </span>
                <span className="font-mono text-lg text-tertiary font-bold">
                  {requisitions.reduce((acc, r) => acc + r.pipeline.techRound, 0)}
                </span>
              </div>
            </div>

            {isError && (
              <div className="bg-error/10 border border-error/30 text-error rounded-xl px-4 py-3 text-xs font-mono">
                Unable to load job postings from backend. Check API connection and reload.
              </div>
            )}

            <div className="inline-flex items-center justify-center gap-2 bg-surface-container-high text-on-surface font-mono text-xs px-4 py-3 rounded-lg border border-white/10 shadow-sm">
              <span className="w-2 h-2 rounded-full bg-tertiary animate-pulse" />
              <span>CV Analyzer Live Sync</span>
            </div>
          </div>
        </div>

        {/* Collapsible Create Job Posting Form */}
        {showCreateForm && (
          <div className="mt-6 p-5 bg-surface-container-lowest rounded-xl border border-primary/30 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <span className="font-headline text-sm font-semibold text-on-surface flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[20px]">add_circle</span>
                New Position Specification
              </span>
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="text-on-surface-variant hover:text-on-surface"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>
            <form onSubmit={submitPosition} className="space-y-3">
              <input
                value={newTitle}
                onChange={(event) => setNewTitle(event.target.value)}
                placeholder="Job title (e.g. Senior Machine Learning Engineer)"
                className="w-full bg-surface-container text-on-surface px-3 py-2 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-primary"
              />
              <textarea
                value={newDescription}
                onChange={(event) => setNewDescription(event.target.value)}
                placeholder="Paste the job description and key technical requirements..."
                rows={5}
                className="w-full bg-surface-container text-on-surface px-3 py-2 rounded-lg border border-white/10 text-sm resize-y focus:outline-none focus:border-primary"
              />
              {createError && <p className="text-xs text-error">{createError}</p>}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-mono text-on-surface-variant hover:bg-surface-container"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="bg-primary text-black font-semibold text-xs px-4 py-2 rounded-lg disabled:opacity-50 hover:bg-amber-400 transition-all shadow"
                >
                  {creating ? 'Creating...' : 'Create Job Posting'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Department Selector Tabs */}
        <div className="mt-6 pt-4 border-t border-white/5">
          <DepartmentTabs
            selectedDepartment={selectedDept}
            onSelectDepartment={setSelectedDept}
          />
        </div>
      </div>

      {/* Filter & Utility Control Bar */}
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4 bg-surface-container-lowest p-3 rounded-xl border border-white/5 shadow-md">
        {/* Search input */}
        <div className="flex flex-1 items-center gap-2.5 bg-surface-container-low px-3.5 py-2 rounded-lg border border-white/5">
          <span className="material-symbols-outlined text-on-surface-variant text-[20px]">
            filter_list
          </span>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Filter by req code, title, tech stack or hiring lead..."
            className="w-full bg-transparent text-on-surface placeholder:text-on-surface-variant/50 text-xs sm:text-sm focus:outline-none"
          />
          {searchInput && (
            <button
              onClick={() => setSearchInput('')}
              className="font-mono text-[11px] text-on-surface-variant hover:text-on-surface bg-surface-container px-2 py-0.5 rounded"
            >
              Clear
            </button>
          )}
        </div>

        {/* Status Filters & Sorting */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center bg-surface-container-low p-1 rounded-lg border border-white/5">
            {(['All', 'Active', 'Urgent', 'Draft', 'Closed'] as const).map((status) => {
              const active = selectedStatus === status;
              return (
                <button
                  key={status}
                  onClick={() => setSelectedStatus(status)}
                  className={`font-mono text-xs px-3 py-1.5 rounded transition-all ${
                    active
                      ? 'bg-surface-container-high text-primary font-bold shadow-sm'
                      : 'text-on-surface-variant hover:text-on-surface'
                  }`}
                >
                  {status}
                </button>
              );
            })}
          </div>

          <div className="h-6 w-px bg-surface-container-high hidden sm:block" />

          <div className="flex items-center gap-2 bg-surface-container-low px-3 py-1.5 rounded-lg border border-white/5 text-on-surface-variant">
            <span className="font-mono text-[10px] uppercase">Sort:</span>
            <span className="font-mono text-xs text-on-surface flex items-center gap-1 font-semibold">
              AI Fit Index (High-Low)
              <span className="material-symbols-outlined text-[16px]">expand_more</span>
            </span>
          </div>
        </div>
      </div>

      {/* Requisitions Bento Grid */}
      {isLoading ? (
        <div className="py-20 flex flex-col items-center justify-center space-y-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="font-mono text-xs text-on-surface-variant">
            Loading requisitions from server...
          </span>
        </div>
      ) : requisitions.length === 0 ? (
        <div className="py-20 flex flex-col items-center justify-center text-center space-y-3 bg-surface-container-low/40 rounded-xl border border-white/5 p-8">
          <span className="material-symbols-outlined text-4xl text-on-surface-variant">work_off</span>
          <h3 className="font-headline text-base font-semibold text-on-surface">No requisitions found</h3>
          <p className="text-xs text-on-surface-variant max-w-sm">
            {effectiveSearch
              ? `No open positions match "${effectiveSearch}". Try adjusting your filters.`
              : 'No positions are currently available from the server.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-12 gap-6">
          {requisitions.map((req) => <RequisitionCard key={req.id} requisition={req} featured />)}
        </div>
      )}

    </div>
  );
};
