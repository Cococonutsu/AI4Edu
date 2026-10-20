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
import * as api from '../api/client';
import { describeError, isUnauthorized } from '../api/client';
import { readNdjsonStream } from '../api/stream';
import type {
  Conversation,
  ConversationPhase,
  FigureSpec,
  Message,
  ToolState,
  TurnStatus,
} from '../api/types';
import { waitKind, type WaitKind } from '../utils/waiting';

export interface ToolDisplayStatus {
  label: string;
  state: ToolState;
}

export interface DisplayMessage extends Message {
  /** 正在接收这个气泡的流式内容。 */
  streaming?: boolean;
  thinking?: boolean;
  toolStatus?: ToolDisplayStatus | null;
  /** 回合结束后的提示（已停止、出错等）。 */
  notice?: string | null;
  /** 开始等待的时间（毫秒时间戳），用于显示已等时长与阶段文案。 */
  waitStartedAt?: number;
  /** 这条消息是否带图，和会话阶段一起决定等待文案。 */
  hasImage?: boolean;
  /** 等待文案的种类；回合开始事件到达后按真实阶段修正。 */
  waitKind?: WaitKind;
  /** 这一回合老师打开过的图示。 */
  figures?: FigureSpec[];
}

interface ChatState {
  conversations: Conversation[];
  conversationsLoading: boolean;
  activeId: number | null;
  loadedId: number | null;
  suppressLoadId: number | null;
  messages: DisplayMessage[];
  messagesLoading: boolean;
  messagesError: string | null;
  sending: boolean;
  /** 当前正在接收的助手气泡 id，用来忽略上一个回合迟到的结束事件。 */
  streamTurnId: number | null;
  error: string | null;
  /** 右侧图示面板当前展示的图；null 表示还没有打开过。 */
  figure: FigureSpec | null;
  /** 面板是否展开（有图时默认展开，学生可以收起）。 */
  figureOpen: boolean;
}

type ChatAction =
  | { type: 'conversations_loading' }
  | { type: 'conversations_loaded'; items: Conversation[] }
  | { type: 'conversations_failed'; message: string | null }
  | { type: 'conversation_merged'; conversation: Conversation }
  | { type: 'conversation_created'; conversation: Conversation }
  | { type: 'conversation_renamed'; id: number; title: string }
  | { type: 'conversation_deleted'; id: number }
  | { type: 'activate'; id: number | null }
  | { type: 'suppress_load_cleared'; id: number }
  | { type: 'messages_loading'; id: number }
  | { type: 'messages_loaded'; id: number; messages: Message[] }
  | { type: 'messages_failed'; id: number; message: string }
  | {
      type: 'send_start';
      conversationId: number;
      userMessage: DisplayMessage;
      assistantMessage: DisplayMessage;
    }
  | {
      type: 'delta';
      conversationId: number;
      messageId: number;
      text: string;
    }
  | {
      type: 'turn_started';
      conversationId: number;
      messageId: number;
      phase: ConversationPhase | null;
    }
  | {
      type: 'thinking';
      conversationId: number;
      messageId: number;
      active: boolean;
    }
  | {
      type: 'tool_status';
      conversationId: number;
      messageId: number;
      status: ToolDisplayStatus | null;
    }
  | {
      type: 'stream_notice';
      conversationId: number;
      messageId: number;
      notice: string;
    }
  | {
      type: 'turn_finished';
      conversationId: number;
      turnId: number;
      status: TurnStatus;
    }
  | { type: 'send_end'; conversationId: number; turnId: number }
  | {
      type: 'figure_show';
      conversationId: number;
      figure: FigureSpec;
      fromHistory?: boolean;
    }
  | { type: 'figure_open'; conversationId: number; figure: FigureSpec | null }
  | { type: 'figure_close' }
  | { type: 'figure_toggle' }
  | { type: 'error'; message: string }
  | { type: 'clear_error' };

const initialState: ChatState = {
  conversations: [],
  conversationsLoading: true,
  activeId: null,
  loadedId: null,
  suppressLoadId: null,
  messages: [],
  messagesLoading: false,
  messagesError: null,
  sending: false,
  streamTurnId: null,
  error: null,
  figure: null,
  figureOpen: false,
};

let tempIdSeq = -1;

function nextTempId(): number {
  const id = tempIdSeq;
  tempIdSeq -= 1;
  return id;
}

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function sortConversations(items: Conversation[]): Conversation[] {
  return [...items].sort((a, b) => timestamp(b.updated_at) - timestamp(a.updated_at));
}

