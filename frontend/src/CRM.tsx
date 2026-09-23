import {useEffect, useRef, useState, type FormEvent} from 'react';
import {CalendarClock, Plus, Search, X} from 'lucide-react';
import {type Action, type Client, type Deal, type DealInput, type Pipeline, type Workspace,
  errorText, loadDeals, localDateTime, money, request} from './api';

const actions: Record<Action, string> = {call: 'Позвонить', message: 'Написать в WhatsApp', proposal: 'Отправить КП', decision: 'Уточнить решение'};

function DealForm({deal, clients, pipelines, initialPipeline, busy, error, onClose, onSave}: {
  deal?: Deal; clients: Client[]; pipelines: Pipeline[]; initialPipeline: string;
  busy: boolean; error: string; onClose: () => void;
  onSave: (data: DealInput, newClient: string) => Promise<void>;
}) {
  const [pipelineId, setPipelineId] = useState(deal?.pipeline_id || initialPipeline);
  const [clientId, setClientId] = useState(deal?.client_id || '');
  const [stageId, setStageId] = useState(deal?.stage_id || pipelines.find(p => p.id === pipelineId)?.stages[0]?.id || '');
  const pipeline = pipelines.find(p => p.id === pipelineId);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void onSave({title: String(form.get('title')).trim(), client_id: clientId, pipeline_id: pipelineId,
      stage_id: stageId, amount: String(form.get('amount') || '0'),
      contact_name: String(form.get('contact') || ''), source: String(form.get('source') || ''),
      description: String(form.get('description') || '')}, String(form.get('newClient') || '').trim());
  };
  return <div className="modalBackdrop" onClick={() => !busy && onClose()}>
    <form className="dealModal" role="dialog" aria-modal="true" aria-label={deal ? 'Редактирование сделки' : 'Новая сделка'} onSubmit={submit} onClick={e => e.stopPropagation()}>
      <div className="drawerHead"><h2>{deal ? 'Редактирование сделки' : 'Новая сделка'}</h2><button aria-label="Закрыть" type="button" disabled={busy} onClick={onClose}><X size={20}/></button></div>
      <fieldset disabled={busy}>
        <label>Название сделки<input name="title" defaultValue={deal?.title} required maxLength={255}/></label>
        <label>Компания / клиент<select value={clientId} onChange={e => setClientId(e.target.value)}><option value="">Новый клиент</option>{clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        {!clientId && <label>Название клиента<input name="newClient" required maxLength={255}/></label>}
        <label>Контактное лицо<input name="contact" defaultValue={deal?.contact_name || ''} maxLength={255}/></label>
        <label>Сумма<input name="amount" type="number" min="0" max="999999999999.99" step="0.01" defaultValue={deal?.amount || '50000'} required/></label>
        <label>Источник<input name="source" list="sources" defaultValue={deal?.source || ''} maxLength={100}/><datalist id="sources">{['2ГИС', 'WhatsApp', 'Сайт', 'Рекомендация', 'Холодный'].map(s => <option key={s}>{s}</option>)}</datalist></label>
        <label>Воронка<select value={pipelineId} onChange={e => {setPipelineId(e.target.value); setStageId(pipelines.find(p => p.id === e.target.value)?.stages[0]?.id || '');}}>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Стадия<select required value={stageId} onChange={e => setStageId(e.target.value)}>{pipeline?.stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label>Описание<textarea name="description" maxLength={10000} defaultValue={deal?.description || ''}/></label>
        {error && <p role="alert" className="errorMessage">{error}</p>}
        <button className="saveFollow" disabled={!stageId}>{busy ? 'Сохранение…' : 'Сохранить сделку'}</button>
      </fieldset>
    </form>
  </div>;
}

function DealDrawer({deal, client, stage, busy, onClose, onEdit, onDelete, onFollow}: {
  deal: Deal; client?: Client; stage?: string; busy: boolean;
  onClose: () => void; onEdit: () => void; onDelete: () => Promise<void>;
  onFollow: (value: {at: string; action: Action; comment: string} | null) => Promise<void>;
}) {
  const [next, setNext] = useState(localDateTime(deal.follow_up_at));
  const [action, setAction] = useState<Action>(deal.follow_up_action || 'call');
  const [comment, setComment] = useState(deal.follow_up_comment || '');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const save = async (clear = false) => {
    setError(''); setStatus('');
    try {
      await onFollow(clear ? null : {at: new Date(next).toISOString(), action, comment});
      if (clear) {setNext(''); setComment(''); setAction('call');}
      setStatus(clear ? 'Follow-up удалён' : 'Follow-up сохранён');
    } catch (e) {setError(errorText(e));}
  };
  return <div className="drawerBackdrop" onClick={() => !busy && onClose()}><aside className="drawer" role="dialog" aria-modal="true" aria-label="Карточка сделки" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><div><small>Сделка</small><h2>{deal.title}</h2></div><button aria-label="Закрыть" disabled={busy} onClick={onClose}><X size={20}/></button></div>
    <div className="dealStatus"><span>{stage}</span><strong>{money(deal.amount, deal.currency)}</strong></div>
    <div className="quickActions"><button disabled={busy} onClick={onEdit}>Редактировать</button><button disabled={busy} onClick={async () => {if (window.confirm('Удалить сделку?')) {try {await onDelete();} catch(e) {setError(errorText(e));}}}}>Удалить</button></div>
    <section className="drawerSection"><h3>Контакт</h3><p>{client?.name}</p><p>{deal.contact_name || 'Контакт не указан'}</p><p>Источник: {deal.source || 'Не указан'}</p>{deal.description && <p>{deal.description}</p>}</section>
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
    {error && <p role="alert" className="errorMessage">{error}</p>}{status && <p role="status">{status}</p>}
    <section className="drawerSection"><h3>Даты сделки</h3><p>Создана: {new Date(deal.created_at).toLocaleString('ru-RU')}</p><p>Обновлена: {new Date(deal.updated_at).toLocaleString('ru-RU')}</p></section>
  </aside></div>;
}

export default function CRM() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineId, setPipelineId] = useState('');
  const [clients, setClients] = useState<Client[]>([]);
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
  const [todayOnly, setTodayOnly] = useState(false);
  const base = `/workspaces/${workspaceId}`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setItems([]); setClients([]); setPipelines([]); setSelectedId(null); setEditing(null);
    const load = async () => {
      try {
        const spaces = await request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setWorkspaces(spaces);
        const id = spaces.some(w => w.id === workspaceId) ? workspaceId : spaces[0]?.id;
        if (!id) {setLoading(false); return;}
        if (id !== workspaceId) {setWorkspaceId(id); return;}
        const path = `/workspaces/${id}`;
        const [nextPipelines, nextClients, nextItems] = await Promise.all([
          request<Pipeline[]>(`${path}/pipelines`, 'GET', undefined, controller.signal),
          request<Client[]>(`${path}/clients`, 'GET', undefined, controller.signal), loadDeals(path, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setPipelines(nextPipelines); setPipelineId(nextPipelines[0]?.id || ''); setClients(nextClients); setItems(nextItems); setLoading(false);
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
  const selected = items.find(d => d.id === selectedId);
  const isToday = (deal: Deal) => !!deal.follow_up_at && new Date(deal.follow_up_at).toDateString() === new Date().toDateString();
  const pipelineItems = items.filter(d => d.pipeline_id === pipelineId);
  const filtered = pipelineItems.filter(d => (!todayOnly || isToday(d)) &&
    `${d.title} ${clients.find(c => c.id === d.client_id)?.name || ''} ${d.contact_name || ''}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <>
    <header><div><h1>CRM · Сделки</h1><p>Управление продажами и следующими контактами</p></div><button className="primary" disabled={loading || busy || !pipeline?.stages.length} onClick={() => {setFormError(''); setEditing('new');}}><Plus size={18}/>Новая сделка</button></header>
    <div className="crmTools">
      <select aria-label="Рабочее пространство" disabled={loading || busy} value={workspaceId} onChange={e => setWorkspaceId(e.target.value)}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
      <select aria-label="Воронка" disabled={loading || busy} value={pipelineId} onChange={e => setPipelineId(e.target.value)}>{pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <div className="search"><Search size={17}/><input aria-label="Поиск сделок" placeholder="Поиск по сделкам и клиентам" value={search} onChange={e => setSearch(e.target.value)}/></div>
      <button className="filter" aria-pressed={todayOnly} onClick={() => setTodayOnly(!todayOnly)}><CalendarClock size={17}/>Follow-up сегодня <b>{pipelineItems.filter(isToday).length}</b></button>
    </div>
    {error && <div role="alert" className="errorMessage">{error} <button disabled={busy || loading} onClick={() => setReload(n => n + 1)}>Повторить загрузку</button></div>}
    {loading ? <p role="status">Загрузка CRM…</p> : !pipeline ? <p>Нет доступных воронок. Проверьте настройку рабочего пространства.</p> : <>
      {busy && <p role="status">Сохранение…</p>}
      {!filtered.length && <p className="muted">{items.length ? 'Нет сделок по выбранным условиям.' : 'Пока нет сделок. Создайте первую сделку.'}</p>}
      <div className="kanban" style={{gridTemplateColumns: `repeat(${pipeline.stages.length || 1}, minmax(230px, 1fr))`}}>
        {pipeline.stages.map(stage => {const list = filtered.filter(d => d.stage_id === stage.id); return <section className="kanbanCol" key={stage.id} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); void move(e.dataTransfer.getData('dealId'), stage.id);}}>
          <div className="colHead"><div><span className="dot"/><b>{stage.name}</b><em>{list.length}</em></div><strong>{money(list.reduce((sum, d) => sum + Math.round(Number(d.amount) * 100), 0) / 100, workspaces.find(w => w.id === workspaceId)?.currency || 'RUB')}</strong></div>
          <div className="dealList">{list.map(d => <article className="deal card" key={d.id} draggable={!busy} tabIndex={0} aria-label={`Открыть ${d.title}`} onKeyDown={e => {if (e.key === 'Enter') setSelectedId(d.id);}} onDragStart={e => e.dataTransfer.setData('dealId', d.id)} onClick={() => setSelectedId(d.id)}>
            <div className="dealTop"><small>{d.source || 'Без источника'}</small></div><h3>{d.title}</h3><p>{clients.find(c => c.id === d.client_id)?.name} · {d.contact_name || 'Без контакта'}</p><strong>{money(d.amount, d.currency)}</strong>
            <div className={`follow ${d.follow_up_at && new Date(d.follow_up_at).getTime() < Date.now() ? 'late' : ''}`}><CalendarClock size={14}/><span>{d.follow_up_at ? new Date(d.follow_up_at).toLocaleString('ru-RU') : 'Не назначен'}</span></div>
          </article>)}</div><button className="addDeal" disabled={busy} onClick={() => {setFormError(''); setEditing('new');}}><Plus size={15}/>Добавить сделку</button>
        </section>;})}
      </div>
    </>}
    {selected && <DealDrawer key={selected.id} deal={selected} client={clients.find(c => c.id === selected.client_id)} stage={pipelines.flatMap(p => p.stages).find(s => s.id === selected.stage_id)?.name} busy={busy}
      onClose={() => setSelectedId(null)} onEdit={() => {setFormError(''); setEditing(selected);}}
      onDelete={() => mutate(async () => {await request(`${base}/deals/${selected.id}`, 'DELETE'); setItems(prev => prev.filter(d => d.id !== selected.id)); setSelectedId(null);})}
      onFollow={value => mutate(async () => replace(await request<Deal>(`${base}/deals/${selected.id}/follow-up`, value ? 'PUT' : 'DELETE', value || undefined)))}/>}
    {editing && <DealForm deal={editing === 'new' ? undefined : editing} clients={clients} pipelines={pipelines} initialPipeline={pipelineId} busy={busy} error={formError} onClose={() => setEditing(null)} onSave={saveDeal}/>}
  </>;
}
