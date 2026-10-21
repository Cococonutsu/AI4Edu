import { useCallback, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../state/auth';
import { useChat } from '../state/chat';
import type { Conversation } from '../api/types';
import { formatConversationTime, gradeLabel, userDisplayName, userInitial } from '../utils/format';
import { CloseIcon, LogOutIcon, PencilIcon, PlusIcon, TrashIcon } from './Icons';
import { SettingsDialog } from './SettingsDialog';

interface ConversationSidebarProps {
  open: boolean;
  onClose: () => void;
  /** 桌面端收起（宽度为 0）；手机端仍用 open 控制抽屉。 */
  collapsed: boolean;
}

export function ConversationSidebar({
  open,
  onClose,
  collapsed,
}: ConversationSidebarProps): JSX.Element {
  const {
    conversations,
    conversationsLoading,
    activeId,
    renameConversation,
    deleteConversation,
  } = useChat();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [loggingOut, setLoggingOut] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const cancelledRef = useRef(false);
  const originalTitleRef = useRef('');

  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  function startNewConversation(): void {
    navigate('/');
    onClose();
  }

  function beginEditing(conversation: Conversation): void {
    cancelledRef.current = false;
    originalTitleRef.current = conversation.title;
    setDraft(conversation.title);
    setEditingId(conversation.id);
  }

  function commitEditing(): void {
    if (cancelledRef.current) {
      cancelledRef.current = false;
      setEditingId(null);
      return;
    }
    const id = editingId;
    const nextTitle = draft.trim();
    const originalTitle = originalTitleRef.current;
    setEditingId(null);
    if (id !== null && nextTitle !== '' && nextTitle !== originalTitle) {
      void renameConversation(id, nextTitle);
    }
  }

  function handleEditKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      event.currentTarget.blur();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      cancelledRef.current = true;
      event.currentTarget.blur();
    }
  }

  function handleDelete(conversation: Conversation): void {
    const confirmed = window.confirm(
      `确定删除对话“${conversation.title}”吗？删除后无法恢复。`,
    );
    if (!confirmed) {
      return;
    }
    const wasActive = activeId === conversation.id;
    void deleteConversation(conversation.id).then(() => {
      if (wasActive) {
        onClose();
      }
    });
  }

  async function handleLogout(): Promise<void> {
    if (loggingOut) {
      return;
    }
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
      navigate('/login', { replace: true });
    }
  }

  return (
    <>
      <aside
        className={`sidebar${open ? ' sidebar-open' : ''}${collapsed ? ' sidebar-collapsed' : ''}`}
        aria-label="对话列表"
        aria-hidden={collapsed && !open ? true : undefined}
      >
        <div className="sidebar-brand">
          <div className="brand-mark" aria-hidden="true">∑</div>
          <div className="brand-text">
            <div className="brand-name">AI4Edu</div>
            <div className="brand-sub">数学辅导</div>
          </div>
          <button
            type="button"
            className="sidebar-close"
            aria-label="收起对话列表"
            onClick={onClose}
          >
            <CloseIcon size={20} />
          </button>
        </div>

        <button type="button" className="new-chat-button" onClick={startNewConversation}>
          <PlusIcon size={18} />
          <span>新对话</span>
        </button>

        <div className="sidebar-section-label">我的对话</div>

        <nav className="conversation-list" aria-label="历史对话">
          {conversationsLoading && conversations.length === 0 && (
            <p className="sidebar-muted">
              <span className="spinner spinner-small" aria-hidden="true" />
              正在加载…
            </p>
          )}

          {!conversationsLoading && conversations.length === 0 && (
            <p className="sidebar-muted">还没有对话，从第一道题开始吧。</p>
          )}

          {conversations.map((conversation) => {
            const isActive = conversation.id === activeId;
            const isEditing = conversation.id === editingId;
            return (
              <div
                key={conversation.id}
                className={`conversation-item${isActive ? ' conversation-item-active' : ''}`}
              >
                {isEditing ? (
                  <input
                    className="conversation-edit-input"
                    value={draft}
                    autoFocus
                    maxLength={120}
                    aria-label="修改对话标题"
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={handleEditKeyDown}
                    onBlur={commitEditing}
                    onFocus={(event) => event.currentTarget.select()}
                  />
                ) : (
                  <>
                    <button
                      type="button"
                      className="conversation-main"
                      onClick={() => {
                        navigate(`/c/${conversation.id}`);
                        onClose();
                      }}
                    >
                      <span className="conversation-title">{conversation.title}</span>
                      <span className="conversation-time">
                        {conversation.running === true && conversation.id !== activeId ? (
                          <span className="conversation-running">
                            <span className="conversation-running-dot" aria-hidden="true" />
                            老师正在回答…
                          </span>
                        ) : (
                          formatConversationTime(conversation.updated_at)
                        )}
                      </span>
                    </button>
                    <div className="conversation-actions">
                      <button
                        type="button"
                        className="conversation-action"
                        aria-label={`重命名对话：${conversation.title}`}
                        title="重命名"
                        onClick={() => beginEditing(conversation)}
                      >
                        <PencilIcon size={15} />
                      </button>
                      <button
                        type="button"
                        className="conversation-action conversation-action-danger"
                        aria-label={`删除对话：${conversation.title}`}
                        title="删除"
                        onClick={() => handleDelete(conversation)}
                      >
                        <TrashIcon size={15} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          {user !== null && (
            <button
              type="button"
              className="user-card"
              aria-label="打开个人设置"
              onClick={() => setSettingsOpen(true)}
            >
              <span className="user-avatar" aria-hidden="true">{userInitial(user)}</span>
              <span className="user-details">
                <span className="user-name">{userDisplayName(user)}</span>
                <span className="user-meta">{gradeLabel(user.grade)}</span>
              </span>
            </button>
          )}
          <button
            type="button"
            className="logout-button"
            onClick={() => void handleLogout()}
            disabled={loggingOut}
          >
            <LogOutIcon size={17} />
            <span>{loggingOut ? '正在退出…' : '退出登录'}</span>
          </button>
        </div>
      </aside>
      <SettingsDialog open={settingsOpen} onClose={closeSettings} />
    </>
  );
}
