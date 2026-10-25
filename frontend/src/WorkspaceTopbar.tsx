import {Bell, CalendarDays, Search} from 'lucide-react';
import type {HomeDestination} from './HomeOverview';

export default function WorkspaceTopbar({userName, onNavigate}: {userName?: string; onNavigate?: (page: HomeDestination) => void}) {
  return <div className="homeTopbar"><button type="button" className="homeSearchButton" disabled={!onNavigate} onClick={() => onNavigate?.('Поиск')}><Search size={15}/><span>Поиск по рабочему пространству</span><kbd>Поиск</kbd></button>
    <div className="homeTopbarRight"><span className="homeToday"><CalendarDays size={15}/>{new Date().toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', weekday: 'short'})}</span>
      <button type="button" className="homeTopbarIcon" aria-label="Открыть уведомления" disabled={!onNavigate} onClick={() => onNavigate?.('Уведомления')}><Bell size={17}/></button>
      <span className="homeTopbarAvatar" aria-label={userName || 'Пользователь'}>{userName?.slice(0, 1).toUpperCase() || 'S'}</span>
    </div>
  </div>;
}
