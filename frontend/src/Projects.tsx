import {useEffect, useRef, useState, type FormEvent} from 'react';
import {Plus, X} from 'lucide-react';
import {type Client, type Deal, type Member, type Project, type ProjectContact, type ProjectEvent, type ProjectMember, type ProjectStage, type Task,
  type TaskStatus, type Workspace, ApiError, errorText, localDateTime, money, projectStatusNames, request} from './api';
import type {ProjectTemplate} from './projectTemplateTypes';
import ProjectWorkPlan from './ProjectWorkPlan';

type Tab = 'active' | 'archive' | 'all';

const statusTabs: {key: Tab; label: string}[] = [{key: 'active', label: 'Активные'}, {key: 'archive', label: 'Архив'}, {key: 'all', label: 'Все'}];

function CreateProject({deals, clients, templates, duplicate, busy, error, onClose, onSave}: {
  deals: Deal[]; clients: Client[]; busy: boolean; error: string; onClose: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
  templates: ProjectTemplate[]; duplicate: boolean;
}) {
  const [dealId, setDealId] = useState('');
  const [title, setTitle] = useState('');
  const [clientId, setClientId] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [startDate, setStartDate] = useState(localDateTime(new Date().toISOString()).slice(0, 10));
  const [force, setForce] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload = dealId ? {deal_id: dealId} : {title: title.trim(), client_id: clientId};
    if (!dealId && (!title.trim() || !clientId)) return;
    void onSave({...payload, ...(templateId ? {template_id: templateId, start_date: startDate} : {}), ...(force ? {force: true} : {})});
  };
  return <div className="modalBackdrop" onClick={() => !busy && onClose()}>
    <form className="dealModal" role="dialog" aria-modal="true" aria-label="Новый проект" onSubmit={submit} onClick={e => e.stopPropagation()}>
      <div className="drawerHead"><h2>Новый проект</h2><button type="button" aria-label="Закрыть" disabled={busy} onClick={onClose}><X size={20}/></button></div>
      <fieldset disabled={busy}>
        <p className="muted">Проект создаётся из выигранной сделки или вручную: клиент, сумма и контакты переносятся автоматически.</p>
        <label>Сделка-источник<select value={dealId} onChange={e => {setDealId(e.target.value); setForce(false);}}><option value="">Без сделки (вручную)</option>{deals.map(deal => <option key={deal.id} value={deal.id}>{deal.title}</option>)}</select></label>
        {!dealId && <>
          <label>Название проекта<input required maxLength={255} value={title} onChange={e => setTitle(e.target.value)}/></label>
          <label>Клиент проекта<select required value={clientId} onChange={e => setClientId(e.target.value)}><option value="">Выберите клиента</option>{clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label>
        </>}
        <label>Шаблон проекта<select value={templateId} onChange={e => setTemplateId(e.target.value)}><option value="">Без шаблона</option>{templates.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        {templateId && <label>Начало проекта по шаблону<input required type="date" value={startDate} onChange={e => setStartDate(e.target.value)}/></label>}
        {duplicate && dealId && <label><input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)}/>Подтверждаю создание ещё одного проекта из этой сделки</label>}
        {error && <p role="alert" className="errorMessage">{error}</p>}
        <button disabled={busy || (!dealId && (!title.trim() || !clientId))}>{busy ? 'Сохранение…' : 'Создать проект'}</button>
      </fieldset>
    </form>
  </div>;
}

