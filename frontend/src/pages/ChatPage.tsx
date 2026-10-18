import { useEffect, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { useChat } from '../state/chat';
import { AlertIcon, CloseIcon, MenuIcon } from '../components/Icons';
import { Composer } from '../components/Composer';
import { ConversationSidebar } from '../components/ConversationSidebar';
import { MessageList } from '../components/MessageList';

export function ChatPage(): JSX.Element {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const parsedId = conversationId === undefined ? null : Number(conversationId);
  const invalidId = conversationId !== undefined
    && (!Number.isInteger(parsedId) || (parsedId ?? 0) <= 0);

  const {
    activeId,
    activeConversation,
    activateConversation,
    error,
    clearError,
  } = useChat();

  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!invalidId) {
      activateConversation(parsedId);
    }
    setSidebarOpen(false);
  }, [activateConversation, parsedId, invalidId]);

  if (invalidId) {
    return <Navigate to="/" replace />;
  }

  const title = activeConversation?.title
    ?? (activeId === null ? '新对话' : '对话');

  return (
    <div className="chat-shell">
      <ConversationSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="关闭对话列表"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <main className="chat-main">
        <header className="chat-header">
          <button
            type="button"
            className="icon-button menu-button"
            aria-label="打开对话列表"
            onClick={() => setSidebarOpen(true)}
          >
            <MenuIcon size={21} />
          </button>
          <h1 className="chat-title" title={title}>{title}</h1>
        </header>

        {error !== null && (
          <div className="chat-alert" role="alert">
            <AlertIcon size={17} />
            <span>{error}</span>
            <button
              type="button"
              className="chat-alert-close"
              aria-label="关闭提示"
              onClick={clearError}
            >
              <CloseIcon size={15} />
            </button>
          </div>
        )}

        <MessageList />
        <Composer key={activeId ?? 'new'} />
      </main>
    </div>
  );
}
