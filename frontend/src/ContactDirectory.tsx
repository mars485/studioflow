import {useEffect, useState, type FormEvent} from 'react';
import {X} from 'lucide-react';
import {type Client, type Contact, type Deal, contactName, errorText, money, request} from './api';

type Draft = {first_name: string; last_name: string; middle_name: string; phone: string;
  email: string; website: string; notes: string; client_ids: string[]};

function ContactEditor({contact, contacts, clients, base, canDelete, initialClientId, onChanged, onOpenDeal}: {
  contact?: Contact; contacts: Contact[]; clients: Client[]; base: string; canDelete: boolean; initialClientId?: string;
  onChanged: (id?: string) => Promise<void>; onOpenDeal: (id: string) => void;
}) {
  const [draft, setDraft] = useState<Draft>({first_name: contact?.first_name || '', last_name: contact?.last_name || '',
    middle_name: contact?.middle_name || '', phone: contact?.phone || '', email: contact?.email || '',
    website: contact?.website || '', notes: contact?.notes || '', client_ids: contact?.client_ids || (initialClientId ? [initialClientId] : [])});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(!!contact);
  const [dealError, setDealError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!contact) return;
    const controller = new AbortController();
    setLoading(true); setDealError('');
    request<Deal[]>(`${base}/contacts/${contact.id}/deals`, 'GET', undefined, controller.signal)
      .then(rows => {if (!controller.signal.aborted) setDeals(rows);})
      .catch(e => {if (!controller.signal.aborted) setDealError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, contact?.id, reload]);
  const set = (key: keyof Draft, value: string) => setDraft(previous => ({...previous, [key]: value}));
  const toggleClient = (id: string) => setDraft(previous => ({...previous,
    client_ids: previous.client_ids.includes(id) ? previous.client_ids.filter(item => item !== id) : [...previous.client_ids, id]}));
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !draft.first_name.trim()) return;
    setBusy(true); setError('');
    try {
      const payload = {first_name: draft.first_name.trim(), last_name: draft.last_name.trim() || null,
        middle_name: draft.middle_name.trim() || null, phone: draft.phone.trim() || null,
        email: draft.email.trim() || null, website: draft.website.trim() || null,
        notes: draft.notes.trim() || null, client_ids: draft.client_ids};
      const saved = await request<Contact>(contact ? `${base}/contacts/${contact.id}` : `${base}/contacts`,
        contact ? 'PATCH' : 'POST', payload);
      await onChanged(saved.id);
    } catch(e) {setError(errorText(e));} finally {setBusy(false);}
  };
  const remove = async () => {
    if (!contact || busy || !window.confirm(`Удалить контакт «${contactName(contact)}»?`)) return;
    setBusy(true); setError('');
    try {await request(`${base}/contacts/${contact.id}`, 'DELETE'); await onChanged();}
    catch(e) {setError(errorText(e));} finally {setBusy(false);}
  };
  const duplicate = !contact && contacts.find(row => row.first_name.toLocaleLowerCase() === draft.first_name.trim().toLocaleLowerCase()
    && (row.last_name || '').toLocaleLowerCase() === draft.last_name.trim().toLocaleLowerCase());
  return <div className="clientEditor"><h3>{contact ? contactName(contact) : 'Новый контакт'}</h3>
    {duplicate && <p className="clientDuplicate">Похожий контакт уже есть: {contactName(duplicate)}.</p>}
    <form onSubmit={e => void save(e)}><fieldset disabled={busy}>
      <label>Имя<input required maxLength={100} value={draft.first_name} onChange={e => set('first_name', e.target.value)}/></label>
      <label>Фамилия<input maxLength={100} value={draft.last_name} onChange={e => set('last_name', e.target.value)}/></label>
      <label>Отчество<input maxLength={100} value={draft.middle_name} onChange={e => set('middle_name', e.target.value)}/></label>
      <label>Рабочий телефон<input maxLength={50} value={draft.phone} onChange={e => set('phone', e.target.value)}/></label>
      <label>Рабочий email<input type="email" value={draft.email} onChange={e => set('email', e.target.value)}/></label>
      <label>Сайт<input maxLength={255} value={draft.website} onChange={e => set('website', e.target.value)}/></label>
      <label>Описание<textarea maxLength={10000} value={draft.notes} onChange={e => set('notes', e.target.value)}/></label>
      <fieldset className="contactCompanies"><legend>Компании</legend>{clients.map(client => <label key={client.id}><input type="checkbox" checked={draft.client_ids.includes(client.id)} onChange={() => toggleClient(client.id)}/>{client.name}</label>)}</fieldset>
      {error && <p role="alert" className="errorMessage">{error}</p>}
      <div className="clientActions"><button className="saveFollow" disabled={!draft.first_name.trim()}>{busy ? 'Сохранение…' : 'Сохранить контакт'}</button>
        {contact && canDelete && <button type="button" className="noteBtn" onClick={() => void remove()}>Удалить контакт</button>}</div>
    </fieldset></form>
    {contact && <section className="clientDeals"><h3>Сделки контакта</h3>
      {loading ? <p role="status">Загрузка сделок…</p> : dealError ? <p role="alert">{dealError} <button type="button" onClick={() => setReload(n => n + 1)}>Повторить</button></p> :
        deals.length ? <ul>{deals.map(deal => <li key={deal.id}><button type="button" onClick={() => onOpenDeal(deal.id)}>{deal.title}</button><span>{money(deal.amount, deal.currency)}</span></li>)}</ul> : <p className="muted">Сделок пока нет.</p>}
    </section>}
  </div>;
}

export default function ContactDirectory({contacts, clients, base, canDelete, initialId, initialClientId, onClose, onChanged, onOpenDeal}: {
  contacts: Contact[]; clients: Client[]; base: string; canDelete: boolean; initialId?: string; initialClientId?: string;
  onClose: () => void; onChanged: () => Promise<void>; onOpenDeal: (id: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(initialId || (initialClientId ? 'new' : null));
  const [search, setSearch] = useState('');
  const selected = contacts.find(row => row.id === selectedId);
  const filtered = contacts.filter(row => `${contactName(row)} ${row.phone || ''} ${row.email || ''}`
    .toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const changed = async (id?: string) => {await onChanged(); setSelectedId(id || null);};
  return <div className="modalBackdrop" onClick={onClose}><section className="clientDirectory dealModal" role="dialog" aria-modal="true" aria-label="Контакты" onClick={e => e.stopPropagation()}>
    <div className="drawerHead"><h2>Контакты</h2><button type="button" aria-label="Закрыть" onClick={onClose}><X size={20}/></button></div>
    <div className="clientDirectoryBody"><aside><label>Поиск контактов<input value={search} onChange={e => setSearch(e.target.value)}/></label>
      <button className="clientListButton" type="button" onClick={() => setSelectedId('new')}>+ Новый контакт</button>
      {filtered.length ? <ul>{filtered.map(row => <li key={row.id}><button className="clientListButton" type="button" aria-current={selectedId === row.id ? 'true' : undefined} onClick={() => setSelectedId(row.id)}>{contactName(row)}</button></li>)}</ul> : <p className="muted">Контакты не найдены.</p>}
    </aside><div>{selectedId ? <ContactEditor key={selectedId} contact={selected} contacts={contacts} clients={clients} base={base} canDelete={canDelete} initialClientId={initialClientId} onChanged={changed} onOpenDeal={onOpenDeal}/> : <p className="muted">Выберите контакт или создайте новый.</p>}</div></div>
  </section></div>;
}
