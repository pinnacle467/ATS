import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

/**
 * Lightweight shared cache for "reference data" (jobs, users, tags,
 * departments, pipeline stages, interview kits) that many pages fetch on
 * every mount even though it rarely changes. Without this, navigating
 * Candidates -> Jobs -> Candidates re-fetches the same jobs/users/tags list
 * from scratch every single time, which is the main cause of pages feeling
 * slow to switch between (see PRD: VPS page-load performance fix).
 *
 * Each resource is cached for `ttlMs` and shared across every component that
 * calls its hook — the first caller triggers the fetch, everyone else reuses
 * the in-flight promise or the cached result. Call `invalidate()` right after
 * a mutation (create/update/delete) so the next read is fresh instead of
 * waiting out the TTL.
 */
function createResource(endpoint, { ttlMs = 5 * 60 * 1000 } = {}) {
  let cache = null;
  let cachedAt = 0;
  let inflight = null;
  const listeners = new Set();

  const notify = () => listeners.forEach((fn) => fn(cache));

  const fetchNow = () => {
    inflight = api
      .get(endpoint)
      .then((r) => {
        cache = r.data;
        cachedAt = Date.now();
        inflight = null;
        notify();
        return cache;
      })
      .catch((e) => {
        inflight = null;
        throw e;
      });
    return inflight;
  };

  const ensure = () => {
    if (cache !== null && Date.now() - cachedAt < ttlMs) return Promise.resolve(cache);
    if (inflight) return inflight;
    return fetchNow();
  };

  const invalidate = () => {
    cache = null;
    cachedAt = 0;
  };

  const useResource = (fallback) => {
    const [data, setData] = useState(cache ?? fallback);
    const [loading, setLoading] = useState(cache === null);

    useEffect(() => {
      const onUpdate = (val) => setData(val);
      listeners.add(onUpdate);
      let alive = true;
      ensure()
        .then((val) => { if (alive) setData(val); })
        .finally(() => { if (alive) setLoading(false); });
      return () => { alive = false; listeners.delete(onUpdate); };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return [data ?? fallback, loading];
  };

  return { useResource, invalidate, refresh: fetchNow };
}

const jobsResource = createResource('/jobs');
const usersResource = createResource('/users');
const tagsResource = createResource('/tags');
const departmentsResource = createResource('/departments');
const pipelineResource = createResource('/settings/pipeline');
const interviewKitsResource = createResource('/interview-kits');

export const useCachedJobs = (fallback = []) => jobsResource.useResource(fallback);
export const useCachedUsers = (fallback = []) => usersResource.useResource(fallback);
export const useCachedTags = (fallback = []) => tagsResource.useResource(fallback);
export const useCachedDepartments = (fallback = []) => departmentsResource.useResource(fallback);
export const useCachedPipelineStages = (fallback = { stages: [] }) => pipelineResource.useResource(fallback);
export const useCachedInterviewKits = (fallback = []) => interviewKitsResource.useResource(fallback);

export const invalidateJobs = jobsResource.invalidate;
export const invalidateUsers = usersResource.invalidate;
export const invalidateTags = tagsResource.invalidate;
export const invalidateDepartments = departmentsResource.invalidate;
export const invalidatePipelineStages = pipelineResource.invalidate;
export const invalidateInterviewKits = interviewKitsResource.invalidate;

// Direct (non-hook) refetchers — call after a mutation (create/update/delete)
// so every already-mounted consumer of that resource updates reactively
// instead of showing stale data until their next remount.
export const refreshJobs = jobsResource.refresh;
export const refreshUsers = usersResource.refresh;
export const refreshTags = tagsResource.refresh;
export const refreshDepartments = departmentsResource.refresh;
export const refreshPipelineStages = pipelineResource.refresh;
export const refreshInterviewKits = interviewKitsResource.refresh;
