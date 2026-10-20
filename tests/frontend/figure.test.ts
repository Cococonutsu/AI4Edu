import { describe, expect, it } from 'vitest';
import type { FigureSpec } from '../../frontend/src/api/types';
import { figureBounds, fitAspect, resolveScope } from '../../frontend/src/utils/figure';

// 学生实测的那张图（2026-10-19）：参数 a、k，A(a, 4k/a)，D 在 y=k/x 上。
const SPEC: FigureSpec = {
  title: '拖动 a，看 △BDE 的面积怎么变',
  parameters: [
    { name: 'a', value: 4, min: 1, max: 8 },
    { name: 'k', value: 4, min: 1, max: 8 },
  ],
  points: [
    { id: 'O', x: '0', y: '0' },
    { id: 'A', x: 'a', y: '4*k/a' },
    { id: 'B', x: 'a', y: '0' },
    { id: 'C', x: 'a/2', y: '2*k/a' },
    { id: 'D', x: 'a', y: 'k/a' },
    { id: 'E', x: 'a/2', y: '0' },
  ],
  curves: [{ expression: 'k/x', from: 0.5, to: 9 }],
  trajectory: [{ parameter: 'a', from: 2, to: 7 }],
};

describe('figure bounds', () => {
  it('回归 #20：参数还没设置时也按初值计算，不会缩成原点附近一小块', () => {
    const [left, top, right, bottom] = figureBounds(SPEC, {});
    // 旧实现在这里得到约 [-0.22, 0.22, 0.22, -0.22]。
    expect(right).toBeGreaterThan(8);
    expect(top).toBeGreaterThan(7);
    expect(left).toBeLessThan(0);
    expect(bottom).toBeLessThanOrEqual(0);
  });

  it('把移动轨迹的起止状态算进视窗', () => {
    const [, top] = figureBounds(SPEC, { a: 4, k: 4 });
    // a=2 时 A 的纵坐标是 4k/a = 8。
    expect(top).toBeGreaterThanOrEqual(8);
  });

  it('后面的点可以引用前面的点', () => {
    const scope = resolveScope(
      { title: 't', points: [{ id: 'A', x: '2', y: '3' }, { id: 'M', x: 'A.x/2', y: 'A.y/2' }] },
      {},
    );
    expect(scope.M).toEqual({ x: 1, y: 1.5 });
  });

  it('陡峭的曲线不会把图压扁', () => {
    const [, top] = figureBounds(
      { title: 't', points: [{ id: 'P', x: '1', y: '1' }], curves: [{ expression: '1/x', from: 0.01, to: 3 }] },
      {},
    );
    expect(top).toBeLessThan(5);
  });
});

describe('fitAspect', () => {
  it('只扩不裁：内容都在，且与画布同宽高比', () => {
    const box = fitAspect([-1, 20, 10, -2], 400, 320);
    const [left, top, right, bottom] = box;
    expect(left).toBeLessThanOrEqual(-1);
    expect(right).toBeGreaterThanOrEqual(10);
    expect(top).toBeGreaterThanOrEqual(20);
    expect(bottom).toBeLessThanOrEqual(-2);
    expect((right - left) / (top - bottom)).toBeCloseTo(400 / 320, 5);
  });

  it('画布尺寸未知时原样返回', () => {
    expect(fitAspect([0, 1, 1, 0], 0, 0)).toEqual([0, 1, 1, 0]);
  });
});

describe('circle', () => {
  const spec: FigureSpec = {
    title: '圆',
    parameters: [{ name: 'm', value: 0 }],
    points: [{ id: 'C', x: '0', y: 'm' }],
    circles: [{ center: 'C', radius: 'sqrt(m^2+12)' }],
  };

  it('回归 #22：圆按半径算式算进视窗', () => {
    const [left, top, right, bottom] = figureBounds(spec, { m: 0 });
    const r = Math.sqrt(12);
    expect(right).toBeGreaterThanOrEqual(r);
    expect(top).toBeGreaterThanOrEqual(r);
    expect(left).toBeLessThanOrEqual(-r);
    expect(bottom).toBeLessThanOrEqual(-r);
  });

  it('圆也可以用过某一点给出半径', () => {
    const withPoint: FigureSpec = {
      title: 't',
      points: [{ id: 'C', x: '0', y: '0' }, { id: 'P', x: '3', y: '4' }],
      circles: [{ center: 'C', through: 'P' }],
    };
    const [, top] = figureBounds(withPoint, {});
    expect(top).toBeGreaterThanOrEqual(5);
  });
});
