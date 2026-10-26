import {useEffect, useState} from 'react';
import {errorText, request} from './api';
import {MergeReceiptDetails, type MergeReceipt} from './CompanyMerge';

export default function ClientMergeHistory({base, targetId, kind = 'client'}: {base: string; targetId: string; kind?: 'client' | 'contact'}) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<MergeReceipt[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setLoading(true); setError(''); setRows([]);
    const params = new URLSearchParams({target_id: targetId, limit: '20', offset: String(offset)});
    request<MergeReceipt[]>(`${base}/${kind === 'contact' ? 'contact-merges' : 'client-merges'}?${params}`, 'GET', undefined, controller.signal)
      .then(next => {if (!controller.signal.aborted) setRows(next);})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, kind, targetId, open, offset, retry]);
  return <section aria-label={kind === 'contact' ? 'История слияний контактов' : 'История слияний компаний'}>
    <button type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Скрыть историю слияний' : 'История слияний'}</button>
    {open && <>{loading ? <p role="status">Загрузка истории слияний…</p> : !error && <>
      {!rows.length ? <p>Слияний на этой странице нет.</p> : rows.map(row => <MergeReceiptDetails key={row.id} receipt={row} kind={kind}/>)}
      <button type="button" disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 20))}>Предыдущие слияния</button>
      <button type="button" disabled={rows.length < 20} onClick={() => setOffset(n => n + 20)}>Следующие слияния</button>
    </>}{error && <p role="alert">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить загрузку истории</button></p>}</>}
  </section>;
}
