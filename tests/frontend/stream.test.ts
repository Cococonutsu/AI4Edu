import { describe, expect, it } from 'vitest';
import { NdjsonDecoder, readNdjsonStream } from '../../frontend/src/api/stream';
import type { StreamEvent } from '../../frontend/src/api/types';

const encoder = new TextEncoder();

function decodeAll(chunks: Uint8Array[]): StreamEvent[] {
  const decoder = new NdjsonDecoder();
  const events: StreamEvent[] = [];
  for (const chunk of chunks) {
    events.push(...decoder.push(chunk));
  }
  events.push(...decoder.flush());
  return events;
}

describe('NdjsonDecoder', () => {
  it('把一个中文字符拆在两个块里也不会乱码', () => {
    const bytes = encoder.encode('{"type":"text_delta","text":"你好"}\n');
    // “你”的 UTF-8 编码是 E4 BD A0，从第一个字节之后切开。
    const splitAt = bytes.indexOf(0xe4);
    expect(splitAt).toBeGreaterThan(0);

    const events = decodeAll([
      bytes.slice(0, splitAt + 1),
      bytes.slice(splitAt + 1),
    ]);

    expect(events).toEqual([{ type: 'text_delta', text: '你好' }]);
  });

  it('一行 JSON 被拆在两个块中也能解析', () => {
    const bytes = encoder.encode('{"type":"text_delta","text":"这是一整行"}\n');
    const splitAt = 20;

    const decoder = new NdjsonDecoder();
    const first = decoder.push(bytes.slice(0, splitAt));
    expect(first).toEqual([]);

    const second = decoder.push(bytes.slice(splitAt));
    const rest = decoder.flush();

    expect([...second, ...rest]).toEqual([
      { type: 'text_delta', text: '这是一整行' },
    ]);
  });

  it('一个块包含多行时按顺序产出事件，空行忽略', () => {
    const chunk = encoder.encode([
      '{"type":"thinking","active":true}',
      '',
      '{"type":"text_delta","text":"先想一想"}',
      '{"type":"tool_status","tool":"analyze_problem","label":"正在读题…","state":"running"}',
      '',
    ].join('\n'));

    const events = decodeAll([chunk]);

    expect(events).toEqual([
      { type: 'thinking', active: true },
      { type: 'text_delta', text: '先想一想' },
      {
        type: 'tool_status',
        tool: 'analyze_problem',
        label: '正在读题…',
        state: 'running',
      },
    ]);
  });

  it('末尾没有换行的最后一行在 flush 时产出', () => {
    const decoder = new NdjsonDecoder();
    const events = decoder.push(encoder.encode('{"type":"text_delta","text":"最后一句"}'));
    expect(events).toEqual([]);

    const flushed = decoder.flush();
    expect(flushed).toEqual([{ type: 'text_delta', text: '最后一句' }]);
  });

  it('非法 JSON 行产生错误事件，后面的行继续解析', () => {
    const events = decodeAll([encoder.encode([
      '这不是 JSON',
      '{"type":"text_delta","text":"还能继续"}',
      '{"type":"thinking"',
      '{"type":"turn_finished","status":"complete"}',
    ].join('\n'))]);

    expect(events).toHaveLength(4);
    expect(events[0]).toMatchObject({ type: 'error' });
    expect(events[1]).toEqual({ type: 'text_delta', text: '还能继续' });
    expect(events[2]).toMatchObject({ type: 'error' });
    expect(events[3]).toEqual({ type: 'turn_finished', status: 'complete' });
  });

  it('兼容 CRLF，并把未知事件类型收拢为 unknown', () => {
    const events = decodeAll([
      encoder.encode('{"type":"thinking","active":false}\r\n'),
      encoder.encode('{"type":"new_event","value":1}\r\n'),
    ]);

    expect(events[0]).toEqual({ type: 'thinking', active: false });
    expect(events[1]).toMatchObject({ type: 'unknown', eventType: 'new_event' });
  });

  it('readNdjsonStream 能读取分块的流，并处理末尾半行', async () => {
    const first = encoder.encode('{"type":"text_delta","text":"你');
    const second = encoder.encode('好"}\n{"type":"turn_finished","status":"complete"}');

    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(first);
        controller.enqueue(second);
        controller.close();
      },
    });

    const events: StreamEvent[] = [];
    for await (const event of readNdjsonStream(body)) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: 'text_delta', text: '你好' },
      { type: 'turn_finished', status: 'complete' },
    ]);
  });
});
