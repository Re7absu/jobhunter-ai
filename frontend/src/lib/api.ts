"use client";

import { useAuth } from "./store";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function authHeaders(): Record<string, string> {
  const token = useAuth.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    useAuth.getState().logout();
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail))
        msg = body.detail
          .map((d: { loc?: (string | number)[]; msg?: string }) => `${d.loc?.slice(-1)[0] ?? "field"}: ${d.msg ?? "invalid"}`)
          .join("; ");
      else msg = JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(),
      ...(headers as Record<string, string>),
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  return handle<T>(res);
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const patch = <T>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });

export async function upload<T>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body: fd, headers: authHeaders() });
  return handle<T>(res);
}

/** Download an authenticated file (CSV/XLSX/CV) and trigger a browser save. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, `Download failed (${res.status})`);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
