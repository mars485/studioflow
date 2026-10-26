import {useEffect, useRef, useState} from 'react';
import {errorText, request, type Member, type Role} from './api';

const actions = ['crm.write', 'clients.write', 'tasks.write', 'projects.write', 'finance.write', 'integrations.write'] as const;
type Action = typeof actions[number];
const actionNames: Record<Action, string> = {'crm.write': 'CRM', 'clients.write': 'Клиенты', 'tasks.write': 'Задачи',
  'projects.write': 'Проекты', 'finance.write': 'Финансы', 'integrations.write': 'Интеграции'};
type Group = {id: string; name: string; description: string; version: number; user_ids: string[]; blocked_actions: Action[]};
type Draft = Omit<Group, 'id' | 'version'>;
type AuditRow = {id: string; group_id: string; actor_name: string; action: string; fields: string[]; created_at: string};

function GroupAuditList({base, version}: {base: string; version: number}) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setRows([]);
    request<AuditRow[]>(`${base}/groups/audit?limit=50&offset=${offset}`, 'GET', undefined, controller.signal)
      .then(next => {if (!controller.signal.aborted) setRows(next);})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, version, offset, retry]);
  return <section aria-label="Журнал изменений групп"><h3>Журнал изменений групп</h3>
    {loading ? <p role="status">Загрузка журнала групп…</p> : !error && <>
      {!rows.length ? <p>Записей на этой странице нет.</p> : <ul className="plainList">{rows.map(row => <li key={row.id}>
        <span>{row.action} · {row.actor_name} · <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString()}</time></span>
        <code>{row.group_id}</code><span>Поля: {row.fields.join(', ') || '—'}</span></li>)}</ul>}
      <button type="button" disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие события групп</button>
      <button type="button" disabled={rows.length < 50} onClick={() => setOffset(n => n + 50)}>Следующие события групп</button>
    </>}
    {error && <p role="alert">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить загрузку журнала групп</button></p>}
  </section>;
}

