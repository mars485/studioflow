import {useEffect, useState} from 'react';
import {errorText, money, request, type Pipeline, type Workspace} from './api';
import {SlidersHorizontal, RotateCw} from 'lucide-react';
import HomeOverview, {type HomeDestination} from './HomeOverview';
import WorkspaceTopbar from './WorkspaceTopbar';

export type Analytics = {generated_at: string; timezone: string; counts: {OPEN: number; WON: number; LOST: number}; conversion_percent: number | null;
  stages: {stage_id: string; name: string; pipeline_name: string; currency: string; count: number; amount: string; stage_type: string}[];
  managers: {user_id: string | null; name: string; currency: string; stage_type: string; count: number; amount: string}[];
  work: {active_tasks: number; overdue_tasks: number; active_projects: number; archived_projects: number; overdue_followups: number; missing_followups: number}};
const kinds: Record<string, string> = {OPEN: 'Открытые', WON: 'Выигранные', LOST: 'Проигранные'};
function Metric({label, value, note}: {label: string; value: string | number; note: string}) {
  return <div className="card metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>;
}

function Summary({base, detailed, openCRM, onNavigate}: {base: string; detailed: boolean; openCRM: () => void; onNavigate?: (page: HomeDestination) => void}) {
  const [data, setData] = useState<Analytics>();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipeline, setPipeline] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setData(undefined);
    const params = new URLSearchParams();
    if (pipeline) params.set('pipeline_id', pipeline);
    if (from) params.set('from_date', from);
    if (to) params.set('to_date', to);
    Promise.all([request<Analytics>(`${base}/analytics?${params}`, 'GET', undefined, controller.signal),
      request<Pipeline[]>(`${base}/pipelines?include_inactive=true`, 'GET', undefined, controller.signal)])
      .then(([next, p]) => {if (!controller.signal.aborted) {setData(next); setPipelines(p);}})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, pipeline, from, to, retry]);
  if (!detailed) return <>
    <div className="homeFilterBar"><details><summary><SlidersHorizontal size={14}/>Фильтры продаж{pipeline || from || to ? ' · применены' : ''}</summary><div className="homeFilterFields">
      <label>Воронка отчёта<select value={pipeline} onChange={e => setPipeline(e.target.value)}><option value="">Все воронки</option>{pipelines.map(row => <option key={row.id} value={row.id}>{row.name}{!row.is_active ? ' · выключена' : ''}</option>)}</select></label>
      <label>Созданы с<input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label>
      <label>Созданы по<input type="date" value={to} onChange={e => setTo(e.target.value)}/></label>
    </div></details><span>{from || to ? 'По дате создания сделки' : 'Все воронки · за всё время'}</span>
      <button type="button" className="homeRefresh" disabled={loading} onClick={() => setRetry(n => n + 1)} aria-label="Обновить показатели"><RotateCw size={12}/>Обновить</button>
    </div>
    {loading ? <p className="homeLoading" role="status">Расчёт показателей…</p> : data && <>
      <HomeOverview data={data} openCRM={openCRM} onNavigate={onNavigate}/>
      <div className="homeStatusLine"><span><i/>Данные из рабочего пространства</span><span>Обновлено {new Date(data.generated_at).toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})} · Даты отчёта: {data.timezone}</span></div>
    </>}
    {error && <p role="alert" className="errorMessage">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить расчёт</button></p>}
  </>;
  return <>
    <section className="card panel" aria-label="Фильтры продаж"><h2>Продажи по дате создания сделки</h2><div className="inlineForm">
      <label>Воронка отчёта<select value={pipeline} onChange={e => setPipeline(e.target.value)}><option value="">Все воронки</option>{pipelines.map(row => <option key={row.id} value={row.id}>{row.name}{!row.is_active ? ' · выключена' : ''}</option>)}</select></label>
      <label>Созданы с<input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label>
      <label>Созданы по<input type="date" value={to} onChange={e => setTo(e.target.value)}/></label>
      <button type="button" disabled={loading} onClick={() => setRetry(n => n + 1)}>Обновить показатели</button>
      <button type="button" onClick={openCRM}>Открыть CRM</button>
    </div></section>
    {loading ? <p role="status">Расчёт показателей…</p> : data && <>
      <p className="muted">Часовой пояс дат: {data.timezone} · Обновлено {new Date(data.generated_at).toLocaleString('ru-RU')}. Без дат — за всё время.</p>
      <section className="metrics" aria-label="Показатели продаж">
        <Metric label="Открытые сделки" value={data.counts.OPEN} note="В выбранной когорте"/>
        <Metric label="Выигранные сделки" value={data.counts.WON} note="Не равно оплатам или выручке"/>
        <Metric label="Проигранные сделки" value={data.counts.LOST} note="По текущей стадии"/>
        <Metric label="Конверсия закрытых" value={data.conversion_percent === null ? '—' : `${data.conversion_percent}%`} note="Выиграно / (выиграно + проиграно)"/>
      </section>
      <p className="muted">Это текущий срез выбранных сделок, не исторический отчёт переходов. Открытые сделки не входят в знаменатель конверсии. Валюты не суммируются между собой.</p>
      <section className="card panel"><h2>Стадии продаж</h2>
        {!data.stages.length ? <p>В выбранном периоде сделок нет.</p> : <div className="portalTableScroll"><table className="taskTable"><thead><tr><th>Воронка</th><th>Стадия</th><th>Тип</th><th>Сделок</th><th>Сумма</th></tr></thead>
          <tbody>{data.stages.map(row => <tr key={`${row.stage_id}:${row.currency}`}><td>{row.pipeline_name}</td><td>{row.name}</td><td>{kinds[row.stage_type]}</td><td>{row.count}</td><td>{money(row.amount, row.currency)}</td></tr>)}</tbody></table></div>}
      </section>
      {detailed && <section className="card panel"><h2>Ответственные · текущий срез</h2>
        {!data.managers.length ? <p>Данных по ответственным нет.</p> : <div className="portalTableScroll"><table className="taskTable"><thead><tr><th>Ответственный</th><th>Состояние сделок</th><th>Количество</th><th>Сумма</th></tr></thead>
          <tbody>{data.managers.map(row => <tr key={`${row.user_id}:${row.currency}:${row.stage_type}`}><td>{row.name}</td><td>{kinds[row.stage_type]}</td><td>{row.count}</td><td>{money(row.amount, row.currency)}</td></tr>)}</tbody></table></div>}
      </section>}
      <section className="card panel" aria-label="Сводка работы студии"><h2>Работа всей студии</h2><p className="muted">Без фильтра по воронке и периоду продаж, на текущий момент.</p>
        <dl><dt>Незавершённые задачи</dt><dd>{data.work.active_tasks}</dd><dt>Просроченные задачи</dt><dd>{data.work.overdue_tasks}</dd>
          <dt>Активные проекты</dt><dd>{data.work.active_projects}</dd><dt>Архивные проекты</dt><dd>{data.work.archived_projects}</dd>
          <dt>Просроченные follow-up</dt><dd>{data.work.overdue_followups}</dd><dt>Открытые сделки без follow-up</dt><dd>{data.work.missing_followups}</dd></dl>
      </section>
    </>}
    {error && <p role="alert" className="errorMessage">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить расчёт</button></p>}
  </>;
}

