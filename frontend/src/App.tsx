import {useEffect, useState} from 'react';
import Auth from './Auth';
import WorkspaceSettings from './WorkspaceSettings';
import {ApiError, errorText, request, type User} from './api';
import CRM from './CRM';
import {Bell,Building2,CheckSquare,ChevronRight,FolderKanban,LayoutDashboard,Settings,Users,Wallet,BarChart3,Phone,MessageCircle,Plus} from 'lucide-react';

const menu=[[LayoutDashboard,'Главная'],[Users,'CRM'],[FolderKanban,'Проекты'],[CheckSquare,'Задачи'],[Building2,'Клиенты'],[Wallet,'Финансы'],[BarChart3,'Аналитика'],[Settings,'Настройки']] as const;
const attention=[{name:'АН «Квадрат»',task:'Отправить коммерческое предложение',time:'Сегодня, 18:00',kind:'message'},{name:'Дом Ипотек',task:'Позвонить по заявке',time:'Просрочено на 1 день',kind:'phone'},{name:'Новый лид',task:'Ответить в WhatsApp',time:'Сегодня, 20:30',kind:'message'}];
const tasks=[['Подготовить прототип лендинга','Высокий'],['Связаться с 10 агентствами недвижимости','Высокий'],['Проверить рекламную кампанию','Средний']];
function Metric({label,value,note}:{label:string,value:string,note:string}){return <div className="card metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>}

export default function App(){
 const [page,setPage]=useState('CRM');
 const [user,setUser]=useState<User | null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [retry,setRetry]=useState(0);
 const [leaving,setLeaving]=useState(false);
 useEffect(() => {
   const controller = new AbortController();
   setLoading(true); setError('');
   request<User>('/auth/me', 'GET', undefined, controller.signal).then(value => {if (!controller.signal.aborted) setUser(value);})
     .catch(e => {if (!controller.signal.aborted && !(e instanceof ApiError && e.status === 401)) setError(errorText(e));})
     .finally(() => {if (!controller.signal.aborted) setLoading(false);});
   const expired = () => {setUser(null); setPage('CRM');};
   window.addEventListener('session-expired', expired);
   return () => {controller.abort(); window.removeEventListener('session-expired', expired);};
 }, [retry]);
 if (loading) return <div className="authPage"><p role="status">Загрузка StudioFlow…</p></div>;
 if (error && !user) return <div className="authPage"><section className="card authCard"><p role="alert">{error}</p><button onClick={() => setRetry(v => v + 1)}>Повторить</button></section></div>;
 if (!user) return <Auth onLogin={value => {setUser(value); setPage('CRM');}}/>;
 async function logout() {
   setLeaving(true); setError('');
   try {await request('/auth/logout', 'POST'); setUser(null); setPage('CRM');}
   catch(e) {setError(errorText(e));} finally {setLeaving(false);}
 }
 return <div className="shell"><aside className="sidebar"><div className="brand"><div className="brandMark">S</div><div><b>StudioFlow</b><span>Web Studio OS</span></div></div><nav>{menu.map(([Icon,label])=><button onClick={()=>setPage(label)} className={page===label?'active':''} key={label}><Icon size={19}/><span>{label}</span></button>)}</nav><div className="profile"><div className="avatar">{user.first_name.slice(0, 1).toUpperCase()}</div><div><b>{user.first_name}</b><span title={user.email}>{user.email}</span><button disabled={leaving} onClick={() => void logout()}>{leaving ? 'Выход…' : 'Выйти'}</button></div></div></aside>
 <main>{error && <p role="alert" className="errorMessage">{error}</p>}{page==='CRM'?<CRM/>:page==='Настройки'?<WorkspaceSettings/>:<Dashboard openCRM={()=>setPage('CRM')}/>}</main></div>
}
function Top({title,subtitle,onNew}:{title:string,subtitle:string,onNew?:()=>void}){return <header><div><h1>{title}</h1><p>{subtitle}</p></div><div className="headerActions"><button className="icon"><Bell size={19}/><i/></button><button className="primary" onClick={onNew}><Plus size={18}/>Новая сделка</button></div></header>}
function Dashboard({openCRM}:{openCRM:()=>void}){return <><Top title="Главная" subtitle="Контроль продаж и работы студии"/><section className="metrics"><Metric label="Новые лиды" value="34" note="+8 за неделю"/><Metric label="Активные сделки" value="12" note="На 486 000 ₽"/><Metric label="Продажи" value="186 000 ₽" note="+24% к прошлому месяцу"/><Metric label="Проекты в работе" value="7" note="2 требуют внимания"/></section><div className="grid"><section className="card panel"><div className="panelHead"><div><h2>Требуют внимания</h2><p>Follow-up на сегодня</p></div><button onClick={openCRM}>Все контакты <ChevronRight size={16}/></button></div>{attention.map((x,i)=><div className="row" key={x.name}><div className={'activity '+(i===1?'danger':'')}>{x.kind==='phone'?<Phone size={17}/>:<MessageCircle size={17}/>}</div><div className="grow"><b>{x.name}</b><span>{x.task}</span></div><time className={i===1?'overdue':''}>{x.time}</time></div>)}</section><section className="card panel"><div className="panelHead"><div><h2>Задачи на сегодня</h2><p>3 задачи · 0 выполнено</p></div></div>{tasks.map(([task,priority],i)=><label className="task" key={task}><input type="checkbox"/><div className="grow"><b>{task}</b><span>StudioFlow · сегодня</span></div><em className={i===2?'medium':''}>{priority}</em></label>)}</section></div><section className="card pipeline"><div className="panelHead"><div><h2>Воронка продаж</h2><p>Текущий месяц</p></div><button onClick={openCRM}>Открыть CRM <ChevronRight size={16}/></button></div><div className="stages">{[['Новый лид','18','540 000 ₽'],['Контакт','11','330 000 ₽'],['КП отправлено','7','245 000 ₽'],['Переговоры','4','180 000 ₽'],['Успешно','3','186 000 ₽']].map((s,i)=><div className="stage" key={s[0]}><div className="stageTop"><span>{s[0]}</span><b>{s[1]}</b></div><strong>{s[2]}</strong><div className="bar"><i style={{width:`${100-i*17}%`}}/></div></div>)}</div></section></>}
