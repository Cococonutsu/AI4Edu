/**
 * 等待时的阶段文案。
 *
 * 模型读一道新题、或者判断学生的思路时，可能要等几十秒，期间后端没有
 * 可展示的中间结果。这里只依据后端真实给出的信息（会话阶段、这条消息
 * 有没有图片、已经等了多久）决定文案，不猜测模型在做什么。
 */

export type WaitKind = 'image' | 'idle' | 'tutoring' | 'completed';

export interface WaitStage {
  /** 当前状态文字。 */
  label: string;
  /** 等得较久时的一句补充（没有则不显示）。 */
  note: string | null;
}

interface StageDef {
  atMs: number;
  label: string;
  note: string | null;
}

const STAGES: Record<WaitKind, StageDef[]> = {
  image: [
    { atMs: 0, label: '正在看你发的题目图片…', note: null },
    { atMs: 5000, label: '正在读题，理清已知和所求…', note: null },
    {
      atMs: 18000,
      label: '正在把这道题拆成几步…',
      note: '你也可以先想想：题目给了哪些条件？最后要求的是什么？',
    },
    {
      atMs: 45000,
      label: '还在把每一步想清楚…',
      note: '读新题会慢一点，可以先把条件抄在草稿纸上。',
    },
    {
      atMs: 90000,
      label: '这道题有点复杂，还在认真想…',
      note: '如果一直没有回应，可以点"停止"后重新发送。',
    },
  ],
  idle: [
    { atMs: 0, label: '正在读你的消息…', note: null },
    { atMs: 6000, label: '正在想怎么回答…', note: null },
    { atMs: 20000, label: '比平时久一点，还在想…', note: '如果一直没有回应，可以点"停止"后重新发送。' },
  ],
  tutoring: [
    { atMs: 0, label: '正在看你的想法…', note: null },
    { atMs: 6000, label: '正在判断你这一步…', note: null },
    {
      atMs: 20000,
      label: '正在想怎么回你…',
      note: '可以先检查一下自己的算式，等下再对照。',
    },
    { atMs: 45000, label: '比平时久一点，还在认真想…', note: '如果一直没有回应，可以点"停止"后重新发送。' },
  ],
  completed: [
    { atMs: 0, label: '正在读你的消息…', note: null },
    { atMs: 6000, label: '正在想怎么回答…', note: null },
    { atMs: 20000, label: '比平时久一点，还在想…', note: '如果一直没有回应，可以点"停止"后重新发送。' },
  ],
};

/** 回合开始时后端给出的信息决定用哪组文案。 */
export function waitKind(phase: string | null, hasImage: boolean): WaitKind {
  if (hasImage) {
    return 'image';
  }
  if (phase === 'tutoring' || phase === 'extension') {
    return 'tutoring';
  }
  if (phase === 'completed') {
    return 'completed';
  }
  return 'idle';
}

const FALLBACK: StageDef = { atMs: 0, label: '正在想…', note: null };

export function waitStage(kind: WaitKind, elapsedMs: number): WaitStage {
  const stages = STAGES[kind] ?? STAGES.idle;
  let current: StageDef = stages[0] ?? FALLBACK;
  for (const stage of stages) {
    if (elapsedMs >= stage.atMs) {
      current = stage;
    }
  }
  return { label: current.label, note: current.note };
}

/**
 * 工具运行期间的一句补充提示；没有对应提示的工具返回 null。
 *
 * 联网搜索/读网页是仅有的两段"老师离开了一下"的等待（对外请求，
 * 秒级到十几秒），给一句和阶段文案同风格的说明，避免干等。
 */
export function toolRunningNote(tool: string): string | null {
  if (tool === 'web_search') {
    return '老师上网查资料去了，稍等一下。';
  }
  if (tool === 'web_fetch') {
    return '老师在读网页，有时要多等几秒。';
  }
  return null;
}

/** "已等 12 秒" / "已等 1 分 05 秒"。 */
export function formatElapsed(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  if (totalSeconds < 60) {
    return `已等 ${totalSeconds} 秒`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `已等 ${minutes} 分 ${seconds.toString().padStart(2, '0')} 秒`;
}
