/**
 * 后台生成中的会话：切回来时判断要不要显示"老师还在回答"的等待气泡。
 *
 * 学生发完消息切到别的对话，后端会继续生成并按步存库。切回来时如果
 * 会话仍在生成、且最后一条是学生的消息，就补一个等待气泡，等待时长从
 * 学生发消息的时间算起。纯函数，便于测试。
 */

import type { Message } from '../api/types';

export interface PendingReply {
  /** 等待开始的时间（毫秒时间戳）：学生最后一条消息的发送时间。 */
  startedAt: number;
  /** 学生最后一条消息是否带图，用来选等待文案。 */
  hasImage: boolean;
}

export function pendingReplyStart(
  messages: Message[],
  running: boolean,
  now: number = Date.now(),
): PendingReply | null {
  if (!running) {
    return null;
  }
  const last = messages[messages.length - 1];
  if (last === undefined || last.role !== 'user') {
    // 老师已经写出了一部分（或还没有任何消息）：直接显示已有内容即可。
    return null;
  }
  const parsed = Date.parse(last.created_at);
  return {
    startedAt: Number.isNaN(parsed) ? now : Math.min(parsed, now),
    hasImage: last.attachments.length > 0,
  };
}
