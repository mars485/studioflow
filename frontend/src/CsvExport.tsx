import {useId, useRef, useState} from 'react';
import {ApiError, errorText} from './api';

export default function CsvExport({base, entity, pipelineId}: {base: string; entity: 'deals' | 'clients' | 'contacts'; pipelineId?: string}) {
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const hintId = useId();
  const [hintDismissed, setHintDismissed] = useState(false);
  const download = async () => {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {
      const params = pipelineId ? `?pipeline_id=${encodeURIComponent(pipelineId)}` : '';
      const response = await fetch(`/api/v1${base}/exports/${entity}.csv${params}`, {credentials: 'same-origin'});
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        if (response.status === 401) window.dispatchEvent(new Event('session-expired'));
        throw new ApiError(response.status, typeof data?.detail === 'string' ? data.detail : `Ошибка экспорта (${response.status})`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement('a'); link.href = url; link.download = `studioflow-${entity}.csv`;
        document.body.appendChild(link); link.click(); link.remove();
      } finally {window.setTimeout(() => URL.revokeObjectURL(url), 1000);}
    } catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  return <span className="csvExport" data-hint-dismissed={hintDismissed}
    onMouseEnter={() => setHintDismissed(false)} onFocusCapture={() => setHintDismissed(false)}
    onKeyDown={event => {if (event.key === 'Escape') setHintDismissed(true);}}>
    <button className="filter" type="button" aria-describedby={hintId} disabled={busy} onClick={() => void download()}>{busy ? 'Подготовка CSV…' : 'Скачать CSV'}</button>
    <small className="csvExportHint" id={hintId} role="tooltip">До 5000 строк, без текстового поиска{pipelineId ? ', выбранная воронка' : ''}.</small>
    {error && <span role="alert">{error}</span>}
  </span>;
}
