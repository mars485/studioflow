import {useEffect, useState} from 'react';
import Auth from './Auth';
import WorkspaceSettings from './WorkspaceSettings';
import {ApiError, errorText, request, type User} from './api';
import CRM from './CRM';
import Tasks from './Tasks';
import Projects from './Projects';
import Finance from './Finance';
import Notifications from './Notifications';
import Integrations from './Integrations';
import Clients from './Clients';
import LiveDashboard from './LiveDashboard';
import GlobalSearch, {type SearchTarget} from './GlobalSearch';
import WorkspaceTopbar from './WorkspaceTopbar';
import {Bell,Building2,CheckSquare,FolderKanban,LayoutDashboard,Settings,Users,Wallet,BarChart3,Plug,Search} from 'lucide-react';

const menu=[[LayoutDashboard,'Главная'],[Search,'Поиск'],[Users,'CRM'],[FolderKanban,'Проекты'],[CheckSquare,'Задачи'],[Building2,'Клиенты'],[Wallet,'Финансы'],[Bell,'Уведомления'],[Plug,'Интеграции'],[BarChart3,'Аналитика'],[Settings,'Настройки']] as const;

export default function App(){
 const [page,setPage]=useState(window.location.hash === '#home' ? 'Главная' : 'CRM');
 const [crmTarget,setCrmTarget]=useState<{workspaceId: string; dealId: string} | null>(null);
 const [searchTarget,setSearchTarget]=useState<SearchTarget | null>(null);
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
   const expired = () => {setUser(null); setCrmTarget(null); setSearchTarget(null); setPage('CRM');};
   window.addEventListener('session-expired', expired);
   return () => {controller.abort(); window.removeEventListener('session-expired', expired);};
 }, [retry]);
   if (loading) return <div className="authPage itgAuth"><p role="status">Загрузка StudioFlow…</p></div>;
   if (error && !user) return <div className="authPage itgAuth"><section className="card authCard"><p role="alert">{error}</p><button onClick={() => setRetry(v => v + 1)}>Повторить</button></section></div>;
 if (!user) return <Auth onLogin={value => {setUser(value); setPage('CRM');}}/>;
 async function logout() {
   setLeaving(true); setError('');
     try {await request('/auth/logout', 'POST'); setUser(null); setCrmTarget(null); setSearchTarget(null); setPage('CRM');}
   catch(e) {setError(errorText(e));} finally {setLeaving(false);}
 }
  const openDeal = (workspaceId: string, dealId: string) => {setCrmTarget({workspaceId, dealId}); setSearchTarget(null); setPage('CRM');};
  const openSearch = (target: SearchTarget) => {
    if (target.kind === 'deal') {openDeal(target.workspaceId, target.id); return;}
    setSearchTarget(target); setCrmTarget(null);
    setPage(target.kind === 'task' ? 'Задачи' : target.kind === 'project' ? 'Проекты' : 'Клиенты');
  };
   const branded = page === 'Главная' || page === 'CRM';
    return <div className={`shell homeShell${page === 'CRM' ? ' crmShell' : ''}${!branded ? ' portalShell' : ''}`}><aside className="sidebar">
    <div className="brand"><div className="brandMark">IT</div><div><b>IT GROUP</b><span>StudioFlow · рабочая среда</span></div></div>
     <nav aria-label="Основная навигация">{menu.map(([Icon,label])=><button aria-label={label} aria-current={page===label?'page':undefined} title={label} onClick={()=>{setCrmTarget(null); setSearchTarget(null); setPage(label);}} className={page===label?'active':''} key={label}><Icon size={19} aria-hidden="true"/><span>{label}</span></button>)}</nav>
    <div className="profile"><div className="avatar">{user.first_name.slice(0, 1).toUpperCase()}</div><div><b>{user.first_name}</b><span title={user.email}>{user.email}</span><button disabled={leaving} onClick={() => void logout()}>{leaving ? 'Выход…' : 'Выйти'}</button></div></div></aside>
  <main>{error && <p role="alert" className="errorMessage">{error}</p>}
    {!branded && <WorkspaceTopbar userName={user.first_name} onNavigate={destination => {setCrmTarget(null); setSearchTarget(null); setPage(destination);}}/>}
    <div className={!branded ? 'portalModule' : undefined} data-module={page}>
    {page==='CRM'?<CRM initialWorkspaceId={crmTarget?.workspaceId} initialDealId={crmTarget?.dealId} userName={user.first_name} onNavigate={destination => {setCrmTarget(null); setSearchTarget(null); setPage(destination);}}/>:page==='Поиск'?<GlobalSearch onOpen={openSearch}/>:page==='Задачи'?<Tasks initialWorkspaceId={searchTarget?.workspaceId} initialTaskId={searchTarget?.kind === 'task' ? searchTarget.id : undefined}/>:page==='Проекты'?<Projects initialWorkspaceId={searchTarget?.workspaceId} initialProjectId={searchTarget?.kind === 'project' ? searchTarget.id : undefined}/>:page==='Клиенты'?<Clients onOpenDeal={openDeal} initialWorkspaceId={searchTarget?.workspaceId} initialTarget={searchTarget?.kind === 'client' || searchTarget?.kind === 'contact' ? {kind: searchTarget.kind, id: searchTarget.id} : undefined}/>:page==='Финансы'?<Finance/>:page==='Уведомления'?<Notifications onOpenDeal={openDeal}/>:page==='Интеграции'?<Integrations onOpenDeal={openDeal}/>:page==='Настройки'?<WorkspaceSettings/>:<LiveDashboard detailed={page==='Аналитика'} userName={user.first_name} onNavigate={destination => {setCrmTarget(null); setSearchTarget(null); setPage(destination);}} openCRM={()=>{setCrmTarget(null); setSearchTarget(null); setPage('CRM');}}/>}
    </div></main></div>
}
