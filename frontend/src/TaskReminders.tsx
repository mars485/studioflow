import {useEffect, useState, type FormEvent} from 'react';
import {type DealTask, type Member, type TaskReminder, errorText, request} from './api';

export default function TaskReminders({base, dealId, task, members}: {base: string; dealId: string; task: DealTask; members: Member[]}) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<TaskReminder[]>([]);
  const [kind, setKind] = useState<TaskReminder['kind']>('DATE');
  const [at, setAt] = useState('');
  const [minutes, setMinutes] = useState(60);
  const [recipient, setRecipient] = useState(task.assignee_user_id || members[0]?.user_id || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const path = `${base}/deals/${dealId}/tasks/${task.id}/reminders`;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    request<TaskReminder[]>(path, 'GET', undefined, controller.signal)
      .then(value => {if (!controller.signal.aborted) setRows(value);})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));});
    return () => controller.abort();
  }, [open, path]);
  const add = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!recipient || (kind === 'DATE' && !at)) return;
    setBusy(true); setError('');
    void request<TaskReminder>(path, 'POST', {recipient_user_id: recipient, kind,
      at: kind === 'DATE' ? new Date(at).toISOString() : null,
      offset_minutes: kind === 'DATE' ? null : minutes})
      .then(row => {setRows(previous => [...previous, row]); setAt('');})
      .catch(e => setError(errorText(e))).finally(() => setBusy(false));
  };
  const remove = (id: string) => {
    setBusy(true); setError('');
    void request(`${path}/${id}`, 'DELETE').then(() => setRows(previous => previous.filter(row => row.id !== id)))
      .catch(e => setError(errorText(e))).finally(() => setBusy(false));
  };
  const description = (row: TaskReminder) => row.kind === 'DATE' ?
    `В ${new Date(row.at!).toLocaleString('ru-RU')}` :
    `${row.offset_minutes} мин до ${row.kind === 'START_OFFSET' ? 'начала' : 'крайнего срока'}`;
  return <div className="taskReminders">
    <button type="button" onClick={() => setOpen(value => !value)}>{open ? 'Скрыть напоминания' : `Напоминания: ${task.title}`}</button>
    {open && <>
      {rows.length ? <ul>{rows.map(row => <li key={row.id}>{description(row)} · {members.find(member => member.user_id === row.recipient_user_id)?.first_name || 'Участник'}{row.acknowledged_at ? ' · просмотрено' : ''} <button type="button" disabled={busy} onClick={() => remove(row.id)}>Удалить напоминание</button></li>)}</ul> : <p className="muted">Напоминаний пока нет.</p>}
      <form onSubmit={add}><fieldset disabled={busy || task.status === 'DONE'}><legend>Новое напоминание</legend>
        <label>Когда<select value={kind} onChange={e => setKind(e.target.value as TaskReminder['kind'])}><option value="DATE">В заданную дату</option><option value="START_OFFSET" disabled={!task.start_at}>До начала задачи</option><option value="DUE_OFFSET" disabled={!task.due_at}>До крайнего срока</option></select></label>
        {kind === 'DATE' ? <label>Дата и время напоминания<input type="datetime-local" required value={at} onChange={e => setAt(e.target.value)}/></label> :
          <label>За сколько минут<input type="number" min="0" max="525600" required value={minutes} onChange={e => setMinutes(Number(e.target.value))}/></label>}
        <label>Кому<select required value={recipient} onChange={e => setRecipient(e.target.value)}><option value="">Выберите участника</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}</select></label>
        <button type="submit">Добавить напоминание</button>
      </fieldset></form>
      {task.status === 'DONE' && <p className="muted">Задача завершена.</p>}
      {error && <p role="alert" className="errorMessage">{error}</p>}
    </>}
  </div>;
}
