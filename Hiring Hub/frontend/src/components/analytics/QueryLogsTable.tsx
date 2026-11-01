import React from 'react';
import { QueryLogItem } from '../../types';

interface QueryLogsTableProps {
  queryLogs: QueryLogItem[];
}

export const QueryLogsTable: React.FC<QueryLogsTableProps> = ({ queryLogs }) => {
  return (
    <div className="lg:col-span-7 bg-surface-container-low rounded-xl p-6 flex flex-col justify-between shadow-sm border border-white/5">
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary text-[20px]">
              travel_explore
            </span>
            <h2 className="font-headline text-base text-on-surface font-semibold">
              Top AI Natural Language Queries
            </h2>
          </div>
          <span className="font-mono text-xs text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded font-semibold">
            Semantic Engine V3
          </span>
        </div>
        <p className="text-xs text-on-surface-variant mb-4">
          Aggregated recruitment query themes dispatched by sourcing leads and hiring managers this week.
        </p>

        <div className="space-y-2.5">
          {queryLogs.length === 0 ? (
            <div className="text-center py-8 text-xs text-on-surface-variant font-mono">
              No natural language queries dispatched yet.
            </div>
          ) : (
            queryLogs.map((item) => (
              <div
                key={item.id}
                className="bg-surface-container p-3 rounded-lg hover:bg-surface-container-high transition-colors flex items-center justify-between border border-white/5 gap-3"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="material-symbols-outlined text-primary text-[20px] shrink-0">
                    {item.icon}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs text-on-surface font-semibold truncate">
                        {item.query}
                      </span>
                      {item.tag && (
                        <span className="font-mono text-[9px] uppercase bg-primary/20 text-primary px-1.5 py-0.2 rounded font-bold">
                          {item.tag}
                        </span>
                      )}
                    </div>
                    <div className="font-mono text-[11px] text-on-surface-variant mt-0.5">
                      {item.retrievedCount} candidates retrieved • {item.accuracyPercent}% accuracy
                    </div>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <span className="font-mono text-xs text-tertiary font-bold block">
                    {item.matchedCount} matched
                  </span>
                  <span className="font-mono text-[10px] text-on-surface-variant uppercase">
                    {item.team}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
