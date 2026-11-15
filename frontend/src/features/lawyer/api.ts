import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { ApiError } from "@/features/cases/api";

export type QueueItem = components["schemas"]["ReviewQueueItem"];
export type ReviewClaim = components["schemas"]["ReviewClaim"];
export type PoolCard = components["schemas"]["PoolCard"];
export type LawyerCase = components["schemas"]["LawyerCase"];
export type OfferInput = components["schemas"]["OfferInput"];
type ApiErrorBody = components["schemas"]["ApiError"];

function csrf(): { "X-CSRFToken": string } {
  const token = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];
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

const keys = {
  queue: ["lawyer", "queue"] as const,
  review: (id: string) => ["lawyer", "review", id] as const,
  pool: (filters: object) => ["lawyer", "pool", filters] as const,
  card: (id: string) => ["lawyer", "pool-card", id] as const,
  cases: ["lawyer", "cases"] as const,
  case: (id: string) => ["lawyer", "case", id] as const,
};

export function useQueue() {
  return useQuery({
    queryKey: keys.queue,
    queryFn: () => unwrap(api.GET("/api/lawyer/claims")),
    // The queue is shared: refresh so a claim taken by someone else disappears.
    refetchInterval: 10_000,
  });
}

export function useReview(id: string) {
  return useQuery({
    queryKey: keys.review(id),
    queryFn: () => unwrap(api.GET("/api/lawyer/claims/{id}", { params: { path: { id } } })),
  });
}

export function useTake() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (item: QueueItem) =>
      unwrap(
        api.POST("/api/lawyer/claims/{id}/take", {
          params: { path: { id: item.id }, header: csrf() },
          body: { expected_version: item.case_version },
        }),
      ),
    onSuccess: (claim) => client.setQueryData(keys.review(claim.id), claim),
    onSettled: () => client.invalidateQueries({ queryKey: keys.queue }),
  });
}

function reviewBody(claim: ReviewClaim) {
  return {
    expected_version: claim.case_version,
    assignment_version: claim.assignment_version,
    claim_version: claim.version.version,
  };
}

export function useApprove() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (claim: ReviewClaim) =>
      unwrap(
        api.POST("/api/lawyer/claims/{id}/approve", {
          params: { path: { id: claim.id }, header: csrf() },
          body: reviewBody(claim),
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: keys.queue }),
  });
}

export function useEdit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { claim: ReviewClaim; text: string; comment: string }) =>
      unwrap(
        api.POST("/api/lawyer/claims/{id}/edit", {
          params: { path: { id: input.claim.id }, header: csrf() },
          body: { ...reviewBody(input.claim), template_text: input.text, comment: input.comment },
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: keys.queue }),
  });
}

export type PoolFilters = {
  category?: string;
  city?: string;
  min_kopecks?: number;
  max_kopecks?: number;
};

export function usePool(filters: PoolFilters) {
  return useQuery({
    queryKey: keys.pool(filters),
    queryFn: () => unwrap(api.GET("/api/lawyer/pool", { params: { query: filters } })),
  });
}

export function usePoolCard(id: string) {
  return useQuery({
    queryKey: keys.card(id),
    queryFn: () => unwrap(api.GET("/api/lawyer/pool/{id}", { params: { path: { id } } })),
  });
}

export function useMakeOffer(cardId: string) {
  return useMutation({
    mutationFn: (body: OfferInput) =>
      unwrap(
        api.POST("/api/lawyer/pool/{id}/offers", {
          params: { path: { id: cardId }, header: csrf() },
          body,
        }),
      ),
  });
}

export function useLawyerCases() {
  return useQuery({
    queryKey: keys.cases,
    queryFn: () => unwrap(api.GET("/api/lawyer/cases")),
  });
}

export function useLawyerCase(id: string) {
  return useQuery({
    queryKey: keys.case(id),
    queryFn: () => unwrap(api.GET("/api/lawyer/cases/{id}", { params: { path: { id } } })),
  });
}

export function useStartWork(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (version: number) =>
      unwrap(
        api.POST("/api/lawyer/cases/{id}/start", {
          params: { path: { id }, header: csrf() },
          body: { expected_version: version },
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: keys.case(id) }),
  });
}

export function useSubmitWork(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { version: number; text: string }) =>
      unwrap(
        api.POST("/api/lawyer/cases/{id}/submit-work", {
          params: { path: { id }, header: csrf() },
          body: { expected_version: input.version, text: input.text },
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: keys.case(id) }),
  });
}
