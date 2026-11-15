import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type CaseDetail = components["schemas"]["CaseDetail"];
export type CaseSummary = components["schemas"]["CaseSummary"];
export type Message = components["schemas"]["Message"];
export type Card = components["schemas"]["Card"];
export type Fact = components["schemas"]["Fact"];
export type CompanyCheck = components["schemas"]["CompanyCheck"];
export type PathOption = components["schemas"]["PathOption"];
export type CasePath = components["schemas"]["CasePath"];
export type Plan = components["schemas"]["SelfGuidedPlan"];
export type Claim = components["schemas"]["Claim"];
export type PersonalData = components["schemas"]["ClaimPersonalData"];
export type Action = components["schemas"]["Action"];
type ApiErrorBody = components["schemas"]["ApiError"];

/** Error from the API with the server's message and field names (never values). */
export class ApiError extends Error {
  readonly status: number;
  readonly fields: string[];

  constructor(status: number, body: Partial<ApiErrorBody> | undefined) {
    super(body?.message ?? "Не удалось выполнить запрос. Попробуйте ещё раз.");
    this.status = status;
    const details = body?.details ?? {};
    this.fields = Array.isArray(details.fields) ? details.fields : Object.keys(details);
  }
}

export const CONSENT_TEXT_VERSION = "demo-v1";

function csrf(): { "X-CSRFToken": string } {
  const token = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];
  // The client middleware sets the same header; this satisfies the typed contract.
  return { "X-CSRFToken": token ? decodeURIComponent(token) : "" };
}

async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (error !== undefined || data === undefined) {
    throw new ApiError(response.status, error as Partial<ApiErrorBody> | undefined);
  }
  return data;
}

export const keys = {
  cases: ["cases"] as const,
  case: (id: string) => ["case", id] as const,
  part: (id: string, part: string) => ["case", id, part] as const,
};

const POLL_MS = 1500;

export function useCases() {
  return useQuery({
    queryKey: keys.cases,
    queryFn: () => unwrap(api.GET("/api/cases")),
  });
}

/** Polls while the AI is working; everything else on the screen derives from this. */
export function useCase(id: string) {
  return useQuery({
    queryKey: keys.case(id),
    queryFn: () => unwrap(api.GET("/api/cases/{id}", { params: { path: { id } } })),
    refetchInterval: (query) => (query.state.data?.ai_state === "thinking" ? POLL_MS : false),
  });
}

export function useMessages(id: string, version: number | undefined) {
  return useQuery({
    queryKey: [...keys.part(id, "messages"), version],
    queryFn: () => unwrap(api.GET("/api/cases/{id}/messages", { params: { path: { id } } })),
    enabled: version !== undefined,
  });
}

export function useCard(id: string, version: number | undefined) {
  return useQuery({
    queryKey: [...keys.part(id, "card"), version],
    queryFn: () => unwrap(api.GET("/api/cases/{id}/card", { params: { path: { id } } })),
    enabled: version !== undefined,
  });
}

export function useCompany(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.part(id, "company"),
    queryFn: () => unwrap(api.GET("/api/cases/{id}/company", { params: { path: { id } } })),
    enabled,
  });
}

export function usePaths(id: string, version: number | undefined) {
  return useQuery({
    queryKey: [...keys.part(id, "paths"), version],
    queryFn: () => unwrap(api.GET("/api/cases/{id}/paths", { params: { path: { id } } })),
    enabled: version !== undefined,
  });
}

export function usePlan(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.part(id, "plan"),
    queryFn: () => unwrap(api.GET("/api/cases/{id}/plan", { params: { path: { id } } })),
    enabled,
  });
}

export function useClaim(id: string, version: number | undefined, enabled: boolean) {
  return useQuery({
    queryKey: [...keys.part(id, "claim"), version],
    queryFn: () => unwrap(api.GET("/api/cases/{id}/claim", { params: { path: { id } } })),
    enabled: enabled && version !== undefined,
  });
}

/** Mutations refresh the case; dependent queries are keyed by its version. */
function useCaseMutation<TInput, TResult>(id: string, run: (input: TInput) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSettled: () => client.invalidateQueries({ queryKey: keys.case(id) }),
  });
}

export function useCreateCase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (message: string) =>
      unwrap(
        api.POST("/api/cases", {
          params: { header: csrf() },
          body: { message, consent: { accepted: true, text_version: CONSENT_TEXT_VERSION } },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.cases }),
  });
}

export function useSendMessage(id: string) {
  return useCaseMutation(id, (input: { text: string; version: number }) =>
    unwrap(
      api.POST("/api/cases/{id}/messages", {
        params: { path: { id }, header: csrf() },
        body: { text: input.text, expected_version: input.version },
      }),
    ),
  );
}

export function useUploadDocument(id: string) {
  return useCaseMutation(id, (input: { file: File; version: number }) =>
    unwrap(
      api.POST("/api/cases/{id}/documents", {
        params: { path: { id }, header: csrf() },
        body: { file: "", expected_version: input.version },
        bodySerializer: () => {
          const form = new FormData();
          form.append("file", input.file);
          form.append("expected_version", String(input.version));
          return form;
        },
      }),
    ),
  );
}

export function useEditFact(id: string) {
  return useCaseMutation(id, (input: { key: string; value: string; version: number }) =>
    unwrap(
      api.PATCH("/api/cases/{id}/card/facts/{key}", {
        params: { path: { id, key: input.key }, header: csrf() },
        body: { value: input.value, expected_version: input.version },
      }),
    ),
  );
}

export function useConfirmCard(id: string) {
  return useCaseMutation(id, (input: { version: number; cardVersion: number }) =>
    unwrap(
      api.POST("/api/cases/{id}/card/confirm", {
        params: { path: { id }, header: csrf() },
        body: { expected_version: input.version, card_version: input.cardVersion },
      }),
    ),
  );
}

export function useChoosePath(id: string) {
  return useCaseMutation(id, (input: { path: CasePath; version: number }) =>
    unwrap(
      api.POST("/api/cases/{id}/path", {
        params: { path: { id }, header: csrf() },
        body: { path: input.path, expected_version: input.version },
      }),
    ),
  );
}

export function useCreateClaim(id: string) {
  return useCaseMutation(id, (version: number) =>
    unwrap(
      api.POST("/api/cases/{id}/claim", {
        params: { path: { id }, header: csrf() },
        body: { expected_version: version },
      }),
    ),
  );
}

export function useConfirmPersonalData(id: string) {
  return useCaseMutation(id, (input: { data: PersonalData; version: number }) =>
    unwrap(
      api.PUT("/api/cases/{id}/claim/personal-data", {
        params: { path: { id }, header: csrf() },
        body: { expected_version: input.version, data: input.data, confirmed: true },
      }),
    ),
  );
}

export function useSubmitClaim(id: string) {
  return useCaseMutation(id, (input: { version: number; claimVersion: number }) =>
    unwrap(
      api.POST("/api/cases/{id}/claim/submit", {
        params: { path: { id }, header: csrf() },
        body: {
          expected_version: input.version,
          claim_version: input.claimVersion,
          consent: { accepted: true, text_version: CONSENT_TEXT_VERSION },
        },
      }),
    ),
  );
}

export function has(caseData: { available_actions: Action[] } | undefined, action: Action) {
  return caseData?.available_actions.includes(action) ?? false;
}
