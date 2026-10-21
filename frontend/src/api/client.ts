import type {
  Conversation,
  ConversationDetail,
  ConversationPhase,
  FigureSpec,
  GradeBand,
  LoginCredentials,
  Message,
  MessageAttachment,
  UploadedAttachment,
  User,
  UserRole,
} from './types';

const API_PREFIX = '/api';

/** 统一的接口错误：status 为 0 表示网络层失败。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

type UnauthorizedHandler = () => void;
const unauthorizedHandlers = new Set<UnauthorizedHandler>();

/** 注册全局 401 回调（AuthProvider 用它跳回登录页）。 */
export function onUnauthorized(handler: UnauthorizedHandler): () => void {
  unauthorizedHandlers.add(handler);
  return () => {
    unauthorizedHandlers.delete(handler);
  };
}

function notifyUnauthorized(): void {
  for (const handler of unauthorizedHandlers) {
    handler();
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function normalizeGradeBand(value: unknown, grade: number): GradeBand {
  if (value === 'primary' || value === 'junior' || value === 'senior') {
    return value;
  }
  if (grade >= 1 && grade <= 6) return 'primary';
  if (grade >= 7 && grade <= 9) return 'junior';
  return 'senior';
}

function normalizeUser(raw: unknown): User {
  const outer = asRecord(raw) ?? {};
  const source = asRecord(outer.user) ?? outer;
  const grade = asNumber(source.grade, 0);
  const role: UserRole = source.role === 'admin' ? 'admin' : 'student';
  return {
    id: asNumber(source.id),
    username: asString(source.username),
    display_name: typeof source.display_name === 'string' && source.display_name.trim() !== ''
      ? source.display_name
      : null,
    grade,
    grade_band: normalizeGradeBand(source.grade_band, grade),
    role,
  };
}

const PHASES: ReadonlySet<string> = new Set(['idle', 'tutoring', 'completed', 'extension']);

function normalizeConversation(raw: unknown): Conversation {
  const source = asRecord(raw) ?? {};
  const phaseValue = asString(source.phase, 'idle');
  const phase: ConversationPhase = PHASES.has(phaseValue)
    ? (phaseValue as ConversationPhase)
    : 'idle';
  return {
    id: asNumber(source.id),
    title: asString(source.title, '未命名对话'),
    phase,
    running: source.running === true,
    created_at: asString(source.created_at),
    updated_at: asString(source.updated_at),
  };
}

function normalizeAttachment(raw: unknown): MessageAttachment | null {
  const source = asRecord(raw) ?? {};
  const id = asNumber(source.id, NaN);
  if (!Number.isFinite(id)) {
    return null;
  }
  return {
    id,
    url: asString(source.url) || `${API_PREFIX}/attachments/${id}`,
  };
}

function normalizeMessage(raw: unknown): Message | null {
  const source = asRecord(raw) ?? {};
  const role = source.role;
  if (role !== 'user' && role !== 'assistant') {
    return null;
  }
  const attachmentsRaw = Array.isArray(source.attachments) ? source.attachments : [];
  const attachments = attachmentsRaw
    .map(normalizeAttachment)
    .filter((item): item is MessageAttachment => item !== null);
  // 图示由后端校验过结构，这里只保留是对象、带标题的项。
  const figures = (Array.isArray(source.figures) ? source.figures : [])
    .filter((item): item is FigureSpec => (
      asRecord(item) !== null && typeof asRecord(item)?.title === 'string'
    ));
  return {
    id: asNumber(source.id),
    role,
    text: asString(source.text),
    attachments,
    figures,
    created_at: asString(source.created_at),
  };
}

function errorMessageForStatus(status: number): string {
  if (status === 400 || status === 422) return '请求内容有误，请检查后重试。';
  if (status === 401) return '登录已过期，请重新登录。';
  if (status === 403) return '没有权限进行这个操作。';
  if (status === 404) return '找不到请求的内容，可能已被删除。';
  if (status === 409) return '当前操作发生冲突，请刷新后再试。';
  if (status === 413) return '图片太大了，请选择 10MB 以内的图片。';
  if (status === 429) return '请求太频繁，请稍等一会儿再试。';
  if (status >= 500) return '服务器出了点问题，请稍后再试。';
  return '操作没有成功，请稍后再试。';
}

function extractDetail(payload: unknown): string | null {
  if (typeof payload === 'string') {
    return payload.trim() === '' ? null : payload;
  }
  const record = asRecord(payload);
  if (record === null) {
    return null;
  }
  for (const key of ['detail', 'message', 'error']) {
    const value = record[key];
    if (typeof value === 'string' && value.trim() !== '') {
      return value;
    }
  }
  return null;
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  let detail: string | null = null;
  try {
    const text = await response.text();
    if (text.trim() !== '') {
      try {
        detail = extractDetail(JSON.parse(text) as unknown);
      } catch {
        detail = null;
      }
    }
  } catch {
    detail = null;
  }
  // 401 使用固定文案，登录页会按需求显示“用户名或密码错误”。
  const message = response.status === 401
    ? '登录已过期，请重新登录。'
    : detail ?? errorMessageForStatus(response.status);
  return new ApiError(response.status, message);
}

interface RequestOptions extends RequestInit {
  /** 登录与读取当前用户时不要触发全局跳转。 */
  skipAuthRedirect?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuthRedirect = false, headers, ...init } = options;
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      credentials: 'same-origin',
      ...init,
      headers,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw new ApiError(0, '无法连接服务器，请检查网络后再试。');
  }

  if (!response.ok) {
    const apiError = await parseErrorResponse(response);
    if (response.status === 401 && !skipAuthRedirect) {
      notifyUnauthorized();
    }
    throw apiError;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (text.trim() === '') {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(response.status, '服务器返回了无法识别的数据，请稍后再试。');
  }
}

function jsonRequest<T>(
  path: string,
  method: string,
  body: unknown,
  skipAuthRedirect = false,
): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    skipAuthRedirect,
  });
}

