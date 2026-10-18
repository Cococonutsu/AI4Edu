import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react';
import {
  getMe,
  isUnauthorized,
  login as apiLogin,
  logout as apiLogout,
  onUnauthorized,
} from '../api/client';
import type { LoginCredentials, User } from '../api/types';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

interface AuthState {
  status: AuthStatus;
  user: User | null;
  notice: string | null;
}

type AuthAction =
  | { type: 'restored'; user: User }
  | { type: 'signed_in'; user: User }
  | { type: 'signed_out'; notice?: string | null }
  | { type: 'notice'; notice: string | null };

const initialState: AuthState = {
  status: 'loading',
  user: null,
  notice: null,
};

function reducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'restored':
    case 'signed_in':
      return { status: 'authenticated', user: action.user, notice: null };
    case 'signed_out':
      return { status: 'anonymous', user: null, notice: action.notice ?? null };
    case 'notice':
      return { ...state, notice: action.notice };
    default:
      return state;
  }
}

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  notice: string | null;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  dismissNotice: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((user) => {
        if (!cancelled) {
          dispatch({ type: 'restored', user });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (isUnauthorized(error)) {
          dispatch({ type: 'signed_out', notice: null });
        } else {
          dispatch({
            type: 'signed_out',
            notice: '暂时无法连接服务器，请检查网络后重试。',
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => onUnauthorized(() => {
    dispatch({ type: 'signed_out', notice: '登录已过期，请重新登录。' });
  }), []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const user = await apiLogin(credentials);
    dispatch({ type: 'signed_in', user });
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // 网络失败或会话已失效时，本地仍然退出，避免把学生困在页面里。
    }
    dispatch({ type: 'signed_out', notice: null });
  }, []);

  const dismissNotice = useCallback(() => {
    dispatch({ type: 'notice', notice: null });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status: state.status,
      user: state.user,
      notice: state.notice,
      login,
      logout,
      dismissNotice,
    }),
    [state.status, state.user, state.notice, login, logout, dismissNotice],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth 必须在 AuthProvider 内使用。');
  }
  return context;
}
