import {useEffect, useRef, useState, type FormEvent} from 'react';
import {Plus, X} from 'lucide-react';
import {type Deal, type Member, type Task, type TaskChecklistItem, type TaskPriority, type TaskStatus, type Workspace, type DealWatcher,
  errorText, loadDeals, loadTasks, localDateTime, request, taskPriorityNames} from './api';
import TaskCalendar from './TaskCalendar';
import TaskTime from './TaskTime';
import TaskRecurrence from './TaskRecurrence';

type Draft = {title: string; description: string; priority: TaskPriority; status_id: string; assignee_user_id: string;
  start_at: string; due_at: string; estimate_minutes: string; deal_id: string};
const emptyDraft: Draft = {title: '', description: '', priority: 'MEDIUM', status_id: '', assignee_user_id: '',
  start_at: '', due_at: '', estimate_minutes: '', deal_id: ''};

const payloadOf = (draft: Draft) => ({
  title: draft.title.trim(),
  description: draft.description || null,
  priority: draft.priority,
  ...(draft.status_id ? {status_id: draft.status_id} : {}),
  assignee_user_id: draft.assignee_user_id || null,
  start_at: draft.start_at ? new Date(draft.start_at).toISOString() : null,
  due_at: draft.due_at ? new Date(draft.due_at).toISOString() : null,
  estimate_minutes: draft.estimate_minutes ? Number(draft.estimate_minutes) : null,
  deal_id: draft.deal_id || null,
});

function TaskForm({statuses, members, deals, initialStatus, initialDue = '', busy, error, onClose, onSave}: {
  statuses: TaskStatus[]; members: Member[]; deals: Deal[]; initialStatus: string; busy: boolean; error: string;
  onClose: () => void; onSave: (draft: Draft) => Promise<void>;
  initialDue?: string;
}) {
  const [draft, setDraft] = useState<Draft>({...emptyDraft, status_id: initialStatus, due_at: initialDue});
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft.title.trim()) return;
    void onSave(draft);
  };
  return <div className="modalBackdrop" onClick={() => !busy && onClose()}>
    <form className="dealModal" role="dialog" aria-modal="true" aria-label="Новая задача" onSubmit={submit} onClick={e => e.stopPropagation()}>
      <div className="drawerHead"><h2>Новая задача</h2><button type="button" aria-label="Закрыть" disabled={busy} onClick={onClose}><X size={20}/></button></div>
      <fieldset disabled={busy}>
        <label>Название задачи<input required maxLength={255} value={draft.title} onChange={e => setDraft({...draft, title: e.target.value})}/></label>
        <label>Описание задачи<textarea maxLength={10000} value={draft.description} onChange={e => setDraft({...draft, description: e.target.value})}/></label>
        <label>Статус задачи<select value={draft.status_id} onChange={e => setDraft({...draft, status_id: e.target.value})}>{statuses.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>Приоритет задачи<select value={draft.priority} onChange={e => setDraft({...draft, priority: e.target.value as TaskPriority})}>{(Object.keys(taskPriorityNames) as TaskPriority[]).map(value => <option key={value} value={value}>{taskPriorityNames[value]}</option>)}</select></label>
        <label>Исполнитель задачи<select value={draft.assignee_user_id} onChange={e => setDraft({...draft, assignee_user_id: e.target.value})}><option value="">Не назначен</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}</select></label>
        <label>Сделка<select value={draft.deal_id} onChange={e => setDraft({...draft, deal_id: e.target.value})}><option value="">Без сделки</option>{deals.map(deal => <option key={deal.id} value={deal.id}>{deal.title}</option>)}</select></label>
        <label>Начало задачи<input type="datetime-local" value={draft.start_at} onChange={e => setDraft({...draft, start_at: e.target.value})}/></label>
        <label>Крайний срок<input type="datetime-local" value={draft.due_at} onChange={e => setDraft({...draft, due_at: e.target.value})}/></label>
        <label>Оценка, минут<input type="number" min="0" max="525600" value={draft.estimate_minutes} onChange={e => setDraft({...draft, estimate_minutes: e.target.value})}/></label>
        {error && <p role="alert" className="errorMessage">{error}</p>}
        <button disabled={busy || !draft.title.trim()}>{busy ? 'Сохранение…' : 'Создать задачу'}</button>
      </fieldset>
    </form>
  </div>;
}

