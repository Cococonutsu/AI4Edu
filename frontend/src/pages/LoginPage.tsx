import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../state/auth';
import { AlertIcon, CloseIcon } from '../components/Icons';
import { MarkdownContent } from '../components/MarkdownContent';

export function LoginPage(): JSX.Element {
  const { status, notice, login, dismissNotice } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'loading') {
    return (
      <div className="page-loading">
        <span className="spinner spinner-large" aria-hidden="true" />
        <span>正在检查登录状态…</span>
      </div>
    );
  }

  if (status === 'authenticated') {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) {
      return;
    }
    const trimmedUsername = username.trim();
    if (trimmedUsername === '' || password === '') {
      setError('请输入用户名和密码。');
      return;
    }

    setSubmitting(true);
    setError(null);
    dismissNotice();
    try {
      await login({ username: trimmedUsername, password });
      navigate('/', { replace: true });
    } catch (loginError) {
      if (loginError instanceof ApiError && loginError.status === 401) {
        setError('用户名或密码错误');
      } else if (loginError instanceof ApiError) {
        setError(loginError.message);
      } else {
        setError('登录失败，请稍后再试。');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <main className="login-sheet">
        <section className="login-cover" aria-hidden="true">
          <div className="login-cover-head">
            <span className="login-wordmark">AI4Edu · 数学辅导</span>
            <span className="login-rule" />
          </div>

          <p className="login-statement">
            不会的题，
            <br />
            我们一起<em>想明白</em>。
          </p>

          <div className="login-example">
            <div className="login-example-question">
              <MarkdownContent>{'$\\triangle OCE$ 和 $\\triangle OAB$ 为什么会相似？'}</MarkdownContent>
            </div>
            <div className="login-example-answer">
              <MarkdownContent>
                {'先看它们共用了哪个角，再看看 $CE$ 和 $AB$ 是什么关系。'}
              </MarkdownContent>
            </div>
          </div>
        </section>

        <section className="login-form-panel">
          <h1 className="login-heading">登录</h1>
          <p className="login-subheading">用老师给你的账号登录</p>

          <form className="login-form" onSubmit={(event) => void handleSubmit(event)}>
            <label className="field">
              <span className="field-label">用户名</span>
              <input
                className="field-input"
                type="text"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                autoFocus
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="请输入用户名"
              />
            </label>

            <label className="field">
              <span className="field-label">密码</span>
              <input
                className="field-input"
                type="password"
                name="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="请输入密码"
              />
            </label>

            {error !== null && (
              <p className="login-alert login-alert-error" role="alert">
                <AlertIcon size={16} />
                <span>{error}</span>
              </p>
            )}

            {error === null && notice !== null && (
              <p className="login-alert login-alert-info" role="status">
                <AlertIcon size={16} />
                <span>{notice}</span>
                <button
                  type="button"
                  className="login-alert-close"
                  aria-label="关闭提示"
                  onClick={dismissNotice}
                >
                  <CloseIcon size={14} />
                </button>
              </p>
            )}

            <button type="submit" className="login-button" disabled={submitting}>
              {submitting && <span className="spinner spinner-on-primary" aria-hidden="true" />}
              <span>{submitting ? '正在登录…' : '进入'}</span>
            </button>
          </form>

          <p className="login-footnote">如果忘记密码，请联系老师重置。</p>
        </section>
      </main>
    </div>
  );
}
