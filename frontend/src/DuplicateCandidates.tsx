import {useEffect, useState} from 'react';
import {errorText, request} from './api';

type Page = {source: {id: string; label: string}; total: number; items: {id: string; label: string; reasons: string[]}[]};
const reasons: Record<string, string> = {email: 'email', phone: 'телефон', name: 'имя/название'};

export default function DuplicateCandidates({base, kind, objectId, onOpen, onClose, onMerge}: {
  base: string; kind: 'client' | 'contact'; objectId: string; onOpen: (id: string) => void | Promise<void>; onClose: () => void;
  onMerge?: (sourceId: string, targetId: string) => void;
}) {
  const [page, setPage] = useState<Page>();
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [opening, setOpening] = useState(false);
  const open = async (id: string) => {
    if (opening) return;
    setOpening(true); setError('');
    try {await onOpen(id);} catch(e) {setError(errorText(e));} finally {setOpening(false);}
  };
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setPage(undefined);
    const params = new URLSearchParams({kind, object_id: objectId, offset: String(offset), limit: '50'});
    request<Page>(`${base}/duplicate-candidates?${params}`, 'GET', undefined, controller.signal)
      .then(next => {if (!controller.signal.aborted) setPage(next);})
      .catch(e => {if (!controller.signal.aborted) setError(errorText(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [base, kind, objectId, offset, retry]);
  return <section className="card settingsCard" aria-label="Возможные дубли"><h2>Возможные дубли</h2>
    <p className="muted">Совпадение не доказывает дубль. Сравниваются email, цифры телефона и полное имя/название без регистра. Код страны и опечатки не исправляются. Проверка сама не объединяет и не удаляет данные.</p>
    <button type="button" onClick={onClose}>Закрыть проверку дублей</button>
    <button type="button" disabled={loading} onClick={() => setRetry(n => n + 1)}>Обновить проверку дублей</button>
    {loading ? <p role="status">Поиск дублей…</p> : page && <><p>Для: {page.source.label} · Возможных дублей: {page.total}</p>
      {!page.items.length ? <p>По этим правилам совпадений нет.</p> : <ul className="plainList">{page.items.map(row => <li key={row.id}>
        <button type="button" disabled={opening} onClick={() => void open(row.id)}>Сравнить: {row.label}</button>
        <span>Совпадает: {row.reasons.map(reason => reasons[reason] || reason).join(', ')} · {row.id}</span>
        {onMerge && <button type="button" disabled={opening} onClick={() => onMerge(row.id, objectId)}>Слияние: {row.label}</button>}
      </li>)}</ul>}
      <button type="button" disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие кандидаты</button>
      <button type="button" disabled={offset + page.items.length >= page.total} onClick={() => setOffset(n => n + 50)}>Следующие кандидаты</button>
    </>}
    {error && <p role="alert">{error} <button type="button" onClick={() => setRetry(n => n + 1)}>Повторить проверку дублей</button></p>}
  </section>;
}
