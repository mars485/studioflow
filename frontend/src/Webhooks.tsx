import {useEffect, useRef, useState} from 'react';
import {errorText, request} from './api';

type Subscription = {id: string; destination: string; events: string[]; enabled: boolean};
type Delivery = {id: string; event_type: string; event_id: string; status: string; attempts: number; last_result: string | null; next_attempt_at: string};
const events = {'deal.created': 'Создание сделки', 'deal.stage_changed': 'Смена стадии сделки', 'task.completed': 'Завершение задачи'};

export default function Webhooks({base}: {base: string}) {
  const [destinations, setDestinations] = useState<string[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [label, setLabel] = useState('');
  const [selected, setSelected] = useState<string[]>(['deal.created']);
  const [secret, setSecret] = useState('');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    Promise.all([request<{destinations: string[]}>(`${base}/webhooks/destinations`, 'GET', undefined, controller.signal),
      request<Subscription[]>(`${base}/webhooks`, 'GET', undefined, controller.signal),
      request<Delivery[]>(`${base}/webhooks/deliveries/list?offset=${offset}&limit=50`, 'GET', undefined, controller.signal)])
      .then(([config, subs, rows]) => {if (!controller.signal.aborted) {setDestinations(config.destinations); setSubscriptions(subs); setDeliveries(rows);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, offset, retry]);
  const run = async (operation: () => Promise<unknown>) => {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {await operation(); setRetry(n => n + 1);} catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  return <section className="card settingsCard" aria-label="Исходящие webhooks"><h2>Исходящие webhooks</h2>
    <p className="muted">События содержат только идентификаторы. Отправляет отдельный worker, не браузер. Нужны разрешённые оператором HTTPS-адреса и ключ подписей. n8n автоматически не подключён.</p>
    {secret && <><label>Ключ подписи webhook<textarea readOnly value={secret}/></label><p>Сохраните ключ сейчас и проверяйте HMAC на стороне получателя; повторно ключ не показывается.</p>
      <button type="button" onClick={() => setSecret('')}>Скрыть ключ webhook</button></>}
    {loading ? <p role="status">Загрузка webhooks…</p> : <>
      {!destinations.length ? <p>Исходящие отправки не настроены оператором.</p> : <form onSubmit={e => {e.preventDefault(); void run(async () => {
        const row = await request<Subscription & {signing_secret: string}>(`${base}/webhooks`, 'POST', {destination: label, events: selected});
        setSecret(row.signing_secret); setLabel('');
      });}}><fieldset disabled={busy}>
        <label>Назначение webhook<select required value={label} onChange={e => setLabel(e.target.value)}><option value="">Выберите назначение</option>{destinations.map(name => <option key={name}>{name}</option>)}</select></label>
        {Object.entries(events).map(([key, title]) => <label key={key}><input type="checkbox" checked={selected.includes(key)} onChange={e => setSelected(old => e.target.checked ? [...old, key] : old.filter(value => value !== key))}/>{title}</label>)}
        <button disabled={!label || !selected.length}>Создать подписку webhook</button>
      </fieldset></form>}
      <ul className="plainList">{subscriptions.map(row => <li key={row.id}>{row.destination} · {row.enabled ? 'Включена' : 'Выключена'} · {row.events.join(', ')}
        <button disabled={busy} type="button" onClick={() => void run(() => request(`${base}/webhooks/${row.id}`, 'PATCH', {enabled: !row.enabled}))}>{row.enabled ? 'Отключить' : 'Включить'} webhook {row.destination}</button>
        {!row.enabled && <button disabled={busy} type="button" onClick={() => {
          if (window.confirm('Удалить отключённую подписку и её журнал доставки? CRM-данные сохранятся. Для нового ключа затем создайте подписку заново.'))
            void run(async () => {await request(`${base}/webhooks/${row.id}`, 'DELETE'); setSecret('');});
        }}>Удалить webhook {row.destination}</button>}
      </li>)}</ul>
      <h3>Журнал доставки</h3>{!deliveries.length ? <p>Доставок пока нет.</p> : <ul className="plainList">{deliveries.map(row => <li key={row.id}>
        {row.event_type} · {row.status} · попыток: {row.attempts} · {row.last_result || 'Ожидает worker'} · {row.event_id}
        {row.status === 'PENDING' && <span>Не раньше {new Date(row.next_attempt_at).toLocaleString('ru-RU')}</span>}
        {row.status === 'FAILED' && <button disabled={busy} type="button" onClick={() => void run(() => request(`${base}/webhooks/deliveries/${row.id}/retry`, 'POST'))}>Повторить доставку {row.event_id}</button>}
      </li>)}</ul>}
      <div className="inlineForm"><button type="button" disabled={busy || !offset} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие доставки</button>
        <button type="button" disabled={busy || deliveries.length < 50} onClick={() => setOffset(n => n + 50)}>Следующие доставки</button></div>
    </>}
    <button type="button" disabled={busy || loading} onClick={() => setRetry(n => n + 1)}>Обновить webhooks</button>
    {error && <p role="alert">{error} <button type="button" disabled={busy} onClick={() => setRetry(n => n + 1)}>Повторить загрузку webhooks</button></p>}
  </section>;
}
