import { describe, expect, it } from 'vitest';
import type { User } from '../../frontend/src/api/types';
import {
  buildPayload,
  validateSettingsForm,
} from '../../frontend/src/utils/settingsForm';

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    username: 's001',
    display_name: '小明',
    grade: 8,
    grade_band: 'junior',
    role: 'student',
    ...overrides,
  };
}

describe('validateSettingsForm', () => {
  it('两值都没有变化时提示没有修改', () => {
    const user = makeUser();
    expect(validateSettingsForm(user, { displayName: '小明', grade: 8 }))
      .toBe('没有修改任何内容。');
  });

  it('名字只有首尾空格变化也算没有修改', () => {
    const user = makeUser();
    expect(validateSettingsForm(user, { displayName: '  小明  ', grade: 8 }))
      .toBe('没有修改任何内容。');
  });

  it('名字为空时不允许提交', () => {
    const user = makeUser();
    expect(validateSettingsForm(user, { displayName: '   ', grade: 9 }))
      .toBe('名字不能为空。');
  });

  it('名字超过 32 个字符时不允许提交', () => {
    const user = makeUser();
    expect(validateSettingsForm(user, { displayName: '名'.repeat(33), grade: 8 }))
      .toBe('名字不能超过 32 个字符。');
  });

  it('年级超出 1–12 时不允许提交', () => {
    const user = makeUser();
    expect(validateSettingsForm(user, { displayName: '小明', grade: 13 }))
      .toBe('年级请选择 1–12 之间的整数。');
  });

  it('合法的修改可以通过', () => {
    const user = makeUser();
    expect(validateSettingsForm(user, { displayName: '小红', grade: 9 })).toBeNull();
  });

  it('没有显示名的学生只改年级时不会被空名拦住', () => {
    const user = makeUser({ display_name: null });
    expect(validateSettingsForm(user, { displayName: '', grade: 9 })).toBeNull();
  });
});

describe('buildPayload', () => {
  it('只有名字变了，只提交 display_name', () => {
    const user = makeUser();
    expect(buildPayload(user, { displayName: '小红', grade: 8 }))
      .toStrictEqual({ display_name: '小红' });
  });

  it('只有年级变了，只提交 grade', () => {
    const user = makeUser();
    expect(buildPayload(user, { displayName: '小明', grade: 9 }))
      .toStrictEqual({ grade: 9 });
  });

  it('两者都变了，两个字段都提交', () => {
    const user = makeUser();
    expect(buildPayload(user, { displayName: '小红', grade: 10 }))
      .toStrictEqual({ display_name: '小红', grade: 10 });
  });

  it('都未修改时返回空对象', () => {
    const user = makeUser();
    expect(buildPayload(user, { displayName: ' 小明 ', grade: 8 })).toStrictEqual({});
  });

  it('名字提交前去掉首尾空格', () => {
    const user = makeUser();
    expect(buildPayload(user, { displayName: '  小红  ', grade: 8 }))
      .toStrictEqual({ display_name: '小红' });
  });
});
