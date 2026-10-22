/** 与后端接口一致的类型定义。字段含义见 docs/architecture.md。 */

export type GradeBand = 'primary' | 'junior' | 'senior';
export type UserRole = 'student' | 'admin';
export type ConversationPhase = 'idle' | 'tutoring' | 'completed' | 'extension';

export interface User {
  id: number;
  username: string;
  display_name: string | null;
  grade: number;
  grade_band: GradeBand;
  role: UserRole;
}

/** 修改个人设置时允许提交的字段，至少包含一个。 */
export interface UpdateMePayload {
  display_name?: string;
  grade?: number;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface Conversation {
  id: number;
  title: string;
  phase: ConversationPhase;
  /** 老师是否正在后台回答这个对话（学生切走后仍在继续）。 */
  running?: boolean;
  created_at: string;
  updated_at: string;
}

/** 消息里引用的一张图；字段与上传接口返回的 UploadedAttachment 相同。 */
export interface MessageAttachment {
  id: number;
  /** 同源图片地址，通常是 /api/attachments/{id}。 */
  url: string;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  attachments: MessageAttachment[];
  /** 该回合老师打开过的图示（`draw_figure`），可能为空。 */
  figures?: FigureSpec[];
  created_at: string;
}

/* ---------- draw_figure 的结构化图形描述 ---------- */

export interface FigureParameter {
  name: string;
  label?: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
}

export interface FigurePoint {
  id: string;
  x: string;
  y: string;
  label?: string;
  role?: 'plain' | 'highlight';
}

export interface FigureSegment {
  from: string;
  to: string;
  dashed?: boolean;
}

export interface FigurePolygon {
  points: string[];
  label?: string;
}

export interface FigureCurve {
  expression: string;
  from?: number;
  to?: number;
  label?: string;
}

export interface FigureCircle {
  center: string;
  /** 圆上一点；与 radius 二选一。 */
  through?: string;
  /** 半径算式，如 "sqrt(m^2+12)"。 */
  radius?: string;
}

export interface FigureReadout {
  label: string;
  expression: string;
  format?: 'number' | 'fraction';
  emphasis?: boolean;
}

export interface FigureTrajectoryStep {
  parameter: string;
  from: number;
  to: number;
  seconds?: number;
  note?: string;
}

export interface FigureSpec {
  kind?: 'figure';
  title: string;
  caption?: string;
  /** 这张图依据的已知条件。 */
  given?: string[];
  /** 代表题目还没求出来的量的参数名，滑块上标“待定”。 */
  unknowns?: string[];
  parameters?: FigureParameter[];
  points?: FigurePoint[];
  segments?: FigureSegment[];
  polygons?: FigurePolygon[];
  curves?: FigureCurve[];
  circles?: FigureCircle[];
  readouts?: FigureReadout[];
  trajectory?: FigureTrajectoryStep[];
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

/** 上传接口返回的附件；与消息里的 MessageAttachment 同形，两个名字区分来源。 */
export type UploadedAttachment = MessageAttachment;

/* ---------- NDJSON 流事件（docs/architecture.md 第 8 节） ---------- */

export type TurnStatus = 'complete' | 'stopped' | 'error';
export type ToolState = 'running' | 'done' | 'error';

export interface TurnStartedEvent {
  type: 'turn_started';
  turn_id: string | number;
  /** 回合开始时的会话阶段，用来选择等待文案。 */
  phase?: ConversationPhase;
}

export interface TextDeltaEvent {
  type: 'text_delta';
  text: string;
}

export interface ThinkingEvent {
  type: 'thinking';
  active: boolean;
}

export interface ToolStatusEvent {
  type: 'tool_status';
  tool: string;
  label: string;
  state: ToolState;
}

/** 等待区展示的工具状态：是 ToolStatusEvent 去掉事件类型后的展示字段。 */
export type ToolDisplayStatus = Pick<ToolStatusEvent, 'tool' | 'label' | 'state'>;

export interface TurnFinishedEvent {
  type: 'turn_finished';
  status: TurnStatus;
  message_id?: number;
}

/** 工具产出的展示数据（`draw_figure` 的图）。 */
export interface DisplayEvent {
  type: 'display';
  kind: string;
  payload: Record<string, unknown>;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

/** 解码器把未知事件收拢成这一种形状，避免前端猜测字段。 */
export interface UnknownStreamEvent {
  type: 'unknown';
  eventType: string;
  payload: Record<string, unknown>;
}

/* ------------------------- 流事件清单与联合类型 ------------------------- */

/**
 * 解码器认识的全部流事件类型。
 * stream.ts 的已知集合与 StreamEventType 都从这里派生，新增事件只改这一处。
 */
export const STREAM_EVENT_TYPES = [
  'turn_started',
  'text_delta',
  'thinking',
  'tool_status',
  'display',
  'turn_finished',
  'error',
] as const;

export type StreamEventType = (typeof STREAM_EVENT_TYPES)[number];

/** 每种已知事件类型对应的数据结构；清单里有类型而这里漏配时，下面的索引访问会报错。 */
interface KnownStreamEventMap {
  turn_started: TurnStartedEvent;
  text_delta: TextDeltaEvent;
  thinking: ThinkingEvent;
  tool_status: ToolStatusEvent;
  display: DisplayEvent;
  turn_finished: TurnFinishedEvent;
  error: ErrorEvent;
}

export type StreamEvent = KnownStreamEventMap[StreamEventType] | UnknownStreamEvent;
