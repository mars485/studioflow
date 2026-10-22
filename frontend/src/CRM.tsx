import {useEffect, useRef, useState, type FormEvent} from 'react';
import {CalendarClock, Plus, Search, X} from 'lucide-react';
import {type Action, type Client, type Contact, type Deal, type DealActivity, type DealInput, type FollowUpCompletion, type Member, type Pipeline, type Stage, type Workspace,
  contactName, errorText, loadDeals, localDateTime, money, request} from './api';
import ClientDirectory from './ClientDirectory';
import ContactDirectory from './ContactDirectory';

const actions: Record<Action, string> = {call: 'Позвонить', message: 'Написать в WhatsApp', proposal: 'Отправить КП', decision: 'Уточнить решение'};

function StageEditor({stage, index, count, busy, base, pipelineId, run, onShift}: {
  stage: Stage; index: number; count: number; busy: boolean; base: string; pipelineId: string;
  run: (operation: () => Promise<unknown>) => Promise<void>; onShift: (index: number, delta: number) => void;
}) {
  const [name, setName] = useState(stage.name);
  const [color, setColor] = useState(stage.color || '#6366f1');
  const [type, setType] = useState<Stage['stage_type']>(stage.stage_type);
  const path = `${base}/pipelines/${pipelineId}/stages`;
  return <li className="stageSettingsRow"><label>Название этапа<input value={name} maxLength={100} onChange={e => setName(e.target.value)}/></label>
    <label>Цвет<input type="color" value={color} onChange={e => setColor(e.target.value)}/></label>
    <label>Тип<select value={type} onChange={e => setType(e.target.value as Stage['stage_type'])}><option value="OPEN">Рабочий</option><option value="WON">Выиграна</option><option value="LOST">Проиграна</option></select></label>
    <div className="stageSettingsActions">
      <button type="button" disabled={busy || index === 0} aria-label={`Выше ${stage.name}`} onClick={() => onShift(index, -1)}>↑</button>
      <button type="button" disabled={busy || index === count - 1} aria-label={`Ниже ${stage.name}`} onClick={() => onShift(index, 1)}>↓</button>
      <button type="button" disabled={busy || !name.trim()} onClick={() => void run(() => request(`${path}/${stage.id}`, 'PATCH', {name: name.trim(), color, stage_type: type}))}>Сохранить {stage.name}</button>
      <button type="button" disabled={busy || count <= 2} onClick={() => void run(() => request(`${path}/${stage.id}`, 'DELETE'))}>Удалить {stage.name}</button>
    </div>
  </li>;
}

function StageSettings({pipeline, base, onClose, onChanged}: {pipeline: Pipeline; base: string; onClose: () => void; onChanged: () => Promise<void>}) {
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const path = `${base}/pipelines/${pipeline.id}/stages`;
  const stages = [...pipeline.stages].sort((a, b) => a.position - b.position);
  const run = async (operation: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true); setError('');
    try {await operation(); await onChanged();} catch(e) {setError(errorText(e));}
    finally {setBusy(false);}
  };
  const shift = (index: number, delta: number) => {
    const ids = stages.map(stage => stage.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    void run(() => request(`${path}/order`, 'PUT', {ids}));
  };
  return <div className="modalBackdrop" onClick={() => !busy && onClose()}><section className="stageSettings dealModal" role="dialog" aria-modal="true" aria-label="Настройка стадий" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><div><small>{pipeline.name}</small><h2>Настройка стадий</h2></div><button type="button" disabled={busy} aria-label="Закрыть" onClick={onClose}><X size={20}/></button></div>
    <p className="muted">Этап со сделками удалить нельзя. В воронке должны остаться минимум два этапа.</p>
    {error && <p role="alert" className="errorMessage">{error}</p>}
    <ol className="stageSettingsList">{stages.map((stage, index) => <StageEditor key={stage.id} stage={stage} index={index} count={stages.length} busy={busy} base={base} pipelineId={pipeline.id} run={run} onShift={shift}/>)}</ol>
    <form onSubmit={e => {e.preventDefault(); void run(async () => {await request(`${path}`, 'POST', {name: newName.trim()}); setNewName('');});}}><label>Новый этап<input value={newName} maxLength={100} onChange={e => setNewName(e.target.value)}/></label><button disabled={busy || !newName.trim()}>Добавить этап</button></form>
  </section></div>;
}

