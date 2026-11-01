import React, { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { uploadCVs, useCVStatuses, useRequisitions } from '../../services/api';
import { useNavigation } from '../../context/NavigationContext';

const ACCEPTED_TYPES = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.webp']);
const MAX_FILE_SIZE = 15 * 1024 * 1024;

export const CVUploaderView: React.FC = () => {
  const { selectedRequisitionId, setSelectedRequisitionId, setCurrentView } = useNavigation();
  const queryClient = useQueryClient();
  const { data: requisitions = [], isLoading } = useRequisitions();
  const [files, setFiles] = useState<File[]>([]);
  const [message, setMessage] = useState<{ text: string; success: boolean } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [trackedCVIds, setTrackedCVIds] = useState<number[]>([]);

  const selectedPositionId = useMemo(() => {
    const numericId = Number(selectedRequisitionId.replace(/\D/g, ''));
    return requisitions.some((position) => Number(position.id) === numericId)
      ? numericId
      : Number(requisitions[0]?.id);
  }, [requisitions, selectedRequisitionId]);
  const { data: cvStatuses = [] } = useCVStatuses(selectedPositionId);
  const visibleStatuses = cvStatuses.filter((cv) => trackedCVIds.includes(cv.id));

  const addFiles = (selected: FileList | null) => {
    if (!selected) return;
    const accepted: File[] = [];
    const rejected: string[] = [];
    Array.from(selected).forEach((file) => {
      const extension = `.${file.name.split('.').pop()?.toLowerCase()}`;
      if (!ACCEPTED_TYPES.has(extension)) rejected.push(`${file.name}: unsupported file type`);
      else if (file.size > MAX_FILE_SIZE) rejected.push(`${file.name}: exceeds 15 MB`);
      else accepted.push(file);
    });
    setFiles((current) => [...current, ...accepted]);
    setMessage(rejected.length ? { text: rejected.join('; '), success: false } : null);
  };

  const submit = async () => {
    if (!selectedPositionId) {
      setMessage({ text: 'Create or import a job posting before uploading CVs.', success: false });
      return;
    }
    if (!files.length) {
      setMessage({ text: 'Select at least one PDF or image CV.', success: false });
      return;
    }
    setUploading(true);
    setMessage(null);
    try {
      const results = await uploadCVs(selectedPositionId, files);
      setTrackedCVIds(results.flatMap((result) => result.id ? [result.id] : []));
      await queryClient.invalidateQueries({ queryKey: ['cv-statuses', selectedPositionId] });
      await queryClient.invalidateQueries({ queryKey: ['candidates'] });
      const rejected = results.filter((result) => result.status === 'rejected');
      setFiles([]);
      setMessage({
        text: `${results.length - rejected.length} CV(s) queued for processing${rejected.length ? `; ${rejected.length} rejected` : ''}.`,
        success: rejected.length === 0,
      });
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Upload failed.', success: false });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-background px-4 sm:px-6 lg:px-8 py-8">
      <div className="max-w-3xl space-y-6">
        <div>
          <h1 className="font-headline text-2xl sm:text-3xl text-on-surface font-bold">Upload CVs</h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Upload candidate CVs for a job posting. Processing runs in the backend and may take a moment.
          </p>
        </div>
        <div className="bg-surface-container-low rounded-xl p-6 border border-white/5 space-y-5">
          <label className="block text-xs font-mono text-on-surface-variant uppercase">
            Job posting
            <select
              value={selectedPositionId || ''}
              onChange={(event) => {
                const id = Number(event.target.value);
                setSelectedRequisitionId(`req-${id}`);
              }}
              disabled={isLoading || !requisitions.length}
              className="mt-2 w-full bg-surface-container text-on-surface px-3 py-2 rounded-lg border border-white/10"
            >
              {!requisitions.length && <option value="">No job postings available</option>}
              {requisitions.map((position) => <option key={position.id} value={position.id}>{position.title}</option>)}
            </select>
          </label>
          <label className="flex flex-col items-center justify-center gap-2 min-h-40 border border-dashed border-primary/40 rounded-xl cursor-pointer hover:bg-primary/5">
            <span className="material-symbols-outlined text-primary text-4xl">upload_file</span>
            <span className="text-sm text-on-surface">Choose PDF or image CVs</span>
            <span className="text-xs text-on-surface-variant">PDF, PNG, JPG, JPEG, WEBP; maximum 15 MB each</span>
            <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp" className="hidden" onChange={(event) => addFiles(event.target.files)} />
          </label>
          {files.length > 0 && (
            <div className="space-y-1 text-sm text-on-surface-variant">
              {files.map((file) => <div key={`${file.name}-${file.size}`}>{file.name}</div>)}
            </div>
          )}
          {visibleStatuses.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-mono uppercase text-on-surface-variant">
                Processing status
              </div>
              {visibleStatuses.map((cv) => (
                <div key={cv.id} className="flex items-center justify-between gap-3 text-xs text-on-surface-variant">
                  <span className="truncate">{cv.filename}</span>
                  <span className={cv.status === 'done' ? 'text-tertiary' : cv.status === 'failed' || cv.status === 'rejected' ? 'text-error' : 'text-primary'}>
                    {cv.status}
                  </span>
                </div>
              ))}
            </div>
          )}
          {message && <div className={`text-xs p-3 rounded-lg ${message.success ? 'text-tertiary bg-tertiary/10' : 'text-error bg-error/10'}`}>{message.text}</div>}
          <div className="flex justify-between gap-3">
            <button onClick={() => setCurrentView('candidate-search')} className="text-xs text-on-surface-variant hover:text-on-surface px-3 py-2">View candidates</button>
            <button onClick={submit} disabled={uploading || !files.length} className="bg-primary text-black font-semibold text-xs px-4 py-2 rounded-lg disabled:opacity-50">
              {uploading ? 'Uploading...' : 'Upload CVs'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
