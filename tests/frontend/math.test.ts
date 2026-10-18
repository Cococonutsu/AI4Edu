import { describe, expect, it } from 'vitest';
import { normalizeMathDelimiters } from '../../frontend/src/utils/math';

describe('normalizeMathDelimiters', () => {
  it('把 \\( \\) 转成行内公式', () => {
    expect(normalizeMathDelimiters('设 \\(C(a, \\frac{k}{a})\\) 在图象上')).toBe(
      '设 $C(a, \\frac{k}{a})$ 在图象上',
    );
  });

  it('把 \\[ \\] 转成独立公式', () => {
    expect(normalizeMathDelimiters('面积为\\[S=\\frac{k}{4}\\]所以')).toBe(
      '面积为\n$$\nS=\\frac{k}{4}\n$$\n所以',
    );
  });

  it('已有的 $ 公式保持不变', () => {
    const text = '行内 $x^2$ 与独立 $$y=\\frac{k}{x}$$';
    expect(normalizeMathDelimiters(text)).toBe(text);
  });

  it('代码中的反斜杠括号不处理', () => {
    const text = '代码 `\\(x\\)` 和\n```\n\\[y\\]\n```';
    expect(normalizeMathDelimiters(text)).toBe(text);
  });
});
