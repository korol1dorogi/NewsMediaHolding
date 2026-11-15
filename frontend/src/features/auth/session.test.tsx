import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { routes } from "@/App";

function renderPath(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());
const user = (role: string) => ({ id: "demo", username: "demo", role, is_demo: true });
it.each([
  ["user", "/user", "Кабинет пользователя"],
  ["lawyer", "/lawyer", "Кабинет юриста"],
])("directs %s to its portal after login", async (role, path, title) => {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/me")) return new Response(null, { status: 401 });
    if (url.endsWith("/csrf")) return Response.json({ csrf_token: "token" });
    if (url.endsWith("/login")) return Response.json(user(role));
    throw new Error("unexpected");
  });
  vi.stubGlobal("fetch", fetcher);
  renderPath("/login");
  await waitFor(() => expect(fetcher).toHaveBeenCalled());
  fireEvent.change(screen.getByLabelText("Логин"), { target: { value: "demo" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Войти" }));
  expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
  expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/csrf"))).toBe(true);
  expect(path).toMatch(/^\//);
});
it("denies a lawyer route to a user", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json(user("user"))),
  );
  renderPath("/lawyer");
  expect(await screen.findByRole("alert")).toHaveTextContent("нет доступа");
});
it("redirects an anonymous user to login", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(null, { status: 401 })),
  );
  renderPath("/user");
  expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument();
});
