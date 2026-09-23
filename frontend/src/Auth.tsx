import {useState, type FormEvent} from 'react';
import {errorText, request, type User} from './api';

export default function Auth({onLogin}: {onLogin: (user: User) => void}) {
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      const user = await request<User>(register ? '/auth/register' : '/auth/login', 'POST', {
        email: String(form.get('email')), password: String(form.get('password')),
        ...(register ? {first_name: String(form.get('name'))} : {}),
      });
      onLogin(user);
    } catch (e) {setError(errorText(e));} finally {setBusy(false);}
  }
  return <div className="authPage"><section className="card authCard">
    <div className="brand"><div className="brandMark">S</div><div><b>StudioFlow</b><span>Web Studio OS</span></div></div>
    <h1>{register ? 'Создать аккаунт' : 'Войти в StudioFlow'}</h1>
    <p className="muted">Продажи и работа вашей студии в одном месте.</p>
    <form onSubmit={submit}><fieldset disabled={busy}>
      {register && <label>Ваше имя<input name="name" autoComplete="given-name" required maxLength={100}/></label>}
      <label>Email<input name="email" type="email" autoComplete="username" required maxLength={320}/></label>
      <label>Пароль<input name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} minLength={12} maxLength={128} required/></label>
      {register && <p className="muted">Не менее 12 символов. После регистрации создайте студию или попросите владельца добавить ваш email.</p>}
      {error && <p role="alert" className="errorMessage">{error}</p>}
      <button className="primary">{busy ? 'Подождите…' : register ? 'Зарегистрироваться' : 'Войти'}</button>
    </fieldset></form>
    <button className="noteBtn" disabled={busy} onClick={() => {setRegister(!register); setError('');}}>{register ? 'У меня уже есть аккаунт' : 'Создать аккаунт'}</button>
  </section></div>;
}
