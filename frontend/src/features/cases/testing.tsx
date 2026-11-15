import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { vi } from "vitest";
import { routes } from "@/App";
import type { CaseDetail } from "./api";

export const CASE_ID = "00000000-0000-4000-8000-000000000001";

export function caseDetail(overrides: Partial<CaseDetail> = {}): CaseDetail {
  return {
    id: CASE_ID,
    state: "draft",
    path: null,
    ai_state: "idle",
    version: 1,
    created_at: "2026-11-15T10:00:00Z",
    updated_at: "2026-11-15T10:00:00Z",
    available_actions: [],
    card_confirmed_at: null,
    pool: null,
    work: null,
    ...overrides,
  };
}

type Handler = (request: Request) => unknown;
export type Calls = { method: string; path: string; body: unknown }[];

/** Stubs fetch with "METHOD /path" handlers. A handler returning a Response is used as is. */
export function mockApi(handlers: Record<string, Handler | object>): Calls {
  const calls: Calls = [];
  const all: Record<string, Handler | object> = {
    "GET /api/auth/me": { id: "u1", username: "demo_anya", role: "user", is_demo: true },
    ...handlers,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request
          ? input
          : new Request(new URL(String(input), "http://localhost"), init);
      const path = new URL(request.url, "http://localhost").pathname;
      const key = `${request.method} ${path}`;
      const text = request.method === "GET" ? "" : await request.clone().text();
      let body: unknown = text;
      try {
        body = text ? JSON.parse(text) : undefined;
      } catch {
        // multipart or plain text body
      }
      calls.push({ method: request.method, path, body });
      const handler = all[key];
      if (handler === undefined) return Response.json({ code: "not_found" }, { status: 404 });
      const result = typeof handler === "function" ? (handler as Handler)(request) : handler;
      return result instanceof Response ? result : Response.json(result);
    }),
  );
  return calls;
}

export function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}
