import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function Home() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/health");
      if (error || !data) throw new Error("API недоступно");
      return data;
    },
  });

  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-bold">Каждое обращение получает ответ</h1>
      <p className="text-muted">
        Каркас приложения. Продуктовые экраны появятся по задачам из docs/tasks.md.
      </p>
      <p data-testid="api-status">
        API: {health.isPending ? "проверяем…" : health.isError ? "недоступно" : health.data.status}
      </p>
    </section>
  );
}
