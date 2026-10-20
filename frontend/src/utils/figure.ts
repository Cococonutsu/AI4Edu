/**
 * 图示的纯计算：参数初值、点坐标、观察值、视窗范围。
 *
 * 画布（`FigureBoard`）和面板（`FigurePanel`）都只调用这里，保证两边
 * 用同一套数，也便于测试。
 */

import type { FigureSpec } from '../api/types';
import { compileExpression, evaluateExpression, type Scope } from './figureExpr';

export type BoundingBox = [number, number, number, number];

/** 图描述里给出的参数初值。 */
export function initialValues(spec: FigureSpec | null): Record<string, number> {
  const values: Record<string, number> = {};
  for (const parameter of spec?.parameters ?? []) {
    values[parameter.name] = parameter.value;
  }
  return values;
}

/**
 * 按顺序计算每个点的坐标：后面的点可以引用前面的点（如 `C.x`）。
 *
 * `values` 里缺的参数用图描述的初值补上，所以即使调用方还没来得及
 * 设置参数，也不会全部变成 NaN。
 */
export function resolveScope(spec: FigureSpec, values: Record<string, number>): Scope {
  const scope: Scope = { ...initialValues(spec), ...values };
  for (const point of spec.points ?? []) {
    scope[point.id] = {
      x: compileExpression(point.x).evaluate(scope),
      y: compileExpression(point.y).evaluate(scope),
    };
  }
  return scope;
}

export function readoutValue(expression: string, scope: Scope): number {
  return evaluateExpression(expression, scope);
}

function isFinitePoint(value: unknown): value is { x: number; y: number } {
  return typeof value === 'object'
    && value !== null
    && Number.isFinite((value as { x: number }).x)
    && Number.isFinite((value as { y: number }).y);
}

/**
 * 视窗范围：覆盖原点、全部点，以及曲线在合理高度内的部分，四周留白。
 *
 * 曲线（如 $y=k/x$）在端点附近可能很高；只取不超过点的最大高度 2 倍的部分，
 * 免得一条曲线把图压扁。
 */
/**
 * 把视窗扩成与画布同样的宽高比（只扩不裁），x、y 同比例，直角看起来还是直角。
 */
export function fitAspect(box: BoundingBox, width: number, height: number): BoundingBox {
  if (!(width > 0) || !(height > 0)) {
    return box;
  }
  const [left, top, right, bottom] = box;
  const spanX = right - left;
  const spanY = top - bottom;
  const target = width / height;
  if (spanX / spanY < target) {
    const extra = (spanY * target - spanX) / 2;
    return [left - extra, top, right + extra, bottom];
  }
  const extra = (spanX / target - spanY) / 2;
  return [left, top + extra, right, bottom - extra];
}

export function figureBounds(spec: FigureSpec, values: Record<string, number>): BoundingBox {
  // 移动轨迹会把参数推到别的值：把起止状态都算进去，演示时点不会跑出画面。
  const states: Record<string, number>[] = [values];
  for (const step of spec.trajectory ?? []) {
    states.push({ ...values, [step.parameter]: step.from }, { ...values, [step.parameter]: step.to });
  }
  const boxes = states.map((state) => singleBounds(spec, state));
  return [
    Math.min(...boxes.map((box) => box[0])),
    Math.max(...boxes.map((box) => box[1])),
    Math.max(...boxes.map((box) => box[2])),
    Math.min(...boxes.map((box) => box[3])),
  ];
}

function singleBounds(spec: FigureSpec, values: Record<string, number>): BoundingBox {
  const scope = resolveScope(spec, values);
  const xs: number[] = [0];
  const ys: number[] = [0];
  for (const point of spec.points ?? []) {
    const value = scope[point.id];
    if (isFinitePoint(value)) {
      xs.push(value.x);
      ys.push(value.y);
    }
  }

  // 圆也要算进视窗，否则画出来会被裁掉。
  for (const circle of spec.circles ?? []) {
    const center = scope[circle.center];
    if (!isFinitePoint(center)) continue;
    let radius = NaN;
    if (circle.radius != null) {
      radius = evaluateExpression(circle.radius, scope);
    } else if (circle.through != null) {
      const through = scope[circle.through];
      if (isFinitePoint(through)) {
        radius = Math.hypot(through.x - center.x, through.y - center.y);
      }
    }
    if (!Number.isFinite(radius)) continue;
    xs.push(center.x - radius, center.x + radius);
    ys.push(center.y - radius, center.y + radius);
  }

  const pointTop = Math.max(...ys.map(Math.abs), 1);
  for (const curve of spec.curves ?? []) {
    const from = curve.from ?? 0.1;
    const to = curve.to ?? 9;
    xs.push(from, to);
    const compiled = compileExpression(curve.expression);
    for (let i = 0; i <= 60; i += 1) {
      const x = from + (to - from) * (i / 60);
      const y = compiled.evaluate({ ...scope, x });
      if (Number.isFinite(y) && Math.abs(y) <= pointTop * 2) {
        ys.push(y);
      }
    }
  }

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const padX = Math.max(maxX - minX, 1) * 0.1;
  const padY = Math.max(maxY - minY, 1) * 0.1;
  return [minX - padX, maxY + padY, maxX + padX, minY - padY];
}
