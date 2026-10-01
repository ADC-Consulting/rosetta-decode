import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getJobTrustReport } from "@/api/jobs";
import type { TrustReportResponse } from "@/api/types";

/**
 * Canonical React Query cache key for a job's trust report. Use this (rather than
 * hand-rolling the array) anywhere a trust-report query needs to be invalidated, so
 * invalidation always targets the same cache entry `useTrustReport` populates.
 *
 * Before this was consolidated, the same `/jobs/{id}/trust-report` resource was cached
 * under two different key shapes (`["job", jobId, "trust-report"]` and
 * `["trust-report", jobId]`) across different components, which meant a verify/refine/
 * restore action had to invalidate both shapes to keep every consumer in sync. This key
 * is now the single source of truth.
 */
export function trustReportQueryKey(
  jobId: string | null | undefined,
): readonly [string, string | null | undefined, string] {
  return ["job", jobId, "trust-report"] as const;
}

/**
 * Shared query for a job's trust report (`GET /jobs/{id}/trust-report`). Wraps a single
 * `useQuery` under the canonical key from `trustReportQueryKey`, so every consumer reads
 * from (and invalidates) the same cache entry.
 *
 * `enabled` composes with `!!jobId` automatically — pass the caller's own gating
 * condition (e.g. a job-status check) and omit it entirely to fetch whenever `jobId` is
 * present.
 */
export function useTrustReport(
  jobId: string | null | undefined,
  options?: { enabled?: boolean },
): UseQueryResult<TrustReportResponse> {
  const enabled = (options?.enabled ?? true) && !!jobId;

  return useQuery<TrustReportResponse>({
    queryKey: trustReportQueryKey(jobId),
    queryFn: () => getJobTrustReport(jobId as string),
    enabled,
  });
}