function PipelineSettingsRow({pipeline, base, busy, run}: {pipeline: Pipeline; base: string; busy: boolean;
  run: (operation: () => Promise<unknown>, selectId?: string) => Promise<void>}) {
  const [name, setName] = useState(pipeline.name);
  const path = `${base}/pipelines/${pipeline.id}`;
  return <li className="pipelineSettingsRow"><label>Название воронки<input value={name} maxLength={255} onChange={e => setName(e.target.value)}/></label>
    <span>{pipeline.is_active ? (pipeline.is_default ? 'Основная' : 'Активна') : 'Отключена'} · {pipeline.stages.length} этапа</span>
    <div className="stageSettingsActions">
      <button type="button" disabled={busy || !name.trim()} onClick={() => void run(() => request(path, 'PATCH', {name: name.trim()}))}>Сохранить {pipeline.name}</button>
      {pipeline.is_active && !pipeline.is_default && <button type="button" disabled={busy} onClick={() => void run(() => request(`${path}/default`, 'POST'))}>Сделать основной</button>}
      <button type="button" disabled={busy} onClick={() => void run(() => request(`${path}/${pipeline.is_active ? 'deactivate' : 'activate'}`, 'POST'))}>{pipeline.is_active ? 'Отключить' : 'Включить'} {pipeline.name}</button>
      <button type="button" disabled={busy} onClick={() => void run(() => request(path, 'DELETE'))}>Удалить {pipeline.name}</button>
    </div>
  </li>;
}

