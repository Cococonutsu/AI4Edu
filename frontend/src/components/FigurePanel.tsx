import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FigureParameter, FigureSpec } from '../api/types';
import { initialValues, readoutValue, resolveScope } from '../utils/figure';
import { formatFraction, formatNumber } from '../utils/figureExpr';
import { FigureBoard } from './FigureBoard';
import { ChevronRightIcon, CloseIcon, PlayIcon, ShapeIcon } from './Icons';

interface FigurePanelProps {
  spec: FigureSpec | null;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}

function parameterLabel(parameter: FigureParameter): string {
  return parameter.label?.trim() || parameter.name;
}

/**
 * 右侧图示面板：图 + 观察值 + 可拖动参数。
 *
 * 图由 `draw_figure` 给出；观察值随参数（滑块、拖动点、移动轨迹）实时重算。
 */
export function FigurePanel({ spec, open, onToggle, onClose }: FigurePanelProps): JSX.Element | null {
  const [values, setValues] = useState<Record<string, number>>(() => initialValues(spec));
  const [valuesFor, setValuesFor] = useState<FigureSpec | null>(spec);
  const [playing, setPlaying] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const frameRef = useRef(0);

  // 换了一张图：在本次渲染里就把参数重置为新图的初值，画布第一次创建时
  // 拿到的就是正确的数（回归 #20：先用空参数建板，视窗缩成原点附近一小块）。
  let current = values;
  if (valuesFor !== spec) {
    current = initialValues(spec);
    setValuesFor(spec);
    setValues(current);
    setPlaying(false);
    setNote(null);
  }

  useEffect(() => () => cancelAnimationFrame(frameRef.current), [spec]);

  const runTrajectory = useCallback((current: FigureSpec) => {
    const steps = current.trajectory ?? [];
    if (steps.length === 0) {
      return;
    }
    cancelAnimationFrame(frameRef.current);
    setPlaying(true);
    let index = 0;
    let started = 0;

    const tick = (now: number): void => {
      const step = steps[index];
      if (step === undefined) {
        setPlaying(false);
        setNote(null);
        return;
      }
      if (started === 0) {
        started = now;
        setNote(step.note?.trim() || null);
      }
      const seconds = Math.max(1, step.seconds ?? 6);
      const progress = Math.min(1, (now - started) / (seconds * 1000));
      // 缓入缓出，像手在拖。
      const eased = progress < 0.5
        ? 2 * progress * progress
        : 1 - ((-2 * progress + 2) ** 2) / 2;
      setValues((previous) => ({
        ...previous,
        [step.parameter]: step.from + (step.to - step.from) * eased,
      }));
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        index += 1;
        started = 0;
        frameRef.current = requestAnimationFrame(tick);
      }
    };
    frameRef.current = requestAnimationFrame(tick);
  }, []);

  // 打开一张新图时自动演示一次移动轨迹。
  useEffect(() => {
    if (spec !== null && open && (spec.trajectory ?? []).length > 0) {
      runTrajectory(spec);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec]);

  const readouts = useMemo(() => {
    if (spec === null) {
      return [];
    }
    const scope = resolveScope(spec, current);
    return (spec.readouts ?? []).map((readout) => {
      const value = readoutValue(readout.expression, scope);
      return {
        label: readout.label,
        emphasis: readout.emphasis === true,
        text: readout.format === 'fraction' ? formatFraction(value) : formatNumber(value),
      };
    });
  }, [spec, current]);

  if (spec === null) {
    return null;
  }

  if (!open) {
    return (
      <button
        type="button"
        className="figure-rail"
        onClick={onToggle}
        aria-label="展开图示面板"
        title="展开图示"
      >
        <ShapeIcon size={18} />
        <span>图示</span>
      </button>
    );
  }

  const parameters = spec.parameters ?? [];
  const unknowns = new Set(spec.unknowns ?? []);

  return (
    <aside className="figure-panel" aria-label="图示面板">
      <header className="figure-header">
        <div className="figure-heading">
          <span className="figure-eyebrow">图示</span>
          <h2 className="figure-title" title={spec.title}>{spec.title}</h2>
        </div>
        <div className="figure-actions">
          <button
            type="button"
            className="icon-button"
            onClick={onToggle}
            aria-label="收起图示面板"
            title="收起"
          >
            <ChevronRightIcon size={17} />
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="关闭图示面板"
            title="关闭"
          >
            <CloseIcon size={16} />
          </button>
        </div>
      </header>

      {spec.caption?.trim() ? (
        <p className="figure-caption">{spec.caption}</p>
      ) : null}

      {(spec.given ?? []).length > 0 && (
        <section className="figure-given" aria-label="已知条件">
          <h3 className="figure-section-title">图依据的已知条件</h3>
          <ul>
            {(spec.given ?? []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="figure-stage">
        <FigureBoard spec={spec} values={current} onValues={setValues} />
      </div>

      {readouts.length > 0 && (
        <section className="figure-readouts" aria-label="观察值">
          <h3 className="figure-section-title">观察值</h3>
          <dl className="readout-list">
            {readouts.map((readout) => (
              <div
                key={readout.label}
                className={`readout-row${readout.emphasis ? ' readout-row-emphasis' : ''}`}
              >
                <dt>{readout.label}</dt>
                <dd>{readout.text}</dd>
              </div>
            ))}
          </dl>
          <p className="readout-hint">拖动点或下面的滑块，看看哪些值在变、哪些不变。</p>
        </section>
      )}

      {parameters.length > 0 && (
        <section className="figure-controls" aria-label="可调参数">
          {unknowns.size > 0 && (
            <p className="figure-unknown-note">
              标着“待定”的量题目还没求出来，图里先假设一个值，拖动看看它会怎样影响图形。
            </p>
          )}
          {parameters.map((parameter) => (
            <label key={parameter.name} className="figure-control">
              <span className="figure-control-label">
                <span>
                  {parameterLabel(parameter)}
                  {unknowns.has(parameter.name) && (
                    <span className="figure-unknown" title="题目还没求出来，这里先假设一个值">
                      待定
                    </span>
                  )}
                </span>
                <span className="figure-control-value">
                  {formatNumber(current[parameter.name] ?? parameter.value)}
                </span>
              </span>
              <input
                type="range"
                min={parameter.min ?? 0.1}
                max={parameter.max ?? 10}
                step={parameter.step ?? 0.1}
                value={current[parameter.name] ?? parameter.value}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setValues((previous) => ({ ...previous, [parameter.name]: next }));
                }}
              />
            </label>
          ))}
          {(spec.trajectory ?? []).length > 0 && (
            <button
              type="button"
              className="figure-replay"
              onClick={() => runTrajectory(spec)}
              disabled={playing}
            >
              <PlayIcon size={14} />
              <span>{playing ? '正在演示…' : '再看一遍变化'}</span>
            </button>
          )}
        </section>
      )}

      {note !== null && <p className="figure-note">{note}</p>}
    </aside>
  );
}
