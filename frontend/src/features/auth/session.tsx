import {
  createContext,
  type FormEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";

type Role = "user" | "lawyer" | "moderator" | "editor";
type User = { id: string; username: string; role: Role; is_demo: boolean };
type Session = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};
const SessionContext = createContext<Session | null>(null);

async function request(path: string, init?: RequestInit): Promise<Response> {
  const result = await fetch(path, { credentials: "same-origin", ...init });
  if (!result.ok)
    throw new Error(
      result.status === 401
        ? "Неверный логин или пароль"
        : "Не удалось выполнить запрос. Попробуйте ещё раз.",
    );
  return result;
}
async function csrf(): Promise<string> {
  const body: unknown = await (await request("/api/auth/csrf")).json();
  if (
    !body ||
    typeof body !== "object" ||
    !("csrf_token" in body) ||
    typeof body.csrf_token !== "string"
  )
    throw new Error("Не удалось получить защитный токен.");
  return body.csrf_token;
}
function validUser(value: unknown): value is User {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === "string" &&
    typeof item.username === "string" &&
    typeof item.is_demo === "boolean" &&
    ["user", "lawyer", "moderator", "editor"].includes(String(item.role))
  );
}
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    request("/api/auth/me")
      .then((r) => r.json())
      .then((v: unknown) => {
        if (active && validUser(v)) setUser(v);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  const login = useCallback(async (username: string, password: string) => {
    const token = await csrf();
    const result: unknown = await (
      await request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": token },
        body: JSON.stringify({ username, password }),
      })
    ).json();
    if (!validUser(result)) throw new Error("Некорректный ответ сервера.");
    setUser(result);
  }, []);
  const logout = useCallback(async () => {
    const token = await csrf();
    await request("/api/auth/logout", { method: "POST", headers: { "X-CSRFToken": token } });
    setUser(null);
  }, []);
  return (
    <SessionContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </SessionContext.Provider>
  );
}
export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("Missing SessionProvider");
  return context;
}
export function RequireRole({ allowedRole }: { allowedRole: "user" | "lawyer" }) {
  const { user, loading } = useSession();
  if (loading) return <p>Проверяем вход…</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== allowedRole) return <p role="alert">У вас нет доступа к этому разделу.</p>;
  return <Outlet />;
}
export function Login() {
  const { user, loading, login } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  if (!loading && user?.role === "user") return <Navigate to="/user" replace />;
  if (!loading && user?.role === "lawyer") return <Navigate to="/lawyer" replace />;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username, password);
      setPassword("");
      navigate("/login", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось войти.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <h1 className="text-2xl font-semibold">Вход</h1>
      <form onSubmit={submit} className="mt-4 grid max-w-sm gap-3">
        <label>
          Логин
          <input
            className="block w-full rounded border p-2"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Пароль
          <input
            className="block w-full rounded border p-2"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-primary p-2 text-primary-foreground"
        >
          Войти
        </button>
      </form>
      {user && !["user", "lawyer"].includes(user.role) && (
        <p role="alert">Для этой роли кабинет пока недоступен.</p>
      )}
    </section>
  );
}
