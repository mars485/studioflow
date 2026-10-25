import {useEffect, useRef, useState, type FormEvent} from 'react';
import {errorText, request, type Pipeline, type Workspace} from './api';
import Webhooks from './Webhooks';

type Token = {id: string; name: string; hint: string; pipeline_id: string | null; expires_at: string; revoked_at: string | null;
  created_at: string; last_used_at: string | null; scope: 'leads:create'};
type Receipt = {id: string; request_key: string; client_id: string | null; deal_id: string | null; created_at: string; deal_title: string | null};

function WorkspaceIntegrations({workspaceId, onOpenDeal}: {workspaceId: string; onOpenDeal: (workspaceId: string, dealId: string) => void}) {
  const base = `/workspaces/${workspaceId}`;
  const [tokens, setTokens] = useState<Token[]>([]);
  const [leads, setLeads] = useState<Receipt[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [tokenOffset, setTokenOffset] = useState(0);
  const [leadOffset, setLeadOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [name, setName] = useState('');
  const [pipelineId, setPipelineId] = useState('');
  const [days, setDays] = useState('90');
  const [secret, setSecret] = useState('');
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setTokens([]); setLeads([]);
    Promise.all([request<Token[]>(`${base}/integration-tokens?limit=50&offset=${tokenOffset}`, 'GET', undefined, controller.signal),
      request<Receipt[]>(`${base}/integration-leads?limit=50&offset=${leadOffset}`, 'GET', undefined, controller.signal),
      request<Pipeline[]>(`${base}/pipelines`, 'GET', undefined, controller.signal)])
      .then(([t, l, p]) => {if (!controller.signal.aborted) {setTokens(t); setLeads(l); setPipelines(p);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, tokenOffset, leadOffset, retry]);
  const run = async (operation: () => Promise<void>) => {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {await operation(); setRetry(n => n + 1);} catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  const create = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const row = await request<Token & {token: string}>(`${base}/integration-tokens`, 'POST', {name: name.trim(), pipeline_id: pipelineId || null, expires_days: Number(days)});
      setSecret(row.token); setName(''); setTokenOffset(0);
    });
  };
  return <>
    <p className="muted">Только сервер сайта или n8n. Не помещайте токен в браузерный JavaScript, URL, Git и публичные логи. Внешние системы автоматически не подключаются. Права автора и доступность воронки проверяются при каждой заявке.</p>
    {secret && <section className="card settingsCard" aria-label="Новый секрет интеграции"><h2>Сохраните токен сейчас</h2>
      <p>Повторно получить его нельзя. Он даёт только создание входящих заявок.</p>
      <label>Новый API-токен<textarea readOnly value={secret} onFocus={e => e.currentTarget.select()}/></label>
      <button onClick={() => setSecret('')}>Скрыть секрет</button>
    </section>}
    <section className="card settingsCard"><h2>Новый токен входящих заявок</h2>
      <form onSubmit={create}><fieldset disabled={busy || loading}>
        <label>Название интеграции<input required maxLength={255} value={name} onChange={e => setName(e.target.value)}/></label>
        <label>Воронка интеграции<select value={pipelineId} onChange={e => setPipelineId(e.target.value)}><option value="">Основная активная</option>{pipelines.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>Срок токена, дней<input type="number" required min="1" max="365" value={days} onChange={e => setDays(e.target.value)}/></label>
        <button disabled={!name.trim() || !pipelines.length}>Создать интеграционный токен</button>
      </fieldset></form>
    </section>
    <div className="integrationActions"><button disabled={busy || loading} onClick={() => setRetry(n => n + 1)}>Обновить интеграции</button></div>
    {loading ? <p role="status">Загрузка интеграций…</p> : <>
      <section className="card settingsCard"><h2>Токены · только leads:create</h2>
        {!tokens.length ? <p className="muted">Токенов пока нет.</p> : <ul className="plainList">{tokens.map(row => <li key={row.id}>
          <div><strong>{row.name}</strong> · {row.hint}<p>Воронка: {pipelines.find(p => p.id === row.pipeline_id)?.name || 'Недоступна'} · До {new Date(row.expires_at).toLocaleString('ru-RU')}</p>
            <p>{row.revoked_at ? 'Отозван' : new Date(row.expires_at) <= new Date() ? 'Истёк' : 'Не отозван'} · Последний приём: {row.last_used_at ? new Date(row.last_used_at).toLocaleString('ru-RU') : '—'}</p></div>
          {!row.revoked_at && <button disabled={busy} onClick={() => {if (window.confirm(`Отозвать токен «${row.name}»?`)) void run(async () => {await request(`${base}/integration-tokens/${row.id}/revoke`, 'POST'); setSecret('');});}}>Отозвать токен {row.name}</button>}
        </li>)}</ul>}
        <div className="inlineForm"><button disabled={busy || !tokenOffset} onClick={() => setTokenOffset(n => Math.max(0, n - 50))}>Предыдущие токены</button>
          <button disabled={busy || tokens.length < 50} onClick={() => setTokenOffset(n => n + 50)}>Следующие токены</button></div>
      </section>
      <section className="card settingsCard"><h2>Журнал принятых заявок</h2>
        {!leads.length ? <p className="muted">Принятых заявок пока нет.</p> : <ol className="activityList">{leads.map(row => <li key={row.id}>
          <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString('ru-RU')}</time><p>Ключ: {row.request_key}</p>
          {row.deal_id ? <button onClick={() => onOpenDeal(workspaceId, row.deal_id!)}>Открыть заявку {row.deal_title || row.deal_id}</button> : <p>Сделка удалена; повтор заявки её не восстановит.</p>}
        </li>)}</ol>}
        <div className="inlineForm"><button disabled={busy || !leadOffset} onClick={() => setLeadOffset(n => Math.max(0, n - 50))}>Предыдущие заявки</button>
          <button disabled={busy || leads.length < 50} onClick={() => setLeadOffset(n => n + 50)}>Следующие заявки</button></div>
      </section>
    </>}
    {error && <p role="alert" className="errorMessage">{error} <button disabled={busy} onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
    <Webhooks base={base}/>
    <section className="card settingsCard"><h2>Серверный вызов</h2>
      <p><code>POST /api/v1/integrations/leads</code> · <code>Authorization: Bearer &lt;TOKEN&gt;</code> · <code>X-StudioFlow-Request: 1</code> · <code>Content-Type: application/json</code></p>
      <pre style={{whiteSpace: 'pre-wrap'}}>{JSON.stringify({request_key: '<UUID одной заявки; сохраняйте для повторов>', title: 'Заявка с сайта', company_name: 'Компания', contact_first_name: 'Имя', email: 'client@example.com', message: 'Описание', source: 'ITG website'}, null, 2)}</pre>
      <p className="muted">Тело до 64 КиБ. Уникальный UUID на новую заявку, тот же UUID при сетевом повторе. Без CORS; требуется серверный обработчик сайта. Для публичного подключения обязательны HTTPS и ограничения reverse proxy.</p>
    </section>
  </>;
}

export default function Integrations({onOpenDeal}: {onOpenDeal: (workspaceId: string, dealId: string) => void}) {
  const [spaces, setSpaces] = useState<Workspace[]>([]);
  const [id, setId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal).then(rows => {
      if (!controller.signal.aborted) {setSpaces(rows); setId(old => rows.some(row => row.id === old) ? old : rows[0]?.id || '');}
    }).catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [retry]);
  const workspace = spaces.find(row => row.id === id);
  return <><header><div><h1>Интеграции</h1><p>Ограниченные серверные токены и входящие заявки</p></div></header>
    {loading ? <p role="status">Загрузка студий…</p> : <>
      <label>Рабочее пространство<select value={id} onChange={e => setId(e.target.value)}>{spaces.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      {!workspace ? <p>Создайте студию в настройках.</p> : workspace.role === 'MANAGER' ? <p role="alert">Интеграции доступны только владельцу и администратору.</p> : <WorkspaceIntegrations key={id} workspaceId={id} onOpenDeal={onOpenDeal}/>}
    </>}
    {error && <p role="alert">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
  </>;
}