export default function EmployeeGroups({base, role, members}: {base: string; role: Role; members: Member[]}) {
  const [rows, setRows] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<{id?: string; version?: number} | null>(null);
  const [draft, setDraft] = useState<Draft>({name: '', description: '', user_ids: [], blocked_actions: []});
  const [success, setSuccess] = useState('');
  const [history, setHistory] = useState(false);
  const [auditVersion, setAuditVersion] = useState(0);
  const sending = useRef(false);
  const nameInput = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const owner = role === 'OWNER';
  useEffect(() => {if (editor) nameInput.current?.focus();}, [editor]);
  useEffect(() => {if (error) errorRef.current?.focus();}, [error]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Group[]>(`${base}/groups`, 'GET', undefined, controller.signal)
      .then(next => {if (!controller.signal.aborted) setRows(next);})
      .catch(e => {if (!controller.signal.aborted) {setRows([]); setError(errorText(e));}})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, retry]);
  const open = (row?: Group) => {
    setEditor(row ? {id: row.id, version: row.version} : {});
    setDraft(row ? {name: row.name, description: row.description, user_ids: row.user_ids, blocked_actions: row.blocked_actions} :
      {name: '', description: '', user_ids: [], blocked_actions: []});
    setError(''); setSuccess('');
  };
  const save = async () => {
    if (!editor || sending.current || !draft.name.trim()) return;
    sending.current = true; setBusy(true); setError(''); setSuccess('');
    try {
      const saved = await request<Group>(editor.id ? `${base}/groups/${editor.id}` : `${base}/groups`, editor.id ? 'PUT' : 'POST',
        {...draft, name: draft.name.trim(), ...(editor.id ? {expected_version: editor.version} : {})});
      setRows(old => [...old.filter(row => row.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name)));
      setEditor(null); setSuccess('Группа сохранена. Ограничения действуют для следующих API-запросов.'); setAuditVersion(n => n + 1);
    } catch(e) {setError(errorText(e));} finally {sending.current = false; setBusy(false);}
  };
  const remove = async (row: Group) => {
    if (sending.current || !window.confirm(`Удалить группу «${row.name}» и снять её ограничения? Участники и данные студии сохранятся.`)) return;
    sending.current = true; setBusy(true); setError(''); setSuccess('');
    try {
      await request(`${base}/groups/${row.id}?expected_version=${row.version}`, 'DELETE');
      setRows(old => old.filter(item => item.id !== row.id)); setSuccess('Группа удалена; участники студии сохранены.'); setAuditVersion(n => n + 1);
    } catch(e) {setError(errorText(e));} finally {sending.current = false; setBusy(false);}
  };
  return <section className="card settingsCard employeeGroups" aria-label="Группы сотрудников"><h2>Группы сотрудников</h2>
    <p>Группы только ограничивают изменения, но не расширяют права роли и не скрывают ранее доступные данные. Запрет любой группы побеждает. Владелец не блокируется; настройками управляет только владелец.</p>
    <button type="button" disabled={loading || busy} onClick={() => setRetry(n => n + 1)}>Обновить группы</button>
    {owner && <button type="button" disabled={loading || busy || !!editor} onClick={() => open()}>Новая группа</button>}
    {loading ? <p role="status">Загрузка групп…</p> : <>
      {!rows.length ? <p>Групп пока нет.</p> : <ul className="plainList">{rows.map(row => <li key={row.id}>
        <div><strong>{row.name}</strong><p>{row.description || 'Без описания'}</p>
          <p>Участники: {row.user_ids.map(id => members.find(member => member.user_id === id)?.email || id).join(', ') || 'нет'}</p>
          <p>Запрещены изменения: {row.blocked_actions.map(action => actionNames[action]).join(', ') || 'нет ограничений'}</p></div>
        {owner && <><button type="button" disabled={busy || !!editor} onClick={() => open(row)}>Редактировать: {row.name}</button>
          <button type="button" disabled={busy || !!editor} onClick={() => void remove(row)}>Удалить группу: {row.name}</button></>}
      </li>)}</ul>}
    </>}
    {editor && owner && <form aria-label="Форма группы" onSubmit={e => {e.preventDefault(); void save();}}><fieldset disabled={busy}>
      <legend>{editor.id ? 'Редактирование группы' : 'Создание группы'}</legend>
      <label>Название группы<input ref={nameInput} required maxLength={100} value={draft.name} onChange={e => setDraft(old => ({...old, name: e.target.value}))}/></label>
      <label>Описание группы<textarea maxLength={1000} value={draft.description} onChange={e => setDraft(old => ({...old, description: e.target.value}))}/></label>
      <fieldset><legend>Участники группы</legend>{members.map(member => <label className="groupCheck" key={member.user_id}>
        <input type="checkbox" checked={draft.user_ids.includes(member.user_id)} onChange={e => setDraft(old => ({...old,
          user_ids: e.target.checked ? [...old.user_ids, member.user_id] : old.user_ids.filter(id => id !== member.user_id)}))}/>{member.email}{member.role === 'OWNER' ? ' (владелец, запреты не применяются)' : ''}</label>)}</fieldset>
      <fieldset><legend>Запретить изменения в модулях</legend>{actions.map(action => <label className="groupCheck" key={action}>
        <input type="checkbox" checked={draft.blocked_actions.includes(action)} onChange={e => setDraft(old => ({...old,
          blocked_actions: e.target.checked ? [...old.blocked_actions, action] : old.blocked_actions.filter(value => value !== action)}))}/>{actionNames[action]}</label>)}</fieldset>
      <button className="primary" disabled={!draft.name.trim()}>{busy ? 'Сохранение группы…' : 'Сохранить группу'}</button>
      <button type="button" onClick={() => setEditor(null)}>Закрыть форму группы</button>
    </fieldset></form>}
    {error && <p role="alert" ref={errorRef} tabIndex={-1}>{error}</p>}
    {success && <p role="status">{success}</p>}
    <button type="button" onClick={() => setHistory(value => !value)}>{history ? 'Скрыть журнал групп' : 'Открыть журнал групп'}</button>
    {history && <GroupAuditList base={base} version={auditVersion}/>}
  </section>;
}
