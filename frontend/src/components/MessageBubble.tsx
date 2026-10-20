import { useCallback, useEffect, useState } from 'react';
import type { FigureSpec } from '../api/types';
import type { DisplayMessage, ToolDisplayStatus } from '../state/chat';
import { useChat } from '../state/chat';
import { formatElapsed, waitStage } from '../utils/waiting';
import { AlertIcon, CheckIcon, ShapeIcon } from './Icons';
import { ImageLightbox } from './ImageLightbox';
import { MarkdownContent } from './MarkdownContent';

/** 等待期间每隔一秒刷新一次，让"已等 N 秒"真的在走。 */
function useElapsed(startedAt: number | undefined, active: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active || startedAt === undefined) {
      return undefined;
    }
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active, startedAt]);

  if (startedAt === undefined) {
    return 0;
  }
  return Math.max(0, now - startedAt);
}

function Dots(): JSX.Element {
  return (
    <span className="thinking-dots" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

/**
 * 等待状态：老师还没开口时显示。
 *
 * - 工具正在执行：显示工具给出的友好状态（"正在读题…"）。
 * - 工具刚完成、还没开始写：先显示打勾的完成状态，下一条是当前阶段。
 * - 其余时间：显示按已等时长变化的阶段文案。
 * - 右侧始终显示已等时长，下方在等得较久时给一句学生可以顺手做的事。
 */
function WaitingStatus({
  message,
  elapsedMs,
}: {
  message: DisplayMessage;
  elapsedMs: number;
}): JSX.Element {
  const kind = message.waitKind ?? 'idle';
  const stage = waitStage(kind, elapsedMs);
  const tool: ToolDisplayStatus | null = message.toolStatus ?? null;
  const toolRunning = tool?.state === 'running';
  const toolDone = tool?.state === 'done';

  return (
    <div className="waiting" role="status" aria-live="polite">
      <div className="waiting-row">
        {toolRunning ? (
          <span className="spinner tool-spinner" aria-hidden="true" />
        ) : toolDone ? (
          <span className="waiting-check">
            <CheckIcon size={14} />
          </span>
        ) : (
          <Dots />
        )}
        <span className="waiting-label">
          {tool !== null ? tool.label : stage.label}
        </span>
        <span className="waiting-elapsed">{formatElapsed(elapsedMs)}</span>
      </div>

      {toolDone && <div className="waiting-sub">{stage.label}</div>}

      {stage.note !== null && !toolRunning && (
        <p className="waiting-note">{stage.note}</p>
      )}

      <span className="waiting-bar" aria-hidden="true" />
    </div>
  );
}

/** 关掉面板后，消息里留一个入口可以重新打开这一回合的图。 */
function FigureChip({ figure }: { figure: FigureSpec }): JSX.Element {
  const { openFigure } = useChat();
  return (
    <button
      type="button"
      className="figure-chip"
      onClick={() => openFigure(figure)}
      title="在右侧打开图示"
    >
      <ShapeIcon size={14} />
      <span>{figure.title || '打开图示'}</span>
    </button>
  );
}

export function MessageBubble({ message }: { message: DisplayMessage }): JSX.Element {
  const [preview, setPreview] = useState<string | null>(null);
  const closePreview = useCallback(() => setPreview(null), []);
  const isUser = message.role === 'user';

  const waiting = !isUser && message.streaming === true && message.text === '';
  const elapsedMs = useElapsed(message.waitStartedAt, waiting);

  const emptyAssistant = !isUser
    && message.text === ''
    && !message.streaming
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

        {!isUser && (message.figures ?? []).map((figure, index) => (
          <FigureChip key={`${figure.title}-${index}`} figure={figure} />
        ))}

        {waiting && <WaitingStatus message={message} elapsedMs={elapsedMs} />}

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
