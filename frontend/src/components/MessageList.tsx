import { useCallback, useEffect, useRef, type UIEvent } from 'react';
import { useChat } from '../state/chat';
import { AlertIcon } from './Icons';
import { MessageBubble } from './MessageBubble';

const NEAR_BOTTOM_PX = 80;

const EXAMPLES = [
  { label: '这题怎么做', text: '这道题怎么做？', needProblem: true },
  { label: '求根公式是什么', text: '求根公式是什么？', needProblem: false },
  { label: '帮我核对一个式子', text: 'x = (-b + sqrt(b^2 - 4ac)) / (2a) 这个式子写对了吗？', needProblem: false },
];

function Welcome({ onExample }: { onExample: (text: string) => void }): JSX.Element {
  return (
    <div className="welcome">
      <div className="welcome-mark" aria-hidden="true">∑</div>
      <h1>今天想想哪道题？</h1>
      <p>把题目发给我，或者拍照上传。我会先看懂题，再一步一步陪你想。</p>
      <p className="welcome-hint">也可以直接问一个知识点，或者让我帮你核对写下的式子。</p>

      <div className="welcome-examples">
        <span className="welcome-examples-label">试试这样问</span>
        {EXAMPLES.map((example) => (
          <button
            type="button"
            key={example.label}
            className="welcome-chip"
            onClick={() => onExample(example.text)}
          >
            {example.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function LoadingConversation(): JSX.Element {
  return (
    <div className="loading-state" role="status">
      <span className="spinner spinner-large" aria-hidden="true" />
      <span>正在打开对话…</span>
    </div>
  );
}

function ConversationError({ message, onRetry }: { message: string; onRetry: () => void }): JSX.Element {
  return (
    <div className="error-state" role="alert">
      <AlertIcon size={22} />
      <p>{message}</p>
      <button type="button" className="secondary-button" onClick={onRetry}>
        重新加载
      </button>
    </div>
  );
}

export function MessageList(): JSX.Element {
  const {
    activeId,
    messages,
    messagesLoading,
    messagesError,
    reloadConversation,
    sendMessage,
  } = useChat();

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const lastActiveRef = useRef<number | null | undefined>(undefined);
  const previousCountRef = useRef(0);

  const scrollToBottom = useCallback(() => {
    const element = scrollRef.current;
    if (element !== null) {
      element.scrollTop = element.scrollHeight;
    }
  }, []);

  useEffect(() => {
    if (lastActiveRef.current !== activeId) {
      lastActiveRef.current = activeId;
      previousCountRef.current = messages.length;
      stickToBottomRef.current = true;
      const frame = requestAnimationFrame(scrollToBottom);
      return () => cancelAnimationFrame(frame);
    }

    if (messages.length > previousCountRef.current) {
      // 自己刚发出消息（或助手气泡刚出现）时，回到最新内容。
      stickToBottomRef.current = true;
    }
    previousCountRef.current = messages.length;

    if (stickToBottomRef.current) {
      const frame = requestAnimationFrame(scrollToBottom);
      return () => cancelAnimationFrame(frame);
    }
    return undefined;
  }, [activeId, messages, scrollToBottom]);

  const handleScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    stickToBottomRef.current = distance < NEAR_BOTTOM_PX;
  }, []);

  return (
    <div className="message-scroll" ref={scrollRef} onScroll={handleScroll}>
      <div className="message-column">
        {messagesLoading ? (
          <LoadingConversation />
        ) : messagesError !== null ? (
          <ConversationError message={messagesError} onRetry={reloadConversation} />
        ) : messages.length === 0 ? (
          <Welcome onExample={(text) => void sendMessage(text, [])} />
        ) : (
          messages.map((message, index) => (
            <MessageBubble key={`${message.id}-${index}`} message={message} />
          ))
        )}
      </div>
    </div>
  );
}