function PipelineSettings({base, onClose, onChanged}: {base: string; onClose: () => void; onChanged: (selectId?: string) => Promise<void>}) {
  const [rows, setRows] = useState<Pipeline[]>([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = async () => setRows(await request<Pipeline[]>(`${base}/pipelines?include_inactive=true`));
  useEffect(() => {
    let active = true;
    request<Pipeline[]>(`${base}/pipelines?include_inactive=true`).then(next => {if (active) setRows(next);})
      .catch(e => {if (active) setError(errorText(e));}).finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [base]);
  const run = async (operation: () => Promise<unknown>, selectId?: string) => {
    if (busy) return;
    setBusy(true); setError('');
    try {await operation(); await load(); await onChanged(selectId);} catch(e) {setError(errorText(e));}
    finally {setBusy(false);}
  };
  const create = async () => {
    if (!name.trim()) return;
    let created: Pipeline | undefined;
    await run(async () => {created = await request<Pipeline>(`${base}/pipelines`, 'POST', {name: name.trim()});}, undefined);
    if (created) {setName(''); await onChanged(created.id);}
  };
  return <div className="modalBackdrop" onClick={() => !busy && onClose()}><section className="pipelineSettings dealModal" role="dialog" aria-modal="true" aria-label="Управление воронками" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><h2>Воронки продаж</h2><button type="button" disabled={busy} aria-label="Закрыть" onClick={onClose}><X size={20}/></button></div>
    <p className="muted">Воронка со сделками сохраняется при отключении. Удалить её нельзя.</p>
    {error && <p role="alert" className="errorMessage">{error} <button type="button" onClick={() => {setLoading(true); setError(''); void load().catch(e => setError(errorText(e))).finally(() => setLoading(false));}}>Повторить</button></p>}
    {loading ? <p role="status">Загрузка воронок…</p> : <ol className="stageSettingsList">{rows.map(row => <PipelineSettingsRow key={row.id} pipeline={row} base={base} busy={busy} run={run}/>)}</ol>}
    <form onSubmit={e => {e.preventDefault(); void create();}}><label>Новая воронка<input value={name} maxLength={255} onChange={e => setName(e.target.value)}/></label><button disabled={busy || !name.trim()}>Создать воронку</button></form>
  </section></div>;
}

function DealForm({deal, clients, contacts, members, pipelines, initialPipeline, busy, error, onClose, onSave}: {
  deal?: Deal; clients: Client[]; contacts: Contact[]; members: Member[]; pipelines: Pipeline[]; initialPipeline: string;
  busy: boolean; error: string; onClose: () => void;
  onSave: (data: DealInput, newClient: string) => Promise<void>;
}) {
  const [pipelineId, setPipelineId] = useState(deal?.pipeline_id || initialPipeline);
  const [clientId, setClientId] = useState(deal?.client_id || '');
  const [contactId, setContactId] = useState(deal?.contact_id || '');
  const [stageId, setStageId] = useState(deal?.stage_id || pipelines.find(p => p.id === pipelineId)?.stages[0]?.id || '');
  const pipeline = pipelines.find(p => p.id === pipelineId);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void onSave({title: String(form.get('title')).trim(), client_id: clientId, contact_id: contactId || null, pipeline_id: pipelineId,
      stage_id: stageId, amount: String(form.get('amount') || '0'),
      responsible_user_id: String(form.get('responsible') || '') || null,
      contact_name: contactId ? null : String(form.get('contact') || ''), source: String(form.get('source') || ''),
      description: String(form.get('description') || ''), start_date: String(form.get('start_date') || '') || null,
      end_date: String(form.get('end_date') || '') || null}, String(form.get('newClient') || '').trim());
  };
  return <div className="modalBackdrop" onClick={() => !busy && onClose()}>
    <form className="dealModal" role="dialog" aria-modal="true" aria-label={deal ? 'Редактирование сделки' : 'Новая сделка'} onSubmit={submit} onClick={e => e.stopPropagation()}>
      <div className="drawerHead"><h2>{deal ? 'Редактирование сделки' : 'Новая сделка'}</h2><button aria-label="Закрыть" type="button" disabled={busy} onClick={onClose}><X size={20}/></button></div>
      <fieldset disabled={busy}>
        <label>Название сделки<input name="title" defaultValue={deal?.title} required maxLength={255}/></label>
        <label>Компания / клиент<select value={clientId} onChange={e => {setClientId(e.target.value); setContactId('');}}><option value="">Новый клиент</option>{clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        {!clientId && <label>Название клиента<input name="newClient" required maxLength={255}/></label>}
        <label>Связанный контакт<select value={contactId} onChange={e => setContactId(e.target.value)}><option value="">Не выбран</option>{contacts.filter(c => c.client_ids.includes(clientId)).map(c => <option key={c.id} value={c.id}>{contactName(c)}</option>)}</select></label>
        {!contactId && <label>Контактное лицо текстом<input name="contact" defaultValue={deal?.contact_name || ''} maxLength={255}/></label>}
        <label>Сумма<input name="amount" type="number" min="0" max="999999999999.99" step="0.01" defaultValue={deal?.amount || '50000'} required/></label>
        <label>Источник<input name="source" list="sources" defaultValue={deal?.source || ''} maxLength={100}/><datalist id="sources">{['2ГИС', 'WhatsApp', 'Сайт', 'Рекомендация', 'Холодный'].map(s => <option key={s}>{s}</option>)}</datalist></label>
        <label>Начало сделки<input name="start_date" type="date" defaultValue={deal?.start_date || ''}/></label>
        <label>Окончание сделки<input name="end_date" type="date" defaultValue={deal?.end_date || ''}/></label>
        <label>Воронка<select value={pipelineId} onChange={e => {setPipelineId(e.target.value); setStageId(pipelines.find(p => p.id === e.target.value)?.stages[0]?.id || '');}}>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Стадия<select required value={stageId} onChange={e => setStageId(e.target.value)}>{pipeline?.stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label>Ответственный<select name="responsible" defaultValue={deal?.responsible_user_id || ''}><option value="">Не назначен</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}</select></label>
        <label>Описание<textarea name="description" maxLength={10000} defaultValue={deal?.description || ''}/></label>
        {error && <p role="alert" className="errorMessage">{error}</p>}
        <button className="saveFollow" disabled={!stageId}>{busy ? 'Сохранение…' : 'Сохранить сделку'}</button>
      </fieldset>
    </form>
  </div>;
}

function DealDrawer({deal, client, contact, stage, responsibleName, base, busy, canDelete, onClose, onEdit, onDelete, onFollow, onComplete, onOpenClient, onOpenContact}: {
  deal: Deal; client?: Client; contact?: Contact; stage?: string; responsibleName?: string; base: string; busy: boolean; canDelete: boolean;
  onClose: () => void; onEdit: () => void; onDelete: () => Promise<void>;
  onFollow: (value: {at: string; action: Action; comment: string} | null) => Promise<void>;
  onComplete: (outcome: string) => Promise<FollowUpCompletion>;
  onOpenClient: () => void;
  onOpenContact: () => void;
}) {
  const [next, setNext] = useState(localDateTime(deal.follow_up_at));
  const [action, setAction] = useState<Action>(deal.follow_up_action || 'call');
  const [comment, setComment] = useState(deal.follow_up_comment || '');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [activities, setActivities] = useState<DealActivity[]>([]);
  const [activityBody, setActivityBody] = useState('');
  const [activityLoading, setActivityLoading] = useState(true);
  const [activityBusy, setActivityBusy] = useState(false);
  const [activityError, setActivityError] = useState('');
  const [activityReload, setActivityReload] = useState(0);
  const [completions, setCompletions] = useState<FollowUpCompletion[]>([]);
  const [completionLoading, setCompletionLoading] = useState(true);
  const [completionError, setCompletionError] = useState('');
  const [completionReload, setCompletionReload] = useState(0);
  const [outcome, setOutcome] = useState('');
  const [completionBusy, setCompletionBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setActivityLoading(true); setActivityError('');
    request<DealActivity[]>(`${base}/deals/${deal.id}/activities`, 'GET', undefined, controller.signal)
      .then(rows => {if (!controller.signal.aborted) {setActivities(rows); setActivityLoading(false);}})
      .catch(e => {if (!controller.signal.aborted) {setActivityError(errorText(e)); setActivityLoading(false);}});
    return () => controller.abort();
  }, [base, deal.id, activityReload]);
  useEffect(() => {
    const controller = new AbortController();
    setCompletionLoading(true); setCompletionError('');
    request<FollowUpCompletion[]>(`${base}/deals/${deal.id}/follow-up/completions`, 'GET', undefined, controller.signal)
      .then(rows => {if (!controller.signal.aborted) {setCompletions(rows); setCompletionLoading(false);}})
      .catch(e => {if (!controller.signal.aborted) {setCompletionError(errorText(e)); setCompletionLoading(false);}});
    return () => controller.abort();
  }, [base, deal.id, completionReload]);
  const addActivity = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!activityBody.trim() || activityBusy) return;
    setActivityBusy(true); setActivityError('');
    try {
      const row = await request<DealActivity>(`${base}/deals/${deal.id}/activities`, 'POST', {body: activityBody.trim()});
      setActivities(previous => [row, ...previous]); setActivityBody('');
    } catch (e) {setActivityError(errorText(e));}
    finally {setActivityBusy(false);}
  };
  const save = async (clear = false) => {
    setError(''); setStatus('');
    try {
      await onFollow(clear ? null : {at: new Date(next).toISOString(), action, comment});
      if (clear) {setNext(''); setComment(''); setAction('call');}
      setStatus(clear ? 'Follow-up удалён' : 'Follow-up сохранён');
    } catch (e) {setError(errorText(e));}
  };
  const complete = async () => {
    if (completionBusy || busy) return;
    setCompletionBusy(true); setCompletionError(''); setStatus('');
    try {
      const item = await onComplete(outcome.trim());
      setCompletions(previous => [item, ...previous]);
      setNext(''); setAction('call'); setComment(''); setOutcome('');
      setStatus('Follow-up выполнен');
    } catch(e) {setCompletionError(errorText(e));}
    finally {setCompletionBusy(false);}
  };
  return <div className="drawerBackdrop" onClick={() => !busy && onClose()}><aside className="drawer" role="dialog" aria-modal="true" aria-label="Карточка сделки" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><div><small>Сделка</small><h2>{deal.title}</h2></div><button aria-label="Закрыть" disabled={busy} onClick={onClose}><X size={20}/></button></div>
    <div className="dealStatus"><span>{stage}</span><strong>{money(deal.amount, deal.currency)}</strong></div>
    <div className="quickActions"><button disabled={busy} onClick={onEdit}>Редактировать</button>{canDelete && <button disabled={busy} onClick={async () => {if (window.confirm('Удалить сделку?')) {try {await onDelete();} catch(e) {setError(errorText(e));}}}}>Удалить</button>}</div>
    <section className="drawerSection"><h3>Контакт</h3><p>{client && <button type="button" className="clientLink" onClick={onOpenClient}>{client.name}</button>}</p><p>{contact ? <button type="button" className="clientLink" onClick={onOpenContact}>{contactName(contact)}</button> : deal.contact_name || 'Контакт не указан'}</p><p>Ответственный: {responsibleName || 'Не назначен'}</p><p>Источник: {deal.source || 'Не указан'}</p><p>Сроки: {deal.start_date || '—'} — {deal.end_date || '—'}</p>{deal.description && <p>{deal.description}</p>}</section>
    <form className="drawerSection followEditor" onSubmit={e => {e.preventDefault(); void save();}}>
      <h3>Следующий контакт</h3><p className="muted">Дата и время в часовом поясе вашего устройства.</p>
      <fieldset disabled={busy}>
        <label>Дата и время<input type="datetime-local" required value={next} onChange={e => setNext(e.target.value)}/></label>
        <label>Что сделать<select value={action} onChange={e => setAction(e.target.value as Action)}>{Object.entries(actions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Комментарий<textarea maxLength={10000} value={comment} onChange={e => setComment(e.target.value)}/></label>
        <button className="saveFollow">{busy ? 'Сохранение…' : 'Сохранить follow-up'}</button>
        {deal.follow_up_at && <button className="noteBtn" type="button" onClick={() => void save(true)}>Удалить follow-up</button>}
      </fieldset>
    </form>
    {deal.follow_up_at && <section className="drawerSection completionSection"><label>Итог контакта<textarea maxLength={10000} value={outcome} onChange={e => setOutcome(e.target.value)} placeholder="Что удалось сделать"/></label><button type="button" disabled={busy || completionBusy} onClick={() => void complete()}>{completionBusy ? 'Сохранение…' : 'Отметить follow-up выполненным'}</button></section>}
    <section className="drawerSection"><h3>Завершённые действия</h3>
      {completionLoading ? <p role="status">Загрузка завершённых действий…</p> : completionError && !completions.length ? <p role="alert">{completionError} <button type="button" onClick={() => setCompletionReload(n => n + 1)}>Повторить</button></p> : completions.length ?
        <ol className="activityList">{completions.map(item => <li key={item.id}><strong>{actions[item.action]}</strong> · {item.completed_by_name} · <time dateTime={item.completed_at}>{new Date(item.completed_at).toLocaleString('ru-RU')}</time><p>{item.outcome_comment || item.planned_comment || 'Без комментария'}</p></li>)}</ol> : <p className="muted">Завершённых действий пока нет.</p>}
      {completionError && completions.length > 0 && <p role="alert" className="errorMessage">{completionError}</p>}
    </section>
    {error && <p role="alert" className="errorMessage">{error}</p>}{status && <p role="status">{status}</p>}
    <section className="drawerSection activitySection"><h3>История действий</h3>
      {activityLoading ? <p role="status">Загрузка истории…</p> : activityError && !activities.length ? <p role="alert">{activityError} <button type="button" onClick={() => setActivityReload(n => n + 1)}>Повторить</button></p> : !activities.length ? <p className="muted">Записей пока нет.</p> :
        <ol className="activityList">{activities.map(item => <li key={item.id}><strong>{item.author_name}</strong> · <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('ru-RU')}</time>{item.kind === 'STAGE_CHANGE' && <span className="activityKind">Смена стадии</span>}<p>{item.body}</p></li>)}</ol>}
      <form onSubmit={e => void addActivity(e)}><label>Новая заметка<textarea value={activityBody} maxLength={10000} onChange={e => setActivityBody(e.target.value)}/></label><button disabled={activityBusy || !activityBody.trim()}>{activityBusy ? 'Сохранение…' : 'Добавить в историю'}</button></form>
      {activityError && activities.length > 0 && <p role="alert" className="errorMessage">{activityError}</p>}
    </section>
    <section className="drawerSection"><h3>Даты сделки</h3><p>Создана: {new Date(deal.created_at).toLocaleString('ru-RU')}</p><p>Обновлена: {new Date(deal.updated_at).toLocaleString('ru-RU')}</p></section>
  </aside></div>;
}

export default function CRM() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineId, setPipelineId] = useState('');
  const [clients, setClients] = useState<Client[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [items, setItems] = useState<Deal[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Deal | 'new' | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [reload, setReload] = useState(0);
  const [search, setSearch] = useState('');
  const [followFilter, setFollowFilter] = useState<'all' | 'today' | 'overdue' | 'none'>('all');
  const [stageSettings, setStageSettings] = useState(false);
  const [pipelineSettings, setPipelineSettings] = useState(false);
  const [clientDirectory, setClientDirectory] = useState<string | null>(null);
  const [contactDirectory, setContactDirectory] = useState<{initialId?: string; initialClientId?: string} | null>(null);
  const base = `/workspaces/${workspaceId}`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setItems([]); setClients([]); setContacts([]); setMembers([]); setPipelines([]); setSelectedId(null); setEditing(null); setStageSettings(false); setPipelineSettings(false); setClientDirectory(null); setContactDirectory(null);
    const load = async () => {
      try {
        const spaces = await request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setWorkspaces(spaces);
        const id = spaces.some(w => w.id === workspaceId) ? workspaceId : spaces[0]?.id;
        if (!id) {setLoading(false); return;}
        if (id !== workspaceId) {setWorkspaceId(id); return;}
        const path = `/workspaces/${id}`;
        const [nextPipelines, nextClients, nextContacts, nextMembers, nextItems] = await Promise.all([
          request<Pipeline[]>(`${path}/pipelines`, 'GET', undefined, controller.signal),
          request<Client[]>(`${path}/clients`, 'GET', undefined, controller.signal),
          request<Contact[]>(`${path}/contacts`, 'GET', undefined, controller.signal),
          request<Member[]>(`${path}/members`, 'GET', undefined, controller.signal), loadDeals(path, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setPipelines(nextPipelines); setPipelineId(nextPipelines[0]?.id || ''); setClients(nextClients); setContacts(nextContacts); setMembers(nextMembers); setItems(nextItems); setLoading(false);
      } catch(e) {if (!controller.signal.aborted) {setError(errorText(e)); setLoading(false);}}
    };
    void load();
    return () => controller.abort();
  }, [workspaceId, reload]);

  const mutate = async (operation: () => Promise<void>) => {
    if (saving.current) throw new Error('Дождитесь завершения сохранения');
    saving.current = true; setBusy(true);
    try {await operation();} finally {saving.current = false; setBusy(false);}
  };
  const replace = (deal: Deal) => setItems(prev => prev.map(item => item.id === deal.id ? deal : item));
  const saveDeal = async (data: DealInput, newClient: string) => {
    setFormError('');
    try {await mutate(async () => {
      if (!data.client_id) {
        // Reuse a client created by an earlier failed deal save in this session.
        const client = clients.find(c => c.name === newClient) || await request<Client>(`${base}/clients`, 'POST', {name: newClient});
        setClients(prev => prev.some(c => c.id === client.id) ? prev : [...prev, client]);
        data.client_id = client.id;
      }
      const isEdit = editing && editing !== 'new';
      const deal = await request<Deal>(`${base}/deals${isEdit ? `/${editing.id}` : ''}`, isEdit ? 'PATCH' : 'POST', data);
      if (isEdit) replace(deal); else setItems(prev => [...prev, deal]);
      setPipelineId(deal.pipeline_id); setEditing(null);
    });} catch(e) {setFormError(errorText(e));}
  };
  const move = async (id: string, stageId: string) => {
    if (busy || !items.some(d => d.id === id && d.stage_id !== stageId)) return;
    setError('');
    try {await mutate(async () => replace(await request<Deal>(`${base}/deals/${id}`, 'PATCH', {stage_id: stageId})));}
    catch(e) {setError(errorText(e));}
  };
  const pipeline = pipelines.find(p => p.id === pipelineId);
  const canManageStages = ['OWNER', 'ADMIN'].includes(workspaces.find(w => w.id === workspaceId)?.role || '');
  const refreshPipelines = async (selectId?: string) => {
    const next = await request<Pipeline[]>(`${base}/pipelines`);
    setPipelines(next);
    setPipelineId(selectId || (next.some(row => row.id === pipelineId) ? pipelineId : next[0]?.id || ''));
  };
  const refreshClients = async () => setClients(await request<Client[]>(`${base}/clients`));
  const refreshContacts = async () => setContacts(await request<Contact[]>(`${base}/contacts`));
  const selected = items.find(d => d.id === selectedId);
  const startOfToday = new Date(); startOfToday.setHours(0, 0, 0, 0);
  const startOfTomorrow = new Date(startOfToday); startOfTomorrow.setDate(startOfTomorrow.getDate() + 1);
  const isToday = (deal: Deal) => !!deal.follow_up_at && new Date(deal.follow_up_at) >= startOfToday && new Date(deal.follow_up_at) < startOfTomorrow;
  const isOverdue = (deal: Deal) => !!deal.follow_up_at && new Date(deal.follow_up_at) < startOfToday;
  const pipelineItems = items.filter(d => d.pipeline_id === pipelineId);
  const filtered = pipelineItems.filter(d => (followFilter === 'all' ||
    (followFilter === 'today' && isToday(d)) || (followFilter === 'overdue' && isOverdue(d)) ||
    (followFilter === 'none' && !d.follow_up_at)) &&
    `${d.title} ${clients.find(c => c.id === d.client_id)?.name || ''} ${contacts.find(c => c.id === d.contact_id) ? contactName(contacts.find(c => c.id === d.contact_id)!) : d.contact_name || ''}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <>
    <header><div><h1>CRM · Сделки</h1><p>Управление продажами и следующими контактами</p></div><button className="primary" disabled={loading || busy || !pipeline?.stages.length} onClick={() => {setFormError(''); setEditing('new');}}><Plus size={18}/>Новая сделка</button></header>
    <div className="crmTools">
      <select aria-label="Рабочее пространство" disabled={loading || busy} value={workspaceId} onChange={e => setWorkspaceId(e.target.value)}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
      <select aria-label="Воронка" disabled={loading || busy} value={pipelineId} onChange={e => setPipelineId(e.target.value)}>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <button type="button" className="filter" disabled={loading} onClick={() => setClientDirectory('list')}>Компании</button>
      <button type="button" className="filter" disabled={loading} onClick={() => setContactDirectory({})}>Контакты</button>
      {canManageStages && <button type="button" className="filter" onClick={() => setPipelineSettings(true)}>Управление воронками</button>}
      {canManageStages && pipeline && <button type="button" className="filter" onClick={() => setStageSettings(true)}>Настроить стадии</button>}
      <div className="search"><Search size={17}/><input aria-label="Поиск сделок" placeholder="Поиск по сделкам и клиентам" value={search} onChange={e => setSearch(e.target.value)}/></div>
      <button className="filter" aria-pressed={followFilter === 'today'} onClick={() => setFollowFilter(followFilter === 'today' ? 'all' : 'today')}><CalendarClock size={17}/>Follow-up сегодня <b>{pipelineItems.filter(isToday).length}</b></button>
      <button className="filter" aria-pressed={followFilter === 'overdue'} onClick={() => setFollowFilter(followFilter === 'overdue' ? 'all' : 'overdue')}>Просрочены <b>{pipelineItems.filter(isOverdue).length}</b></button>
      <button className="filter" aria-pressed={followFilter === 'none'} onClick={() => setFollowFilter(followFilter === 'none' ? 'all' : 'none')}>Нет дел <b>{pipelineItems.filter(d => !d.follow_up_at).length}</b></button>
    </div>
    {error && <div role="alert" className="errorMessage">{error} <button disabled={busy || loading} onClick={() => setReload(n => n + 1)}>Повторить загрузку</button></div>}
    {loading ? <p role="status">Загрузка CRM…</p> : !pipeline ? <p>Нет доступных воронок. Откройте «Настройки», чтобы создать студию, или попросите владельца добавить вас.</p> : <>
      {busy && <p role="status">Сохранение…</p>}
      {!filtered.length && <p className="muted">{items.length ? 'Нет сделок по выбранным условиям.' : 'Пока нет сделок. Создайте первую сделку.'}</p>}
      <div className="kanban" style={{gridTemplateColumns: `repeat(${pipeline.stages.length || 1}, minmax(230px, 1fr))`}}>
        {pipeline.stages.map(stage => {const list = filtered.filter(d => d.stage_id === stage.id); return <section className="kanbanCol" key={stage.id} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); void move(e.dataTransfer.getData('dealId'), stage.id);}}>
          <div className="colHead"><div><span className="dot"/><b>{stage.name}</b><em>{list.length}</em></div><strong>{money(list.reduce((sum, d) => sum + Math.round(Number(d.amount) * 100), 0) / 100, workspaces.find(w => w.id === workspaceId)?.currency || 'RUB')}</strong></div>
          <div className="dealList">{list.map(d => <article className="deal card" key={d.id} draggable={!busy} tabIndex={0} aria-label={`Открыть ${d.title}`} onKeyDown={e => {if (e.key === 'Enter') setSelectedId(d.id);}} onDragStart={e => e.dataTransfer.setData('dealId', d.id)} onClick={() => setSelectedId(d.id)}>
            <div className="dealTop"><small>{d.source || 'Без источника'}</small></div><h3>{d.title}</h3><p>{clients.find(c => c.id === d.client_id)?.name} · {contacts.find(c => c.id === d.contact_id) ? contactName(contacts.find(c => c.id === d.contact_id)!) : d.contact_name || 'Без контакта'}</p><p>Ответственный: {members.find(m => m.user_id === d.responsible_user_id)?.first_name || 'Не назначен'}</p><strong>{money(d.amount, d.currency)}</strong>
            <div className={`follow ${d.follow_up_at && new Date(d.follow_up_at).getTime() < Date.now() ? 'late' : ''}`}><CalendarClock size={14}/><span>{d.follow_up_at ? new Date(d.follow_up_at).toLocaleString('ru-RU') : 'Не назначен'}</span></div>
          </article>)}</div><button className="addDeal" disabled={busy} onClick={() => {setFormError(''); setEditing('new');}}><Plus size={15}/>Добавить сделку</button>
        </section>;})}
      </div>
    </>}
    {selected && <DealDrawer key={selected.id} base={base} canDelete={['OWNER', 'ADMIN'].includes(workspaces.find(w => w.id === workspaceId)?.role || '')} deal={selected} client={clients.find(c => c.id === selected.client_id)} contact={contacts.find(c => c.id === selected.contact_id)} stage={pipelines.flatMap(p => p.stages).find(s => s.id === selected.stage_id)?.name} responsibleName={members.find(m => m.user_id === selected.responsible_user_id)?.first_name} busy={busy}
      onClose={() => setSelectedId(null)} onEdit={() => {setFormError(''); setEditing(selected);}}
      onOpenClient={() => {setSelectedId(null); setClientDirectory(selected.client_id);}}
      onOpenContact={() => {setSelectedId(null); setContactDirectory({initialId: selected.contact_id || undefined});}}
      onDelete={() => mutate(async () => {await request(`${base}/deals/${selected.id}`, 'DELETE'); setItems(prev => prev.filter(d => d.id !== selected.id)); setSelectedId(null);})}
      onFollow={value => mutate(async () => replace(await request<Deal>(`${base}/deals/${selected.id}/follow-up`, value ? 'PUT' : 'DELETE', value || undefined)))}
      onComplete={async outcome => {let completion!: FollowUpCompletion; await mutate(async () => {const result = await request<{completion: FollowUpCompletion; deal: Deal}>(`${base}/deals/${selected.id}/follow-up/complete`, 'POST', {outcome_comment: outcome || null}); completion = result.completion; replace(result.deal);}); return completion;}}/>}
    {editing && <DealForm deal={editing === 'new' ? undefined : editing} clients={clients} contacts={contacts} members={members} pipelines={pipelines} initialPipeline={pipelineId} busy={busy} error={formError} onClose={() => setEditing(null)} onSave={saveDeal}/>}
    {stageSettings && pipeline && <StageSettings pipeline={pipeline} base={base} onClose={() => setStageSettings(false)} onChanged={refreshPipelines}/>}
    {pipelineSettings && <PipelineSettings base={base} onClose={() => setPipelineSettings(false)} onChanged={refreshPipelines}/>}
    {clientDirectory && <ClientDirectory clients={clients} contacts={contacts} base={base} initialId={clientDirectory === 'list' ? undefined : clientDirectory} canDelete={canManageStages} onClose={() => setClientDirectory(null)} onChanged={refreshClients} onOpenDeal={id => {setClientDirectory(null); setSelectedId(id);}} onOpenContact={(id, clientId) => {setClientDirectory(null); setContactDirectory({initialId: id, initialClientId: clientId});}}/>}
    {contactDirectory && <ContactDirectory contacts={contacts} clients={clients} base={base} canDelete={canManageStages} initialId={contactDirectory.initialId} initialClientId={contactDirectory.initialClientId} onClose={() => setContactDirectory(null)} onChanged={refreshContacts} onOpenDeal={id => {setContactDirectory(null); setSelectedId(id);}}/>}
  </>;
}
