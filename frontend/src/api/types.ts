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

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface Conversation {
  id: number;
  title: string;
  phase: ConversationPhase;
  created_at: string;
  updated_at: string;
}

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
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface UploadedAttachment {
  id: number;
  url: string;
}

/* ---------- NDJSON 流事件（docs/architecture.md 第 8 节） ---------- */

export type TurnStatus = 'complete' | 'stopped' | 'error';
export type ToolState = 'running' | 'done' | 'error';

export interface TurnStartedEvent {
  type: 'turn_started';
  turn_id: string | number;
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

export interface TurnFinishedEvent {
  type: 'turn_finished';
  status: TurnStatus;
  message_id?: number;
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

export type StreamEvent =
  | TurnStartedEvent
  | TextDeltaEvent
  | ThinkingEvent
  | ToolStatusEvent
  | TurnFinishedEvent
  | ErrorEvent
  | UnknownStreamEvent;
