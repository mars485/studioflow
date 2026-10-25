import {useEffect, useState, type FormEvent} from 'react';
import {type DealTask, type Member, errorText, localDateTime, request} from './api';
import TaskReminders from './TaskReminders';

type Draft = {title: string; description: string; priority: DealTask['priority']; assignee_user_id: string;
  start_at: string; due_at: string};
const empty: Draft = {title: '', description: '', priority: 'MEDIUM', assignee_user_id: '', start_at: '', due_at: ''};

export default function DealTasks({base, dealId, members, canDelete}: {base: string; dealId: string; members: Member[]; canDelete: boolean}) {
  const [rows, setRows] = useState<DealTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(empty);
  const path = `${base}/deals/${dealId}/tasks`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    request<DealTask[]>(path, 'GET', undefined, controller.signal)
      .then(result => {if (!controller.signal.aborted) {setRows(result); setLoading(false);}})
      .catch(e => {if (!controller.signal.aborted) {setError(errorText(e)); setLoading(false);}});
    return () => controller.abort();
  }, [path, reload]);

  const run = async (operation: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError('');
    try {await operation();} catch(e) {setError(errorText(e));}
    finally {setBusy(false);}
  };
  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft.title.trim()) return;
    void run(async () => {
      const payload = {title: draft.title.trim(), description: draft.description || null, priority: draft.priority,
        assignee_user_id: draft.assignee_user_id || null,
        start_at: draft.start_at ? new Date(draft.start_at).toISOString() : null,
        due_at: draft.due_at ? new Date(draft.due_at).toISOString() : null};
      const row = await request<DealTask>(editingId ? `${path}/${editingId}` : path, editingId ? 'PATCH' : 'POST', payload);
      setRows(previous => editingId ? previous.map(item => item.id === row.id ? row : item) : [...previous, row]);
      setDraft(empty); setEditingId(null);
    });
  };
  const edit = (row: DealTask) => {
    setEditingId(row.id);
    setDraft({title: row.title, description: row.description || '', priority: row.priority,
      assignee_user_id: row.assignee_user_id || '', start_at: localDateTime(row.start_at), due_at: localDateTime(row.due_at)});
  };
  const toggle = (row: DealTask) => void run(async () => {
    const updated = await request<DealTask>(`${path}/${row.id}`, 'PATCH', {status: row.status === 'OPEN' ? 'DONE' : 'OPEN'});
    setRows(previous => previous.map(item => item.id === row.id ? updated : item));
  });
  const remove = (row: DealTask) => {
    if (!window.confirm(`Удалить задачу «${row.title}»?`)) return;
    void run(async () => {await request(`${path}/${row.id}`, 'DELETE'); setRows(previous => previous.filter(item => item.id !== row.id));});
  };

  return <section className="drawerSection dealTasks"><h3>Задачи по сделке</h3>
    {loading ? <p role="status">Загрузка задач…</p> : error && !rows.length ? <p role="alert">{error} <button type="button" onClick={() => setReload(n => n + 1)}>Повторить</button></p> : rows.length ?
      <ul className="dealTaskList">{rows.map(row => <li key={row.id}>
        <label><input type="checkbox" checked={row.status === 'DONE'} disabled={busy} onChange={() => toggle(row)}/><strong>{row.title}</strong></label>
        <p>{row.priority === 'HIGH' ? 'Высокий' : row.priority === 'LOW' ? 'Низкий' : 'Средний'} приоритет · {members.find(member => member.user_id === row.assignee_user_id)?.first_name || 'Без исполнителя'}{row.due_at ? ` · до ${new Date(row.due_at).toLocaleString('ru-RU')}` : ''}</p>
        {row.description && <p>{row.description}</p>}
        <TaskReminders base={base} dealId={dealId} task={row} members={members}/>
        <button type="button" disabled={busy} onClick={() => edit(row)}>Изменить {row.title}</button>
        {canDelete && <button type="button" disabled={busy} onClick={() => remove(row)}>Удалить {row.title}</button>}
      </li>)}</ul> : <p className="muted">Задач по сделке пока нет.</p>}
    {error && rows.length > 0 && <p role="alert" className="errorMessage">{error}</p>}
    <form onSubmit={save}><h4>{editingId ? 'Изменить задачу' : 'Новая задача'}</h4>
      <fieldset disabled={busy}>
        <label>Название задачи<input required maxLength={255} value={draft.title} onChange={e => setDraft({...draft, title: e.target.value})}/></label>
        <label>Описание задачи<textarea maxLength={10000} value={draft.description} onChange={e => setDraft({...draft, description: e.target.value})}/></label>
        <label>Приоритет задачи<select value={draft.priority} onChange={e => setDraft({...draft, priority: e.target.value as DealTask['priority']})}><option value="LOW">Низкий</option><option value="MEDIUM">Средний</option><option value="HIGH">Высокий</option></select></label>
        <label>Исполнитель задачи<select value={draft.assignee_user_id} onChange={e => setDraft({...draft, assignee_user_id: e.target.value})}><option value="">Не назначен</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}</select></label>
        <label>Начало задачи<input type="datetime-local" value={draft.start_at} onChange={e => setDraft({...draft, start_at: e.target.value})}/></label>
        <label>Крайний срок<input type="datetime-local" value={draft.due_at} onChange={e => setDraft({...draft, due_at: e.target.value})}/></label>
        <button disabled={!draft.title.trim()}>{busy ? 'Сохранение…' : editingId ? 'Сохранить задачу' : 'Добавить задачу'}</button>
        {editingId && <button type="button" onClick={() => {setEditingId(null); setDraft(empty);}}>Отмена</button>}
      </fieldset>
    </form>
  </section>;
}
