import { useState } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { useSession } from "./session";

export function Portal({ allowedRole }: { allowedRole: "user" | "lawyer" }) {
  const { logout } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  async function exit() {
    try {
      await logout();
      navigate("/login", { replace: true });
    } catch {
      setError("Не удалось выйти. Попробуйте ещё раз.");
    }
  }
  return (
    <section>
      <header className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-semibold">
          {allowedRole === "user" ? "Кабинет пользователя" : "Кабинет юриста"}
        </h1>
        <button type="button" onClick={exit}>
          Выйти
        </button>
      </header>
      {error && <p role="alert">{error}</p>}
      <nav aria-label="Разделы кабинета" className="mt-5 flex flex-wrap gap-4">
        {(allowedRole === "user"
          ? [
              ["", "Мои обращения"],
              ["new", "Новое обращение"],
            ]
          : [
              ["queue", "Очередь"],
              ["pool", "Пул обращений"],
              ["cases", "Мои дела"],
            ]
        ).map(([path, title]) => (
          <Link key={path} to={path ?? ""}>
            {title}
          </Link>
        ))}
      </nav>
      <div className="mt-6">
        <Outlet />
      </div>
    </section>
  );
}
export function Placeholder() {
  return <p>Раздел готовится.</p>;
}
