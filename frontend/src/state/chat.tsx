/**
 * 聊天状态的瘦 Provider：只做组合。
 *
 * - 用 useReducer 持有 chatReducer 的纯状态机；
 * - 调用 chatActions 里的各业务域 hook（会话列表、流消费、连发控制、图示面板），
 *   把它们的返回值拼成 context value；
 * - 唯一知道路由的地方：新建会话成功后跳转、删除当前会话后回到首页。
 *
 * reducer 实现在 chatReducer.ts，各域的回调与副作用在 chatActions.ts。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import type { Conversation, FigureSpec } from '../api/types';
import {
  useConversationList,
  useFigurePanel,
  useMessageStream,
  useSending,
} from './chatActions';
import {
  initialState,
  reducer,
  type ChatAction,
  type ChatState,
  type DisplayMessage,
  type ToolDisplayStatus,
} from './chatReducer';

// 供既有消费方（如 MessageBubble）继续从 '../state/chat' 引类型。
export type { ChatAction, ChatState, DisplayMessage, ToolDisplayStatus };

interface ChatContextValue {
  conversations: Conversation[];
  conversationsLoading: boolean;
  activeId: number | null;
  activeConversation: Conversation | null;
  messages: DisplayMessage[];
  messagesLoading: boolean;
  messagesError: string | null;
  sending: boolean;
  error: string | null;
  /** 右侧面板当前展示的图与展开状态。 */
  figure: FigureSpec | null;
  figureOpen: boolean;
  setFigure: (figure: FigureSpec | null) => void;
  setFigureOpen: (open: boolean) => void;
  openFigure: (figure: FigureSpec) => void;
  closeFigure: () => void;
  toggleFigure: () => void;
  activateConversation: (id: number | null) => void;
  reloadConversation: () => void;
  sendMessage: (text: string, attachmentIds: number[]) => Promise<boolean>;
  stopGeneration: () => void;
  renameConversation: (id: number, title: string) => Promise<void>;
  deleteConversation: (id: number) => Promise<void>;
  refreshConversations: () => Promise<void>;
  clearError: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }): JSX.Element {
  const [state, dispatch] = useReducer(reducer, initialState);
  const navigate = useNavigate();
  const stateRef = useRef(state);
  stateRef.current = state;

  const list = useConversationList(dispatch, state);
  const sending = useSending();
  const figurePanel = useFigurePanel();

  const onConversationCreated = useCallback((conversation: Conversation) => {
    navigate(`/c/${conversation.id}`, { replace: true });
  }, [navigate]);

  const stream = useMessageStream(dispatch, state, {
    sending,
    createConversation: list.createConversation,
    refresh: list.refresh,
    figure: figurePanel,
    onConversationCreated,
  });

  // 切回来的是仍在后台生成的会话时，轮询等它答完。
  useEffect(() => {
    const id = state.backgroundRunId;
    if (id === null || id !== state.activeId) {
      return undefined;
    }
    return stream.pollBackgroundRun(id);
  }, [state.backgroundRunId, state.activeId, stream.pollBackgroundRun]);

  const { markDone } = sending;
  const deleteConversation = useCallback(async (id: number) => {
    const wasActive = stateRef.current.activeId === id;
    const deletedId = await list.deleteConversation(id);
    if (deletedId !== null && wasActive) {
      markDone();
      navigate('/', { replace: true });
    }
  }, [list.deleteConversation, markDone, navigate]);

  const clearError = useCallback(() => {
    dispatch({ type: 'clear_error' });
  }, []);

  const activeConversation = useMemo(
    () => state.conversations.find((item) => item.id === state.activeId) ?? null,
    [state.conversations, state.activeId],
  );

  const value = useMemo<ChatContextValue>(
    () => ({
      conversations: state.conversations,
      conversationsLoading: state.conversationsLoading,
      activeId: state.activeId,
      activeConversation,
      messages: state.messages,
      messagesLoading: state.messagesLoading,
      messagesError: state.messagesError,
      sending: sending.sending,
      error: state.error,
      figure: figurePanel.figure,
      figureOpen: figurePanel.figureOpen,
      setFigure: figurePanel.setFigure,
      setFigureOpen: figurePanel.setFigureOpen,
      openFigure: figurePanel.openFigure,
      closeFigure: figurePanel.closeFigure,
      toggleFigure: figurePanel.toggleFigure,
      activateConversation: stream.activateConversation,
      reloadConversation: stream.reloadConversation,
      sendMessage: stream.sendMessage,
      stopGeneration: stream.stopGeneration,
      renameConversation: list.renameConversation,
      deleteConversation,
      refreshConversations: list.refresh,
      clearError,
    }),
    [
      state.conversations,
      state.conversationsLoading,
      state.activeId,
      state.messages,
      state.messagesLoading,
      state.messagesError,
      state.error,
      activeConversation,
      sending,
      figurePanel,
      stream,
      list,
      deleteConversation,
      clearError,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatContextValue {
  const context = useContext(ChatContext);
  if (context === null) {
    throw new Error('useChat 必须在 ChatProvider 内使用。');
  }
  return context;
}
