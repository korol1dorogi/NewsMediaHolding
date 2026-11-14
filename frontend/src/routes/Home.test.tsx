import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { routes } from "@/App";

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("routing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows API status on the home page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ status: "ok" })),
    );
    renderAt("/");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Каждое обращение");
    expect(await screen.findByText("API: ok")).toBeInTheDocument();
  });

  it("shows not found for unknown routes", () => {
    renderAt("/no-such-page");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Страница не найдена");
  });
});