function StatusSettings({base, statuses, busy, error, onClose, onReload}: {
  base: string; statuses: TaskStatus[]; busy: boolean; error: string; onClose: () => void; onReload: () => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [names, setNames] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState('');
  const run = async (operation: () => Promise<unknown>) => {
    setLocalError('');
    try {await operation(); await onReload();} catch(e) {setLocalError(errorText(e));}
  };
  const shift = (index: number, delta: number) => {
    const ids = statuses.map(row => row.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    void run(() => request(`${base}/task-statuses/order`, 'PUT', {ids}));
  };
  return <div className="modalBackdrop" onClick={() => !busy && onClose()}><section className="dealModal" role="dialog" aria-modal="true" aria-label="Статусы задач" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><h2>Статусы задач</h2><button type="button" aria-label="Закрыть" onClick={onClose}><X size={20}/></button></div>
    <p className="muted">Статус с задачами удалить нельзя. В рабочем процессе должен остаться завершающий статус.</p>
    {(localError || error) && <p role="alert" className="errorMessage">{localError || error}</p>}
    <ol className="statusList">{statuses.map((row, index) => <li key={row.id}>
      <input aria-label={`Название статуса ${row.name}`} maxLength={50} value={names[row.id] ?? row.name} onChange={e => setNames({...names, [row.id]: e.target.value})}/>
      <label className="statusFinal"><input type="checkbox" checked={row.is_final} aria-label={`Завершающий статус ${row.name}`}
        onChange={e => void run(() => request(`${base}/task-statuses/${row.id}`, 'PATCH', {is_final: e.target.checked}))}/>Завершающий</label>
      <button type="button" disabled={busy || index === 0} aria-label={`Выше ${row.name}`} onClick={() => shift(index, -1)}>↑</button>
      <button type="button" disabled={busy || index === statuses.length - 1} aria-label={`Ниже ${row.name}`} onClick={() => shift(index, 1)}>↓</button>
      <button type="button" disabled={busy || !(names[row.id] ?? row.name).trim() || (names[row.id] ?? row.name) === row.name}
        onClick={() => void run(() => request(`${base}/task-statuses/${row.id}`, 'PATCH', {name: (names[row.id] ?? row.name).trim()}))}>Сохранить {row.name}</button>
      <button type="button" disabled={busy} onClick={() => void run(() => request(`${base}/task-statuses/${row.id}`, 'DELETE'))}>Удалить {row.name}</button>
    </li>)}</ol>
    <form onSubmit={e => {e.preventDefault(); if (!name.trim()) return; void run(async () => {await request(`${base}/task-statuses`, 'POST', {name: name.trim()}); setName('');});}}>
      <label>Новый статус<input maxLength={50} value={name} onChange={e => setName(e.target.value)}/></label>
      <button disabled={busy || !name.trim()}>Добавить статус</button>
    </form>
  </section></div>;
}

function TaskDrawer({base, task, statuses, members, deals, busy, error, reload, onClose, onChanged, onDeleted, onOpenTask}: {
  base: string; task: Task; statuses: TaskStatus[]; members: Member[]; deals: Deal[]; busy: boolean; error: string; reload: () => Promise<void>;
  onClose: () => void; onChanged: (task: Task) => void; onDeleted: () => void;
  onOpenTask: (id: string) => void;
}) {
  const path = `${base}/tasks/${task.id}`;
  const [draft, setDraft] = useState({description: task.description || '', status_id: task.status_id, priority: task.priority,
    assignee_user_id: task.assignee_user_id || '', start_at: localDateTime(task.start_at), due_at: localDateTime(task.due_at),
    estimate_minutes: task.estimate_minutes ? String(task.estimate_minutes) : '', deal_id: task.deal_id || ''});
  const [items, setItems] = useState<TaskChecklistItem[]>([]);
  const [itemText, setItemText] = useState('');
  const [children, setChildren] = useState<Task[]>([]);
  const [childTitle, setChildTitle] = useState('');
  const [watchers, setWatchers] = useState<DealWatcher[]>([]);
  const [watcherId, setWatcherId] = useState('');
  const [localError, setLocalError] = useState('');
  const [localBusy, setLocalBusy] = useState(false);
  const load = async () => {
    const [nextItems, nextWatchers] = await Promise.all([
      request<TaskChecklistItem[]>(`${path}/checklist`), request<DealWatcher[]>(`${path}/watchers`)]);
    setItems(nextItems); setWatchers(nextWatchers);
    setChildren(await request<Task[]>(`${base}/tasks?parent_task_id=${task.id}`));
  };
  useEffect(() => {void load().catch(e => setLocalError(errorText(e)));}, [path]);
  const run = async (operation: () => Promise<unknown>) => {
    if (localBusy) return;
    setLocalBusy(true); setLocalError('');
    try {await operation();} catch(e) {setLocalError(errorText(e));}
    finally {setLocalBusy(false);}
  };
  const save = () => void run(async () => {
    const updated = await request<Task>(path, 'PATCH', {description: draft.description || null, status_id: draft.status_id,
      priority: draft.priority, assignee_user_id: draft.assignee_user_id || null, deal_id: draft.deal_id || null,
      start_at: draft.start_at ? new Date(draft.start_at).toISOString() : null,
      due_at: draft.due_at ? new Date(draft.due_at).toISOString() : null,
      estimate_minutes: draft.estimate_minutes ? Number(draft.estimate_minutes) : null});
    onChanged(updated); await load(); await reload();
  });
  const addItem = () => {
    if (!itemText.trim()) return;
    void run(async () => {
      const row = await request<TaskChecklistItem>(`${path}/checklist`, 'POST', {text: itemText.trim()});
      setItems(previous => [...previous, row]); setItemText(''); await reload();
    });
  };
  const toggleItem = (row: TaskChecklistItem) => void run(async () => {
    const updated = await request<TaskChecklistItem>(`${path}/checklist/${row.id}`, 'PATCH', {is_done: !row.is_done});
    setItems(previous => previous.map(item => item.id === updated.id ? updated : item)); await reload();
  });
  const removeItem = (row: TaskChecklistItem) => void run(async () => {
    await request(`${path}/checklist/${row.id}`, 'DELETE');
    setItems(previous => previous.filter(item => item.id !== row.id)); await reload();
  });
  const addChild = () => {
    if (!childTitle.trim()) return;
    void run(async () => {
      const row = await request<Task>(`${base}/tasks`, 'POST', {title: childTitle.trim(), parent_task_id: task.id});
      setChildren(previous => [...previous, row]); setChildTitle(''); await reload();
    });
  };
  const addWatcher = () => {
    if (!watcherId) return;
    void run(async () => {
      const row = await request<DealWatcher>(`${path}/watchers`, 'POST', {user_id: watcherId});
      setWatchers(previous => [...previous, row]); setWatcherId('');
    });
  };
  const removeWatcher = (row: DealWatcher) => void run(async () => {
    await request(`${path}/watchers/${row.user_id}`, 'DELETE');
    setWatchers(previous => previous.filter(item => item.user_id !== row.user_id));
  });
  const removeTask = () => {
    if (!window.confirm(`Удалить задачу «${task.title}»?`)) return;
    void run(async () => {await request(path, 'DELETE'); onDeleted();});
  };
  const progress = task.checklist_total ? Math.round(task.checklist_done * 100 / task.checklist_total) : 0;
  return <div className="drawerBackdrop" onClick={() => !localBusy && onClose()}><aside className="drawer" role="dialog" aria-modal="true" aria-label="Карточка задачи" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><div><small>Задача</small><h2>{task.title}</h2></div><button type="button" aria-label="Закрыть" onClick={onClose}><X size={20}/></button></div>
    <p className="muted">{task.status_name} · {taskPriorityNames[task.priority]}{task.estimate_minutes ? ` · ${task.estimate_minutes} мин` : ''}{task.checklist_total ? ` · чек-лист ${task.checklist_done}/${task.checklist_total} (${progress}%)` : ''}</p>
    <section className="drawerSection"><h3>Поля задачи</h3><fieldset disabled={localBusy}>
      <label>Описание<textarea maxLength={10000} value={draft.description} onChange={e => setDraft({...draft, description: e.target.value})}/></label>
      <label>Статус<select aria-label="Статус" value={draft.status_id} onChange={e => setDraft({...draft, status_id: e.target.value})}>{statuses.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      <label>Приоритет<select value={draft.priority} onChange={e => setDraft({...draft, priority: e.target.value as TaskPriority})}>{(Object.keys(taskPriorityNames) as TaskPriority[]).map(value => <option key={value} value={value}>{taskPriorityNames[value]}</option>)}</select></label>
      <label>Исполнитель<select value={draft.assignee_user_id} onChange={e => setDraft({...draft, assignee_user_id: e.target.value})}><option value="">Не назначен</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}</select></label>
      <label>Сделка<select value={draft.deal_id} onChange={e => setDraft({...draft, deal_id: e.target.value})}><option value="">Без сделки</option>{deals.map(deal => <option key={deal.id} value={deal.id}>{deal.title}</option>)}</select></label>
      <label>Начало<input type="datetime-local" value={draft.start_at} onChange={e => setDraft({...draft, start_at: e.target.value})}/></label>
      <label>Крайний срок<input type="datetime-local" value={draft.due_at} onChange={e => setDraft({...draft, due_at: e.target.value})}/></label>
      <label>Оценка, минут<input type="number" min="0" max="525600" value={draft.estimate_minutes} onChange={e => setDraft({...draft, estimate_minutes: e.target.value})}/></label>
      <button type="button" disabled={localBusy} onClick={save}>{localBusy ? 'Сохранение…' : 'Сохранить задачу'}</button>
      <button type="button" disabled={localBusy} onClick={removeTask}>Удалить задачу</button>
    </fieldset></section>
    <TaskTime base={base} taskId={task.id} isFinal={task.is_final}/>
    <TaskRecurrence base={base} taskId={task.id} isFinal={task.is_final} isChild={!!task.parent_task_id} onOpenTask={onOpenTask}/>
    <section className="drawerSection"><h3>Чек-лист</h3>
      {items.length ? <ul className="plainList">{items.map(row => <li key={row.id}>
        <label><input type="checkbox" checked={row.is_done} disabled={localBusy} onChange={() => toggleItem(row)}/> {row.text}</label>
        <button type="button" disabled={localBusy} aria-label={`Удалить пункт ${row.text}`} onClick={() => removeItem(row)}>Убрать</button>
      </li>)}</ul> : <p className="muted">Пунктов пока нет.</p>}
      <div className="inlineForm"><input aria-label="Новый пункт чек-листа" maxLength={500} value={itemText} onChange={e => setItemText(e.target.value)}/>
        <button type="button" disabled={localBusy || !itemText.trim()} onClick={addItem}>Добавить пункт</button></div>
    </section>
    <section className="drawerSection"><h3>Подзадачи</h3>
      {children.length ? <ul className="plainList">{children.map(row => <li key={row.id}><span>{row.title}</span><span className="muted"> · {row.status_name}</span></li>)}</ul> : <p className="muted">Подзадач нет.</p>}
      <div className="inlineForm"><input aria-label="Новая подзадача" maxLength={255} value={childTitle} onChange={e => setChildTitle(e.target.value)}/>
        <button type="button" disabled={localBusy || !childTitle.trim()} onClick={addChild}>Добавить подзадачу</button></div>
    </section>
    <section className="drawerSection"><h3>Наблюдатели</h3>
      {watchers.length ? <ul className="plainList">{watchers.map(row => <li key={row.user_id}>
        <span>{[row.first_name, row.last_name].filter(Boolean).join(' ')} · {row.email}</span>
        <button type="button" disabled={localBusy} aria-label={`Убрать наблюдателя ${row.first_name}`} onClick={() => removeWatcher(row)}>Убрать</button>
      </li>)}</ul> : <p className="muted">Наблюдателей нет.</p>}
      <div className="inlineForm"><select aria-label="Новый наблюдатель задачи" value={watcherId} onChange={e => setWatcherId(e.target.value)}>
        <option value="">Выберите участника</option>{members.filter(member => !watchers.some(row => row.user_id === member.user_id)).map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}
      </select><button type="button" disabled={localBusy || !watcherId} onClick={addWatcher}>Добавить наблюдателя</button></div>
    </section>
    {(localError || error) && <p role="alert" className="errorMessage">{localError || error}</p>}
  </aside></div>;
}

export default function Tasks({initialWorkspaceId = '', initialTaskId}: {initialWorkspaceId?: string; initialTaskId?: string} = {}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState(initialWorkspaceId);
  const targetOpened = useRef(false);
  const [statuses, setStatuses] = useState<TaskStatus[]>([]);
  const [rows, setRows] = useState<Task[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [view, setView] = useState<'board' | 'list' | 'calendar'>('board');
  const [initialDue, setInitialDue] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);
  const [settings, setSettings] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const base = `/workspaces/${workspaceId}`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setRows([]); setStatuses([]); setSelectedId(null);
    const load = async () => {
      try {
        const spaces = await request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setWorkspaces(spaces);
        const id = spaces.some(space => space.id === workspaceId) ? workspaceId : spaces[0]?.id;
        if (!id) {setLoading(false); return;}
        if (id !== workspaceId) {setWorkspaceId(id); return;}
        const path = `/workspaces/${id}`;
        const [nextStatuses, nextTasks, nextMembers, nextDeals] = await Promise.all([
          request<TaskStatus[]>(`${path}/task-statuses`, 'GET', undefined, controller.signal),
          loadTasks(path, controller.signal),
          request<Member[]>(`${path}/members`, 'GET', undefined, controller.signal),
          loadDeals(path, controller.signal)]);
        if (controller.signal.aborted) return;
        setStatuses(nextStatuses); setRows(nextTasks); setMembers(nextMembers); setDeals(nextDeals); setLoading(false);
        if (initialTaskId && !targetOpened.current) {
          targetOpened.current = true;
          if (nextTasks.some(row => row.id === initialTaskId)) setSelectedId(initialTaskId);
          else setError('Задача из поиска больше недоступна');
        }
      } catch(e) {if (!controller.signal.aborted) {setError(errorText(e)); setLoading(false);}}
    };
    void load();
    return () => controller.abort();
  }, [workspaceId, reload]);

  const refresh = async () => setRows(await loadTasks(base));
  const refreshStatuses = async () => setStatuses(await request<TaskStatus[]>(`${base}/task-statuses`));
  const create = async (draft: Draft) => {
    setFormError(''); setBusy(true);
    try {
      const row = await request<Task>(`${base}/tasks`, 'POST', payloadOf(draft));
      setRows(previous => [...previous, row]); setCreating(false);
    } catch(e) {setFormError(errorText(e));}
    finally {setBusy(false);}
  };
  const move = async (task: Task, statusId: string) => {
    if (busy || task.status_id === statusId) return;
    setBusy(true); setError('');
    try {
      const updated = await request<Task>(`${base}/tasks/${task.id}`, 'PATCH', {status_id: statusId});
      setRows(previous => previous.map(item => item.id === updated.id ? updated : item));
    } catch(e) {setError(errorText(e));}
    finally {setBusy(false);}
  };
  const role = workspaces.find(space => space.id === workspaceId)?.role || '';
  const canManage = ['OWNER', 'ADMIN'].includes(role);
  const selected = rows.find(row => row.id === selectedId);
  const initialStatus = statuses.find(row => !row.is_final)?.id || statuses[0]?.id || '';
  const ordered = [...statuses].sort((a, b) => a.position - b.position);

  return <>
    <header><div><h1>Задачи</h1><p>Рабочий процесс, чек-листы и подзадачи студии</p></div>
      <div className="headerActions"><button className="filter" aria-pressed={view === 'board'} onClick={() => setView('board')}>Канбан</button>
         <button className="filter" aria-pressed={view === 'list'} onClick={() => setView('list')}>Список</button>
         <button className="filter" aria-pressed={view === 'calendar'} onClick={() => setView('calendar')}>Календарь</button>
        {canManage && <button className="filter" onClick={() => setSettings(true)}>Статусы</button>}
         <button className="primary" disabled={loading || !initialStatus} onClick={() => {setInitialDue(''); setFormError(''); setCreating(true);}}><Plus size={18}/>Новая задача</button></div></header>
    <div className="crmTools">
      <select aria-label="Рабочее пространство" disabled={loading || busy} value={workspaceId} onChange={e => setWorkspaceId(e.target.value)}>{workspaces.map(space => <option key={space.id} value={space.id}>{space.name}</option>)}</select>
      <span className="muted">{rows.length} задач · {rows.filter(row => !row.is_final).length} активных</span>
    </div>
    {error && <p role="alert" className="errorMessage">{error} <button type="button" onClick={() => setReload(n => n + 1)}>Повторить</button></p>}
    {loading ? <p role="status">Загрузка задач…</p> : !ordered.length ? <p>Статусы задач не найдены.</p> : view === 'calendar' ?
      <TaskCalendar tasks={rows} members={members} onOpen={setSelectedId} onCreate={day => {setInitialDue(`${day}T18:00`); setFormError(''); setCreating(true);}}/> : view === 'board' ?
      <div className="kanban" style={{gridTemplateColumns: `repeat(${ordered.length}, minmax(220px, 1fr))`}}>
        {ordered.map(status => {const list = rows.filter(row => row.status_id === status.id && (!row.parent_task_id)); return <section className="kanbanCol" key={status.id}
          onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); void move(rows.find(row => row.id === e.dataTransfer.getData('taskId'))!, status.id);}}>
          <div className="colHead"><div><span className="dot"/><b>{status.name}</b><em>{list.length}</em></div></div>
          <div className="dealList">{list.map(task => <article className="deal card" key={task.id} tabIndex={0} draggable={!busy} aria-label={`Открыть ${task.title}`}
            onDragStart={e => e.dataTransfer.setData('taskId', task.id)} onClick={() => setSelectedId(task.id)} onKeyDown={e => {if (e.key === 'Enter') setSelectedId(task.id);}}>
            <div className="dealTop"><small>{taskPriorityNames[task.priority]}</small></div><h3>{task.title}</h3>
            <p>{members.find(member => member.user_id === task.assignee_user_id)?.first_name || 'Без исполнителя'}{task.due_at ? ` · до ${new Date(task.due_at).toLocaleDateString('ru-RU')}` : ''}</p>
            <p className="muted">{deals.find(deal => deal.id === task.deal_id)?.title || 'Без сделки'}{task.checklist_total ? ` · чек-лист ${task.checklist_done}/${task.checklist_total}` : ''}{task.estimate_minutes ? ` · ${task.estimate_minutes} мин` : ''}</p>
          </article>)}</div>
        </section>;})}
      </div> :
      <div className="portalTableScroll"><table className="taskTable"><thead><tr><th>Задача</th><th>Статус</th><th>Приоритет</th><th>Исполнитель</th><th>Срок</th><th>Сделка</th></tr></thead>
        <tbody>{rows.filter(row => !row.parent_task_id).map(task => <tr key={task.id} tabIndex={0} onClick={() => setSelectedId(task.id)}>
          <td><button type="button" className="linkLike" onClick={() => setSelectedId(task.id)}>{task.title}</button></td>
          <td>{task.status_name}</td><td>{taskPriorityNames[task.priority]}</td>
          <td>{members.find(member => member.user_id === task.assignee_user_id)?.first_name || '—'}</td>
          <td>{task.due_at ? new Date(task.due_at).toLocaleString('ru-RU') : '—'}</td>
          <td>{deals.find(deal => deal.id === task.deal_id)?.title || '—'}</td></tr>)}</tbody></table></div>}
    {creating && <TaskForm statuses={ordered} members={members} deals={deals} initialStatus={initialStatus} initialDue={initialDue} busy={busy} error={formError}
      onClose={() => setCreating(false)} onSave={create}/>}
    {settings && <StatusSettings base={base} statuses={ordered} busy={busy} error={error} onClose={() => setSettings(false)} onReload={refreshStatuses}/>}
    {selected && <TaskDrawer key={selected.id} base={base} task={selected} statuses={ordered} members={members} deals={deals} busy={busy} error={error}
      onOpenTask={setSelectedId}
      reload={refresh} onClose={() => setSelectedId(null)}
      onChanged={updated => setRows(previous => previous.map(item => item.id === updated.id ? updated : item))}
      onDeleted={() => {setRows(previous => previous.filter(item => item.id !== selected.id)); setSelectedId(null);}}/>}
  </>;
}
