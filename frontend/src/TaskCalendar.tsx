import {useState} from 'react';
import type {Member, Task} from './api';

export const dayKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
export function monthDays(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1, 12);
  first.setDate(first.getDate() - (first.getDay() + 6) % 7);
  return Array.from({length: 42}, (_, index) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + index, 12));
}
export function occursOn(task: Task, key: string): boolean {
  const start = task.start_at ? dayKey(new Date(task.start_at)) : null;
  const end = task.due_at ? dayKey(new Date(task.due_at)) : null;
  return Boolean(start && end ? start <= key && key <= end : (start || end) === key);
}

export default function TaskCalendar({tasks, members, onOpen, onCreate, initialMonth = new Date()}: {
  tasks: Task[]; members: Member[]; onOpen: (id: string) => void; onCreate: (day: string) => void; initialMonth?: Date;
}) {
  const [month, setMonth] = useState(() => new Date(initialMonth.getFullYear(), initialMonth.getMonth(), 1, 12));
  const [assignee, setAssignee] = useState('all');
  const [includeDone, setIncludeDone] = useState(true);
  const [expanded, setExpanded] = useState('');
  const days = monthDays(month);
  const visible = tasks.filter(task => (includeDone || !task.is_final) && (assignee === 'all' || (task.assignee_user_id || 'none') === assignee));
  const today = dayKey(new Date());
  const taskButton = (task: Task) => <button type="button" className={`calendarTask ${task.is_final ? 'completed' : ''}`} key={task.id}
    onClick={() => onOpen(task.id)} aria-label={`Открыть задачу ${task.title}`}>
    {task.parent_task_id ? '↳ ' : ''}{task.title}<small>{task.status_name}</small>
  </button>;
  return <section aria-label="Календарь задач">
    <div className="calendarTools">
      <button type="button" aria-label="Предыдущий месяц" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1, 12))}>←</button>
      <h2 aria-live="polite">{month.toLocaleDateString('ru-RU', {month: 'long', year: 'numeric'})}</h2>
      <button type="button" aria-label="Следующий месяц" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1, 12))}>→</button>
      <button type="button" onClick={() => {const now = new Date(); setMonth(new Date(now.getFullYear(), now.getMonth(), 1, 12));}}>Сегодня</button>
      <label>Исполнитель календаря<select value={assignee} onChange={e => setAssignee(e.target.value)}><option value="all">Все</option><option value="none">Без исполнителя</option>
        {members.map(row => <option key={row.user_id} value={row.user_id}>{row.first_name} · {row.email}</option>)}</select></label>
      <label><input type="checkbox" checked={includeDone} onChange={e => setIncludeDone(e.target.checked)}/>Показывать завершённые</label>
    </div>
    <p className="muted">Часовой пояс браузера: {Intl.DateTimeFormat().resolvedOptions().timeZone}. Нажмите задачу для изменения дат.</p>
    <div className="calendarScroll"><table className="taskCalendar"><thead><tr>{['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(day => <th scope="col" key={day}>{day}</th>)}</tr></thead>
      <tbody>{Array.from({length: 6}, (_, week) => <tr key={week}>{days.slice(week * 7, week * 7 + 7).map(date => {
        const key = dayKey(date), rows = visible.filter(task => occursOn(task, key));
        return <td key={key} className={date.getMonth() !== month.getMonth() ? 'outsideMonth' : ''}>
          <section aria-label={`День ${key}`}><div className="calendarDayHead"><time dateTime={key} aria-current={key === today ? 'date' : undefined}>{date.getDate()}</time>
            <button type="button" aria-label={`Создать задачу ${key}`} onClick={() => onCreate(key)}>+</button></div>
            {(expanded === key ? rows : rows.slice(0, 4)).map(taskButton)}
            {rows.length > 4 && <button type="button" className="calendarMore" onClick={() => setExpanded(expanded === key ? '' : key)}>{expanded === key ? 'Свернуть' : `Ещё ${rows.length - 4}`}</button>}
          </section></td>;
      })}</tr>)}</tbody></table></div>
    <section className="drawerSection" aria-label="Задачи без дат"><h3>Без дат</h3>
      {visible.filter(task => !task.start_at && !task.due_at).length ? visible.filter(task => !task.start_at && !task.due_at).map(taskButton) : <p className="muted">Задач без дат нет.</p>}
    </section>
  </section>;
}
