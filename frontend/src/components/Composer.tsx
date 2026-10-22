import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
} from 'react';
import { describeError, uploadAttachment } from '../api/client';
import { useChat } from '../state/chat';
import { AlertIcon, CloseIcon, ImageIcon, SendIcon, StopIcon } from './Icons';

const MAX_ATTACHMENTS = 4;
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

interface PendingAttachment {
  key: string;
  id: number | null;
  previewUrl: string;
  uploading: boolean;
}

export function Composer(): JSX.Element {
  const { activeId, messages, messagesLoading, sending, sendMessage, stopGeneration } = useChat();

  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composingRef = useRef(false);
  const compositionEndedAtRef = useRef(0);
  const attachmentsRef = useRef(attachments);
  attachmentsRef.current = attachments;

  useEffect(() => () => {
    for (const item of attachmentsRef.current) {
      URL.revokeObjectURL(item.previewUrl);
    }
  }, []);

  useEffect(() => {
    const element = textareaRef.current;
    if (element === null) {
      return;
    }
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
  }, [text]);

  const uploading = attachments.some((item) => item.uploading);
  const readyIds = attachments
    .filter((item): item is PendingAttachment & { id: number } => (
      item.id !== null && !item.uploading
    ))
    .map((item) => item.id);
  const canSend = !sending
    && !messagesLoading
    && !uploading
    && (text.trim() !== '' || readyIds.length > 0);

  async function startUpload(file: File): Promise<void> {
    if (attachmentsRef.current.length >= MAX_ATTACHMENTS) {
      setError(`最多只能上传 ${MAX_ATTACHMENTS} 张图片。`);
      return;
    }
    const key = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    const previewUrl = URL.createObjectURL(file);
    const pending: PendingAttachment = { key, id: null, previewUrl, uploading: true };
    // 同步更新 ref，避免连续选择/粘贴时绕过 4 张上限。
    attachmentsRef.current = [...attachmentsRef.current, pending];
    setAttachments(attachmentsRef.current);

    try {
      const uploaded = await uploadAttachment(file, activeId ?? undefined);
      attachmentsRef.current = attachmentsRef.current.map((item) => (
        item.key === key
          ? { ...item, id: uploaded.id, uploading: false }
          : item
      ));
      setAttachments(attachmentsRef.current);
    } catch (uploadError) {
      const target = attachmentsRef.current.find((item) => item.key === key);
      if (target !== undefined) {
        URL.revokeObjectURL(target.previewUrl);
      }
      attachmentsRef.current = attachmentsRef.current.filter((item) => item.key !== key);
      setAttachments(attachmentsRef.current);
      setError(describeError(uploadError, '图片上传失败，请重试。'));
    }
  }

  function addFiles(files: File[]): void {
    if (files.length === 0) {
      return;
    }
    setError(null);
    let remaining = MAX_ATTACHMENTS - attachmentsRef.current.length;
    if (remaining <= 0) {
      setError(`最多只能上传 ${MAX_ATTACHMENTS} 张图片。`);
      return;
    }

    const messages = new Set<string>();
    const accepted: File[] = [];

    for (const file of files) {
      if (remaining <= 0) {
        messages.add(`最多只能上传 ${MAX_ATTACHMENTS} 张图片。`);
        break;
      }
      if (!ACCEPTED_TYPES.includes(file.type)) {
        messages.add('只支持 PNG、JPEG、WebP 格式的图片。');
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        messages.add('图片大小不能超过 10MB。');
        continue;
      }
      if (file.size === 0) {
        messages.add('这张图片是空的，请换一张。');
        continue;
      }
      accepted.push(file);
      remaining -= 1;
    }

    for (const file of accepted) {
      void startUpload(file);
    }
    if (messages.size > 0) {
      setError(Array.from(messages).join(' '));
    }
  }

  function removeAttachment(key: string): void {
    const target = attachmentsRef.current.find((item) => item.key === key);
    if (target !== undefined) {
      URL.revokeObjectURL(target.previewUrl);
    }
    attachmentsRef.current = attachmentsRef.current.filter((item) => item.key !== key);
    setAttachments(attachmentsRef.current);
  }

  async function handleSend(): Promise<void> {
    if (!canSend) {
      return;
    }
    const ids = readyIds;
    const trimmed = text.trim();
    if (trimmed === '' && ids.length === 0) {
      return;
    }

    // 连发防重由 useChat().sending（useSending 的单一锁）兜底。
    const accepted = await sendMessage(trimmed, ids);
    if (accepted) {
      for (const item of attachmentsRef.current) {
        URL.revokeObjectURL(item.previewUrl);
      }
      attachmentsRef.current = [];
      setText('');
      setAttachments([]);
      setError(null);
      textareaRef.current?.focus();
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void handleSend();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== 'Enter' || event.shiftKey) {
      return;
    }
    const composing = composingRef.current
      || event.nativeEvent.isComposing
      || Date.now() - compositionEndedAtRef.current < 50;
    if (composing) {
      return;
    }
    if (!canSend) {
      return;
    }
    event.preventDefault();
    void handleSend();
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const files = event.target.files;
    if (files !== null && files.length > 0) {
      addFiles(Array.from(files));
    }
    event.target.value = '';
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>): void {
    const files = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === 'file')
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null)
      .filter((file) => file.type.startsWith('image/'));
    if (files.length === 0) {
      return;
    }
    event.preventDefault();
    addFiles(files);
  }

  function handleDragOver(event: DragEvent<HTMLFormElement>): void {
    if (!event.dataTransfer.types.includes('Files')) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    setDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLFormElement>): void {
    const related = event.relatedTarget;
    if (related instanceof Node && event.currentTarget.contains(related)) {
      return;
    }
    setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLFormElement>): void {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 0) {
      addFiles(Array.from(event.dataTransfer.files));
    }
  }

  return (
    <div className="composer-wrap">
      <form
        className={`composer${dragging ? ' composer-dragging' : ''}`}
        onSubmit={handleSubmit}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {dragging && <div className="composer-drop-hint">松开鼠标，把图片放进来</div>}

        {attachments.length > 0 && (
          <div className="pending-images">
            {attachments.map((item) => (
              <div className="pending-image" key={item.key}>
                <img src={item.previewUrl} alt="待发送的图片" />
                {item.uploading && (
                  <span className="pending-image-overlay" aria-label="正在上传图片">
                    <span className="spinner" aria-hidden="true" />
                  </span>
                )}
                <button
                  type="button"
                  className="pending-image-remove"
                  aria-label="移除这张图片"
                  onClick={() => removeAttachment(item.key)}
                >
                  <CloseIcon size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        <label className="sr-only" htmlFor="composer-text">输入消息</label>
        <textarea
          id="composer-text"
          ref={textareaRef}
          className="composer-textarea"
          rows={1}
          value={text}
          placeholder={messages.length > 0 ? '写下你的想法，或者问我一个问题…' : '把题目发给我…'}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onCompositionStart={() => {
            composingRef.current = true;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
            compositionEndedAtRef.current = Date.now();
          }}
        />

        {error !== null && (
          <p className="composer-error" role="alert">
            <AlertIcon size={14} />
            <span>{error}</span>
          </p>
        )}

        <div className="composer-toolbar">
          <div className="composer-tools">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              multiple
              hidden
              onChange={handleFileChange}
            />
            <button
              type="button"
              className="composer-tool"
              aria-label="选择图片"
              title="选择图片（PNG / JPEG / WebP，最多 4 张）"
              onClick={() => fileInputRef.current?.click()}
              disabled={attachments.length >= MAX_ATTACHMENTS}
            >
              <ImageIcon size={19} />
              <span>图片</span>
            </button>
            <span className="composer-count" aria-live="polite">
              {attachments.length > 0 ? `${attachments.length}/${MAX_ATTACHMENTS}` : ''}
            </span>
          </div>

          <div className="composer-actions">
            <span className="composer-hint">Enter 发送 · Shift + Enter 换行</span>
            {sending ? (
              <button type="button" className="stop-button" onClick={stopGeneration}>
                <StopIcon size={16} />
                <span>停止</span>
              </button>
            ) : (
              <button
                type="submit"
                className="send-button"
                disabled={!canSend}
                aria-label="发送消息"
              >
                <SendIcon size={17} />
                <span>发送</span>
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
