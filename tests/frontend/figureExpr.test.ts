import { describe, expect, it } from 'vitest';
import {
  compileExpression,
  evaluateExpression,
  FigureExprError,
  formatFraction,
  formatNumber,
} from '../../frontend/src/utils/figureExpr';

describe('figureExpr', () => {
  it('按四则运算与括号求值', () => {
    expect(evaluateExpression('2+3*4', {})).toBe(14);
    expect(evaluateExpression('(2+3)*4', {})).toBe(20);
    expect(evaluateExpression('-a^2', { a: 3 })).toBe(-9);
    expect(evaluateExpression('2^3^2', {})).toBe(512);
  });

  it('可以使用参数与点坐标', () => {
    expect(evaluateExpression('a*b/4', { a: 4, b: 4 })).toBe(4);
    expect(evaluateExpression('C.x*C.y', { C: { x: 2, y: 3 } })).toBe(6);
  });

  it('支持白名单函数与 pi', () => {
    expect(evaluateExpression('sqrt(16)', {})).toBe(4);
    expect(evaluateExpression('max(1, 5)', {})).toBe(5);
    expect(evaluateExpression('pi', {})).toBeCloseTo(Math.PI);
    expect(evaluateExpression('sqrt(-1)', {})).toBeNaN();
  });

  it('除以 0 与未知名称返回 NaN，不抛异常', () => {
    expect(evaluateExpression('1/0', {})).toBeNaN();
    expect(evaluateExpression('Q.x', {})).toBeNaN();
  });

  it('拒绝不属于白名单的语法', () => {
    expect(() => compileExpression("__import__('os')")).toThrow(FigureExprError);
    expect(() => compileExpression('a;b')).toThrow(FigureExprError);
    expect(() => compileExpression('1+')).toThrow(FigureExprError);
  });

  it('能报出引用到的名称', () => {
    const compiled = compileExpression('a + C.x');
    expect([...compiled.names].sort()).toEqual(['C', 'a']);
  });

  it('格式化数值与分数', () => {
    expect(formatNumber(5)).toBe('5');
    expect(formatNumber(0.25)).toBe('0.25');
    expect(formatNumber(NaN)).toBe('—');
    expect(formatFraction(0.25)).toBe('1/4');
    expect(formatFraction(2.5)).toBe('5/2');
    expect(formatFraction(3)).toBe('3');
  });
});
