import {useEffect, useRef, useState} from 'react';
import {type Contact, type CustomFieldType, type Deal, type DealAttachment, type DealContactLink, type DealCustomField, type DealTag, type DealWatcher, type Member,
  contactName, errorText, newRequestKey, request} from './api';

type Props = {base: string; deal: Deal; members: Member[]; contacts: Contact[]; onDealChange: (deal: Deal) => void};

const fieldTypes: Record<CustomFieldType, string> = {TEXT: 'Текст', NUMBER: 'Число', DATE: 'Дата'};
const utmFields = [
  ['utm_source', 'utm_source'], ['utm_medium', 'utm_medium'], ['utm_campaign', 'utm_campaign'],
  ['utm_term', 'utm_term'], ['utm_content', 'utm_content'], ['http_referrer', 'http_referrer'],
] as const;

export default function DealDetails({base, deal, members, contacts, onDealChange}: Props) {
  const path = `${base}/deals/${deal.id}`;
  const [tags, setTags] = useState<DealTag[]>([]);
  const [watchers, setWatchers] = useState<DealWatcher[]>([]);
  const [links, setLinks] = useState<DealContactLink[]>([]);
  const [attachments, setAttachments] = useState<DealAttachment[]>([]);
  const [custom, setCustom] = useState<DealCustomField[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [reload, setReload] = useState(0);
  const [tagName, setTagName] = useState('');
  const [watcherId, setWatcherId] = useState('');
  const [contactId, setContactId] = useState('');
  const [file, setFile] = useState<File>();
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadKey = useRef(newRequestKey());
  const saving = useRef(false);
  const [utm, setUtm] = useState({utm_source: deal.utm_source || '', utm_medium: deal.utm_medium || '',
    utm_campaign: deal.utm_campaign || '', utm_term: deal.utm_term || '', utm_content: deal.utm_content || '',
    http_referrer: deal.http_referrer || ''});

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setLoadFailed(false);
    const get = <T,>(suffix: string) => request<T>(`${path}${suffix}`, 'GET', undefined, controller.signal);
    Promise.all([get<DealTag[]>('/tags'), get<DealWatcher[]>('/watchers'), get<DealContactLink[]>('/contacts'),
      get<DealAttachment[]>('/attachments'), get<{values: DealCustomField[]}>('/custom-fields')])
      .then(([nextTags, nextWatchers, nextLinks, nextAttachments, nextCustom]) => {
        if (controller.signal.aborted) return;
        setTags(nextTags); setWatchers(nextWatchers); setLinks(nextLinks); setAttachments(nextAttachments);
        setCustom(nextCustom.values); setLoading(false);
      })
      .catch(e => {if (!controller.signal.aborted) {setError(errorText(e)); setLoadFailed(true); setLoading(false);}});
    return () => controller.abort();
  }, [path, reload]);

  useEffect(() => {
    setUtm({utm_source: deal.utm_source || '', utm_medium: deal.utm_medium || '', utm_campaign: deal.utm_campaign || '',
      utm_term: deal.utm_term || '', utm_content: deal.utm_content || '', http_referrer: deal.http_referrer || ''});
  }, [deal.id, deal.utm_source, deal.utm_medium, deal.utm_campaign, deal.utm_term, deal.utm_content, deal.http_referrer]);

  const run = async (operation: () => Promise<void>, done = '') => {
    if (saving.current) return;
    saving.current = true;
    setBusy(true); setError(''); setStatus('');
    try {await operation(); if (done) setStatus(done);} catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  const addTag = () => {
    if (!tagName.trim()) return;
    void run(async () => {
      const row = await request<DealTag>(`${path}/tags`, 'POST', {name: tagName.trim()});
      setTags(previous => previous.some(item => item.id === row.id) ? previous : [...previous, row].sort((a, b) => a.name.localeCompare(b.name)));
      setTagName('');
    }, 'Тег добавлен');
  };
  const removeTag = (row: DealTag) => void run(async () => {
    await request(`${path}/tags/${row.id}`, 'DELETE');
    setTags(previous => previous.filter(item => item.id !== row.id));
  }, 'Тег убран');
  const addWatcher = () => {
    if (!watcherId) return;
    void run(async () => {
      const row = await request<DealWatcher>(`${path}/watchers`, 'POST', {user_id: watcherId});
      setWatchers(previous => [...previous, row]);
      setWatcherId('');
    }, 'Наблюдатель добавлен');
  };
  const removeWatcher = (row: DealWatcher) => void run(async () => {
    await request(`${path}/watchers/${row.user_id}`, 'DELETE');
    setWatchers(previous => previous.filter(item => item.user_id !== row.user_id));
  }, 'Наблюдатель убран');
  const addContact = () => {
    if (!contactId) return;
    void run(async () => {
      const row = await request<DealContactLink>(`${path}/contacts`, 'POST', {contact_id: contactId});
      setLinks(previous => [...previous, row]);
      onDealChange(await request<Deal>(path));
      setContactId('');
    }, 'Контакт связан со сделкой');
  };
  const makePrimary = (row: DealContactLink) => void run(async () => {
    const updated = await request<DealContactLink>(`${path}/contacts/${row.contact_id}`, 'PATCH', {is_primary: true});
    setLinks(previous => previous.map(item => item.contact_id === updated.contact_id ? updated : {...item, is_primary: false}));
    onDealChange(await request<Deal>(path));
  }, 'Основной контакт обновлён');
  const removeLink = (row: DealContactLink) => void run(async () => {
    await request(`${path}/contacts/${row.contact_id}`, 'DELETE');
    const next = await request<DealContactLink[]>(`${path}/contacts`);
    setLinks(next);
    onDealChange(await request<Deal>(path));
  }, 'Контакт отвязан от сделки');
  const addAttachment = () => {
    if (!file) return;
    void run(async () => {
      const row = await request<DealAttachment>(`${path}/attachments/upload?filename=${encodeURIComponent(file.name)}&upload_key=${uploadKey.current}`, 'POST', file);
      setAttachments(previous => [row, ...previous.filter(item => item.id !== row.id)]);
      setFile(undefined); if (fileInput.current) fileInput.current.value = '';
    }, 'Вложение добавлено');
  };
  const removeAttachment = (row: DealAttachment) => void run(async () => {
    await request(`${path}/attachments/${row.id}`, 'DELETE');
    setAttachments(previous => previous.filter(item => item.id !== row.id));
  }, 'Вложение удалено');
  const saveUtm = () => void run(async () => {
    const updated = await request<Deal>(path, 'PATCH', {...utm});
    onDealChange(updated);
  }, 'UTM-метки сохранены');
  const saveCustom = () => void run(async () => {
    const values = custom.filter(field => field.key.trim()).map(field => ({key: field.key.trim(), type: field.type, value: field.value}));
    const saved = await request<{values: DealCustomField[]}>(`${path}/custom-fields`, 'PUT', {values});
    setCustom(saved.values);
  }, 'Пользовательские поля сохранены');

  const freeMembers = members.filter(member => !watchers.some(row => row.user_id === member.user_id));
  const freeContacts = contacts.filter(contact => !links.some(row => row.contact_id === contact.id));

  return <section className="drawerSection dealDetails">
    <h3>Дополнительно</h3>
    {loading ? <p role="status">Загрузка дополнительных полей…</p> :
      loadFailed
        ? <p role="alert">{error} <button type="button" onClick={() => setReload(n => n + 1)}>Повторить</button></p> : <>
        <div className="dealDetailBlock"><h4>Теги</h4>
          {tags.length ? <ul className="tagList" aria-label="Теги сделки">{tags.map(row => <li key={row.id}>
            <span className="tagChip">{row.name}</span>
            <button type="button" disabled={busy} aria-label={`Убрать тег ${row.name}`} onClick={() => removeTag(row)}>×</button>
          </li>)}</ul> : <p className="muted">Тегов пока нет.</p>}
          <div className="inlineForm"><input aria-label="Новый тег" maxLength={50} value={tagName} onChange={e => setTagName(e.target.value)}/>
            <button type="button" disabled={busy || !tagName.trim()} onClick={addTag}>Добавить тег</button></div>
        </div>
        <div className="dealDetailBlock"><h4>Наблюдатели</h4>
          {watchers.length ? <ul className="plainList" aria-label="Наблюдатели сделки">{watchers.map(row => <li key={row.user_id}>
            {[row.first_name, row.last_name].filter(Boolean).join(' ')} · {row.email}
            <button type="button" disabled={busy} aria-label={`Убрать наблюдателя ${row.first_name}`} onClick={() => removeWatcher(row)}>Убрать</button>
          </li>)}</ul> : <p className="muted">Наблюдателей нет.</p>}
          <div className="inlineForm"><select aria-label="Новый наблюдатель" value={watcherId} onChange={e => setWatcherId(e.target.value)}>
            <option value="">Выберите участника</option>{freeMembers.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}
          </select><button type="button" disabled={busy || !watcherId} onClick={addWatcher}>Добавить наблюдателя</button></div>
        </div>
        <div className="dealDetailBlock"><h4>Контакты сделки</h4>
          {links.length ? <ul className="plainList" aria-label="Контакты сделки">{links.map(row => <li key={row.contact_id}>
            <span>{row.last_name || ''} {row.first_name} {row.middle_name || ''}</span>
            {row.phone && <span className="muted"> · {row.phone}</span>}
            {row.is_primary ? <strong className="primaryBadge">Основной</strong> :
              <button type="button" disabled={busy} onClick={() => makePrimary(row)}>Сделать основным</button>}
            <button type="button" disabled={busy} aria-label={`Отвязать контакт ${row.first_name}`} onClick={() => removeLink(row)}>Отвязать</button>
          </li>)}</ul> : <p className="muted">Дополнительных контактов нет.</p>}
          <div className="inlineForm"><select aria-label="Новый контакт сделки" value={contactId} onChange={e => setContactId(e.target.value)}>
            <option value="">Выберите контакт</option>{freeContacts.map(contact => <option key={contact.id} value={contact.id}>{contactName(contact)}</option>)}
          </select><button type="button" disabled={busy || !contactId} onClick={addContact}>Связать контакт</button></div>
        </div>
        <div className="dealDetailBlock"><h4>Вложения</h4>
          <p className="muted">Файлы сохраняются в базе студии. По умолчанию до 10 МиБ на файл и 100 МиБ на студию. Перед открытием проверяйте файлы антивирусом.</p>
          {attachments.length ? <ul className="plainList" aria-label="Вложения сделки">{attachments.map(row => <li key={row.id}>
            <span>{row.filename}</span><span className="muted"> · {row.content_type} · {row.size_bytes} Б · {row.uploaded_by_name}</span>
            {row.has_content ? <a href={`/api/v1${path}/attachments/${row.id}/download`} download={row.filename}>Скачать {row.filename}</a> : <span className="muted">Только метаданные — файл не загружен</span>}
            <button type="button" disabled={busy} aria-label={`Удалить вложение ${row.filename}`} onClick={() => removeAttachment(row)}>Удалить</button>
          </li>)}</ul> : <p className="muted">Вложений нет.</p>}
          <label>Файл<input ref={fileInput} type="file" disabled={busy} onChange={e => {setFile(e.target.files?.[0]); uploadKey.current = newRequestKey();}}/></label>
          <button type="button" disabled={busy || !file} onClick={addAttachment}>{busy ? 'Сохранение…' : 'Загрузить файл'}</button>
        </div>
        <div className="dealDetailBlock"><h4>UTM-метки</h4>
          <div className="utmGrid">{utmFields.map(([key, label]) => <label key={key}>{label}
            <input maxLength={key === 'http_referrer' ? 2048 : 255} value={utm[key]} onChange={e => setUtm({...utm, [key]: e.target.value})}/>
          </label>)}</div>
          <button type="button" disabled={busy} onClick={saveUtm}>Сохранить UTM-метки</button>
        </div>
        <div className="dealDetailBlock"><h4>Пользовательские поля</h4>
          {custom.length ? <ul className="plainList">{custom.map((field, index) => <li key={index}>
            <input aria-label={`Ключ поля ${index + 1}`} maxLength={100} value={field.key} onChange={e => setCustom(previous => previous.map((item, position) => position === index ? {...item, key: e.target.value} : item))}/>
            <select aria-label={`Тип поля ${index + 1}`} value={field.type} onChange={e => setCustom(previous => previous.map((item, position) => position === index ? {...item, type: e.target.value as CustomFieldType} : item))}>
              {(Object.keys(fieldTypes) as CustomFieldType[]).map(type => <option key={type} value={type}>{fieldTypes[type]}</option>)}
            </select>
            <input aria-label={`Значение поля ${index + 1}`} maxLength={10000} value={field.value} onChange={e => setCustom(previous => previous.map((item, position) => position === index ? {...item, value: e.target.value} : item))}/>
            <button type="button" disabled={busy} onClick={() => setCustom(previous => previous.filter((_, position) => position !== index))}>Убрать</button>
          </li>)}</ul> : <p className="muted">Пользовательских полей нет.</p>}
          <div className="inlineForm"><button type="button" disabled={busy} onClick={() => setCustom(previous => [...previous, {key: '', type: 'TEXT', value: ''}])}>Добавить поле</button>
            <button type="button" disabled={busy} onClick={saveCustom}>Сохранить поля</button></div>
        </div>
      </>}
    {error && !loadFailed && <p role="alert" className="errorMessage">{error}</p>}
    {status && <p role="status">{status}</p>}
  </section>;
}
