import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";

type AiState = components["schemas"]["AiState"];
export function useAiState(caseId: string | null) {
  const [state, setState] = useState<AiState | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    setState(null);
    setError(false);
    if (!caseId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const { data, error: apiError } = await api.GET("/api/cases/{id}", {
          params: { path: { id: caseId as string } },
        });
        if (stopped) return;
        if (apiError || !data) {
          setError(true);
          return;
        }
        setState(data.ai_state);
        if (data.ai_state === "thinking") timer = setTimeout(poll, 2000);
      } catch {
        if (!stopped) setError(true);
      }
    }
    void poll();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [caseId]);
  return { state, error };
}
