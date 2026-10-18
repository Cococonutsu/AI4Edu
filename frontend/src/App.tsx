import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './state/auth';
import { ChatProvider } from './state/chat';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';

function FullPageLoading({ label }: { label: string }): JSX.Element {
  return (
    <div className="page-loading">
      <span className="spinner spinner-large" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

function ProtectedRoute(): JSX.Element {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return <FullPageLoading label="正在加载…" />;
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

function ChatShell(): JSX.Element {
  return (
    <ChatProvider>
      <Outlet />
    </ChatProvider>
  );
}

export default function App(): JSX.Element {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<ChatShell />}>
              <Route path="/" element={<ChatPage />} />
              <Route path="/c/:conversationId" element={<ChatPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
