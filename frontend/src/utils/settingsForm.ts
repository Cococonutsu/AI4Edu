import type { UpdateMePayload, User } from '../api/types';

/** 显示名长度上限，与后端契约一致。 */
export const DISPLAY_NAME_MAX = 32;

/** 年级范围，与后端契约一致。 */
export const GRADE_MIN = 1;
export const GRADE_MAX = 12;

export interface SettingsFormValues {
  displayName: string;
  grade: number;
}

function trimmedName(value: string): string {
  return value.trim();
}

function originalName(user: User): string {
  return (user.display_name ?? '').trim();
}

function nameChanged(user: User, values: SettingsFormValues): boolean {
  return trimmedName(values.displayName) !== originalName(user);
}

function gradeChanged(user: User, values: SettingsFormValues): boolean {
  return values.grade !== user.grade;
}

/**
 * 个人设置的客户端校验。返回第一条中文错误；可以提交时返回 null。
 * 只有真正改动过的字段才需要满足契约，避免没有显示名的学生只改年级时被空名拦住。
 */
export function validateSettingsForm(user: User, values: SettingsFormValues): string | null {
  if (!nameChanged(user, values) && !gradeChanged(user, values)) {
    return '没有修改任何内容。';
  }

  const name = trimmedName(values.displayName);
  if (nameChanged(user, values)) {
    if (name === '') {
      return '名字不能为空。';
    }
    if (name.length > DISPLAY_NAME_MAX) {
      return `名字不能超过 ${DISPLAY_NAME_MAX} 个字符。`;
    }
  }

  if (gradeChanged(user, values)) {
    if (!Number.isInteger(values.grade) || values.grade < GRADE_MIN || values.grade > GRADE_MAX) {
      return `年级请选择 ${GRADE_MIN}–${GRADE_MAX} 之间的整数。`;
    }
  }

  return null;
}

/** 只带上真正变化的字段，避免把未修改的值再写回后端。 */
export function buildPayload(user: User, values: SettingsFormValues): UpdateMePayload {
  const payload: UpdateMePayload = {};
  if (nameChanged(user, values)) {
    payload.display_name = trimmedName(values.displayName);
  }
  if (gradeChanged(user, values)) {
    payload.grade = values.grade;
  }
  return payload;
}
