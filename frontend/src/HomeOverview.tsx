import {ArrowRight, ArrowUpRight, CheckCheck, Clock3, FolderKanban, Layers3, Target, TrendingUp, AlertCircle, CircleCheck, Plus} from 'lucide-react';
import {money} from './api';
import type {Analytics} from './LiveDashboard';

export type HomeDestination = 'CRM' | 'Задачи' | 'Проекты' | 'Поиск' | 'Уведомления' | 'Аналитика' | 'Настройки';

export default function HomeOverview({data, openCRM, onNavigate}: {
  data: Analytics; openCRM: () => void; onNavigate?: (page: HomeDestination) => void;
}) {
  const go = (page: HomeDestination) => page === 'CRM' ? openCRM() : onNavigate?.(page);
  const total = data.counts.OPEN + data.counts.WON + data.counts.LOST;
  const max = Math.max(1, ...data.stages.map(row => row.count));
  const focus = [
    {label: 'Просроченные задачи', count: data.work.overdue_tasks, note: 'Проверьте сроки и приоритеты', page: 'Задачи' as const},
    {label: 'Просроченные follow-up', count: data.work.overdue_followups, note: 'Вернитесь к диалогу с клиентом', page: 'CRM' as const},
    {label: 'Сделки без следующего шага', count: data.work.missing_followups, note: 'Запланируйте следующий контакт', page: 'CRM' as const},
  ];
  return <>
    <section className="homeWelcome" aria-label="Рабочий день">
      <div><div className="homeEyebrow"><span/>Рабочее пространство ITG</div><h2>Меньше рутины.<br/>Больше результата.</h2>
        <p>Продажи, команда и проекты — в одном рабочем пространстве.</p>
        <div className="homeWelcomeActions"><button className="primary" onClick={openCRM}>Открыть CRM <ArrowUpRight size={17}/></button>
          {onNavigate && <button onClick={() => go('Задачи')}>К задачам <ArrowRight size={16}/></button>}</div>
      </div>
      <dl className="homeOperationalSummary" aria-label="Сейчас в студии">
        <div><dt>Задачи в работе</dt><dd>{data.work.active_tasks}</dd></div>
        <div><dt>Активные проекты</dt><dd>{data.work.active_projects}</dd></div>
        <div><dt>Follow-up просрочены</dt><dd className={data.work.overdue_followups ? 'attentionValue' : undefined}>{data.work.overdue_followups}</dd></div>
      </dl>
    </section>

    <div className="homeSectionHeading"><h2>Продажи в цифрах</h2><span>Текущий срез сделок</span></div>
    <section className="homeMetrics" aria-label="Показатели продаж">
      {[
        {label: 'Открытые сделки', value: data.counts.OPEN, note: 'В работе у команды', icon: Layers3, tone: 'red'},
        {label: 'Выигранные сделки', value: data.counts.WON, note: 'Успешно закрыты', icon: CircleCheck, tone: 'green'},
        {label: 'Проигранные сделки', value: data.counts.LOST, note: 'По текущей стадии', icon: Target, tone: 'gray'},
        {label: 'Конверсия закрытых', value: data.conversion_percent === null ? '—' : `${data.conversion_percent}%`, note: 'Выиграно / все закрытые', icon: TrendingUp, tone: 'red'},
      ].map(({label, value, note, icon: Icon, tone}) => <div className="homeMetric" key={label}><div className="homeMetricTop"><span>{label}</span><span className={`homeMetricIcon ${tone}`}><Icon size={18}/></span></div>
        <strong>{value}</strong><small>{note}</small></div>)}
    </section>

    <div className="homeWidgetGrid">
      <section className="homeWidget homeSales" aria-label="Воронка продаж"><div className="homeWidgetHead"><div><span className="homeEyebrow">ПРОДАЖИ</span><h2>Воронка продаж <span className="homeCount">{total}</span></h2></div>
        <button className="homeTextButton" onClick={openCRM}>В CRM <ArrowUpRight size={15}/></button></div>
        <div className="homeFunnelLegend"><span><i/>Количество сделок по стадиям</span><span>Сумма · валюта</span></div>
        {!data.stages.length ? <div className="homeEmpty"><Layers3 size={28}/><h3>Здесь начнётся ваша воронка</h3><p>Создайте первую сделку в CRM — и она появится в сводке.</p><button className="homeTextButton" onClick={openCRM}>Перейти в CRM <ArrowRight size={15}/></button></div> :
          <div className="homeFunnel">{data.stages.map(row => <div className={`homeFunnelRow ${row.stage_type.toLowerCase()}`} key={`${row.stage_id}:${row.currency}`}>
            <div className="homeFunnelTitle"><span>{row.name}</span><small>{row.pipeline_name}</small></div>
            <div className="homeFunnelTrack"><div style={{width: `${Math.max(3, row.count / max * 100)}%`}}/></div>
            <b>{row.count}</b><span className="homeFunnelAmount">{money(row.amount, row.currency)}</span>
          </div>)}</div>}
        <div className="homeWidgetFoot"><span>Валюты считаются отдельно</span>{onNavigate && <button className="homeTextButton" onClick={() => go('Аналитика')}>Подробный отчёт <ArrowRight size={14}/></button>}</div>
      </section>

      <section className="homeWidget homeFocus" aria-label="Требует внимания"><div className="homeWidgetHead"><div><span className="homeEyebrow">ФОКУС ДНЯ</span><h2>Требует внимания</h2></div><span className="homeFocusIcon"><AlertCircle size={20}/></span></div>
        <p className="homeWidgetDescription">Ничего важного не должно потеряться.</p>
        <div className="homeFocusList">{focus.map(row => <button key={row.label} onClick={() => go(row.page)} disabled={!onNavigate && row.page !== 'CRM'}>
          <span className={`homeFocusCount ${row.count ? 'hasItems' : ''}`}>{row.count}</span><span><b>{row.label}</b><small>{row.note}</small></span><ArrowUpRight size={16}/>
        </button>)}</div>
        <div className="homeFocusNote"><Clock3 size={14}/><span>По всей студии, на текущий момент</span></div>
      </section>
    </div>

    <section className="homeWork" aria-label="Сводка работы студии"><div className="homeSectionHeading"><h2>Команда и проекты</h2><span>Без фильтра по периоду продаж</span></div>
      <div className="homeWorkGrid"><div className="homeWorkCard"><span className="homeWorkIcon"><CheckCheck size={21}/></span><div><span>Незавершённые задачи</span><strong>{data.work.active_tasks}</strong><small>Просроченные задачи: {data.work.overdue_tasks}</small></div>
        {onNavigate && <button aria-label="Открыть задачи студии" onClick={() => go('Задачи')}><ArrowUpRight size={18}/></button>}</div>
        <div className="homeWorkCard"><span className="homeWorkIcon"><FolderKanban size={21}/></span><div><span>Активные проекты</span><strong>{data.work.active_projects}</strong><small>Архивные проекты: {data.work.archived_projects}</small></div>
          {onNavigate && <button aria-label="Открыть проекты студии" onClick={() => go('Проекты')}><ArrowUpRight size={18}/></button>}</div>
        <div className="homeQuickStart"><span className="homeEyebrow">СЛЕДУЮЩИЙ ШАГ</span><h3>От идеи к действию</h3><p>Продолжите работу со сделками и следующими контактами.</p><button onClick={openCRM}><Plus size={16}/>Перейти к сделкам<ArrowRight size={16}/></button></div>
      </div>
    </section>
    <p className="homeDataNote">Текущие стадии выбранных сделок, не история переходов. Выигранная сумма не равна оплатам или выручке. Конверсия не учитывает открытые сделки.</p>
  </>;
}
