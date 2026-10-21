import { describe, expect, it } from 'vitest';
import type { Message } from '../../frontend/src/api/types';
import { pendingReplyStart } from '../../frontend/src/utils/pendingReply';

function message(role: 'user' | 'assistant', createdAt: string, attachments = 0): Message {
  return {
    id: 1,
    role,
    text: 'x',
    attachments: Array.from({ length: attachments }, (_, i) => ({ id: i + 1, url: `/api/attachments/${i + 1}` })),
    created_at: createdAt,
  };
}

describe('pendingReplyStart', () => {
  it('回归 #25：切回仍在生成的对话时，补一个从学生发消息时算起的等待气泡', () => {
    const now = Date.parse('2026-10-20T08:00:30Z');
    const result = pendingReplyStart(
      [message('assistant', '2026-10-20T07:59:00Z'), message('user', '2026-10-20T08:00:00Z', 1)],
      true,
      now,
    );
    expect(result).toEqual({ startedAt: Date.parse('2026-10-20T08:00:00Z'), hasImage: true });
  });

  it('没有在生成时不补气泡', () => {
    expect(pendingReplyStart([message('user', '2026-10-20T08:00:00Z')], false)).toBeNull();
  });

  it('老师已经写出内容时不补气泡', () => {
    expect(
      pendingReplyStart([message('user', '2026-10-20T08:00:00Z'), message('assistant', '2026-10-20T08:00:20Z')], true),
    ).toBeNull();
  });

  it('时间无法解析或在未来时，按现在算', () => {
    const now = Date.parse('2026-10-20T08:00:00Z');
    expect(pendingReplyStart([message('user', 'bad')], true, now)?.startedAt).toBe(now);
    expect(pendingReplyStart([message('user', '2026-10-20T09:00:00Z')], true, now)?.startedAt).toBe(now);
  });
});
