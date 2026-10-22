/**
 * 聊天各业务域的自定义 hook，从原 ChatProvider 的回调拆出。
 *
 * - useConversationList：会话列表的加载、刷新、合并，以及新建/重命名/删除。
 * - useMessageStream：runTurn 的流事件消费与 dispatch 翻译、发送、停止、
 *   当前会话的消息加载与切换、后台生成的轮询。
 * - useSending：连发控制的唯一真相（防重入锁 + 展示状态），
 *   收敛了原 Provider 的 sendingRef/creatingRef 与 Composer 的 submitLockRef。
 * - useFigurePanel：图示面板的开合状态（useState，不进 reducer）。
 *
 * 本文件不碰路由：需要跳转的流程把结果返回给 Provider（chat.tsx），
 * 由 Provider 决定 navigate。
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
} from 'react';
import * as api from '../api/client';
import { describeError, isUnauthorized } from '../api/client';
import { readNdjsonStream } from '../api/stream';
import type {
  Conversation,
  ConversationDetail,
  FigureSpec,
  Message,
} from '../api/types';
import { waitKind } from '../utils/waiting';
import type { ChatAction, ChatState, DisplayMessage } from './chatReducer';
import { nextTempId, pendingBubble } from './chatReducer';

/* ------------------------------ 会话列表域 ------------------------------ */

export interface ConversationListActions {
  refresh: () => Promise<void>;
  /** 新建会话；成功时已派发 conversation_created 并返回新会话，失败返回 null。 */
  createConversation: () => Promise<Conversation | null>;
  renameConversation: (id: number, title: string) => Promise<void>;
  /** 删除会话；成功返回被删的 id，失败返回 null。是否跳转由调用方决定。 */
  deleteConversation: (id: number) => Promise<number | null>;
}

