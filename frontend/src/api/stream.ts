import type { ErrorEvent, StreamEvent } from './types';

const KNOWN_EVENT_TYPES = new Set([
  'turn_started',
  'text_delta',
  'thinking',
  'tool_status',
  'display',
  'turn_finished',
  'error',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function errorEvent(message: string): ErrorEvent {
  return { type: 'error', message };
}

/** 把一行 JSON 转成事件；无法识别的内容返回 null（空行）或错误事件。 */
function parseLine(line: string): StreamEvent | null {
  const text = line.endsWith('\r') ? line.slice(0, -1) : line;
  if (text.trim() === '') {
    return null;
  }

  let value: unknown;
  try {
    value = JSON.parse(text) as unknown;
  } catch {
    return errorEvent('收到了一条无法解析的服务器消息，已跳过。');
  }

  if (!isRecord(value) || typeof value.type !== 'string') {
    return errorEvent('收到了一条格式不正确的服务器消息，已跳过。');
  }

  if (!KNOWN_EVENT_TYPES.has(value.type)) {
    return {
      type: 'unknown',
      eventType: value.type,
      payload: value,
    };
  }

  return value as unknown as StreamEvent;
}

/**
 * NDJSON 增量解码器。
 *
 * - 使用 TextDecoder 的 stream 模式，UTF-8 多字节字符跨块时不会乱码。
 * - 保留未以换行结束的半行，等下一块或 flush() 再解析。
 * - 空行忽略；坏行转成 error 事件，不抛异常。
 */
export class NdjsonDecoder {
  private readonly decoder = new TextDecoder('utf-8');
  private buffer = '';
  private flushed = false;

  push(chunk: Uint8Array): StreamEvent[] {
    if (this.flushed) {
      throw new Error('NdjsonDecoder 已经 flush，不能继续写入。');
    }
    this.buffer += this.decoder.decode(chunk, { stream: true });
    return this.drain(false);
  }

  flush(): StreamEvent[] {
    if (this.flushed) {
      return [];
    }
    this.flushed = true;
    this.buffer += this.decoder.decode();
    return this.drain(true);
  }

  private drain(flush: boolean): StreamEvent[] {
    const lines = this.buffer.split('\n');
    // 最后一段如果不以换行结束，就留到下一次。
    this.buffer = flush ? '' : (lines.pop() ?? '');

    const events: StreamEvent[] = [];
    for (const line of lines) {
      const event = parseLine(line);
      if (event !== null) {
        events.push(event);
      }
    }
    return events;
  }
}

/** 读取 fetch 返回的 NDJSON 流，逐条产出事件。 */
export async function* readNdjsonStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<StreamEvent, void, void> {
  const reader = stream.getReader();
  const decoder = new NdjsonDecoder();
  let reachedEnd = false;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        reachedEnd = true;
        break;
      }
      if (value !== undefined) {
        for (const event of decoder.push(value)) {
          yield event;
        }
      }
    }
    for (const event of decoder.flush()) {
      yield event;
    }
  } finally {
    if (!reachedEnd) {
      // 调用方提前 break（例如收到 turn_finished）时关闭剩余响应体。
      try {
        await reader.cancel();
      } catch {
        // 已经中止或断开的流无需再处理。
      }
    }
    reader.releaseLock();
  }
}