function mergeConversation(items: Conversation[], conversation: Conversation): Conversation[] {
  const exists = items.some((item) => item.id === conversation.id);
  if (!exists) {
    return sortConversations([conversation, ...items]);
  }
  return items.map((item) => (item.id === conversation.id ? { ...item, ...conversation } : item));
}

function updateMessage(
  messages: DisplayMessage[],
  messageId: number,
  update: (message: DisplayMessage) => DisplayMessage,
): DisplayMessage[] {
  return messages.map((message) => (message.id === messageId ? update(message) : message));
}

function noticeForStatus(status: TurnStatus): string | null {
  if (status === 'stopped') return '已停止生成。';
  if (status === 'error') return '这次回答没有完成，请再试一次。';
  return null;
}

function reducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'conversations_loading':
      return { ...state, conversationsLoading: true };

    case 'conversations_loaded':
      return {
        ...state,
        conversations: sortConversations(action.items),
        conversationsLoading: false,
      };

    case 'conversations_failed':
      return {
        ...state,
        conversationsLoading: false,
        error: action.message ?? state.error,
      };

    case 'conversation_merged':
      return {
        ...state,
        conversations: mergeConversation(state.conversations, action.conversation),
      };

    case 'conversation_created':
      return {
        ...state,
        conversations: mergeConversation(state.conversations, action.conversation),
        activeId: action.conversation.id,
        loadedId: action.conversation.id,
        suppressLoadId: action.conversation.id,
        messages: [],
        messagesLoading: false,
        messagesError: null,
        streamTurnId: null,
        error: null,
        figure: null,
        figureOpen: false,
      };

    case 'conversation_renamed':
      return {
        ...state,
        conversations: state.conversations.map((item) => (
          item.id === action.id ? { ...item, title: action.title } : item
        )),
      };

    case 'conversation_deleted': {
      const conversations = state.conversations.filter((item) => item.id !== action.id);
      if (state.activeId !== action.id) {
        return { ...state, conversations };
      }
      return {
        ...state,
        conversations,
        activeId: null,
        loadedId: null,
        suppressLoadId: null,
        messages: [],
        messagesLoading: false,
        messagesError: null,
        sending: false,
        streamTurnId: null,
      };
    }

    case 'activate': {
      if (action.id === state.activeId) {
        if (state.suppressLoadId === action.id) {
          return { ...state, suppressLoadId: null };
        }
        return state;
      }
      return {
        ...state,
        activeId: action.id,
        loadedId: null,
        suppressLoadId: null,
        messages: [],
        messagesLoading: action.id !== null,
        messagesError: null,
        sending: false,
        streamTurnId: null,
        error: null,
        // 切换会话时先清空图；加载完历史后再按最新的一张打开。
        figure: null,
        figureOpen: false,
      };
    }

    case 'suppress_load_cleared':
      return state.suppressLoadId === action.id
        ? { ...state, suppressLoadId: null }
        : state;

    case 'messages_loading':
      if (state.activeId !== action.id) {
        return state;
      }
      return { ...state, messagesLoading: true, messagesError: null };

    case 'messages_loaded':
      if (state.activeId !== action.id) {
        return state;
      }
      const messages = action.messages.map((message) => ({ ...message }));
      const lastFigure = [...messages]
        .reverse()
        .flatMap((message) => message.figures ?? [])[0] ?? null;
      return {
        ...state,
        messages,
        loadedId: action.id,
        messagesLoading: false,
        messagesError: null,
        figure: lastFigure ?? state.figure,
        figureOpen: lastFigure !== null ? true : state.figureOpen,
      };

    case 'messages_failed':
      if (state.activeId !== action.id) {
        return state;
      }
      return {
        ...state,
        messagesLoading: false,
        messagesError: action.message,
      };

    case 'send_start':
      if (state.activeId !== action.conversationId) {
        return state;
      }
      return {
        ...state,
        messages: [...state.messages, action.userMessage, action.assistantMessage],
        sending: true,
        streamTurnId: action.assistantMessage.id,
        error: null,
      };

    case 'delta':
      if (state.activeId !== action.conversationId) {
        return state;
      }
      return {
        ...state,
        messages: updateMessage(state.messages, action.messageId, (message) => ({
          ...message,
          text: message.text + action.text,
        })),
      };

    case 'turn_started':
      if (state.activeId !== action.conversationId) {
        return state;
      }
      return {
        ...state,
        messages: updateMessage(state.messages, action.messageId, (message) => ({
          ...message,
          waitKind: waitKind(action.phase, message.hasImage === true),
        })),
      };

    case 'thinking':
      if (state.activeId !== action.conversationId) {
        return state;
      }
      return {
        ...state,
        messages: updateMessage(state.messages, action.messageId, (message) => ({
          ...message,
          thinking: action.active,
        })),
      };

    case 'tool_status':
      if (state.activeId !== action.conversationId) {
        return state;
      }
      return {
        ...state,
        messages: updateMessage(state.messages, action.messageId, (message) => ({
          ...message,
          toolStatus: action.status,
        })),
      };

    case 'stream_notice':
      if (state.activeId !== action.conversationId) {
        return state;
      }
      return {
        ...state,
        messages: updateMessage(state.messages, action.messageId, (message) => ({
          ...message,
          notice: action.notice,
        })),
      };

    case 'turn_finished': {
      if (state.activeId !== action.conversationId || state.streamTurnId !== action.turnId) {
        return state;
      }
      const notice = noticeForStatus(action.status);
      return {
        ...state,
        sending: false,
        streamTurnId: null,
        messages: state.messages.map((message) => (
          message.streaming
            ? {
                ...message,
                streaming: false,
                thinking: false,
                toolStatus: message.toolStatus?.state === 'running' ? null : message.toolStatus,
                notice: message.notice ?? notice,
              }
            : message
        )),
      };
    }

    case 'send_end':
      if (state.activeId !== action.conversationId || state.streamTurnId !== action.turnId) {
        return state;
      }
      return {
        ...state,
        sending: false,
        streamTurnId: null,
        messages: state.messages.map((message) => (
          message.streaming
            ? {
                ...message,
                streaming: false,
                thinking: false,
                toolStatus: message.toolStatus?.state === 'running' ? null : message.toolStatus,
              }
            : message
        )),
      };

    case 'figure_show': {
      if (state.activeId !== action.conversationId) {
        return state;
      }
      const streaming = state.messages.filter((message) => message.streaming === true);
      const target = streaming[streaming.length - 1];
      return {
        ...state,
        messages: target === undefined
          ? state.messages
          : updateMessage(state.messages, target.id, (message) => ({
              ...message,
              figures: [...(message.figures ?? []), action.figure],
            })),
        figure: action.figure,
        // 历史加载时只恢复图，不改动学生当前的收起状态。
        figureOpen: action.fromHistory ? state.figureOpen : true,
      };
    }

    case 'figure_open':
      if (state.activeId !== action.conversationId) {
        return state;
      }
      return {
        ...state,
        figure: action.figure ?? state.figure,
        figureOpen: true,
      };

    case 'figure_close':
      return { ...state, figureOpen: false };

    case 'figure_toggle':
      return { ...state, figureOpen: !state.figureOpen };

    case 'error':
      return { ...state, error: action.message };

    case 'clear_error':
      return { ...state, error: null };

    default:
      return state;
  }
}

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
  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);
  const creatingRef = useRef(false);
  const loadingIdsRef = useRef(new Set<number>());

  const refreshConversations = useCallback(async () => {
    dispatch({ type: 'conversations_loading' });
    try {
      const items = await api.listConversations();
      dispatch({ type: 'conversations_loaded', items });
    } catch (error) {
      if (!isUnauthorized(error)) {
        dispatch({
          type: 'conversations_failed',
          message: describeError(error, '无法加载对话列表，请刷新页面重试。'),
        });
      } else {
        dispatch({ type: 'conversations_failed', message: null });
      }
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  useEffect(() => () => {
    abortRef.current?.abort();
    abortRef.current = null;
    sendingRef.current = false;
  }, []);

  const loadMessages = useCallback(async (id: number) => {
    if (loadingIdsRef.current.has(id)) {
      return;
    }
    loadingIdsRef.current.add(id);
    dispatch({ type: 'messages_loading', id });
    try {
      const detail = await api.getConversation(id);
      dispatch({ type: 'messages_loaded', id, messages: detail.messages });
      dispatch({ type: 'conversation_merged', conversation: detail });
    } catch (error) {
      if (!isUnauthorized(error)) {
        dispatch({
          type: 'messages_failed',
          id,
          message: describeError(error, '无法加载这个对话，请稍后重试。'),
        });
      }
    } finally {
      loadingIdsRef.current.delete(id);
    }
  }, []);

  const activateConversation = useCallback((id: number | null) => {
    const current = stateRef.current;

    if (id === current.activeId) {
      if (id !== null && current.suppressLoadId === id) {
        dispatch({ type: 'suppress_load_cleared', id });
        return;
      }
      if (id !== null && current.loadedId !== id && current.messagesError === null) {
        void loadMessages(id);
      }
      return;
    }

    if (current.sending) {
      abortRef.current?.abort();
      abortRef.current = null;
      sendingRef.current = false;
    }

    dispatch({ type: 'activate', id });
    if (id !== null) {
      void loadMessages(id);
    }
  }, [loadMessages]);

  const reloadConversation = useCallback(() => {
    const id = stateRef.current.activeId;
    if (id === null) {
      return;
    }
    loadingIdsRef.current.delete(id);
    void loadMessages(id);
  }, [loadMessages]);

  const runTurn = useCallback(async (
    conversationId: number,
    text: string,
    attachmentIds: number[],
    assistantId: number,
    controller: AbortController,
  ) => {
    let ended = false;
    let finishedByEvent = false;
    let receivedError = false;

    const endTurn = () => {
      if (ended) {
        return;
      }
      ended = true;
      if (abortRef.current === controller) {
        abortRef.current = null;
        sendingRef.current = false;
      }
      dispatch({ type: 'send_end', conversationId, turnId: assistantId });
      void refreshConversations();
    };

    try {
      const body = await api.sendMessage(conversationId, text, attachmentIds, controller.signal);
      for await (const event of readNdjsonStream(body)) {
        switch (event.type) {
          case 'turn_started':
            dispatch({
              type: 'turn_started',
              conversationId,
              messageId: assistantId,
              phase: event.phase ?? null,
            });
            break;

          case 'text_delta':
            dispatch({
              type: 'delta',
              conversationId,
              messageId: assistantId,
              text: event.text,
            });
            break;

          case 'thinking':
            dispatch({
              type: 'thinking',
              conversationId,
              messageId: assistantId,
              active: event.active,
            });
            break;

          case 'display':
            if (event.kind === 'figure') {
              dispatch({
                type: 'figure_show',
                conversationId,
                figure: event.payload as unknown as FigureSpec,
              });
            }
            break;

          case 'tool_status':
            dispatch({
              type: 'tool_status',
              conversationId,
              messageId: assistantId,
              status: {
                label: event.label,
                state: event.state,
              },
            });
            break;

          case 'turn_finished':
            finishedByEvent = true;
            dispatch({
              type: 'turn_finished',
              conversationId,
              turnId: assistantId,
              status: event.status,
            });
            break;

          case 'error':
            receivedError = true;
            dispatch({
              type: 'stream_notice',
              conversationId,
              messageId: assistantId,
              notice: event.message.trim() !== ''
                ? event.message
                : '服务暂时出了点问题，请稍后再试。',
            });
            break;

          case 'unknown':
            console.warn('[ai4edu] 收到未知的流事件类型：', event.eventType);
            break;

          default:
            break;
        }

        if (finishedByEvent) {
          break;
        }
      }

      if (!finishedByEvent) {
        if (controller.signal.aborted) {
          dispatch({
            type: 'stream_notice',
            conversationId,
            messageId: assistantId,
            notice: '已停止生成。',
          });
        } else if (!receivedError) {
          dispatch({
            type: 'stream_notice',
            conversationId,
            messageId: assistantId,
            notice: '回答意外中断，请再试一次。',
          });
        }
      }
    } catch (error) {
      if (controller.signal.aborted) {
        dispatch({
          type: 'stream_notice',
          conversationId,
          messageId: assistantId,
          notice: '已停止生成。',
        });
      } else if (!isUnauthorized(error)) {
        dispatch({
          type: 'stream_notice',
          conversationId,
          messageId: assistantId,
          notice: describeError(error, '网络连接中断，请检查网络后再试。'),
        });
      }
    } finally {
      endTurn();
    }
  }, [refreshConversations]);

  const sendMessage = useCallback(async (
    text: string,
    attachmentIds: number[],
  ): Promise<boolean> => {
    if (sendingRef.current || creatingRef.current) {
      return false;
    }

    let conversationId = stateRef.current.activeId;
    if (conversationId === null) {
      creatingRef.current = true;
      try {
        const created = await api.createConversation();
        conversationId = created.id;
        dispatch({ type: 'conversation_created', conversation: created });
        navigate(`/c/${created.id}`, { replace: true });
      } catch (error) {
        if (!isUnauthorized(error)) {
          dispatch({
            type: 'error',
            message: describeError(error, '创建对话失败，请稍后再试。'),
          });
        }
        return false;
      } finally {
        creatingRef.current = false;
      }
    }

    const now = new Date().toISOString();
    const userMessage: DisplayMessage = {
      id: nextTempId(),
      role: 'user',
      text,
      attachments: attachmentIds.map((id) => ({
        id,
        url: `/api/attachments/${id}`,
      })),
      created_at: now,
    };
    const assistantMessage: DisplayMessage = {
      id: nextTempId(),
      role: 'assistant',
      text: '',
      attachments: [],
      created_at: now,
      streaming: true,
      thinking: false,
      toolStatus: null,
      notice: null,
      waitStartedAt: Date.now(),
      hasImage: attachmentIds.length > 0,
      figures: [],
      // 回合开始事件到达前先按已有阶段给一个初值；后端告知真实阶段后再修正。
      waitKind: waitKind(
        stateRef.current.conversations.find((item) => item.id === conversationId)?.phase
          ?? null,
        attachmentIds.length > 0,
      ),
    };

    dispatch({
      type: 'send_start',
      conversationId,
      userMessage,
      assistantMessage,
    });

    const controller = new AbortController();
    abortRef.current = controller;
    sendingRef.current = true;
    void runTurn(conversationId, text, attachmentIds, assistantMessage.id, controller);
    return true;
  }, [navigate, runTurn]);

  const stopGeneration = useCallback(() => {
    const id = stateRef.current.activeId;
    if (id !== null) {
      void api.stopConversation(id).catch((error: unknown) => {
        if (!isUnauthorized(error)) {
          console.warn('[ai4edu] 停止生成请求失败：', error);
        }
      });
    }
    abortRef.current?.abort();
  }, []);

  const renameConversation = useCallback(async (id: number, title: string) => {
    const trimmed = title.trim();
    if (trimmed === '') {
      return;
    }
    try {
      await api.renameConversation(id, trimmed);
      dispatch({ type: 'conversation_renamed', id, title: trimmed });
    } catch (error) {
      if (!isUnauthorized(error)) {
        dispatch({
          type: 'error',
          message: describeError(error, '重命名失败，请稍后再试。'),
        });
      }
    }
  }, []);

  const deleteConversation = useCallback(async (id: number) => {
    try {
      await api.deleteConversation(id);
      const wasActive = stateRef.current.activeId === id;
      dispatch({ type: 'conversation_deleted', id });
      if (wasActive) {
        navigate('/', { replace: true });
      }
    } catch (error) {
      if (!isUnauthorized(error)) {
        dispatch({
          type: 'error',
          message: describeError(error, '删除对话失败，请稍后再试。'),
        });
      }
    }
  }, [navigate]);

  const clearError = useCallback(() => {
    dispatch({ type: 'clear_error' });
  }, []);

  const openFigure = useCallback((figure: FigureSpec) => {
    const id = stateRef.current.activeId;
    if (id !== null) {
      dispatch({ type: 'figure_open', conversationId: id, figure });
    }
  }, []);

  const closeFigure = useCallback(() => {
    dispatch({ type: 'figure_close' });
  }, []);

  const toggleFigure = useCallback(() => {
    dispatch({ type: 'figure_toggle' });
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
      sending: state.sending,
      error: state.error,
      figure: state.figure,
      figureOpen: state.figureOpen,
      openFigure,
      closeFigure,
      toggleFigure,
      activateConversation,
      reloadConversation,
      sendMessage,
      stopGeneration,
      renameConversation,
      deleteConversation,
      refreshConversations,
      clearError,
    }),
    [
      state.conversations,
      state.conversationsLoading,
      state.activeId,
      state.messages,
      state.messagesLoading,
      state.messagesError,
      state.sending,
      state.error,
      state.figure,
      state.figureOpen,
      openFigure,
      closeFigure,
      toggleFigure,
      activeConversation,
      activateConversation,
      reloadConversation,
      sendMessage,
      stopGeneration,
      renameConversation,
      deleteConversation,
      refreshConversations,
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

