import { Link, Outlet } from "react-router-dom";
import { useSession } from "@/features/auth/session";

export function Layout() {
  const { user, loading } = useSession();
  return (
    <div className="min-h-screen">
      <header className="border-b border-border">
        <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
          <Link to="/" className="font-semibold">
            Сервис обращений
          </Link>
          {!loading && !user && <Link to="/login">Войти</Link>}
          {user && <span className="ml-auto text-sm text-muted">{user.username}</span>}
        </nav>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