/* ---------------------------- 鉴权 ---------------------------- */

export async function getMe(): Promise<User> {
  const raw = await request<unknown>('/auth/me', { skipAuthRedirect: true });
  return normalizeUser(raw);
}

export async function login(credentials: LoginCredentials): Promise<User> {
  const raw = await jsonRequest<unknown>('/auth/login', 'POST', credentials, true);
  return normalizeUser(raw);
}

export async function logout(): Promise<void> {
  await request<void>('/auth/logout', { method: 'POST', skipAuthRedirect: true });
}

/* ---------------------------- 会话 ---------------------------- */

export async function listConversations(): Promise<Conversation[]> {
  const raw = await request<unknown>('/conversations');
  const source = asRecord(raw);
  const nested = source === null ? undefined : source.conversations;
  const items = Array.isArray(raw) ? raw : Array.isArray(nested) ? nested : null;
  if (items === null) {
    throw new ApiError(200, '对话列表的格式不正确，请刷新页面。');
  }
  return items.map(normalizeConversation);
}

export async function createConversation(): Promise<Conversation> {
  const raw = await request<unknown>('/conversations', { method: 'POST' });
  const outer = asRecord(raw);
  const conversation = normalizeConversation(outer?.conversation ?? raw);
  if (conversation.id <= 0) {
    throw new ApiError(200, '创建对话失败，请稍后再试。');
  }
  return conversation;
}

export async function getConversation(id: number): Promise<ConversationDetail> {
  const raw = await request<unknown>(`/conversations/${id}`);
  const outer = asRecord(raw) ?? {};
  const conversationRaw = outer.conversation ?? raw;
  const conversation = normalizeConversation(conversationRaw);
  const messagesRaw = Array.isArray(outer.messages)
    ? outer.messages
    : Array.isArray(asRecord(conversationRaw)?.messages)
      ? (asRecord(conversationRaw)?.messages as unknown[])
      : [];
  const messages = messagesRaw
    .map(normalizeMessage)
    .filter((item): item is Message => item !== null);
  return { ...conversation, messages };
}

export async function renameConversation(id: number, title: string): Promise<void> {
  await request<unknown>(`/conversations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id: number): Promise<void> {
  await request<void>(`/conversations/${id}`, { method: 'DELETE' });
}

/* ---------------------------- 附件 ---------------------------- */

export async function uploadAttachment(
  file: File,
  conversationId?: number,
): Promise<UploadedAttachment> {
  const form = new FormData();
  form.append('file', file, file.name || 'image');
  if (conversationId !== undefined) {
    form.append('conversation_id', String(conversationId));
  }
  const raw = await request<unknown>('/attachments', {
    method: 'POST',
    body: form,
  });
  const outer = asRecord(raw) ?? {};
  const source = asRecord(outer.attachment) ?? outer;
  const id = asNumber(source.id, NaN);
  if (!Number.isFinite(id)) {
    throw new ApiError(200, '图片上传失败，请重试。');
  }
  return {
    id,
    url: asString(source.url) || `${API_PREFIX}/attachments/${id}`,
  };
}

/* ---------------------------- 消息与流 ---------------------------- */

export async function sendMessage(
  conversationId: number,
  text: string,
  attachmentIds: number[],
  signal: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}/conversations/${conversationId}/messages`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/x-ndjson',
      },
      body: JSON.stringify({ text, attachment_ids: attachmentIds }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw new ApiError(0, '无法连接服务器，请检查网络后再试。');
  }

  if (!response.ok) {
    const apiError = await parseErrorResponse(response);
    if (response.status === 401) {
      notifyUnauthorized();
    }
    throw apiError;
  }

  if (response.body === null) {
    throw new ApiError(response.status, '服务器没有返回回答，请重试。');
  }
  return response.body;
}

export async function stopConversation(conversationId: number): Promise<void> {
  await request<void>(`/conversations/${conversationId}/stop`, { method: 'POST' });
}

/** 诊断信息用，不展示给学生。 */
export function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message.trim() !== '') {
    return error.message;
  }
  return fallback;
}
