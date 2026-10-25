import {useEffect, useState} from 'react';
import {errorText, request} from './api';

type AuditRow = {id: string; deal_id: string; actor_id: string; actor_kind: 'USER' | 'INTEGRATION'; actor_name: string;
  action: 'CREATED' | 'UPDATED' | 'DELETED'; fields: string[]; created_at: string};
const actions = {CREATED: 'Создание', UPDATED: 'Изменение', DELETED: 'Удаление'};

export default function DealAudit({base}: {base: string}) {
  const [draftId, setDraftId] = useState('');
  const [action, setAction] = useState('');
  const [filter, setFilter] = useState({id: '', action: ''});
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setRows([]);
    const params = new URLSearchParams({limit: '50', offset: String(offset)});
    if (filter.id) params.set('deal_id', filter.id);
    if (filter.action) params.set('action', filter.action);
    request<{items: AuditRow[]; total: number}>(`${base}/deal-audit?${params}`, 'GET', undefined, controller.signal)
      .then(page => {if (!controller.signal.aborted) {setRows(page.items); setTotal(page.total);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, filter, offset, retry]);
  return <section className="card settingsCard" aria-label="Аудит сделок"><h2>Аудит основных изменений сделок</h2>
    <p className="muted">Только создание, основной PATCH и удаление после включения журнала. Отдельные действия follow-up, комментарии и другие модули сюда не входят. Значения полей не сохраняются. История остаётся после удаления сделки, записи доступны только для чтения.</p>
    <form className="inlineForm" onSubmit={e => {e.preventDefault(); setFilter({id: draftId.trim(), action}); setOffset(0);}}>
      <label>UUID сделки в аудите<input value={draftId} onChange={e => setDraftId(e.target.value)}
        pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/></label>
      <label>Операция аудита<select aria-label="Операция аудита" value={action} onChange={e => setAction(e.target.value)}><option value="">Все операции</option>{Object.entries(actions).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
      <button>Применить фильтр аудита</button>
    </form>
    <button type="button" disabled={loading} onClick={() => setRetry(n => n + 1)}>Обновить аудит</button>
    {loading ? <p role="status">Загрузка аудита…</p> : !error && <><p>Записей аудита: {total}</p>
      {!rows.length ? <p>Записей по выбранному фильтру нет.</p> : <ul className="plainList">{rows.map(row => <li key={row.id}>
        <strong>{actions[row.action]}</strong><span>{new Date(row.created_at).toLocaleString('ru-RU')} · {row.actor_name} · {row.actor_kind === 'USER' ? 'Пользователь' : 'Токен интеграции'}</span>
        <span>Сделка: {row.deal_id} · Автор: {row.actor_id}</span>
        {row.fields.length > 0 && <span>Изменены поля: {row.fields.join(', ')}</span>}
      </li>)}</ul>}
      <button type="button" disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие записи аудита</button>
      <button type="button" disabled={offset + rows.length >= total} onClick={() => setOffset(n => n + 50)}>Следующие записи аудита</button>
    </>}
    {error && <p role="alert">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить загрузку аудита</button></p>}
  </section>;
}
