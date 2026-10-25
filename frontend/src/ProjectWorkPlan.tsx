import {useEffect, useRef, useState} from 'react';
import {errorText, request, type Member} from './api';

export type WorkStage = {id: string; project_id: string; title: string; position: number; status: 'PLANNED' | 'ACTIVE' | 'DONE';
  manager_user_id: string | null; start_date: string | null; end_date: string | null};
export const workStatusNames = {PLANNED: 'Запланировано', ACTIVE: 'В работе', DONE: 'Готово'};
const ordinal = (value: string) => Date.parse(value + 'T00:00:00Z') / 86400000;
export function workTimeline(rows: WorkStage[]) {
  const dated = rows.filter(row => row.start_date || row.end_date);
  if (!dated.length) return null;
  const start = dated.map(row => row.start_date || row.end_date!).sort()[0];
  const end = dated.map(row => row.end_date || row.start_date!).sort().at(-1)!;
  const days = ordinal(end) - ordinal(start) + 1;
  return {start, end, bars: dated.map(row => ({...row,
    left: (ordinal(row.start_date || row.end_date!) - ordinal(start)) / days * 100,
    width: (ordinal(row.end_date || row.start_date!) - ordinal(row.start_date || row.end_date!) + 1) / days * 100}))};
}

function StageEditor({stage, members, busy, onSave}: {stage: WorkStage; members: Member[]; busy: boolean; onSave: (draft: object) => void}) {
  const [draft, setDraft] = useState({title: stage.title, status: stage.status, manager_user_id: stage.manager_user_id || '', start_date: stage.start_date || '', end_date: stage.end_date || ''});
  return <form className="workEditor" onSubmit={e => {e.preventDefault(); onSave({...draft, manager_user_id: draft.manager_user_id || null, start_date: draft.start_date || null, end_date: draft.end_date || null});}}>
    <fieldset disabled={busy}>
      <label>Название этапа {stage.title}<input required maxLength={255} value={draft.title} onChange={e => setDraft({...draft, title: e.target.value})}/></label>
      <label>Состояние этапа {stage.title}<select value={draft.status} onChange={e => setDraft({...draft, status: e.target.value as WorkStage['status']})}>{Object.entries(workStatusNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Ответственный этапа {stage.title}<select value={draft.manager_user_id} onChange={e => setDraft({...draft, manager_user_id: e.target.value})}><option value="">Не назначен</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.first_name} · {member.email}</option>)}</select></label>
      <label>Начало этапа {stage.title}<input type="date" value={draft.start_date} onChange={e => setDraft({...draft, start_date: e.target.value})}/></label>
      <label>Окончание этапа {stage.title}<input type="date" value={draft.end_date} onChange={e => setDraft({...draft, end_date: e.target.value})}/></label>
      <button disabled={!draft.title.trim()}>Сохранить этап {stage.title}</button>
    </fieldset>
  </form>;
}

export default function ProjectWorkPlan({base, projectId, view, members, archived, canDelete, onChanged}: {
  base: string; projectId: string; view: 'plan' | 'gantt'; members: Member[]; archived: boolean; canDelete: boolean; onChanged: () => Promise<void>;
}) {
  const path = `${base}/projects/${projectId}/work-plan`;
  const [rows, setRows] = useState<WorkStage[]>([]);
  const [title, setTitle] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [templateDescription, setTemplateDescription] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<WorkStage[]>(path, 'GET', undefined, controller.signal).then(next => {if (!controller.signal.aborted) setRows(next);})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [path, retry]);
  const run = async (operation: () => Promise<unknown>) => {
    if (saving.current || archived) return;
    saving.current = true; setBusy(true); setError('');
    try {await operation(); setRows(await request<WorkStage[]>(path)); await onChanged();}
    catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  };
  const shift = (index: number, delta: number) => {
    const ids = rows.map(row => row.id); [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    void run(() => request(`${path}/order`, 'PUT', {ids}));
  };
  const timeline = workTimeline(rows);
  return <section aria-label={view === 'plan' ? 'Порядок работ проекта' : 'Гант проекта'} className="drawerSection">
    {archived && <p className="muted">Архивный проект: план только для чтения.</p>}
    {loading ? <p role="status">Загрузка плана работ…</p> : view === 'plan' ? <>
      {!rows.length && <p className="muted">Этапов работ пока нет.</p>}
      <ol className="workStageList">{rows.map((stage, index) => <li key={stage.id}>
        <h4>{stage.title} · {workStatusNames[stage.status]}</h4>
        <StageEditor stage={stage} members={members} busy={busy || archived} onSave={draft => void run(() => request(`${path}/${stage.id}`, 'PATCH', draft))}/>
        <div className="inlineForm"><button disabled={busy || archived || !index} onClick={() => shift(index, -1)}>Выше {stage.title}</button>
          <button disabled={busy || archived || index === rows.length - 1} onClick={() => shift(index, 1)}>Ниже {stage.title}</button>
          {canDelete && <button disabled={busy || archived} onClick={() => {if (window.confirm(`Удалить этап «${stage.title}»?`)) void run(() => request(`${path}/${stage.id}`, 'DELETE'));}}>Удалить этап {stage.title}</button>}</div>
      </li>)}</ol>
      <form onSubmit={e => {e.preventDefault(); void run(async () => {await request(path, 'POST', {title: title.trim()}); setTitle('');});}}><fieldset disabled={busy || archived}>
        <label>Новый этап работ<input required maxLength={255} value={title} onChange={e => setTitle(e.target.value)}/></label><button disabled={!title.trim() || rows.length >= 500}>Добавить этап работ</button>
      </fieldset></form>
      {canDelete && <form onSubmit={e => {e.preventDefault(); void run(async () => {
        await request(`${base}/projects/${projectId}/template`, 'POST', {name: templateName.trim(), description: templateDescription || null}); setTemplateName(''); setTemplateDescription('');
      });}}><fieldset disabled={busy || archived || !rows.length}>
        <label>Название шаблона плана<input required maxLength={255} value={templateName} onChange={e => setTemplateName(e.target.value)}/></label>
        <label>Описание шаблона плана<textarea maxLength={10000} value={templateDescription} onChange={e => setTemplateDescription(e.target.value)}/></label>
        <button disabled={!templateName.trim()}>Сохранить план как шаблон</button>
        <p className="muted">Копируются этапы и относительные даты, без людей, выполнений, задач и финансов.</p>
      </fieldset></form>}
    </> : <>
      <p className="muted">Упрощённая временная шкала этапов, без зависимостей и автопланирования. Даты меняются в «Порядке работ».</p>
      {timeline ? <><p>{timeline.start} — {timeline.end}</p>{timeline.bars.map(row => <div className="workGanttRow" key={row.id}>
        <div><strong>{row.title}</strong><small>{row.start_date || row.end_date} — {row.end_date || row.start_date}</small></div>
        <div className="workGanttTrack"><div role="img" aria-label={`${row.title}: ${row.start_date || row.end_date} — ${row.end_date || row.start_date}`} className={`workGanttBar ${row.status}`} style={{left: `${row.left}%`, width: `${row.width}%`}}>{workStatusNames[row.status]}</div></div>
      </div>)}</> : <p className="muted">Для временной шкалы задайте даты этапов.</p>}
      <h4>Без дат</h4><ul>{rows.filter(row => !row.start_date && !row.end_date).map(row => <li key={row.id}>{row.title}</li>)}</ul>
    </>}
    {error && <p role="alert" className="errorMessage">{error} <button disabled={busy} onClick={() => setRetry(n => n + 1)}>Повторить загрузку плана</button></p>}
  </section>;
}