export default function LiveDashboard({detailed, openCRM, onNavigate, userName}: {
  detailed: boolean; openCRM: () => void; onNavigate?: (page: HomeDestination) => void; userName?: string;
}) {
  const [spaces, setSpaces] = useState<Workspace[]>([]);
  const [id, setId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal).then(rows => {
      if (!controller.signal.aborted) {setSpaces(rows); setId(old => rows.some(row => row.id === old) ? old : rows[0]?.id || '');}
    }).catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [retry]);
  const workspaceSelect = <label className={!detailed ? 'homeWorkspace' : undefined}><span>Рабочее пространство</span><select aria-label="Рабочее пространство" value={id} onChange={e => setId(e.target.value)}>{spaces.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>;
  return <div className={!detailed ? 'homeDashboard' : 'analyticsDashboard'}>
    {!detailed && <WorkspaceTopbar userName={userName} onNavigate={onNavigate}/>}
    <header className={!detailed ? 'homePageHeading' : undefined}><div><h1>{detailed ? 'Аналитика' : 'Главная'}</h1><p>{detailed ? 'Данные вашей студии из PostgreSQL, без демонстрационных KPI' : userName ? `С возвращением, ${userName}. Вот чем живёт ваша студия.` : 'Ваш рабочий день начинается здесь.'}</p></div>{!detailed && !loading && spaces.length > 0 && workspaceSelect}</header>
    {!detailed && <nav className="homeTabs" aria-label="Разделы рабочего стола"><button aria-current="page">Обзор студии</button>
      <button disabled={!onNavigate} onClick={() => onNavigate?.('Задачи')}>Задачи команды</button><button disabled={!onNavigate} onClick={() => onNavigate?.('Аналитика')}>Отчёт по продажам</button></nav>}
    {loading ? <p role="status">Загрузка студий…</p> : <>
      {detailed && workspaceSelect}
      {id ? <Summary key={id} base={`/workspaces/${id}`} detailed={detailed} openCRM={openCRM} onNavigate={onNavigate}/> : <p className={!detailed ? 'homeLoading' : undefined}>Создайте студию в настройках.{!detailed && onNavigate && <button type="button" onClick={() => onNavigate('Настройки')}>Открыть настройки</button>}</p>}
    </>}
    {error && <p role="alert">{error} <button onClick={() => setRetry(n => n + 1)}>Повторить</button></p>}
  </div>;
}
