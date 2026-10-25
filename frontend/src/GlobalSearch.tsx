import {useEffect, useState} from 'react';
import {errorText, request, type Workspace} from './api';

export type SearchTarget = {workspaceId: string; kind: 'deal' | 'client' | 'contact' | 'task' | 'project'; id: string};
type Result = {kind: SearchTarget['kind']; id: string; label: string; state: string};
const names = {deal: 'Сделка', client: 'Компания', contact: 'Контакт', task: 'Задача', project: 'Проект'};
const actions = {deal: 'сделку', client: 'компанию', contact: 'контакт', task: 'задачу', project: 'проект'};

function Results({workspaceId, onOpen}: {workspaceId: string; onOpen: (target: SearchTarget) => void}) {
  const [draft, setDraft] = useState('');
  const [kind, setKind] = useState('all');
  const [query, setQuery] = useState<{text: string; kind: string} | null>(null);
  const [rows, setRows] = useState<Result[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!query) return;
    const controller = new AbortController(); setLoading(true); setError(''); setRows([]); setTotal(0);
    const params = new URLSearchParams({q: query.text, kind: query.kind, limit: '50', offset: String(offset)});
    request<{items: Result[]; total: number}>(`/workspaces/${workspaceId}/search?${params}`, 'GET', undefined, controller.signal)
      .then(data => {if (!controller.signal.aborted) {setRows(data.items); setTotal(data.total);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [workspaceId, query, offset, retry]);
  return <><form onSubmit={e => {e.preventDefault(); setQuery({text: draft.trim(), kind}); setOffset(0);}} className="inlineForm">
    <label>Поисковый запрос<input required minLength={2} maxLength={255} value={draft} onChange={e => setDraft(e.target.value)}/></label>
    <label>Тип результата<select value={kind} onChange={e => setKind(e.target.value)}><option value="all">Все типы</option>{Object.entries(names).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <button disabled={draft.trim().length < 2}>Найти в студии</button>
  </form>
    {loading ? <p role="status">Поиск…</p> : query && !error && <section aria-label="Результаты общего поиска"><p>Найдено: {total} · запрос «{query.text}»</p>
      {!rows.length ? <p>Совпадений нет.</p> : <ul className="plainList">{rows.map(row => <li key={`${row.kind}:${row.id}`}>
        <span>{names[row.kind]} · {row.state === 'ARCHIVED' ? 'Архив' : row.state}</span>
        <button type="button" onClick={() => onOpen({workspaceId, kind: row.kind, id: row.id})}>Открыть {actions[row.kind]} {row.label}</button>
      </li>)}</ul>}
      <button type="button" disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие результаты</button>
      <button type="button" disabled={offset + rows.length >= total} onClick={() => setOffset(n => n + 50)}>Следующие результаты</button>
    </section>}
    {error && <p role="alert">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить поиск</button></p>}
  </>;
}

export default function GlobalSearch({onOpen}: {onOpen: (target: SearchTarget) => void}) {
  const [spaces, setSpaces] = useState<Workspace[]>([]);
  const [id, setId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal).then(rows => {
      if (!controller.signal.aborted) {setSpaces(rows); setId(old => rows.some(row => row.id === old) ? old : rows[0]?.id || '');}
    }).catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [retry]);
  return <><header><div><h1>Общий поиск</h1><p>Сделки, компании, контакты, задачи и проекты выбранной студии</p></div></header>
    {loading ? <p role="status">Загрузка студий…</p> : <><label>Рабочее пространство<select value={id} onChange={e => setId(e.target.value)}>{spaces.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      {id ? <Results key={id} workspaceId={id} onOpen={onOpen}/> : <p>Создайте студию в настройках.</p>}</>}
    {error && <p role="alert">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
  </>;
}
