import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './app.css';

const root = document.getElementById('root')!;
root.classList.add('itgTheme');
ReactDOM.createRoot(root).render(<React.StrictMode><App/></React.StrictMode>);
