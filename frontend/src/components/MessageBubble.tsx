import { useCallback, useState } from 'react';
import type { DisplayMessage, ToolDisplayStatus } from '../state/chat';
import { AlertIcon, CheckIcon } from './Icons';
import { ImageLightbox } from './ImageLightbox';
import { MarkdownContent } from './MarkdownContent';

function ThinkingIndicator(): JSX.Element {
  return (
    <div className="thinking-indicator" role="status">
      <span className="thinking-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span>老师正在思考…</span>
    </div>
  );
}

function ToolStatusIcon({ state }: { state: ToolDisplayStatus['state'] }): JSX.Element {
  if (state === 'running') {
    return <span className="spinner tool-spinner" aria-hidden="true" />;
  }
  if (state === 'done') {
    return <CheckIcon size={14} />;
  }
  return <AlertIcon size={14} />;
}

function ToolStatusBar({ status }: { status: ToolDisplayStatus }): JSX.Element {
  return (
    <div className={`tool-status tool-status-${status.state}`} role="status">
      <ToolStatusIcon state={status.state} />
      {/* 只展示后端给的友好 label，不展示工具名、参数或结果。 */}
      <span className="tool-status-label">{status.label}</span>
    </div>
  );
}

function TypingDots(): JSX.Element {
  return (
    <span className="typing-dots" aria-label="老师正在回复">
      <span />
      <span />
      <span />
    </span>
  );
}

export function MessageBubble({ message }: { message: DisplayMessage }): JSX.Element {
  const [preview, setPreview] = useState<string | null>(null);
  const closePreview = useCallback(() => setPreview(null), []);
  const isUser = message.role === 'user';
  const hasStatus = Boolean(message.thinking || message.toolStatus);
  const showTyping = Boolean(message.streaming && message.text === '' && !hasStatus);
  const emptyAssistant = !isUser
    && message.text === ''
    && !message.streaming
    && !hasStatus
    && !message.notice
    && message.attachments.length === 0;

  if (emptyAssistant) {
    return <></>;
  }

  return (
    <div className={`message-row ${isUser ? 'message-row-user' : 'message-row-assistant'}`}>
      {!isUser && (
        <div className="assistant-avatar" aria-hidden="true">
          师
        </div>
      )}

      <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
        {message.attachments.length > 0 && (
          <div className="message-images">
            {message.attachments.map((attachment) => {
              const src = `/api/attachments/${attachment.id}`;
              return (
                <button
                  key={attachment.id}
                  type="button"
                  className="message-image-button"
                  aria-label="放大查看图片"
                  onClick={() => setPreview(src)}
                >
                  <img src={src} alt="学生上传的题目图片" loading="lazy" decoding="async" />
                </button>
              );
            })}
          </div>
        )}

        {message.text !== '' && (
          isUser
            ? <p className="user-text">{message.text}</p>
            : <MarkdownContent>{message.text}</MarkdownContent>
        )}

        {message.thinking && <ThinkingIndicator />}
        {message.toolStatus && <ToolStatusBar status={message.toolStatus} />}
        {showTyping && <TypingDots />}

        {message.notice && (
          <p className="message-notice" role="status">
            <AlertIcon size={14} />
            <span>{message.notice}</span>
          </p>
        )}
      </div>

      {preview !== null && (
        <ImageLightbox src={preview} onClose={closePreview} />
      )}
    </div>
  );
}
