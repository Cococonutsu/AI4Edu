import type { User } from '../api/types';

/** 把年级数字转成学生和家长都熟悉的中文说法。 */
export function gradeLabel(grade: number): string {
  if (grade >= 1 && grade <= 6) {
    return `${grade}年级`;
  }
  if (grade === 7) return '初一';
  if (grade === 8) return '初二';
  if (grade === 9) return '初三';
  if (grade === 10) return '高一';
  if (grade === 11) return '高二';
  if (grade === 12) return '高三';
  return '学生';
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/** 会话列表里的简短时间：今天显示时刻，昨天显示“昨天”，更早显示日期。 */
export function formatConversationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const time = date.getTime();
  const dayMs = 24 * 60 * 60 * 1000;

  if (time >= startOfToday) {
    return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  }
  if (time >= startOfToday - dayMs) {
    return '昨天';
  }
  if (date.getFullYear() === now.getFullYear()) {
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  }
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

export function userDisplayName(user: User): string {
  const displayName = user.display_name?.trim() ?? '';
  return displayName !== '' ? displayName : (user.username || '学生');
}

export function userInitial(user: User): string {
  const name = userDisplayName(user);
  const chars = Array.from(name);
  return chars[0] ?? '学';
}
