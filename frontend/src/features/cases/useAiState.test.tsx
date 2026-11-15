import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useAiState } from "./useAiState";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
it("stops after a completed state", async () => {
  const fetcher = vi.fn(async () => Response.json({ ai_state: "idle" }));
  vi.stubGlobal("fetch", fetcher);
  const { result } = renderHook(() => useAiState("00000000-0000-4000-8000-000000000001"));
  await waitFor(() => expect(result.current.state).toBe("idle"));
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it("stops polling when unmounted", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn(async () => Response.json({ ai_state: "thinking" }));
  vi.stubGlobal("fetch", fetcher);
  const { unmount } = renderHook(() => useAiState("00000000-0000-4000-8000-000000000001"));
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(fetcher).toHaveBeenCalledTimes(1);
});
