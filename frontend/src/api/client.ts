import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.split("=")[1];
}

// Sessions + CSRF on one origin: Django expects the csrftoken cookie echoed in a header.
const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (UNSAFE_METHODS.has(request.method)) {
      const token = readCookie("csrftoken");
      if (token) request.headers.set("X-CSRFToken", decodeURIComponent(token));
    }
    return request;
  },
};

export const api = createClient<paths>({
  // Absolute same-origin URL: browsers resolve "" too, but Node (tests) needs an origin.
  baseUrl: globalThis.location?.origin ?? "",
  credentials: "same-origin",
  // Resolve fetch at call time so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
});
api.use(csrfMiddleware);
