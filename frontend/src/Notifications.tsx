import {useEffect, useRef, useState} from 'react';
import {errorText, request, type Workspace} from './api';

export type InboxNotification = {id: string; workspace_id: string; activity_id: string; deal_id: string; deal_title: string;
  body: string; author_name: string; read_at: string | null; created_at: string};

function Inbox({workspaceId, onOpenDeal}: {workspaceId: string; onOpenDeal: (workspaceId: string, dealId: string) => void}) {
  const base = `/workspaces/${workspaceId}/notifications`;
  const [rows, setRows] = useState<InboxNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setRows([]);
    Promise.all([request<InboxNotification[]>(`${base}?unread_only=${unreadOnly}&limit=50&offset=${offset}`, 'GET', undefined, controller.signal),
      request<{count: number}>(`${base}/unread-count`, 'GET', undefined, controller.signal)])
      .then(([next, count]) => {if (!controller.signal.aborted) {setRows(next); setUnread(count.count);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, unreadOnly, offset, retry]);
  const run = async (operation: () => Promise<void>) => {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {await operation(); setRetry(n => n + 1);} catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  return <>
    <div className="crmTools notificationTools"><span role="status">Непрочитанных: {unread}</span>
      <label className="checkboxLabel"><input type="checkbox" disabled={busy} checked={unreadOnly} onChange={e => {setUnreadOnly(e.target.checked); setOffset(0);}}/>Только непрочитанные</label>
      <button disabled={loading || busy} onClick={() => {setOffset(0); setRetry(n => n + 1);}}>Обновить уведомления</button>
      <button disabled={loading || busy || !unread} onClick={() => void run(async () => {await request(`${base}/read-all`, 'POST'); setOffset(0);})}>Прочитать все</button>
    </div>
    {loading ? <p role="status">Загрузка уведомлений…</p> : !error && !rows.length ? <p className="muted">Уведомлений нет.</p> :
      <ol className="activityList">{rows.map(row => <li key={row.id}>
        <strong>{row.author_name}</strong> · {row.deal_title} · <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString('ru-RU')}</time>
        <p style={{whiteSpace: 'pre-wrap'}}>{row.body}</p><p className="muted">{row.read_at ? 'Прочитано' : 'Новое упоминание'}</p>
        <button disabled={busy} onClick={() => void run(async () => {await request(`${base}/${row.id}/read`, 'POST'); onOpenDeal(workspaceId, row.deal_id);})}>Открыть сделку {row.deal_title}</button>
        {!row.read_at && <button disabled={busy} onClick={() => void run(async () => {await request(`${base}/${row.id}/read`, 'POST'); setOffset(0);})}>Прочитать уведомление {row.deal_title}</button>}
      </li>)}</ol>}
    {error && <p role="alert" className="errorMessage">{error} <button disabled={busy} onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
    <div className="crmTools"><button disabled={loading || busy || !offset} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие уведомления</button>
      <button disabled={loading || busy || rows.length < 50} onClick={() => setOffset(n => n + 50)}>Следующие уведомления</button></div>
  </>;
}

export default function Notifications({onOpenDeal}: {onOpenDeal: (workspaceId: string, dealId: string) => void}) {
  const [spaces, setSpaces] = useState<Workspace[]>([]);
  const [id, setId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal).then(rows => {
      if (!controller.signal.aborted) {setSpaces(rows); setId(previous => rows.some(row => row.id === previous) ? previous : rows[0]?.id || '');}
    }).catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [retry]);
  return <><header><div><h1>Уведомления</h1><p>Адресные упоминания внутри студии · без email и push</p></div></header>
    {loading ? <p role="status">Загрузка студий…</p> : <>
      <label>Рабочее пространство<select value={id} onChange={e => setId(e.target.value)}>{spaces.map(space => <option key={space.id} value={space.id}>{space.name}</option>)}</select></label>
      {id ? <Inbox key={id} workspaceId={id} onOpenDeal={onOpenDeal}/> : <p>Создайте студию в настройках.</p>}
    </>}
    {error && <p role="alert">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
  </>;
}
