import {useEffect, useState, type FormEvent} from 'react';
import {X} from 'lucide-react';
import {type Client, type Contact, type Deal, contactName, errorText, money, request} from './api';
import ClientMergeHistory from './ClientMergeHistory';

type Draft = {name: string; phone: string; email: string; website: string; notes: string};
const empty: Draft = {name: '', phone: '', email: '', website: '', notes: ''};

function ClientEditor({client, clients, contacts, base, canDelete, onChanged, onOpenDeal, onOpenContact}: {
  client?: Client; clients: Client[]; contacts: Contact[]; base: string; canDelete: boolean;
  onChanged: (selectedId?: string) => Promise<void>; onOpenDeal: (id: string) => void;
  onOpenContact: (id?: string, clientId?: string) => void;
}) {
  const person = client?.type === 'PERSON';
  const [draft, setDraft] = useState<Draft>(client ? {
    name: client.name, phone: client.phone || '', email: client.email || '',
    website: client.website || '', notes: client.notes || '',
  } : empty);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(!!client);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dealError, setDealError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!client) return;
    const controller = new AbortController();
    setLoading(true); setDealError('');
    request<Deal[]>(`${base}/clients/${client.id}/deals`, 'GET', undefined, controller.signal)
      .then(rows => {if (!controller.signal.aborted) setDeals(rows);})
      .catch(e => {if (!controller.signal.aborted) setDealError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, client?.id, reload]);
  const set = (key: keyof Draft, value: string) => setDraft(previous => ({...previous, [key]: value}));
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !draft.name.trim()) return;
    setBusy(true); setError('');
    try {
      const payload = {name: draft.name.trim(), phone: draft.phone.trim() || null,
        email: draft.email.trim() || null, website: draft.website.trim() || null, notes: draft.notes.trim() || null};
      const saved = await request<Client>(client ? `${base}/clients/${client.id}` : `${base}/clients`, client ? 'PATCH' : 'POST', payload);
      await onChanged(saved.id);
    } catch(e) {setError(errorText(e));}
    finally {setBusy(false);}
  };
  const remove = async () => {
    if (!client || busy || !window.confirm(`Удалить ${person ? 'клиента' : 'компанию'} «${client.name}»?`)) return;
    setBusy(true); setError('');
    try {await request(`${base}/clients/${client.id}`, 'DELETE'); await onChanged();}
    catch(e) {setError(errorText(e));} finally {setBusy(false);}
  };
  const duplicate = !client && clients.find(row => row.name.trim().toLocaleLowerCase() === draft.name.trim().toLocaleLowerCase());
  return <div className="clientEditor"><h3>{client ? client.name : 'Новая компания'}</h3>
    {person && <p className="muted">Частное лицо. Имя заявителя не является названием юридической компании.</p>}
    {duplicate && <p className="clientDuplicate">Компания с таким названием уже есть: {duplicate.name}. Выберите её в списке, если это тот же клиент.</p>}
    <form onSubmit={e => void save(e)}><fieldset disabled={busy}>
      <label>{person ? 'Имя клиента' : 'Название компании'}<input required maxLength={255} value={draft.name} onChange={e => set('name', e.target.value)}/></label>
      <label>Рабочий телефон<input maxLength={50} value={draft.phone} onChange={e => set('phone', e.target.value)}/></label>
      <label>Рабочий email<input type="email" value={draft.email} onChange={e => set('email', e.target.value)}/></label>
      <label>Сайт<input maxLength={255} value={draft.website} onChange={e => set('website', e.target.value)}/></label>
      <label>Описание<textarea maxLength={10000} value={draft.notes} onChange={e => set('notes', e.target.value)}/></label>
      {error && <p role="alert" className="errorMessage">{error}</p>}
      <div className="clientActions"><button className="saveFollow" disabled={!draft.name.trim()}>{busy ? 'Сохранение…' : person ? 'Сохранить клиента' : 'Сохранить компанию'}</button>
        {client && canDelete && <button type="button" className="noteBtn" onClick={() => void remove()}>{person ? 'Удалить клиента' : 'Удалить компанию'}</button>}</div>
    </fieldset></form>
    {client && <section className="clientDeals"><h3>{person ? 'Контактные лица' : 'Контакты компании'}</h3>
      <ul>{contacts.filter(row => row.client_ids.includes(client.id)).map(row => <li key={row.id}><button type="button" onClick={() => onOpenContact(row.id)}>{contactName(row)}</button></li>)}</ul>
      <button type="button" className="noteBtn" onClick={() => onOpenContact(undefined, client.id)}>Добавить контакт</button>
    </section>}
    {client && <section className="clientDeals"><h3>{person ? 'Сделки клиента' : 'Сделки компании'}</h3>
      {loading ? <p role="status">Загрузка сделок…</p> : dealError ? <p role="alert">{dealError} <button type="button" onClick={() => setReload(n => n + 1)}>Повторить</button></p> :
        deals.length ? <ul>{deals.map(deal => <li key={deal.id}><button type="button" onClick={() => onOpenDeal(deal.id)}>{deal.title}</button><span>{money(deal.amount, deal.currency)}</span></li>)}</ul> : <p className="muted">Сделок пока нет.</p>}
    </section>}
    {client && canDelete && <ClientMergeHistory base={base} targetId={client.id}/>}
  </div>;
}

export default function ClientDirectory({clients, contacts, base, canDelete, initialId, onClose, onChanged, onOpenDeal, onOpenContact}: {
  clients: Client[]; contacts: Contact[]; base: string; canDelete: boolean; initialId?: string; onClose: () => void;
  onChanged: (selectedId?: string) => Promise<void>; onOpenDeal: (id: string) => void;
  onOpenContact: (id?: string, clientId?: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(initialId || null);
  const [search, setSearch] = useState('');
  const selected = clients.find(row => row.id === selectedId);
  const filtered = clients.filter(row => `${row.name} ${row.email || ''} ${row.phone || ''}`
    .toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const changed = async (id?: string) => {await onChanged(id); setSelectedId(id || null);};
  return <div className="modalBackdrop" onClick={onClose}><section className="clientDirectory dealModal" role="dialog" aria-modal="true" aria-label="Компании" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><h2>Компании</h2><button type="button" aria-label="Закрыть" onClick={onClose}><X size={20}/></button></div>
    <div className="clientDirectoryBody"><aside><label>Поиск компаний<input value={search} onChange={e => setSearch(e.target.value)}/></label>
      <button className="clientListButton" type="button" onClick={() => setSelectedId('new')}>+ Новая компания</button>
      {filtered.length ? <ul>{filtered.map(row => <li key={row.id}><button className="clientListButton" type="button" aria-current={selectedId === row.id ? 'true' : undefined} onClick={() => setSelectedId(row.id)}>{row.name}</button></li>)}</ul> : <p className="muted">Компании не найдены.</p>}
    </aside><div>{selectedId ? <ClientEditor key={selectedId} client={selected} clients={clients} contacts={contacts} base={base} canDelete={canDelete} onChanged={changed} onOpenDeal={onOpenDeal} onOpenContact={onOpenContact}/> : <p className="muted">Выберите компанию или создайте новую.</p>}</div></div>
  </section></div>;
}
