import { useEffect, useRef } from 'react';
import JXG from 'jsxgraph';
import type { FigureSpec } from '../api/types';
import { figureBounds, fitAspect, initialValues } from '../utils/figure';
import { compileExpression, type Scope } from '../utils/figureExpr';

/** 图形使用的墨色，与练习纸风格一致。 */
const COLORS = {
  axis: '#83958b',
  curve: '#2f5d4c',
  line: '#4e6157',
  fill: 'rgba(191, 69, 48, 0.12)',
  fillLine: 'rgba(191, 69, 48, 0.4)',
  point: '#1d2e27',
  highlight: '#bf4530',
  label: '#1d2e27',
};

type Board = ReturnType<typeof JXG.JSXGraph.initBoard>;

export interface FigureBoardProps {
  spec: FigureSpec;
  /** 参数当前值；由面板持有，滑块、拖动与轨迹都改它。 */
  values: Record<string, number>;
  /** 拖动点时把新的参数值交给面板。 */
  onValues: (values: Record<string, number>) => void;
}

/** 找出"坐标就是某个参数"的点，这类点允许直接拖动。 */
function draggableParamsOf(spec: FigureSpec): Map<string, [string, string]> {
  const names = new Set((spec.parameters ?? []).map((parameter) => parameter.name));
  const result = new Map<string, [string, string]>();
  for (const point of spec.points ?? []) {
    const x = point.x.trim();
    const y = point.y.trim();
    if (names.has(x) && names.has(y) && x !== y) {
      result.set(point.id, [x, y]);
    }
  }
  return result;
}

/**
 * 用 JSXGraph 画一张可拖动、会动的图。
 *
 * - 点坐标、曲线、观察值都是算式，读 `values`；
 * - 坐标恰好是某个参数的点可以直接拖，拖动会改参数，其他元素跟着变；
 * - 面板里的滑块改参数时 `values` 变化，只重算不重建。
 */
export function FigureBoard({ spec, values, onValues }: FigureBoardProps): JSX.Element {
  const boxRef = useRef<HTMLDivElement>(null);
  const boardRef = useRef<Board | null>(null);
  const valuesRef = useRef(values);
  valuesRef.current = values;
  const onValuesRef = useRef(onValues);
  onValuesRef.current = onValues;

  useEffect(() => {
    const box = boxRef.current;
    if (box === null) {
      return undefined;
    }

    const board = JXG.JSXGraph.initBoard(box, {
      // 视窗先按内容算，再扩成画布的宽高比；不让 JSXGraph 自己裁。
      boundingbox: fitAspect(
        figureBounds(spec, valuesRef.current),
        box.clientWidth,
        box.clientHeight,
      ),
      axis: true,
      grid: false,
      keepaspectratio: false,
      showCopyright: false,
      showNavigation: false,
      showInfobox: false,
    });
    boardRef.current = board;

    const points = new Map<string, { coords: number[] }>();
    const draggable = draggableParamsOf(spec);

    const defaults = initialValues(spec);
    const currentScope = (): Scope => {
      const scope: Scope = { ...defaults, ...valuesRef.current };
      for (const [id, point] of points) {
        scope[id] = { x: point.coords[0] ?? NaN, y: point.coords[1] ?? NaN };
      }
      return scope;
    };

    for (const point of spec.points ?? []) {
      const xExpr = compileExpression(point.x);
      const yExpr = compileExpression(point.y);
      const canDrag = draggable.has(point.id);
      const color = point.role === 'highlight' ? COLORS.highlight : COLORS.point;
      const element = board.create(
        'point',
        [
          () => xExpr.evaluate(currentScope()),
          () => yExpr.evaluate(currentScope()),
        ],
        {
          name: point.label || point.id,
          size: canDrag ? 4 : 3,
          fixed: !canDrag,
          highlight: canDrag,
          showInfobox: false,
          strokeColor: color,
          fillColor: canDrag ? '#fdfefb' : color,
          strokeWidth: canDrag ? 2 : 1.5,
          label: { color, fontSize: 14, offset: [9, 9] },
        },
      );
      points.set(point.id, element as unknown as { coords: number[] });

      if (canDrag) {
        const [xParam, yParam] = draggable.get(point.id) as [string, string];
        element.on('drag', () => {
          const [x, y] = (element as unknown as { coords: number[] }).coords;
          if (x === undefined || y === undefined) {
            return;
          }
          onValuesRef.current({
            ...valuesRef.current,
            [xParam]: Math.round(x * 1000) / 1000,
            [yParam]: Math.round(y * 1000) / 1000,
          });
        });
      }
    }

    for (const curve of spec.curves ?? []) {
      const compiled = compileExpression(curve.expression);
      board.create(
        'functiongraph',
        [
          (x: number) => compiled.evaluate({ ...defaults, ...valuesRef.current, x }),
          () => curve.from ?? 0.1,
          () => curve.to ?? 9,
        ],
        { strokeColor: COLORS.curve, strokeWidth: 1.8, highlight: false, fixed: true },
      );
    }

    for (const segment of spec.segments ?? []) {
      const a = points.get(segment.from);
      const b = points.get(segment.to);
      if (a === undefined || b === undefined) continue;
      board.create('segment', [a, b], {
        strokeColor: COLORS.line,
        strokeWidth: 1.3,
        dash: segment.dashed === true ? 2 : 0,
        highlight: false,
        fixed: true,
      });
    }

    for (const polygon of spec.polygons ?? []) {
      const vertices = polygon.points
        .map((id) => points.get(id))
        .filter((item): item is { coords: number[] } => item !== undefined);
      if (vertices.length < 3) continue;
      board.create('polygon', vertices, {
        fillColor: COLORS.fill,
        fillOpacity: 1,
        strokeColor: COLORS.fillLine,
        strokeWidth: 1,
        borders: { strokeColor: COLORS.fillLine, strokeWidth: 1 },
        vertices: { visible: false },
        highlight: false,
        fixed: true,
      });
    }

    for (const circle of spec.circles ?? []) {
      const center = points.get(circle.center);
      if (center === undefined) continue;
      const radiusExpr = circle.radius == null
        ? null
        : compileExpression(circle.radius);
      let element;
      if (radiusExpr !== null) {
        // 半径给的是算式：JSXGraph 的"圆心 + 半径函数"形式。
        element = board.create(
          'circle',
          [center, () => radiusExpr.evaluate({ ...defaults, ...valuesRef.current })],
          {
            strokeColor: COLORS.curve,
            strokeWidth: 1.4,
            highlight: false,
            fixed: true,
          },
        );
      } else {
        const through = circle.through == null
          ? undefined
          : points.get(circle.through);
        if (through === undefined) continue;
        element = board.create('circle', [center, through], {
          strokeColor: COLORS.curve,
          strokeWidth: 1.4,
          highlight: false,
          fixed: true,
        });
      }
      void element;
    }

    return () => {
      boardRef.current = null;
      JXG.JSXGraph.freeBoard(board);
    };
    // 只在图本身变化时重建；参数变化走下面的 update。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec]);

  useEffect(() => {
    boardRef.current?.update();
  }, [values]);

  return <div className="figure-board" ref={boxRef} />;
}