export function useConversationList(
  dispatch: Dispatch<ChatAction>,
  state: ChatState,
): ConversationListActions {
  const refresh = useCallback(async () => {
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
    void refresh();
  }, [refresh]);

  // 侧边栏：有别的对话在后台生成时，定期刷新列表，让“正在回答”的标记按时消失。
  const anyBackgroundRunning = state.conversations.some(
    (item) => item.running === true && item.id !== state.activeId,
  );
  useEffect(() => {
    if (!anyBackgroundRunning) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refresh();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [anyBackgroundRunning, refresh]);

  const createConversation = useCallback(async (): Promise<Conversation | null> => {
    try {
      const created = await api.createConversation();
      dispatch({ type: 'conversation_created', conversation: created });
      return created;
    } catch (error) {
      if (!isUnauthorized(error)) {
        dispatch({
          type: 'error',
          message: describeError(error, '创建对话失败，请稍后再试。'),
        });
      }
      return null;
    }
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

  const deleteConversation = useCallback(async (id: number): Promise<number | null> => {
    try {
      await api.deleteConversation(id);
      dispatch({ type: 'conversation_deleted', id });
      return id;
    } catch (error) {
      if (!isUnauthorized(error)) {
        dispatch({
          type: 'error',
          message: describeError(error, '删除对话失败，请稍后再试。'),
        });
      }
      return null;
    }
  }, []);

  return useMemo(
    () => ({ refresh, createConversation, renameConversation, deleteConversation }),
    [refresh, createConversation, renameConversation, deleteConversation],
  );
}

/* ------------------------------- 连发控制域 ------------------------------- */

export interface SendingControl {
  /** 展示用：是否处于发送/创建中（供 Composer 的按钮状态消费）。 */
  sending: boolean;
  /** 命令式查询：当前是否允许发起新的发送。 */
  canSubmit: () => boolean;
  /** 占住防重入锁并进入发送展示态。 */
  markSending: () => void;
  /** 释放锁并结束发送展示态。 */
  markDone: () => void;
}

export function useSending(): SendingControl {
  const lockRef = useRef(false);
  const [sending, setSending] = useState(false);

  const canSubmit = useCallback(() => !lockRef.current, []);
  const markSending = useCallback(() => {
    lockRef.current = true;
    setSending(true);
  }, []);
  const markDone = useCallback(() => {
    lockRef.current = false;
    setSending(false);
  }, []);

  return useMemo(
    () => ({ sending, canSubmit, markSending, markDone }),
    [sending, canSubmit, markSending, markDone],
  );
}

/* ------------------------------- 图示面板域 ------------------------------- */

export interface FigurePanelControl {
  figure: FigureSpec | null;
  figureOpen: boolean;
  setFigure: (figure: FigureSpec | null) => void;
  setFigureOpen: (open: boolean) => void;
  /** 展示一张图并展开面板（流事件到达、点击消息里的图示入口时用）。 */
  openFigure: (figure: FigureSpec) => void;
  closeFigure: () => void;
  toggleFigure: () => void;
  /** 加载历史后恢复最新一张图；没有图时保持面板现状。 */
  restoreFromHistory: (messages: Message[]) => void;
  /** 切换或新建会话时清空面板。 */
  resetFigure: () => void;
}

export function useFigurePanel(): FigurePanelControl {
  const [figure, setFigure] = useState<FigureSpec | null>(null);
  const [figureOpen, setFigureOpen] = useState(false);

  const openFigure = useCallback((next: FigureSpec) => {
    setFigure(next);
    setFigureOpen(true);
  }, []);
  const closeFigure = useCallback(() => setFigureOpen(false), []);
  const toggleFigure = useCallback(() => setFigureOpen((open) => !open), []);
  const restoreFromHistory = useCallback((messages: Message[]) => {
    const lastFigure = [...messages]
      .reverse()
      .flatMap((message) => message.figures ?? [])[0] ?? null;
    if (lastFigure !== null) {
      setFigure(lastFigure);
      setFigureOpen(true);
    }
  }, []);
  const resetFigure = useCallback(() => {
    setFigure(null);
    setFigureOpen(false);
  }, []);

  return useMemo(
    () => ({
      figure,
      figureOpen,
      setFigure,
      setFigureOpen,
      openFigure,
      closeFigure,
      toggleFigure,
      restoreFromHistory,
      resetFigure,
    }),
    [figure, figureOpen, openFigure, closeFigure, toggleFigure, restoreFromHistory, resetFigure],
  );
}

/* -------------------------------- 流消费域 -------------------------------- */

export interface MessageStreamDeps {
  sending: SendingControl;
  /** 会话列表域提供的新建会话（成功时已派发 conversation_created）。 */
  createConversation: () => Promise<Conversation | null>;
  /** 会话列表域提供的刷新。 */
  refresh: () => Promise<void>;
  /** 图示面板域。 */
  figure: FigurePanelControl;
  /** 新会话创建成功后由 Provider 跳转（本域不碰路由）。 */
  onConversationCreated: (conversation: Conversation) => void;
}

export interface MessageStreamActions {
  /** 发送一条消息；正在发送或创建会话失败时返回 false。 */
  sendMessage: (text: string, attachmentIds: number[]) => Promise<boolean>;
  stopGeneration: () => void;
  /**
   * 轮询一个正在后台生成的会话直到它答完；返回清理函数。
   * 调用方（Provider）负责保证 id 是当前会话。
   */
  pollBackgroundRun: (id: number) => () => void;
  /** 激活（切换到）某个会话；切换时断开本页正在接收的流。 */
  activateConversation: (id: number | null) => void;
  /** 重新加载当前会话的消息。 */
  reloadConversation: () => void;
}

export function useMessageStream(
  dispatch: Dispatch<ChatAction>,
  state: ChatState,
  deps: MessageStreamDeps,
): MessageStreamActions {
  // 只解构各个稳定的回调作为依赖：sending/figure 这两个控制对象会随内部
  // 状态变化而更换标识，直接放进依赖数组会让下面的卸载清理被反复触发。
  const {
    canSubmit,
    markSending,
    markDone,
  } = deps.sending;
  const { createConversation } = deps;
  const { refresh } = deps;
  const {
    openFigure,
    restoreFromHistory,
    resetFigure,
  } = deps.figure;
  const { onConversationCreated } = deps;

  const stateRef = useRef(state);
  stateRef.current = state;
  const abortRef = useRef<AbortController | null>(null);
  const loadingIdsRef = useRef(new Set<number>());

  useEffect(() => () => {
    abortRef.current?.abort();
    abortRef.current = null;
    markDone();
  }, [markDone]);

  const loadMessages = useCallback(async (id: number) => {
    if (loadingIdsRef.current.has(id)) {
      return;
    }
    loadingIdsRef.current.add(id);
    dispatch({ type: 'messages_loading', id });
    try {
      const detail: ConversationDetail = await api.getConversation(id);
      dispatch({
        type: 'messages_loaded',
        id,
        messages: detail.messages,
        running: detail.running === true,
        pending: pendingBubble(detail),
      });
      dispatch({ type: 'conversation_merged', conversation: detail });
      // 下面的展示态迁移与旧 reducer 的 messages_loaded 分支同步：只在
      // 这个会话仍是当前会话时生效（加载途中切走时不污染新会话的界面）。
      if (stateRef.current.activeId === id) {
        // 本页不在接收流时，按后端的 running 进入或结束“后台等待”的展示态。
        if (stateRef.current.streamTurnId === null) {
          if (detail.running === true) {
            markSending();
          } else {
            markDone();
          }
        }
        restoreFromHistory(detail.messages);
      }
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
  }, [markSending, markDone, restoreFromHistory]);

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
      // 只断开本页对这条流的接收；后端会继续把回答生成完并存库，
      // 切回来时按 running 显示等待并轮询（不调用 /stop）。
      abortRef.current?.abort();
      abortRef.current = null;
      markDone();
    }

    // 切换会话时先清空面板；加载完历史后再按最新的一张打开。
    resetFigure();
    dispatch({ type: 'activate', id });
    if (id !== null) {
      void loadMessages(id);
    }
  }, [loadMessages, markDone, resetFigure]);

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
        markDone();
      }
      dispatch({ type: 'send_end', conversationId, turnId: assistantId });
      void refresh();
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
              const spec = event.payload as unknown as FigureSpec;
              // 消息上记一笔（供气泡里的图示入口使用），面板由图示域展开。
              dispatch({ type: 'figure_displayed', conversationId, figure: spec });
              openFigure(spec);
            }
            break;

          case 'tool_status':
            dispatch({
              type: 'tool_status',
              conversationId,
              messageId: assistantId,
              status: {
                tool: event.tool,
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
  }, [refresh, markDone, openFigure]);

  const sendMessage = useCallback(async (
    text: string,
    attachmentIds: number[],
  ): Promise<boolean> => {
    if (!canSubmit()) {
      return false;
    }
    markSending();

    let conversationId = stateRef.current.activeId;
    if (conversationId === null) {
      const created = await createConversation();
      if (created === null) {
        markDone();
        return false;
      }
      conversationId = created.id;
      resetFigure();
      onConversationCreated(created);
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
    void runTurn(conversationId, text, attachmentIds, assistantMessage.id, controller);
    return true;
  }, [canSubmit, markSending, markDone, createConversation, resetFigure, onConversationCreated, runTurn]);

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

  const pollBackgroundRun = useCallback((id: number): (() => void) => {
    let cancelled = false;
    const timer = window.setInterval(() => {
      void api.getConversation(id).then((detail) => {
        if (cancelled || detail.running === true) {
          return;
        }
        dispatch({ type: 'messages_loaded', id, messages: detail.messages, running: false });
        dispatch({ type: 'conversation_merged', conversation: detail });
        // 与 reducer 的 activeId 守卫同步：切走后到达的最后一轮不碰界面态。
        if (stateRef.current.activeId === id) {
          markDone();
          restoreFromHistory(detail.messages);
        }
        void refresh();
      }).catch(() => {
        // 网络抖动：下一次再看。
      });
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [markDone, restoreFromHistory, refresh]);

  return useMemo(
    () => ({
      sendMessage,
      stopGeneration,
      pollBackgroundRun,
      activateConversation,
      reloadConversation,
    }),
    [sendMessage, stopGeneration, pollBackgroundRun, activateConversation, reloadConversation],
  );
}
