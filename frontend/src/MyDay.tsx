import {useEffect, useState} from 'react';
import {type DueTaskReminder, type MyDay as MyDayData, errorText, request} from './api';
import './MyDay.css';

const empty: MyDayData = {tasks: [], follow_ups: []};

export default function MyDay({base, onOpenDeal}: {base: string; onOpenDeal: (id: string) => void}) {
  const [data, setData] = useState<MyDayData>(empty);
  const [reminders, setReminders] = useState<DueTaskReminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setData(empty);
    Promise.all([request<MyDayData>(`${base}/my-day`, 'GET', undefined, controller.signal),
      request<DueTaskReminder[]>(`${base}/reminders/due`, 'GET', undefined, controller.signal)])
      .then(([rows, due]) => {if (!controller.signal.aborted) {setData(rows); setReminders(due); setLoading(false);}})
      .catch(e => {if (!controller.signal.aborted) {setError(errorText(e)); setLoading(false);}});
    return () => controller.abort();
  }, [base, reload]);
  useEffect(() => {
    const timer = window.setInterval(() => {setNow(Date.now()); setReload(n => n + 1);}, 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const complete = async (dealId: string, taskId: string) => {
    if (busyId) return;
    setBusyId(taskId); setError('');
    try {
      await request(`${base}/deals/${dealId}/tasks/${taskId}`, 'PATCH', {status: 'DONE'});
      setData(previous => ({...previous, tasks: previous.tasks.filter(item => item.task.id !== taskId)}));
    } catch(e) {setError(errorText(e));}
    finally {setBusyId('');}
  };
  const acknowledge = async (id: string) => {
    if (busyId) return;
    setBusyId(id); setError('');
    try {
      await request(`${base}/reminders/${id}/ack`, 'POST');
      setReminders(previous => previous.filter(item => item.id !== id));
    } catch(e) {setError(errorText(e));}
    finally {setBusyId('');}
  };
  const endToday = new Date(now); endToday.setHours(24, 0, 0, 0);
  const category = (iso: string | null) => !iso ? 'Без срока' : new Date(iso).getTime() < now ? 'Просрочено' : new Date(iso) < endToday ? 'Сегодня' : 'Позже';
  const dueToday = data.tasks.filter(item => category(item.task.due_at) === 'Сегодня').length + data.follow_ups.filter(item => category(item.at) === 'Сегодня').length;
  const overdue = data.tasks.filter(item => category(item.task.due_at) === 'Просрочено').length + data.follow_ups.filter(item => category(item.at) === 'Просрочено').length;
  return <section className="myDay card" aria-label="Мой день">
    <div className="myDayHead"><div><h2>Мой день</h2><p>Мои задачи по активным сделкам и следующие контакты</p></div><button type="button" disabled={loading} onClick={() => setReload(n => n + 1)}>Обновить</button></div>
    {loading ? <p role="status">Загрузка моих дел…</p> : <>
      <p className="myDayCount">Сегодня: {dueToday} · Просрочено: {overdue}</p>
      {!data.tasks.length && !data.follow_ups.length && !reminders.length && <p className="muted">Назначенных дел пока нет.</p>}
      {reminders.length > 0 && <div><h3>Напоминания</h3><ul className="myDayList">{reminders.map(item => <li key={item.id}>
        <span className="myDayOverdue">Сработало</span>
        <button type="button" onClick={() => onOpenDeal(item.deal_id)}>{item.task_title}</button>
        <small>{item.deal_title} · {item.trigger_at ? new Date(item.trigger_at).toLocaleString('ru-RU') : ''}</small>
        <button type="button" disabled={!!busyId} onClick={() => void acknowledge(item.id)}>{busyId === item.id ? 'Сохранение…' : 'Прочитано'}</button>
      </li>)}</ul></div>}
      <ul className="myDayList">{data.follow_ups.map(item => <li key={`follow-${item.deal_id}`}>
        <span className={category(item.at) === 'Просрочено' ? 'myDayOverdue' : ''}>{category(item.at)}</span>
        <button type="button" onClick={() => onOpenDeal(item.deal_id)}>{item.deal_title}</button>
        <small>Следующий контакт · {new Date(item.at).toLocaleString('ru-RU')}{item.comment ? ` · ${item.comment}` : ''}</small>
      </li>)}{data.tasks.map(item => <li key={item.task.id}>
        <span className={category(item.task.due_at) === 'Просрочено' ? 'myDayOverdue' : ''}>{category(item.task.due_at)}</span>
        <button type="button" onClick={() => onOpenDeal(item.task.deal_id)}>{item.task.title}</button>
        <small>{item.deal_title}{item.task.due_at ? ` · до ${new Date(item.task.due_at).toLocaleString('ru-RU')}` : ''}</small>
        <button type="button" disabled={!!busyId} onClick={() => void complete(item.task.deal_id, item.task.id)}>{busyId === item.task.id ? 'Сохранение…' : 'Выполнено'}</button>
      </li>)}</ul>
    </>}
    {error && <p role="alert" className="errorMessage">{error} <button type="button" onClick={() => setReload(n => n + 1)}>Повторить</button></p>}
  </section>;
}
