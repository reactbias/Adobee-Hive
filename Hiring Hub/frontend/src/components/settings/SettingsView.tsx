import React, { useState } from 'react';
import { getApiKey, setApiKey, bootstrapOrganization, fetchWithAuth } from '../../services/api';

export const SettingsView: React.FC = () => {
  const [apiKeyInput, setApiKeyInput] = useState(getApiKey());
  const [statusMsg, setStatusMsg] = useState<{ text: string; success: boolean } | null>(null);
  const [testing, setTesting] = useState(false);

  const handleSaveApiKey = () => {
    setApiKey(apiKeyInput.trim());
    setStatusMsg({ text: 'API Key saved to localStorage.', success: true });
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setStatusMsg(null);
    try {
      const res = await fetchWithAuth<unknown[]>('/positions');
      setStatusMsg({
        text: `Backend connection verified! Found ${Array.isArray(res) ? res.length : 0} positions.`,
        success: true,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMsg({
        text: `Connection test failed: ${msg}. Make sure backend is running on port 8000.`,
        success: false,
      });
    } finally {
      setTesting(false);
    }
  };

  const handleBootstrapOrg = async () => {
    setTesting(true);
    setStatusMsg(null);
    try {
      const key = await bootstrapOrganization('Adobee Hive');
      setApiKeyInput(key);
      setStatusMsg({
        text: `Organization 'Adobee Hive' provisioned! API Key set to: ${key}`,
        success: true,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMsg({ text: `Bootstrap failed: ${msg}`, success: false });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-background px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div>
        <h1 className="font-headline text-2xl sm:text-3xl text-on-surface font-bold tracking-tight">
          Settings & Cluster Configuration
        </h1>
        <p className="text-xs sm:text-sm text-on-surface-variant max-w-2xl mt-1 leading-relaxed">
          Manage ATS webhook synchronizations, LLM embedding models, and backend CV Analyzer connectivity.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Backend CV Analyzer Connection Card */}
        <div className="bg-surface-container-low rounded-xl p-6 border border-white/5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-[22px]">api</span>
              <h2 className="font-headline text-base text-on-surface font-semibold">
                Backend CV Analyzer Connection
              </h2>
            </div>
            <span className="font-mono text-xs text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded font-semibold">
              FastAPI:8000
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="block font-mono text-[11px] text-on-surface-variant uppercase mb-1">
                Organization API Key (x-api-key)
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  placeholder="Enter organization API key..."
                  className="flex-1 bg-surface-container text-xs text-on-surface font-mono px-3 py-2 rounded-lg border border-white/10 focus:outline-none focus:border-primary"
                />
                <button
                  onClick={handleSaveApiKey}
                  className="bg-primary text-black font-semibold text-xs px-3 py-2 rounded-lg hover:bg-amber-400 transition-colors"
                >
                  Save
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 pt-1">
              <button
                onClick={handleTestConnection}
                disabled={testing}
                className="bg-surface-container hover:bg-surface-container-high text-on-surface text-xs px-3.5 py-2 rounded-lg border border-white/5 flex items-center gap-1.5 transition-colors"
              >
                <span className="material-symbols-outlined text-[16px] text-tertiary">
                  {testing ? 'sync' : 'network_check'}
                </span>
                <span>{testing ? 'Testing...' : 'Test Connection'}</span>
              </button>

              <button
                onClick={handleBootstrapOrg}
                disabled={testing}
                className="bg-surface-container hover:bg-surface-container-high text-on-surface text-xs px-3.5 py-2 rounded-lg border border-white/5 flex items-center gap-1.5 transition-colors"
              >
                <span className="material-symbols-outlined text-[16px] text-secondary">domain_add</span>
                <span>Auto-Bootstrap Org</span>
              </button>
            </div>

            {statusMsg && (
              <div
                className={`p-2.5 rounded-lg text-xs font-mono border ${
                  statusMsg.success
                    ? 'bg-tertiary/10 text-tertiary border-tertiary/20'
                    : 'bg-error/10 text-error border-error/20'
                }`}
              >
                {statusMsg.text}
              </div>
            )}
          </div>
        </div>

        {/* Integrations Card */}
        <div className="bg-surface-container-low rounded-xl p-6 border border-white/5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-[22px]">sync_alt</span>
              <h2 className="font-headline text-base text-on-surface font-semibold">
                Connected ATS Platforms
              </h2>
            </div>
            <span className="font-mono text-xs text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded font-semibold">
              Roadmap Preview
            </span>
          </div>

          <div className="space-y-3">
            {[
              { name: 'Greenhouse Recruiting', status: 'ATS Sync Connector', id: 'Roadmap v2.0' },
              { name: 'Checkr Background Verification', status: 'Background Clearance Verification', id: 'Roadmap v2.0' },
              { name: 'The Work Number (Equifax)', status: 'Tenure & Employment History API', id: 'Roadmap v2.1' },
            ].map((integ) => (
              <div
                key={integ.name}
                className="bg-surface-container p-3 rounded-lg flex items-center justify-between border border-white/5"
              >
                <div>
                  <div className="text-xs font-semibold text-on-surface">{integ.name}</div>
                  <div className="font-mono text-[11px] text-on-surface-variant mt-0.5">
                    {integ.status} • {integ.id}
                  </div>
                </div>
                <span className="font-mono text-[10px] text-on-surface-variant bg-surface-container-high px-2 py-0.5 rounded border border-white/5">
                  Upcoming
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* AI Neural Engine Config */}
        <div className="bg-surface-container-low rounded-xl p-6 border border-white/5 shadow-lg space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-secondary text-[22px]">neurology</span>
              <h2 className="font-headline text-base text-on-surface font-semibold">
                Hive Neural Matcher & Recruiter Agent Configuration
              </h2>
            </div>
            <span className="font-mono text-xs text-primary bg-primary/10 px-2 py-0.5 rounded font-semibold">
              OpenAI Model: gpt-4o
            </span>
          </div>

          <div className="space-y-4 text-xs">
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-on-surface">Code Repository & OSS Impact Weight</span>
                <span className="font-mono text-primary font-bold">35%</span>
              </div>
              <div className="w-full bg-surface-container-high h-2 rounded-full overflow-hidden">
                <div className="bg-primary h-full rounded-full" style={{ width: '35%' }} />
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-on-surface">Architectural & Systems Latency Calibration</span>
                <span className="font-mono text-secondary font-bold">45%</span>
              </div>
              <div className="w-full bg-surface-container-high h-2 rounded-full overflow-hidden">
                <div className="bg-secondary h-full rounded-full" style={{ width: '45%' }} />
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-on-surface">Verified Career History & Tenure Duration</span>
                <span className="font-mono text-tertiary font-bold">20%</span>
              </div>
              <div className="w-full bg-surface-container-high h-2 rounded-full overflow-hidden">
                <div className="bg-tertiary h-full rounded-full" style={{ width: '20%' }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
