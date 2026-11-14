import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-bold">Страница не найдена</h1>
      <Link to="/" className="underline">
        На главную
      </Link>
    </section>
  );
}
