import {useEffect, useRef, useState} from 'react';
import {ApiError, errorText, newRequestKey, request} from './api';

type Kind = 'client' | 'contact';
type Field = 'name' | 'first_name' | 'last_name' | 'middle_name' | 'phone' | 'email' | 'website' | 'notes';
type Profile = {id: string} & Partial<Record<Field, string | null>>;
const fieldsByKind: Record<Kind, Field[]> = {client: ['name', 'phone', 'email', 'website', 'notes'],
  contact: ['first_name', 'last_name', 'middle_name', 'phone', 'email', 'website', 'notes']};
const fieldNames: Record<Field, string> = {name: 'Название', first_name: 'Имя', last_name: 'Фамилия', middle_name: 'Отчество', phone: 'Телефон', email: 'Email', website: 'Сайт', notes: 'Описание'};
const relationNames: Record<string, string> = {deals: 'Сделки', primary_deals: 'Основной контакт сделок', projects: 'Проекты', companies: 'Компании', tasks: 'Задачи', invoices: 'Счета', incoming_leads: 'Входящие заявки', contacts: 'Контакты'};
const profileName = (profile: Profile) => profile.name ?? [profile.last_name, profile.first_name, profile.middle_name].filter(Boolean).join(' ');
const resource = (kind: Kind) => kind === 'contact' ? 'contact-merges' : 'client-merges';
type Snapshot = {source: Profile; target: Profile; references: Record<string, {source: string[]; target: string[]}>};
type Preview = {source: Profile; target: Profile; preview_version: string; counts: Record<string, {source: number; target: number}>};
export type MergeReceipt = {id: string; request_key: string; source_id: string; target_id: string; actor_name: string;
  created_at: string; source_fields: Field[]; snapshot: Snapshot};
type Payload = {source_id: string; target_id: string; preview_version: string; source_fields: Field[]; confirmed: true; request_key: string};

export function MergeReceiptDetails({receipt, kind = 'client'}: {receipt: MergeReceipt; kind?: Kind}) {
  const fields = fieldsByKind[kind];
  return <details><summary>Квитанция слияния: {profileName(receipt.snapshot.source)} → {profileName(receipt.snapshot.target)}</summary>
    <p>{receipt.actor_name} · <time dateTime={receipt.created_at}>{new Date(receipt.created_at).toLocaleString()}</time></p>
    <p>Номер операции: <code>{receipt.id}</code>. Поля исходной: {receipt.source_fields.map(field => fieldNames[field]).join(', ') || 'не выбраны'}.</p>
    <p>Исходная запись: <code>{receipt.source_id}</code>. Основная: <code>{receipt.target_id}</code>.</p>
    <div className="portalTableScroll"><table className="taskTable"><caption>Исходные значения до слияния</caption><thead><tr><th>Поле</th><th>Исходная</th><th>Основная</th></tr></thead>
      <tbody>{fields.map(field => <tr key={field}><th scope="row">{fieldNames[field]}</th><td>{receipt.snapshot.source[field] || '—'}</td><td>{receipt.snapshot.target[field] || '—'}</td></tr>)}</tbody></table></div>
    <ul>{Object.entries(receipt.snapshot.references).map(([key, value]) => <li key={key}>{relationNames[key] || key}: перенесено {value.source.length}</li>)}</ul>
    <p>Автоматической отмены нет. Исходные данные сохранены в журнале; финансовые снимки не переписаны.</p>
  </details>;
}

