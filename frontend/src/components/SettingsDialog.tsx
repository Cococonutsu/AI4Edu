import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent,
} from 'react';
import { ApiError } from '../api/client';
import { useAuth } from '../state/auth';
import { gradeLabel } from '../utils/format';
import {
  buildPayload,
  DISPLAY_NAME_MAX,
  GRADE_MAX,
  GRADE_MIN,
  validateSettingsForm,
} from '../utils/settingsForm';

interface SettingsDialogProps {
  open: boolean;
  onClose: () => void;
}

const GRADE_OPTIONS = Array.from(
  { length: GRADE_MAX - GRADE_MIN + 1 },
  (_, index) => GRADE_MIN + index,
);

export function SettingsDialog({ open, onClose }: SettingsDialogProps): JSX.Element | null {
  const { user, saveSettings } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [grade, setGrade] = useState(GRADE_MIN);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // 每次打开都从当前用户资料重置表单，避免带入上一次的草稿。
  useEffect(() => {
    if (!open || user === null) {
      return;
    }
    setDisplayName(user.display_name ?? '');
    setGrade(user.grade);
    setError(null);
    setSaving(false);
    nameInputRef.current?.focus();
  }, [open, user]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open || user === null) {
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (saving || user === null) {
      return;
    }
    const values = { displayName, grade };
    const validationError = validateSettingsForm(user, values);
    if (validationError !== null) {
      setError(validationError);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveSettings(buildPayload(user, values));
      onClose();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : '保存失败，请稍后再试。',
      );
    } finally {
      setSaving(false);
    }
  }

  function handleOverlayClick(event: MouseEvent<HTMLDivElement>): void {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }

  return (
    <div className="settings-overlay" onClick={handleOverlayClick}>
      <form
        className="settings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        aria-describedby="settings-hint"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <div className="settings-head">
          <h2 id="settings-title" className="settings-title">个人设置</h2>
          <p id="settings-hint" className="settings-hint">
            名字用来称呼你，年级帮助老师把握讲解的深浅。
          </p>
        </div>

        <label className="settings-field">
          <span className="settings-label">名字</span>
          <input
            ref={nameInputRef}
            className="settings-input"
            type="text"
            value={displayName}
            maxLength={DISPLAY_NAME_MAX}
            autoComplete="nickname"
            placeholder="怎么称呼你？"
            disabled={saving}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </label>

        <label className="settings-field">
          <span className="settings-label">年级</span>
          <select
            className="settings-select"
            value={grade}
            disabled={saving}
            onChange={(event) => setGrade(Number(event.target.value))}
          >
            {GRADE_OPTIONS.map((option) => (
              <option key={option} value={option}>{gradeLabel(option)}</option>
            ))}
          </select>
        </label>

        {error !== null && (
          <p className="settings-error" role="alert">{error}</p>
        )}

        <div className="settings-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
            disabled={saving}
          >
            取消
          </button>
          <button type="submit" className="settings-save" disabled={saving}>
            {saving ? '正在保存…' : '保存'}
          </button>
        </div>
      </form>
    </div>
  );
}
