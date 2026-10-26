import {useEffect, useRef, useState} from 'react';
import {contactName, errorText, request, type Client, type Contact, type Workspace} from './api';
import ClientDirectory from './ClientDirectory';
import ContactDirectory from './ContactDirectory';
import CsvExport from './CsvExport';
import DuplicateCandidates from './DuplicateCandidates';
import CompanyMerge from './CompanyMerge';

type InitialTarget = {kind: 'client' | 'contact'; id: string};
function WorkspaceClients({workspace, onOpenDeal, onModalChange, initialTarget}: {workspace: Workspace; onOpenDeal: (workspaceId: string, dealId: string) => void; onModalChange: (open: boolean) => void; initialTarget?: InitialTarget}) {
  const base = `/workspaces/${workspace.id}`;
  const [clients, setClients] = useState<Client[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [tab, setTab] = useState<'clients' | 'contacts'>('clients');
  const [search, setSearch] = useState('');
  const [companyId, setCompanyId] = useState<string | null>(null);
  const [contact, setContact] = useState<{initialId?: string; initialClientId?: string} | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const targetOpened = useRef(false);
  const [duplicateTarget, setDuplicateTarget] = useState<InitialTarget | null>(null);
  const [mergePair, setMergePair] = useState<{sourceId: string; targetId: string; kind: 'client' | 'contact'} | null>(null);
  useEffect(() => {onModalChange(!!companyId || !!contact || !!mergePair);}, [companyId, contact, mergePair, onModalChange]);
  useEffect(() => () => onModalChange(false), [onModalChange]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    Promise.all([request<Client[]>(`${base}/clients`, 'GET', undefined, controller.signal), request<Contact[]>(`${base}/contacts`, 'GET', undefined, controller.signal)])
      .then(([c, people]) => {if (!controller.signal.aborted) {
        setClients(c); setContacts(people);
        if (initialTarget && !targetOpened.current) {
          targetOpened.current = true;
          const found = (initialTarget.kind === 'client' ? c : people).some(row => row.id === initialTarget.id);
          if (!found) setError('Объект из поиска больше недоступен');
          else if (initialTarget.kind === 'client') setCompanyId(initialTarget.id);
          else {setTab('contacts'); setContact({initialId: initialTarget.id});}
        }
      }})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, retry]);
  const refresh = async () => {
    const [c, people] = await Promise.all([request<Client[]>(`${base}/clients`), request<Contact[]>(`${base}/contacts`)]);
    setClients(c); setContacts(people);
  };
  const query = search.toLocaleLowerCase().trim();
  const companyRows = clients.filter(row => `${row.name} ${row.phone || ''} ${row.email || ''}`.toLocaleLowerCase().includes(query));
  const contactRows = contacts.filter(row => `${contactName(row)} ${row.phone || ''} ${row.email || ''}`.toLocaleLowerCase().includes(query));
  const canDelete = workspace.role !== 'MANAGER';
  return <>
    <div className="crmTools"><div role="tablist" aria-label="Каталог клиентов">
      <button role="tab" aria-selected={tab === 'clients'} onClick={() => setTab('clients')}>Компании</button>
      <button role="tab" aria-selected={tab === 'contacts'} onClick={() => setTab('contacts')}>Контакты</button></div>
      <input aria-label="Поиск клиентов" placeholder="Имя, компания, телефон, email" value={search} onChange={e => setSearch(e.target.value)}/>
      <button className="primary" disabled={loading || !!error} onClick={() => tab === 'clients' ? setCompanyId('new') : setContact({initialId: 'new'})}>{tab === 'clients' ? 'Новая компания' : 'Новый контакт'}</button>
      {canDelete && !loading && !error && <CsvExport key={tab} base={base} entity={tab}/>}
    </div>
    {loading ? <p role="status">Загрузка клиентов…</p> : !error && (tab === 'clients' ? <>
      {!companyRows.length ? <p className="muted">Компании не найдены.</p> : <div className="portalTableScroll"><table className="taskTable"><thead><tr><th>Компания</th><th>Телефон</th><th>Email</th><th>Контакты</th></tr></thead>
        <tbody>{companyRows.map(row => <tr key={row.id}><td><button className="linkLike" onClick={() => setCompanyId(row.id)}>{row.name}</button></td>
          <td>{row.phone || '—'}</td><td>{row.email || '—'}</td><td>{contacts.filter(person => person.client_ids.includes(row.id)).length}
            <button type="button" aria-label={`Проверить дубли: ${row.name}`} onClick={() => setDuplicateTarget({kind: 'client', id: row.id})}>Проверить дубли</button></td></tr>)}</tbody></table></div>}
    </> : <>
      {!contactRows.length ? <p className="muted">Контакты не найдены.</p> : <div className="portalTableScroll"><table className="taskTable"><thead><tr><th>Контакт</th><th>Телефон</th><th>Email</th><th>Компании</th></tr></thead>
        <tbody>{contactRows.map(row => <tr key={row.id}><td><button className="linkLike" onClick={() => setContact({initialId: row.id})}>{contactName(row)}</button></td>
          <td>{row.phone || '—'}</td><td>{row.email || '—'}</td><td>{clients.filter(company => row.client_ids.includes(company.id)).map(company => company.name).join(', ') || '—'}
            <button type="button" aria-label={`Проверить дубли: ${contactName(row)}`} onClick={() => setDuplicateTarget({kind: 'contact', id: row.id})}>Проверить дубли</button></td></tr>)}</tbody></table></div>}
    </>)}
    {error && <p role="alert" className="errorMessage">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
    {mergePair && <CompanyMerge key={`${mergePair.sourceId}:${mergePair.targetId}`} base={base} {...mergePair}
      onClose={() => setMergePair(null)} onMerged={async () => {await refresh();}}/>}
    {duplicateTarget && <DuplicateCandidates key={`${duplicateTarget.kind}:${duplicateTarget.id}`} base={base} kind={duplicateTarget.kind} objectId={duplicateTarget.id}
      onMerge={canDelete ? (sourceId, targetId) => {setDuplicateTarget(null); setMergePair({sourceId, targetId, kind: duplicateTarget.kind});} : undefined}
      onClose={() => setDuplicateTarget(null)} onOpen={async id => {
        // Re-read the exact candidate: it may be new or deleted since this directory loaded.
        if (duplicateTarget.kind === 'client') {
          const row = await request<Client>(`${base}/clients/${id}`);
          setClients(old => [...old.filter(item => item.id !== id), row]); setCompanyId(id);
        } else {
          const row = await request<Contact>(`${base}/contacts/${id}`);
          setContacts(old => [...old.filter(item => item.id !== id), row]); setContact({initialId: id});
        }
      }}/>}
    {companyId && <ClientDirectory key={companyId} clients={clients} contacts={contacts} base={base} canDelete={canDelete} initialId={companyId}
      onClose={() => setCompanyId(null)} onChanged={refresh} onOpenDeal={id => onOpenDeal(workspace.id, id)}
      onOpenContact={(id, clientId) => {setCompanyId(null); setContact({initialId: id, initialClientId: clientId});}}/>}
    {contact && <ContactDirectory key={contact.initialId || contact.initialClientId || 'new'} contacts={contacts} clients={clients} base={base} canDelete={canDelete}
      {...contact} onClose={() => setContact(null)} onChanged={refresh} onOpenDeal={id => onOpenDeal(workspace.id, id)}/>}
  </>;
}

export default function Clients({onOpenDeal, initialWorkspaceId = '', initialTarget}: {onOpenDeal: (workspaceId: string, dealId: string) => void; initialWorkspaceId?: string; initialTarget?: InitialTarget}) {
  const [spaces, setSpaces] = useState<Workspace[]>([]);
  const [id, setId] = useState(initialWorkspaceId);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal).then(rows => {
      if (!controller.signal.aborted) {setSpaces(rows); setId(old => rows.some(row => row.id === old) ? old : rows[0]?.id || '');}
    }).catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [retry]);
  const workspace = spaces.find(row => row.id === id);
  return <><header><div><h1>Клиенты</h1><p>Компании, контактные лица и связанные сделки</p></div></header>
    {loading ? <p role="status">Загрузка студий…</p> : <>
      <label>Рабочее пространство<select aria-label="Рабочее пространство" disabled={editing} value={id} onChange={e => setId(e.target.value)}>{spaces.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      {workspace ? <WorkspaceClients key={id} workspace={workspace} onOpenDeal={onOpenDeal} onModalChange={setEditing} initialTarget={id === initialWorkspaceId ? initialTarget : undefined}/> : <p>Создайте студию в настройках.</p>}
    </>}
    {error && <p role="alert">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
  </>;
}
