import { describe, expect, it } from 'vitest';
import {
  formatElapsed,
  toolRunningNote,
  waitKind,
  waitStage,
} from '../../frontend/src/utils/waiting';

describe('waitKind', () => {
  it('带图一律按读题处理', () => {
    expect(waitKind('idle', true)).toBe('image');
    expect(waitKind('tutoring', true)).toBe('image');
  });

  it('不带图时按会话阶段区分', () => {
    expect(waitKind(null, false)).toBe('idle');
    expect(waitKind('idle', false)).toBe('idle');
    expect(waitKind('tutoring', false)).toBe('tutoring');
    expect(waitKind('extension', false)).toBe('tutoring');
    expect(waitKind('completed', false)).toBe('completed');
  });
});

describe('waitStage', () => {
  it('文案随等待时长变化，不会一直停在同一句', () => {
    const labels = [0, 5000, 18000, 45000, 90000].map((ms) => waitStage('image', ms).label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it('刚开始不打扰，等久了才给一句可以做的事', () => {
    expect(waitStage('image', 1000).note).toBeNull();
    expect(waitStage('image', 20000).note).not.toBeNull();
    expect(waitStage('tutoring', 50000).note).toContain('停止');
  });

  it('阶段是单调推进的', () => {
    expect(waitStage('tutoring', 7000).label).toBe(waitStage('tutoring', 19000).label);
    expect(waitStage('tutoring', 21000).label).not.toBe(waitStage('tutoring', 19000).label);
  });
});

describe('formatElapsed', () => {
  it('一分钟以内只显示秒', () => {
    expect(formatElapsed(0)).toBe('已等 0 秒');
    expect(formatElapsed(12_900)).toBe('已等 12 秒');
  });

  it('超过一分钟显示分和两位秒', () => {
    expect(formatElapsed(65_000)).toBe('已等 1 分 05 秒');
  });

  it('负数按 0 处理', () => {
    expect(formatElapsed(-500)).toBe('已等 0 秒');
  });
});


describe('toolRunningNote', () => {
  it('联网搜索给一句同风格的补充提示', () => {
    expect(toolRunningNote('web_search')).toBe('老师上网查资料去了，稍等一下。');
  });

  it('读网页给一句同风格的补充提示', () => {
    expect(toolRunningNote('web_fetch')).toBe('老师在读网页，有时要多等几秒。');
  });

  it('其它工具没有补充提示', () => {
    expect(toolRunningNote('analyze_problem')).toBeNull();
    expect(toolRunningNote('record_diagnosis')).toBeNull();
    expect(toolRunningNote('draw_figure')).toBeNull();
  });
});