function ProjectDrawer({base, project, stages, members, clients, deals, statuses, busy, canManage, onClose, onChanged}: {
  base: string; project: Project; stages: ProjectStage[]; members: Member[]; clients: Client[]; deals: Deal[]; statuses: TaskStatus[];
  busy: boolean; onClose: () => void; onChanged: () => Promise<void>;
  canManage: boolean;
}) {
  const [tab, setTab] = useState<'info' | 'tasks' | 'team' | 'events' | 'plan' | 'gantt'>('info');
  const path = `${base}/projects/${project.id}`;
  const [draft, setDraft] = useState({stage_id: project.stage_id, manager_user_id: project.manager_user_id || '',
    start_date: project.start_date || '', end_date: project.end_date || ''});
  const [tasks, setTasks] = useState<Task[]>([]);
  const [team, setTeam] = useState<ProjectMember[]>([]);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [contacts, setContacts] = useState<ProjectContact[]>([]);
  const [memberId, setMemberId] = useState('');
  const [taskTitle, setTaskTitle] = useState('');
  const [note, setNote] = useState('');
  const [localError, setLocalError] = useState('');
  const [localBusy, setLocalBusy] = useState(false);
  const reload = async () => {
    const [nextTasks, nextTeam, nextEvents, nextContacts] = await Promise.all([
      request<Task[]>(`${base}/tasks?project_id=${project.id}`), request<ProjectMember[]>(`${path}/members`),
      request<ProjectEvent[]>(`${path}/events`), request<ProjectContact[]>(`${path}/contacts`)]);
    setTasks(nextTasks); setTeam(nextTeam); setEvents(nextEvents); setContacts(nextContacts);
  };
  useEffect(() => {void reload().catch(e => setLocalError(errorText(e)));}, [path]);
  const run = async (operation: () => Promise<unknown>) => {
    if (localBusy) return;
    setLocalBusy(true); setLocalError('');
    try {await operation();} catch(e) {setLocalError(errorText(e));}
    finally {setLocalBusy(false);}
  };
  const save = () => void run(async () => {
    await request(path, 'PATCH', {stage_id: draft.stage_id, manager_user_id: draft.manager_user_id || null,
      start_date: draft.start_date || null, end_date: draft.end_date || null});
    await onChanged(); await reload();
  });
  const setStatus = (status: Project['status']) => void run(async () => {
    await request(path, 'PATCH', {status});
    await onChanged(); await reload();
  });
  const addMember = () => {
    if (!memberId) return;
    void run(async () => {
      await request(`${path}/members`, 'POST', {user_id: memberId});
      setMemberId(''); await reload();
    });
  };
  const removeMember = (row: ProjectMember) => void run(async () => {
    await request(`${path}/members/${row.user_id}`, 'DELETE'); await reload();
  });
  const addTask = () => {
    if (!taskTitle.trim()) return;
    void run(async () => {
      const status = statuses.find(row => !row.is_final) || statuses[0];
      await request(`${base}/tasks`, 'POST', {title: taskTitle.trim(), project_id: project.id, status_id: status?.id});
      setTaskTitle(''); await reload(); await onChanged();
    });
  };
  const addNote = () => {
    if (!note.trim()) return;
    void run(async () => {
      await request(`${path}/events`, 'POST', {body: note.trim()}); setNote(''); await reload();
    });
  };
  const managerName = members.find(member => member.user_id === project.manager_user_id)?.first_name || 'Не назначен';
  return <div className="drawerBackdrop" onClick={() => !localBusy && onClose()}><aside className="drawer" role="dialog" aria-modal="true" aria-label="Карточка проекта" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><div><small>Проект · {projectStatusNames[project.status]}</small><h2>{project.title}</h2></div>
      <button type="button" aria-label="Закрыть" onClick={onClose}><X size={20}/></button></div>
    <div className="projectTabs" role="tablist">
      {([['info', 'Общие'], ['tasks', `Задачи ${project.tasks_done}/${project.tasks_total}`], ['plan', 'Порядок работ'], ['gantt', 'Гант'], ['team', `Команда ${project.members_count}`], ['events', 'События']] as const)
        .map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}
    </div>
    {tab === 'info' && <section className="drawerSection">
      <p><strong>{money(project.amount, project.currency)}</strong> · {clients.find(client => client.id === project.client_id)?.name || 'Клиент не найден'}</p>
      <p className="muted">Сделка: {deals.find(deal => deal.id === project.deal_id)?.title || 'Без сделки'} · Менеджер: {managerName}</p>
      {contacts.length > 0 && <p className="muted">Контакты: {contacts.map(contact => [contact.last_name, contact.first_name].filter(Boolean).join(' ')).join(', ')}</p>}
      <fieldset disabled={localBusy}>
        <label>Этап проекта<select value={draft.stage_id} onChange={e => setDraft({...draft, stage_id: e.target.value})}>{stages.map(stage => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label>
        <label>Менеджер проекта<select value={draft.manager_user_id} onChange={e => setDraft({...draft, manager_user_id: e.target.value})}><option value="">Не назначен</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}</select></label>
        <label>Начало<input type="date" value={draft.start_date} onChange={e => setDraft({...draft, start_date: e.target.value})}/></label>
        <label>Окончание<input type="date" value={draft.end_date} onChange={e => setDraft({...draft, end_date: e.target.value})}/></label>
        <button type="button" disabled={localBusy} onClick={save}>Сохранить проект</button>
        {project.status === 'ARCHIVED'
          ? <button type="button" disabled={localBusy} onClick={() => setStatus('ACTIVE')}>Вернуть из архива</button>
          : <button type="button" disabled={localBusy} onClick={() => setStatus('ARCHIVED')}>В архив</button>}
      </fieldset>
    </section>}
    {tab === 'tasks' && <section className="drawerSection">
      {tasks.length ? <ul className="plainList">{tasks.map(task => <li key={task.id}><span>{task.title}</span><span className="muted"> · {task.status_name}</span></li>)}</ul> : <p className="muted">Задач проекта пока нет.</p>}
      <div className="inlineForm"><input aria-label="Новая задача проекта" maxLength={255} value={taskTitle} onChange={e => setTaskTitle(e.target.value)}/>
        <button type="button" disabled={localBusy || !taskTitle.trim()} onClick={addTask}>Добавить задачу</button></div>
    </section>}
    {tab === 'team' && <section className="drawerSection">
      {team.length ? <ul className="plainList">{team.map(row => <li key={row.user_id}><span>{[row.first_name, row.last_name].filter(Boolean).join(' ')} · {row.email}{row.role === 'LEAD' ? ' · ведущий' : ''}</span>
        <button type="button" disabled={localBusy} aria-label={`Убрать из команды ${row.first_name}`} onClick={() => removeMember(row)}>Убрать</button></li>)}</ul> : <p className="muted">Команда не назначена.</p>}
      <div className="inlineForm"><select aria-label="Новый участник" value={memberId} onChange={e => setMemberId(e.target.value)}>
        <option value="">Выберите участника</option>{members.filter(member => !team.some(row => row.user_id === member.user_id)).map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}
      </select><button type="button" disabled={localBusy || !memberId} onClick={addMember}>Добавить участника</button></div>
    </section>}
    {tab === 'events' && <section className="drawerSection">
      {events.length ? <ol className="activityList">{events.map(event => <li key={event.id}><strong>{event.author_name}</strong> · <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString('ru-RU')}</time><p>{event.body}</p></li>)}</ol> : <p className="muted">Событий пока нет.</p>}
      <div className="inlineForm"><input aria-label="Новая запись" maxLength={10000} value={note} onChange={e => setNote(e.target.value)}/>
        <button type="button" disabled={localBusy || !note.trim()} onClick={addNote}>Добавить запись</button></div>
    </section>}
    {(tab === 'plan' || tab === 'gantt') && <ProjectWorkPlan base={base} projectId={project.id} view={tab} members={members}
      archived={project.status === 'ARCHIVED'} canDelete={canManage} onChanged={async () => {await reload(); await onChanged();}}/>}
    {localError && <p role="alert" className="errorMessage">{localError}</p>}
  </aside></div>;
}

