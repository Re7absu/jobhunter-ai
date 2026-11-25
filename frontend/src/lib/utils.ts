import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Backend stores naive UTC timestamps. */
export function parseUtc(value?: string | null): Date | null {
  if (!value) return null;
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function fmtDate(value?: string | null, withTime = false): string {
  const d = parseUtc(value);
  if (!d) return "—";
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone: "Asia/Riyadh",
  });
}

export function timeAgo(value?: string | null): string {
  const d = parseUtc(value);
  if (!d) return "—";
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const categoryLabel = (c?: string | null) =>
  c === "product_management" ? "Product Management" : c === "technology" ? "Technology" : c ?? "—";

export const levelLabel = (l?: string | null) =>
  ({ internship: "Internship", coop: "Co-op", graduate: "Graduate", entry: "Entry", junior: "Junior", mid: "Mid", senior: "Senior" })[
    l ?? ""
  ] ?? "—";

const SOURCE_LABELS: Record<string, string> = {
  jsearch: "JSearch",
  serpapi: "SerpAPI",
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workable: "Workable",
  smartrecruiters: "SmartRecruiters",
  careers_page: "Careers page",
};
export const sourceLabel = (s?: string | null) => (s ? SOURCE_LABELS[s] ?? s : "—");

const METHOD_LABELS: Record<string, string> = {
  search_api: "Job search API",
  ats_board_auto: "Company ATS board (auto-detected)",
  ats_board_manual: "Company ATS board (tracked)",
  careers_page_auto: "Careers page (auto-detected)",
  careers_page_manual: "Careers page (tracked)",
};
export const methodLabel = (m?: string | null) => (m ? METHOD_LABELS[m] ?? m : "—");
export const methodShort = (m?: string | null) =>
  m?.startsWith("ats_board") ? "ATS board" : m?.startsWith("careers_page") ? "Careers page" : "Search API";

export function buildQuery(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === "all") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
