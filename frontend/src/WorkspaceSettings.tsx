import {useEffect, useRef, useState, type FormEvent} from 'react';
import {errorText, request, roleNames, type Member, type Role, type Workspace} from './api';

export default function WorkspaceSettings() {
  const [spaces, setSpaces] = useState<Workspace[]>([]);
  const [id, setId] = useState('');
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const workspace = spaces.find(w => w.id === id);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setMembers([]);
    async function load() {
      try {
        const list = await request<Workspace[]>('/workspaces', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setSpaces(list);
        const nextId = list.some(w => w.id === id) ? id : list[0]?.id || '';
        if (nextId !== id) {setId(nextId); return;}
        const people = nextId ? await request<Member[]>(`/workspaces/${nextId}/members`, 'GET', undefined, controller.signal) : [];
        if (!controller.signal.aborted) {setMembers(people); setLoading(false);}
      } catch(e) {if (!controller.signal.aborted) {setError(errorText(e)); setLoading(false);}}
    }
    void load();
    return () => controller.abort();
  }, [id, version]);
  async function mutate(operation: () => Promise<void>) {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {await operation(); setVersion(v => v + 1);} catch(e) {setError(errorText(e));}
    finally {saving.current = false; setBusy(false);}
  }
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget;
    const name = String(new FormData(form).get('name'));
    void mutate(async () => {const added = await request<Workspace>('/workspaces', 'POST', {name}); setId(added.id); form.reset();});
  }
  const canManage = workspace && workspace.role !== 'MANAGER';
  const roles: Role[] = workspace?.role === 'OWNER' ? ['OWNER', 'ADMIN', 'MANAGER'] : ['MANAGER'];
  return <>
    <header><div><h1>Настройки студии</h1><p>Рабочие пространства, участники и доступ</p></div></header>
    {error && <p className="errorMessage" role="alert">{error} <button disabled={busy || loading} onClick={() => setVersion(v => v + 1)}>Повторить загрузку</button></p>}
    {loading && <p role="status">Загрузка настроек…</p>}
    <section className="card settingsCard"><h2>Новая студия</h2><form onSubmit={create}><fieldset disabled={busy || loading} className="inlineForm"><label>Название новой студии<input name="name" required maxLength={255}/></label><button className="primary">Создать студию</button></fieldset></form>
    {!loading && !spaces.length && <p>Создайте студию или попросите её владельца добавить ваш email в участники.</p>}</section>
    {!!spaces.length && <section className="card settingsCard">
      <label>Рабочее пространство<select aria-label="Студия в настройках" disabled={busy || loading} value={id} onChange={e => setId(e.target.value)}>{spaces.map(w => <option value={w.id} key={w.id}>{w.name}</option>)}</select></label>
      {workspace && <p>Ваша роль: {roleNames[workspace.role]}</p>}
      {canManage && <form key={workspace.id + workspace.name} onSubmit={e => {e.preventDefault(); const name = String(new FormData(e.currentTarget).get('name')); void mutate(async () => {await request(`/workspaces/${id}`, 'PATCH', {name});});}}>
        <fieldset disabled={busy || loading} className="inlineForm"><label>Название студии<input name="name" defaultValue={workspace.name} required maxLength={255}/></label><button>Сохранить название</button></fieldset>
      </form>}
      <h2>Участники</h2><p className="muted">Владелец назначает роли. Администратор управляет менеджерами. Менеджер работает со сделками без права их удаления.</p>
      {!loading && members.map(member => <div className="memberRow" key={member.id}>
        <div className="grow"><b>{member.first_name}</b><span>{member.email}</span></div>
        {canManage && (workspace.role === 'OWNER' || member.role === 'MANAGER') ? <>
          <select aria-label={`Роль ${member.email}`} value={member.role} disabled={busy} onChange={e => {const role = e.target.value; void mutate(async () => {await request(`/workspaces/${id}/members/${member.id}`, 'PATCH', {role});});}}>{roles.map(role => <option key={role} value={role}>{roleNames[role]}</option>)}</select>
          <button disabled={busy} onClick={() => {if (window.confirm(`Удалить ${member.email} из студии?`)) void mutate(async () => {await request(`/workspaces/${id}/members/${member.id}`, 'DELETE');});}}>Удалить участника</button>
        </> : <span>{roleNames[member.role]}</span>}
      </div>)}
      {canManage && <form onSubmit={e => {e.preventDefault(); const form = e.currentTarget; const data = new FormData(form); void mutate(async () => {await request(`/workspaces/${id}/members`, 'POST', {email: data.get('email'), role: data.get('role')}); form.reset();});}}>
        <fieldset disabled={busy || loading} className="inlineForm"><label>Email участника<input type="email" name="email" required maxLength={320}/></label><label>Роль<select name="role" defaultValue="MANAGER">{roles.map(role => <option key={role} value={role}>{roleNames[role]}</option>)}</select></label><button className="primary">Добавить участника</button></fieldset>
        <p className="muted">Участник должен заранее зарегистрироваться. Письмо-приглашение пока не отправляется.</p>
      </form>}
    </section>}
  </>;
}
