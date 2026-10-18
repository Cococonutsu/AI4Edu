import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import 'katex/dist/katex.min.css';
import App from './App';
import './styles/global.css';
import './styles/login.css';
import './styles/chat.css';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('页面缺少 #root 容器。');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
