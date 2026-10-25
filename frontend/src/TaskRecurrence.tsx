import {useEffect, useRef, useState} from 'react';
import {errorText, request} from './api';

export type Recurrence = {interval_days: number; remaining: number; enabled: boolean; processed: boolean; next_task_id: string | null; stop_reason: string | null};
export default function TaskRecurrence({base, taskId, isFinal, isChild, onOpenTask}: {
  base: string; taskId: string; isFinal: boolean; isChild: boolean; onOpenTask: (id: string) => void;
}) {
  const path = `${base}/tasks/${taskId}/recurrence`;
  const [rule, setRule] = useState<Recurrence | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [days, setDays] = useState('7');
  const [remaining, setRemaining] = useState('1');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    request<Recurrence | null>(path, 'GET', undefined, controller.signal).then(next => {
      if (!controller.signal.aborted) {setRule(next); setEnabled(next?.enabled || false); setDays(String(next?.interval_days || 7)); setRemaining(String(next?.remaining || 1));}
    }).catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [path, isFinal, retry]);
  const save = async () => {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {setRule(await request<Recurrence>(path, 'PUT', {enabled, interval_days: Number(days), remaining: Number(remaining)}));}
    catch(e) {setError(errorText(e));} finally {saving.current = false; setBusy(false);}
  };
  return <section className="drawerSection" aria-label="Повторение задачи"><h3>Повторение после завершения</h3>
    <p className="muted">Следующая задача создаётся после завершения, через указанное число суток (по 24 часа). Это не календарное расписание. Люди и связи сохраняются, чек-лист сбрасывается; напоминания и время не копируются.</p>
    {loading ? <p role="status">Загрузка повторения…</p> : <>
      {rule?.next_task_id && <button type="button" onClick={() => onOpenTask(rule.next_task_id!)}>Открыть следующую задачу</button>}
      {rule?.stop_reason && <p role="status">Повторение остановлено: {rule.stop_reason === 'PROJECT_ARCHIVED' ? 'проект в архиве' : rule.stop_reason === 'CHILD_TASK' ? 'задача стала подзадачей' : 'нет открытого статуса задач'}.</p>}
      {rule?.processed && !rule.next_task_id && !rule.stop_reason && <p>Продолжение уже создавалось и было удалено.</p>}
      {isChild ? <p>Повторение подзадач не поддерживается.</p> : <form onSubmit={e => {e.preventDefault(); void save();}}>
        <fieldset disabled={busy || isFinal || !!rule?.processed}>
          <label><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>Повторять задачу</label>
          <label>Интервал, суток<input required type="number" min="1" max="365" step="1" value={days} onChange={e => setDays(e.target.value)}/></label>
          <label>Следующих задач<input required type="number" min="1" max="365" step="1" value={remaining} onChange={e => setRemaining(e.target.value)}/></label>
          <button>Сохранить повторение</button>
        </fieldset>
      </form>}
    </>}
    {error && <p role="alert">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить загрузку повторения</button></p>}
  </section>;
}