export default function CompanyMerge({base, sourceId, targetId, onClose, onMerged, kind = 'client'}: {
  base: string; sourceId: string; targetId: string; onClose: () => void; onMerged: (receipt: MergeReceipt) => Promise<void>;
  kind?: Kind;
}) {
  const fields = fieldsByKind[kind];
  const title = kind === 'contact' ? 'Слияние контактов' : 'Слияние компаний';
  const noun = kind === 'contact' ? 'контакты' : 'компании';
  const success = kind === 'contact' ? 'Контакты объединены' : 'Компании объединены';
  const [preview, setPreview] = useState<Preview>();
  const [sourceFields, setSourceFields] = useState<Field[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [stale, setStale] = useState(false);
  const [receipt, setReceipt] = useState<MergeReceipt>();
  // A failed/uncertain response must retry the exact same operation, not create another one.
  const attempt = useRef<Payload | null>(null);
  const sending = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {heading.current?.focus();}, []);
  useEffect(() => {if (error) errorRef.current?.focus();}, [error]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setPreview(undefined); setStale(false);
    setConfirmed(false); setSourceFields([]); attempt.current = null;
    request<Preview>(`${base}/${resource(kind)}/preview`, 'POST', {source_id: sourceId, target_id: targetId}, controller.signal)
      .then(row => {if (!controller.signal.aborted) setPreview(row);})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, kind, sourceId, targetId, retry]);
  const synchronize = async (saved: MergeReceipt) => {
    try {await onMerged(saved);}
    catch(e) {setError(`Слияние уже выполнено. Не удалось обновить каталог: ${errorText(e)}`);}
  };
  const merge = async () => {
    if (sending.current || !preview || stale || !confirmed) return;
    sending.current = true; setBusy(true); setError('');
    attempt.current ??= {source_id: sourceId, target_id: targetId, preview_version: preview.preview_version,
      source_fields: sourceFields, confirmed: true, request_key: newRequestKey()};
    try {
      const saved = await request<MergeReceipt>(`${base}/${resource(kind)}`, 'POST', attempt.current);
      setReceipt(saved); await synchronize(saved);
    } catch(e) {
      setError(errorText(e));
      if (e instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(e.status)) {
        attempt.current = null; setStale(true); setConfirmed(false);
      }
    } finally {sending.current = false; setBusy(false);}
  };
  return <section className="card settingsCard companyMerge" aria-label={title} aria-busy={loading || busy}>
    <h2 ref={heading} tabIndex={-1}>{title}</h2>
    <button type="button" disabled={busy} onClick={onClose}>Закрыть слияние</button>
    {receipt ? <><p role="status">{success}. Исходные карточки сохранены в журнале.</p><MergeReceiptDetails receipt={receipt} kind={kind}/>
      {error && <button type="button" disabled={busy} onClick={async () => {setBusy(true); setError(''); await synchronize(receipt); setBusy(false);}}>Обновить каталог после слияния</button>}</> : <>
      <p>Это необратимое изменение каталога. Совпадение реквизитов само по себе не доказывает дубль.</p>
      {loading ? <p role="status">Загрузка предпросмотра…</p> : preview && <>
        <p><strong>Останется: {profileName(preview.target)}</strong> · <code>{preview.target.id}</code></p>
        <p>Будет убрана запись из каталога: {profileName(preview.source)} · <code>{preview.source.id}</code></p>
        <fieldset disabled={busy || !!attempt.current || stale}><legend>Какие значения сохранить</legend>
          <p>По умолчанию сохраняются значения основной записи. Для замены отметьте поля исходной.</p>
          {fields.map(field => <div className="companyMergeField" key={field}><label>
            <input type="checkbox" checked={sourceFields.includes(field)} onChange={e => setSourceFields(old => e.target.checked ? [...old, field] : old.filter(value => value !== field))}/>
            Взять из исходной: {fieldNames[field]}</label><p>Основная: {preview.target[field] || '—'}</p><p>Исходная: {preview.source[field] || '—'}</p></div>)}
          <ul>{Object.entries(preview.counts).map(([key, counts]) => <li key={key}>{relationNames[key] || key}: перенести {counts.source}, у основной {counts.target}</li>)}</ul>
          <p>{kind === 'contact' ? 'Объединяются компании, задачи, связи сделок и проектов. Основной контакт сделки сохраняет свою роль; третий основной контакт не меняется.' : 'Связи контактов объединяются. Сделки, проекты, счета и входящие заявки сохранят свои ID.'} Суммы, оплаты и реквизиты ранее созданных счетов не изменятся.</p>
          <label className="companyMergeConfirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>
            Я проверил {noun} и подтверждаю слияние в «{profileName(preview.target)}»</label>
        </fieldset>
        <button type="button" className="primary" disabled={!confirmed || busy || stale} onClick={() => void merge()}>{busy ? 'Объединение…' : attempt.current ? 'Повторить слияние' : 'Подтвердить слияние'}</button>
        {!!attempt.current && !busy && <p>При сетевой ошибке повторите тот же запрос: операция защищена от повторного выполнения.</p>}
      </>}
      <button type="button" disabled={loading || busy || !!attempt.current} onClick={() => setRetry(n => n + 1)}>Обновить предпросмотр</button>
    </>}
    {error && <p role="alert" ref={errorRef} tabIndex={-1}>{error}</p>}
  </section>;
}
