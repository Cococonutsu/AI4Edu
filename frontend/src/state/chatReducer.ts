/**
 * 聊天域的纯 reducer：ChatState / ChatAction / DisplayMessage 类型与全部状态迁移。
 *
 * 无 React 依赖、无副作用。会话列表、消息加载、发送回合、NDJSON 流事件的
 * 结果都先翻译成 ChatAction 再到这里更新状态；图示面板的开合状态不在本文件
 * （由 Provider 层的 useState 管理，见 chatActions.ts 的 useFigurePanel）。
 */

import type {
  Conversation,
  ConversationPhase,
  FigureSpec,
  Message,
  ToolState,
  TurnStatus,
} from '../api/types';
import { pendingReplyStart } from '../utils/pendingReply';
import { waitKind, type WaitKind } from '../utils/waiting';

export interface ToolDisplayStatus {
  tool: string;
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

export interface ChatState {
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
  /** 正在后台生成、本页没有接着流的会话 id（切回来后轮询等它答完）。 */
  backgroundRunId: number | null;
  error: string | null;
}

export type ChatAction =
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
  | {
      type: 'messages_loaded';
      id: number;
      messages: Message[];
      /** 后端说这个会话还在生成。 */
      running?: boolean;
      /** 还在生成且最后一条是学生消息时补的等待气泡。 */
      pending?: DisplayMessage | null;
    }
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
      /** 流中老师展示了一张图：把它记到正在流式的消息上（面板开合走 Provider 的 useState）。 */
      type: 'figure_displayed';
      conversationId: number;
      figure: FigureSpec;
    }
  | { type: 'error'; message: string }
  | { type: 'clear_error' };

export const initialState: ChatState = {
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
  backgroundRunId: null,
  error: null,
};

let tempIdSeq = -1;

/** 乐观更新用的临时消息 id（负数，不与后端 id 冲突）。 */
export function nextTempId(): number {
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

export function reducer(state: ChatState, action: ChatAction): ChatState {
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
        backgroundRunId: null,
        error: null,
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
        backgroundRunId: null,
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
        backgroundRunId: null,
        error: null,
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
      const messages: DisplayMessage[] = action.messages.map((message) => ({ ...message }));
      // 本页正在接收流时不碰发送状态；否则按后端的 running 进入或结束“后台等待”。
      const foreground = state.streamTurnId !== null;
      const running = !foreground && action.running === true;
      if (running && action.pending) {
        messages.push(action.pending);
      }
      return {
        ...state,
        messages,
        loadedId: action.id,
        messagesLoading: false,
        messagesError: null,
        sending: foreground ? state.sending : running,
        backgroundRunId: running ? action.id : null,
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

    case 'figure_displayed': {
      if (state.activeId !== action.conversationId) {
        return state;
      }
      const streaming = state.messages.filter((message) => message.streaming === true);
      const target = streaming[streaming.length - 1];
      if (target === undefined) {
        return state;
      }
      return {
        ...state,
        messages: updateMessage(state.messages, target.id, (message) => ({
          ...message,
          figures: [...(message.figures ?? []), action.figure],
        })),
      };
    }

    case 'error':
      return { ...state, error: action.message };

    case 'clear_error':
      return { ...state, error: null };

    default:
      return state;
  }
}

/** 会话还在后台生成、最后一条是学生消息时，补一个等待气泡。 */
export function pendingBubble(detail: Conversation & { messages: Message[] }): DisplayMessage | null {
  const pending = pendingReplyStart(detail.messages, detail.running === true);
  if (pending === null) {
    return null;
  }
  return {
    id: nextTempId(),
    role: 'assistant',
    text: '',
    attachments: [],
    created_at: new Date(pending.startedAt).toISOString(),
    streaming: true,
    thinking: false,
    toolStatus: null,
    notice: null,
    waitStartedAt: pending.startedAt,
    hasImage: pending.hasImage,
    waitKind: waitKind(detail.phase, pending.hasImage),
    figures: [],
  };
}
