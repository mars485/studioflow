import {useEffect, useRef, useState} from 'react';
import {errorText, newRequestKey, request} from './api';

export type TimeEntry = {id: string; task_id: string; task_title: string; author_name: string; worked_on: string; seconds: number;
  started_at: string | null; ended_at: string | null; comment: string | null; is_running: boolean; elapsed_seconds: number; can_edit: boolean; stop_reason: string | null};
type TimePage = {items: TimeEntry[]; total_seconds: number; timezone: string; today: string};
export const duration = (seconds: number) => `${Math.floor(seconds / 3600)} ч ${Math.floor(seconds % 3600 / 60)} мин ${seconds % 60} с`;

export default function TaskTime({base, taskId, isFinal}: {base: string; taskId: string; isFinal: boolean}) {
  const path = `${base}/tasks/${taskId}`;
  const [page, setPage] = useState<TimePage>();
  const [timer, setTimer] = useState<TimeEntry | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [date, setDate] = useState('');
  const [minutes, setMinutes] = useState('');
  const [comment, setComment] = useState('');
  const manualKey = useRef(newRequestKey());
  const timerKey = useRef(newRequestKey());
  const [tick, setTick] = useState(0);
  const received = useRef(Date.now());
  const [editing, setEditing] = useState<TimeEntry | null>(null);
  const [editMinutes, setEditMinutes] = useState('');
  const [editDate, setEditDate] = useState('');
  const [editComment, setEditComment] = useState('');
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    Promise.all([request<TimePage>(`${path}/time-entries?limit=50&offset=${offset}`, 'GET', undefined, controller.signal),
      request<TimeEntry | null>(`${base}/time-timer`, 'GET', undefined, controller.signal)])
      .then(([next, active]) => {if (!controller.signal.aborted) {setPage(next); setTimer(active); received.current = Date.now(); setTick(0); setDate(old => old || next.today);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [path, base, offset, retry, isFinal]);
  useEffect(() => {
    if (!timer) return;
    const interval = window.setInterval(() => setTick(Math.max(0, Math.floor((Date.now() - received.current) / 1000))), 1000);
    return () => window.clearInterval(interval);
  }, [timer]);
  const run = async (operation: () => Promise<unknown>) => {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {await operation(); setRetry(n => n + 1);} catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  return <section className="drawerSection" aria-label="Учёт времени"><h3>Учёт времени</h3>
    <button type="button" disabled={busy || loading} onClick={() => setRetry(n => n + 1)}>Обновить время</button>
    {loading ? <p role="status">Загрузка времени…</p> : page && <>
      <p>Записано: {duration(page.total_seconds)} · часовой пояс студии: {page.timezone}</p>
      {timer ? <p role="status">Таймер: {timer.task_title} · {duration(timer.elapsed_seconds + tick)} <button type="button" disabled={busy}
        onClick={() => void run(() => request(`${base}/time-entries/${timer.id}/stop`, 'POST'))}>Остановить таймер</button></p> :
        <button type="button" disabled={busy || isFinal} onClick={() => void run(async () => {
          await request(`${path}/timer`, 'POST', {request_key: timerKey.current}); timerKey.current = newRequestKey();
        })}>Запустить таймер</button>}
      <form onSubmit={e => {e.preventDefault(); void run(async () => {
        await request(`${path}/time-entries`, 'POST', {request_key: manualKey.current, worked_on: date, minutes: Number(minutes), comment: comment || null});
        manualKey.current = newRequestKey(); setMinutes(''); setComment(''); setOffset(0);
      });}}><fieldset disabled={busy}>
        <label>Дата работы<input required type="date" max={page.today} value={date} onChange={e => {setDate(e.target.value); manualKey.current = newRequestKey();}}/></label>
        <label>Затрачено минут<input required type="number" min="1" max="525600" step="1" value={minutes} onChange={e => {setMinutes(e.target.value); manualKey.current = newRequestKey();}}/></label>
        <label>Комментарий к времени<textarea maxLength={2000} value={comment} onChange={e => {setComment(e.target.value); manualKey.current = newRequestKey();}}/></label>
        <button disabled={!date || !minutes}>Записать время</button>
      </fieldset></form>
      {!page.items.length ? <p className="muted">Записей времени нет.</p> : <ul className="plainList">{page.items.map(row => <li key={row.id}>
        <span>{row.worked_on} · {row.author_name} · {row.is_running ? 'Таймер работает' : duration(row.seconds)} · {row.started_at ? 'Таймер' : 'Вручную'}{row.comment ? ` · ${row.comment}` : ''}
          {row.stop_reason === 'TASK_COMPLETED' ? ' · Остановлен завершением задачи' : row.stop_reason === 'MEMBERSHIP_REVOKED' ? ' · Остановлен отзывом доступа' : ''}</span>
        {row.can_edit && !row.is_running && <><button type="button" disabled={busy} aria-label={`Изменить время ${row.id}`} onClick={() => {
          setEditing(row); setEditMinutes(String(row.seconds / 60)); setEditDate(row.worked_on); setEditComment(row.comment || '');
        }}>Изменить</button><button type="button" disabled={busy} aria-label={`Удалить время ${row.id}`} onClick={() => {
          if (window.confirm('Удалить запись времени?')) void run(() => request(`${base}/time-entries/${row.id}`, 'DELETE'));
        }}>Удалить</button></>}
      </li>)}</ul>}
      {editing && <form aria-label="Изменение времени" onSubmit={e => {e.preventDefault(); void run(async () => {
        await request(`${base}/time-entries/${editing.id}`, 'PATCH', {comment: editComment || null,
          ...(!editing.started_at ? {minutes: Number(editMinutes), worked_on: editDate} : {})}); setEditing(null);
      });}}><fieldset disabled={busy}>
        {!editing.started_at && <><label>Исправленная дата<input type="date" required max={page.today} value={editDate} onChange={e => setEditDate(e.target.value)}/></label>
          <label>Исправленные минуты<input type="number" required min="1" max="525600" step="1" value={editMinutes} onChange={e => setEditMinutes(e.target.value)}/></label></>}
        <label>Исправленный комментарий<textarea maxLength={2000} value={editComment} onChange={e => setEditComment(e.target.value)}/></label>
        <button>Сохранить запись времени</button><button type="button" onClick={() => setEditing(null)}>Отменить правку времени</button>
      </fieldset></form>}
      <div className="inlineForm"><button type="button" disabled={busy || !offset} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущее время</button>
        <button type="button" disabled={busy || page.items.length < 50} onClick={() => setOffset(n => n + 50)}>Следующее время</button></div>
    </>}
    {error && <p role="alert">{error} <button type="button" disabled={busy} onClick={() => setRetry(n => n + 1)}>Повторить загрузку времени</button></p>}
  </section>;
}
