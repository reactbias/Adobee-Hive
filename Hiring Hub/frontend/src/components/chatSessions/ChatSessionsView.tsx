import React, { useEffect, useState } from 'react';
import { ChatSession } from '../../types';
import { useNavigation } from '../../context/NavigationContext';
import { fetchChatSessions } from '../../services/api';

export const ChatSessionsView: React.FC = () => {
  const { setCurrentView, setSelectedRequisitionId } = useNavigation();
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  const loadSessions = () => {
    fetchChatSessions().then(setSessions).catch(() => setSessions([]));
  };

  useEffect(() => {
    loadSessions();
  }, []);

  return (
    <div className="w-full min-h-screen bg-background px-4 sm:px-6 lg:px-8 py-8">
      <div className="max-w-4xl space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
          <h1 className="font-headline text-2xl sm:text-3xl text-on-surface font-bold">Chat Sessions</h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Review recruiter queries and the candidate results returned by the filter agent.
          </p>
          </div>
          <button
            onClick={loadSessions}
            className="shrink-0 p-2 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high"
            title="Refresh sessions"
          >
            <span className="material-symbols-outlined">refresh</span>
          </button>
        </div>
        {sessions.length === 0 ? (
          <div className="bg-surface-container-low rounded-xl p-8 border border-white/5 text-sm text-on-surface-variant">
            No chat sessions yet. Open a candidate pool and run a filter query.
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => {
                  setSelectedRequisitionId(session.positionId);
                  setCurrentView('candidate-search');
                }}
                className="w-full text-left bg-surface-container-low rounded-xl p-5 border border-white/5 hover:border-primary/40"
              >
                <div className="flex items-center justify-between gap-4">
                  <span className="font-semibold text-on-surface">{session.positionTitle}</span>
                  <span className="text-xs font-mono text-on-surface-variant">
                    {session.messages.length} messages
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant mt-2">
                  {session.messages.find((message) => message.sender === 'recruiter')?.text || 'Empty session'}
                </p>
                <span className="block text-[11px] font-mono text-on-surface-variant mt-3">
                  Updated {session.updatedAt ? new Date(session.updatedAt).toLocaleString() : 'Recently'}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
