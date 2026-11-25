"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { get } from "./api";

/** Tiny data-fetching hook: GET `path` (re-runs when path changes), exposes reload(). */
export function useFetch<T>(path: string | null, opts: { pollMs?: number } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const mounted = useRef(true);

  const load = useCallback(
    async (silent = false) => {
      if (!path) return;
      if (!silent) setLoading(true);
      try {
        const d = await get<T>(path);
        if (mounted.current) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (mounted.current) setError((e as Error).message);
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [path],
  );

  useEffect(() => {
    mounted.current = true;
    load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  useEffect(() => {
    if (!opts.pollMs) return;
    const t = setInterval(() => load(true), opts.pollMs);
    return () => clearInterval(t);
  }, [load, opts.pollMs]);

  return { data, error, loading, reload: load, setData };
}

/** Wrap an async action with toast feedback. */
export async function act<T>(fn: () => Promise<T>, success?: string): Promise<T | undefined> {
  try {
    const r = await fn();
    if (success) toast.success(success);
    return r;
  } catch (e) {
    toast.error((e as Error).message);
    return undefined;
  }
}