export default function Projects({initialWorkspaceId = '', initialProjectId}: {initialWorkspaceId?: string; initialProjectId?: string} = {}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState(initialWorkspaceId);
  const targetOpened = useRef(false);
  const [stages, setStages] = useState<ProjectStage[]>([]);
  const [statuses, setStatuses] = useState<TaskStatus[]>([]);
  const [rows, setRows] = useState<Project[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [templates, setTemplates] = useState<ProjectTemplate[]>([]);
  const [templateNames, setTemplateNames] = useState<Record<string, string>>({});
  const [duplicate, setDuplicate] = useState(false);
  const [tab, setTab] = useState<Tab>('active');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const base = `/workspaces/${workspaceId}`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setRows([]); setSelectedId(null);
    const load = async () => {
      try {
        const spaces = await request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setWorkspaces(spaces);
        const id = spaces.some(space => space.id === workspaceId) ? workspaceId : spaces[0]?.id;
        if (!id) {setLoading(false); return;}
        if (id !== workspaceId) {setWorkspaceId(id); return;}
        const path = `/workspaces/${id}`;
        const [nextProjects, nextStages, nextStatuses, nextMembers, nextClients, nextDeals, nextTemplates] = await Promise.all([
          request<Project[]>(`${path}/projects?status=all`, 'GET', undefined, controller.signal),
          request<ProjectStage[]>(`${path}/project-stages`, 'GET', undefined, controller.signal),
          request<TaskStatus[]>(`${path}/task-statuses`, 'GET', undefined, controller.signal),
          request<Member[]>(`${path}/members`, 'GET', undefined, controller.signal),
          request<Client[]>(`${path}/clients`, 'GET', undefined, controller.signal),
          request<Deal[]>(`${path}/deals?limit=500`, 'GET', undefined, controller.signal),
          request<ProjectTemplate[]>(`${path}/project-templates`, 'GET', undefined, controller.signal)]);
        if (controller.signal.aborted) return;
        setRows(nextProjects); setStages(nextStages); setStatuses(nextStatuses); setMembers(nextMembers); setClients(nextClients); setDeals(nextDeals);
        if (initialProjectId && !targetOpened.current) {
          targetOpened.current = true;
          const target = nextProjects.find(row => row.id === initialProjectId);
          if (target) {setSelectedId(target.id); setTab(target.status === 'ARCHIVED' ? 'archive' : 'active');}
          else setError('Проект из поиска больше недоступен');
        }
        setTemplates(nextTemplates);
        setLoading(false);
      } catch(e) {if (!controller.signal.aborted) {setError(errorText(e)); setLoading(false);}}
    };
    void load();
    return () => controller.abort();
  }, [workspaceId, reload]);

  const refresh = async () => {
    const [projects, nextTemplates] = await Promise.all([request<Project[]>(`${base}/projects?status=all`), request<ProjectTemplate[]>(`${base}/project-templates`)]);
    setRows(projects); setTemplates(nextTemplates);
  };
  const create = async (payload: Record<string, unknown>) => {
    setFormError(''); setBusy(true);
    try {
      await request(`${base}/projects`, 'POST', payload);
      setCreating(false); await refresh();
    } catch(e) {setDuplicate(e instanceof ApiError && e.status === 409); setFormError(errorText(e));}
    finally {setBusy(false);}
  };
  const visible = rows.filter(row => tab === 'all' || (tab === 'active' ? row.status === 'ACTIVE' : row.status !== 'ACTIVE'));
  const selected = rows.find(row => row.id === selectedId);
  const canManage = ['OWNER', 'ADMIN'].includes(workspaces.find(row => row.id === workspaceId)?.role || '');
  const changeTemplate = async (row: ProjectTemplate, remove = false) => {
    if (busy) return;
    if (remove && !window.confirm(`Удалить шаблон «${row.name}»? Созданные проекты останутся.`)) return;
    setBusy(true); setError('');
    try {
      await request(`${base}/project-templates/${row.id}`, remove ? 'DELETE' : 'PATCH', remove ? undefined : {name: templateNames[row.id] ?? row.name});
      await refresh();
    } catch(e) {setError(errorText(e));} finally {setBusy(false);}
  };

  return <>
    <header><div><h1>Проекты</h1><p>Исполнение после продажи: этапы, команда и задачи</p></div>
      <button className="primary" disabled={loading} onClick={() => {setDuplicate(false); setFormError(''); setCreating(true);}}><Plus size={18}/>Новый проект</button></header>
    <div className="crmTools">
      <select aria-label="Рабочее пространство" disabled={loading || busy} value={workspaceId} onChange={e => setWorkspaceId(e.target.value)}>{workspaces.map(space => <option key={space.id} value={space.id}>{space.name}</option>)}</select>
      {statusTabs.map(item => <button key={item.key} type="button" className="filter" aria-pressed={tab === item.key} onClick={() => setTab(item.key)}>{item.label}</button>)}
      <span className="muted">{visible.length} проектов</span>
    </div>
    {error && <p role="alert" className="errorMessage">{error} <button type="button" onClick={() => setReload(n => n + 1)}>Повторить</button></p>}
    {loading ? <p role="status">Загрузка проектов…</p> : !visible.length ? <p className="muted">Проектов нет. Создайте проект из выигранной сделки или вручную.</p> :
      <div className="portalTableScroll"><table className="taskTable"><thead><tr><th>Проект</th><th>Клиент</th><th>Этап</th><th>Менеджер</th><th>Сроки</th><th>Задачи</th><th>Статус</th></tr></thead>
        <tbody>{visible.map(project => <tr key={project.id} onClick={() => setSelectedId(project.id)}>
          <td><button type="button" className="linkLike" onClick={() => setSelectedId(project.id)}>{project.title}</button></td>
          <td>{clients.find(client => client.id === project.client_id)?.name || '—'}</td>
          <td>{project.stage_name}</td>
          <td>{members.find(member => member.user_id === project.manager_user_id)?.first_name || '—'}</td>
          <td>{project.start_date || '—'} — {project.end_date || '—'}</td>
          <td>{project.tasks_done}/{project.tasks_total}</td>
          <td>{projectStatusNames[project.status]}</td></tr>)}</tbody></table></div>}
    {!loading && <details><summary>Шаблоны проектов ({templates.length})</summary>
      {!templates.length && <p className="muted">Сохраните план существующего проекта как шаблон во вкладке «Порядок работ».</p>}
      {templates.map(row => <div key={row.id} className="inlineForm"><span>{row.name} · {row.phases.length} этапов</span>
        {canManage && <><input aria-label={`Название шаблона ${row.name}`} maxLength={255} value={templateNames[row.id] ?? row.name} onChange={e => setTemplateNames({...templateNames, [row.id]: e.target.value})}/>
          <button disabled={busy || !(templateNames[row.id] ?? row.name).trim()} onClick={() => void changeTemplate(row)}>Сохранить шаблон {row.name}</button>
          <button disabled={busy} onClick={() => void changeTemplate(row, true)}>Удалить шаблон {row.name}</button></>}
      </div>)}
    </details>}
    {creating && <CreateProject deals={deals} clients={clients} templates={templates} duplicate={duplicate} busy={busy} error={formError} onClose={() => setCreating(false)} onSave={create}/>}
    {selected && <ProjectDrawer key={selected.id} base={base} project={selected} stages={stages} members={members} clients={clients}
      deals={deals} statuses={statuses} busy={busy} canManage={canManage} onClose={() => setSelectedId(null)} onChanged={refresh}/>}
  </>;
}
