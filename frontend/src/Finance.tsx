import {useEffect, useRef, useState, type FormEvent} from 'react';
import {errorText, loadDeals, money, newRequestKey, request, type Client, type Deal, type Member, type Project, type Workspace} from './api';
import {type Act, type Invoice, type Organization, type Payment, invoiceStatusNames, today} from './financeTypes';

function InvoiceCard({base, invoice, onChanged, onClose}: {base: string; invoice: Invoice; onChanged: (row: Invoice) => void; onClose: () => void}) {
  const path = `${base}/invoices/${invoice.id}`;
  const [payments, setPayments] = useState<Payment[]>([]);
  const [acts, setActs] = useState<Act[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const paymentKey = useRef(newRequestKey());
  const [amount, setAmount] = useState('');
  const [paidOn, setPaidOn] = useState(today());
  const [comment, setComment] = useState('');
  const [actDate, setActDate] = useState(today());
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    Promise.all([request<Payment[]>(`${path}/payments`, 'GET', undefined, controller.signal),
      request<Act[]>(`${path}/acts`, 'GET', undefined, controller.signal)])
      .then(([p, a]) => {if (!controller.signal.aborted) {setPayments(p); setActs(a);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [path, retry]);
  const run = async (operation: () => Promise<unknown>) => {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {await operation(); onChanged(await request<Invoice>(path)); setRetry(n => n + 1);}
    catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  const pay = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      await request(`${path}/payments`, 'POST', {request_key: paymentKey.current, amount, paid_on: paidOn, comment: comment || null});
      paymentKey.current = newRequestKey(); setAmount(''); setComment('');
    });
  };
  return <div className="drawerBackdrop"><aside className="drawer financeDrawer" role="dialog" aria-modal="true" aria-label="Карточка счёта">
    <div className="drawerHead"><h2>Счёт №{invoice.number}</h2><button disabled={busy} onClick={onClose}>Закрыть</button></div>
    <p role="status" aria-label="Статус оплаты">{invoiceStatusNames[invoice.status]} · Оплачено: {money(invoice.paid_amount, invoice.currency)} · Остаток: {money(invoice.remaining_amount, invoice.currency)}</p>
    <div className="financeActions">
      {invoice.state === 'DRAFT' && <button disabled={busy} onClick={() => void run(() => request(path, 'PATCH', {state: 'ISSUED'}))}>Выставить счёт</button>}
      {invoice.state === 'ISSUED' && !invoice.sent_at && <button disabled={busy} onClick={() => void run(() => request(`${path}/sent`, 'POST'))}>Отметить отправленным</button>}
      {invoice.state !== 'CANCELLED' && invoice.paid_amount === '0.00' && !acts.length && <button disabled={busy || loading} onClick={() => void run(() => request(path, 'PATCH', {state: 'CANCELLED'}))}>Отменить счёт</button>}
      <button onClick={() => window.print()}>Печать / PDF</button>
    </div>
    <p className="muted">{invoice.sent_at ? `Отмечен отправленным: ${new Date(invoice.sent_at).toLocaleString('ru-RU')}` : 'Не отмечен отправленным'}. Почта из приложения не отправляется.</p>
    <section className="invoicePrint" aria-label="Печатная форма счёта">
      <h2>StudioFlow · Счёт №{invoice.number} от {invoice.issued_on}</h2>
      <p><strong>Исполнитель:</strong> {invoice.seller.name} · ИНН {invoice.seller.tax_id || 'не указан'} · КПП {invoice.seller.tax_branch || '—'}</p>
      <p>{invoice.seller.address}</p><p>Банк: {invoice.seller.bank} · БИК: {invoice.seller.bank_code} · Счёт: {invoice.seller.bank_account}</p>
      <p><strong>Заказчик:</strong> {invoice.buyer.name} · ИНН {invoice.buyer.tax_id || 'не указан'} · {invoice.buyer.address}</p>
      <table><thead><tr><th>Услуга</th><th>Сумма</th></tr></thead><tbody><tr><td>{invoice.description}</td><td>{money(invoice.amount, invoice.currency)}</td></tr></tbody></table>
      <p><strong>Итого: {money(invoice.amount, invoice.currency)}</strong></p>
      <p className="muted">Упрощённая форма. Налоговый расчёт и ЭДО не выполняются. {invoiceStatusNames[invoice.status]}.</p>
    </section>
    {loading ? <p role="status">Загрузка оплат и актов…</p> : <>
      <section className="drawerSection"><h3>Платежи</h3>
        {!payments.length ? <p className="muted">Оплат пока нет.</p> : <ul>{payments.map(row => <li key={row.id}>{row.paid_on} · {money(row.amount, invoice.currency)} · {row.comment}</li>)}</ul>}
        {invoice.state === 'ISSUED' && invoice.status !== 'PAID' && <form onSubmit={pay}><fieldset disabled={busy}>
          <label>Сумма платежа<input required inputMode="decimal" type="number" step="0.01" min="0.01" max={invoice.remaining_amount} value={amount} onChange={e => setAmount(e.target.value)}/></label>
          <label>Дата платежа<input required type="date" value={paidOn} onChange={e => setPaidOn(e.target.value)}/></label>
          <label>Комментарий платежа<input maxLength={2000} value={comment} onChange={e => setComment(e.target.value)}/></label>
          <button>Добавить платёж</button>
        </fieldset></form>}
      </section>
      <section className="drawerSection"><h3>Акты</h3>
        {!acts.length ? <p className="muted">Актов пока нет.</p> : <ul>{acts.map(row => <li key={row.id}>Акт №{row.number} от {row.issued_on} · {row.status === 'SIGNED' ? 'Подписан' : 'Черновик'}
          {row.status !== 'SIGNED' && <button disabled={busy} onClick={() => void run(() => request(`${base}/acts/${row.id}/sign`, 'POST'))}>Отметить подписанным №{row.number}</button>}</li>)}</ul>}
        {invoice.state === 'ISSUED' && <form onSubmit={e => {e.preventDefault(); void run(() => request(`${path}/acts`, 'POST', {issued_on: actDate}));}}><fieldset disabled={busy}>
          <label>Дата акта<input type="date" required value={actDate} onChange={e => setActDate(e.target.value)}/></label><button>Создать акт</button>
        </fieldset></form>}
        <p className="muted">Подписание — учётная отметка, не электронная подпись.</p>
      </section>
    </>}
    {error && <p role="alert" className="errorMessage">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить загрузку</button></p>}
  </aside></div>;
}

function FinanceWorkspace({workspace}: {workspace: Workspace}) {
  const base = `/workspaces/${workspace.id}`;
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [mode, setMode] = useState<'invoice' | 'organization' | null>(null);
  const [search, setSearch] = useState('');
  const [orgDraft, setOrgDraft] = useState({name: '', tax_id: '', tax_branch: '', address: '', bank: '', bank_account: '', bank_code: ''});
  const [orgId, setOrgId] = useState('');
  const [draft, setDraft] = useState({organization_id: '', client_id: '', deal_id: '', project_id: '', manager_user_id: '',
    issued_on: today(), amount: '', description: '', buyer_tax_id: '', buyer_address: ''});
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    const listInvoices = async () => {
      const result: Invoice[] = [];
      for (let offset = 0; ; offset += 500) {
        const page = await request<Invoice[]>(`${base}/invoices?limit=500&offset=${offset}`, 'GET', undefined, controller.signal);
        result.push(...page); if (page.length < 500) return result;
      }
    };
    Promise.all([request<Organization[]>(`${base}/organizations`, 'GET', undefined, controller.signal), listInvoices(),
      request<Client[]>(`${base}/clients`, 'GET', undefined, controller.signal), loadDeals(base, controller.signal),
      request<Project[]>(`${base}/projects?status=all`, 'GET', undefined, controller.signal),
      request<Member[]>(`${base}/members`, 'GET', undefined, controller.signal)])
      .then(([o, i, c, d, p, m]) => {if (!controller.signal.aborted) {setOrganizations(o); setInvoices(i); setClients(c); setDeals(d); setProjects(p); setMembers(m);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, retry]);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {
      if (mode === 'organization') {
        const payload = Object.fromEntries(['name', 'tax_id', 'tax_branch', 'address', 'bank', 'bank_account', 'bank_code'].map(key => [key, orgDraft[key as keyof typeof orgDraft]]));
        const row = await request<Organization>(`${base}/organizations${orgId ? '/' + orgId : ''}`, orgId ? 'PUT' : 'POST', payload);
        setOrganizations(rows => [...rows.filter(o => o.id !== row.id), row]);
      } else {
        const row = await request<Invoice>(`${base}/invoices`, 'POST', {...draft, deal_id: draft.deal_id || null,
          project_id: draft.project_id || null, manager_user_id: draft.manager_user_id || null});
        setInvoices(rows => [row, ...rows]); setSelectedId(row.id);
      }
      setMode(null);
    } catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  const selected = invoices.find(row => row.id === selectedId);
  return <>
    <div className="financeActions"><button className="primary" disabled={loading || busy || !organizations.length || !clients.length} onClick={() => {setError(''); setDraft({organization_id: organizations[0]?.id || '', client_id: '', deal_id: '', project_id: '', manager_user_id: '', issued_on: today(), amount: '', description: '', buyer_tax_id: '', buyer_address: ''}); setMode('invoice');}}>Новый счёт</button>
      <button disabled={loading || busy} onClick={() => {setOrgId(''); setOrgDraft({name: '', tax_id: '', tax_branch: '', address: '', bank: '', bank_account: '', bank_code: ''}); setMode('organization');}}>Добавить организацию</button>
      <input aria-label="Поиск счетов" placeholder="Номер или клиент" value={search} onChange={e => setSearch(e.target.value)}/>
    </div>
    {loading ? <p role="status">Загрузка финансов…</p> : <>
      {!organizations.length && <p>Сначала добавьте реквизиты организации. Клиенты создаются в CRM.</p>}
      <details><summary>Организации ({organizations.length})</summary>{organizations.map(row => <p key={row.id}>{row.name} · {row.tax_id} <button onClick={() => {setOrgId(row.id); setOrgDraft(row); setMode('organization');}}>Изменить реквизиты {row.name}</button></p>)}</details>
      {!invoices.length ? <p className="muted">Счетов пока нет.</p> : <div className="portalTableScroll"><table className="financeTable"><thead><tr><th>№ / Дата</th><th>Контрагент</th><th>Сумма</th><th>Статус</th><th>Проект / Сделка</th></tr></thead>
        <tbody>{invoices.filter(row => `${row.number} ${row.buyer.name}`.toLowerCase().includes(search.toLowerCase())).map(row => <tr key={row.id}>
          <td><button onClick={() => setSelectedId(row.id)}>Счёт №{row.number}</button><br/>{row.issued_on}</td><td>{row.buyer.name}</td><td>{money(row.amount, row.currency)}</td>
          <td>{invoiceStatusNames[row.status]}</td><td>{projects.find(p => p.id === row.project_id)?.title || '—'} / {deals.find(d => d.id === row.deal_id)?.title || '—'}</td>
        </tr>)}</tbody></table></div>}
    </>}
    {mode && <div className="modalBackdrop"><form className="dealModal" role="dialog" aria-modal="true" aria-label={mode === 'invoice' ? 'Новый счёт' : 'Реквизиты организации'} onSubmit={e => void submit(e)}>
      <div className="drawerHead"><h2>{mode === 'invoice' ? 'Новый счёт' : 'Реквизиты организации'}</h2><button type="button" disabled={busy} onClick={() => setMode(null)}>Закрыть</button></div>
      <fieldset disabled={busy}>
        {mode === 'organization' ? (Object.entries({name: 'Название организации', tax_id: 'ИНН организации', tax_branch: 'КПП', address: 'Адрес организации', bank: 'Банк', bank_account: 'Расчётный счёт', bank_code: 'БИК'}) as [keyof typeof orgDraft, string][]).map(([key, label]) =>
          <label key={key}>{label}<input required={key === 'name'} maxLength={key === 'address' ? 1000 : key === 'tax_id' ? 12 : key === 'tax_branch' ? 9 : key === 'bank_account' ? 34 : key === 'bank_code' ? 11 : 255} value={orgDraft[key]} onChange={e => setOrgDraft({...orgDraft, [key]: e.target.value})}/></label>) : <>
          <label>Организация<select required value={draft.organization_id} onChange={e => setDraft({...draft, organization_id: e.target.value})}>{organizations.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label>Сделка счёта<select value={draft.deal_id} onChange={e => {const deal = deals.find(row => row.id === e.target.value); setDraft({...draft, deal_id: e.target.value, project_id: '', ...(deal ? {client_id: deal.client_id, amount: deal.amount, description: deal.title} : {})});}}><option value="">Без сделки</option>{deals.map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select></label>
          <label>Клиент счёта<select required value={draft.client_id} onChange={e => setDraft({...draft, client_id: e.target.value, deal_id: '', project_id: ''})}><option value="">Выберите клиента</option>{clients.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label>Проект счёта<select value={draft.project_id} onChange={e => setDraft({...draft, project_id: e.target.value})}><option value="">Без проекта</option>{projects.filter(row => row.client_id === draft.client_id).map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select></label>
          <label>Менеджер счёта<select value={draft.manager_user_id} onChange={e => setDraft({...draft, manager_user_id: e.target.value})}><option value="">Не назначен</option>{members.map(row => <option key={row.user_id} value={row.user_id}>{row.first_name}</option>)}</select></label>
          <label>Дата счёта<input required type="date" value={draft.issued_on} onChange={e => setDraft({...draft, issued_on: e.target.value})}/></label>
          <label>Сумма счёта<input required type="number" min="0.01" step="0.01" max="999999999999.99" value={draft.amount} onChange={e => setDraft({...draft, amount: e.target.value})}/></label>
          <label>Назначение счёта<textarea required maxLength={10000} value={draft.description} onChange={e => setDraft({...draft, description: e.target.value})}/></label>
          <label>ИНН заказчика<input maxLength={12} value={draft.buyer_tax_id} onChange={e => setDraft({...draft, buyer_tax_id: e.target.value})}/></label>
          <label>Адрес заказчика<input maxLength={1000} value={draft.buyer_address} onChange={e => setDraft({...draft, buyer_address: e.target.value})}/></label>
        </>}
        {error && <p role="alert" className="errorMessage">{error}</p>}
        <button className="primary">{busy ? 'Сохранение…' : mode === 'invoice' ? 'Создать счёт' : 'Сохранить организацию'}</button>
      </fieldset>
    </form></div>}
    {!mode && error && <p role="alert" className="errorMessage">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
    {selected && <InvoiceCard key={selected.id} base={base} invoice={selected} onClose={() => setSelectedId('')} onChanged={row => setInvoices(rows => rows.map(old => old.id === row.id ? row : old))}/>}
  </>;
}

export default function Finance() {
  const [spaces, setSpaces] = useState<Workspace[]>([]);
  const [id, setId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal).then(rows => {
      if (!controller.signal.aborted) {setSpaces(rows); setId(old => rows.some(w => w.id === old) ? old : rows[0]?.id || '');}
    }).catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [retry]);
  const workspace = spaces.find(row => row.id === id);
  return <><header><div><h1>Финансы</h1><p>Счета, поступления и акты · без бухгалтерского ядра</p></div></header>
    {loading ? <p role="status">Загрузка студий…</p> : <>
      <label>Рабочее пространство<select value={id} onChange={e => setId(e.target.value)}>{spaces.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      {!workspace ? <p>Создайте студию в настройках.</p> : workspace.role === 'MANAGER' ? <p role="alert">Финансы доступны только владельцу и администратору.</p> : <FinanceWorkspace key={id} workspace={workspace}/>}
    </>}
    {error && <p role="alert">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
  </>;
}
