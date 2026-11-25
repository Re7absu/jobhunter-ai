"use client";

import { ChevronLeft, ChevronRight, ExternalLink, Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, Input, Select } from "@/components/ui/primitives";
import { STATUSES } from "@/lib/types";
import { type AppFilters } from "@/lib/store";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const STATUS_VARIANT: Record<string, "secondary" | "info" | "warning" | "success" | "danger" | "violet" | "outline"> = {
  Discovered: "secondary",
  Analyzed: "outline",
  "Awaiting Approval": "warning",
  Approved: "info",
  "Ready to Apply": "info",
  Applied: "success",
  "Follow-up Required": "warning",
  "Response Received": "violet",
  "Interview Scheduled": "violet",
  Rejected: "danger",
  Closed: "secondary",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={STATUS_VARIANT[status] ?? "outline"}>{status}</Badge>;
}

export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return <span className="text-xs text-muted-foreground">—</span>;
  const variant = score >= 80 ? "success" : score >= 65 ? "info" : score >= 50 ? "warning" : "danger";
  return (
    <Badge variant={variant} className="tabular-nums">
      {score}%
    </Badge>
  );
}

export function ExtLink({ href, children, className }: { href?: string | null; children?: React.ReactNode; className?: string }) {
  if (!href) return <span className="text-muted-foreground">—</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cn("inline-flex items-center gap-1 text-primary hover:underline", className)}>
      {children ?? "Open"} <ExternalLink className="h-3 w-3" />
    </a>
  );
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      <Inbox className="h-8 w-8 text-muted-foreground/60" />
      <div className="font-medium">{title}</div>
      {hint && <p className="max-w-md text-sm text-muted-foreground">{hint}</p>}
      {action}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
      <span>
        {total} result{total === 1 ? "" : "s"}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft />
        </Button>
        <span>
          Page {page} / {pages}
        </span>
        <Button variant="ghost" size="icon" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export function FiltersBar({
  filters,
  set,
  reset,
  showStatus = true,
  extra,
}: {
  filters: AppFilters;
  set: <K extends keyof AppFilters>(k: K, v: AppFilters[K]) => void;
  reset: () => void;
  showStatus?: boolean;
  extra?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="grid grid-cols-2 gap-2 p-3 md:grid-cols-4 xl:grid-cols-8">
        <Input placeholder="Company or title…" value={filters.company} onChange={(e) => set("company", e.target.value)} className="col-span-2" />
        <Select value={filters.city} onChange={(e) => set("city", e.target.value)}>
          <option value="all">All cities</option>
          <option value="Riyadh">Riyadh</option>
          <option value="Jeddah">Jeddah</option>
        </Select>
        <Select value={filters.category} onChange={(e) => set("category", e.target.value)}>
          <option value="all">All categories</option>
          <option value="technology">Technology</option>
          <option value="product_management">Product Management</option>
        </Select>
        {showStatus && (
          <Select value={filters.status} onChange={(e) => set("status", e.target.value)}>
            <option value="all">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        )}
        <Select value={filters.minScore} onChange={(e) => set("minScore", e.target.value)}>
          <option value="">Any score</option>
          <option value="80">80%+ Excellent</option>
          <option value="65">65%+ Good</option>
          <option value="50">50%+ Potential</option>
        </Select>
        <Input type="date" title="From" value={filters.dateFrom} onChange={(e) => set("dateFrom", e.target.value)} />
        <div className="flex gap-2">
          <Input type="date" title="To" value={filters.dateTo} onChange={(e) => set("dateTo", e.target.value)} />
          <Button variant="ghost" size="sm" onClick={reset}>
            Reset
          </Button>
        </div>
        {extra}
      </CardContent>
    </Card>
  );
}

export function filtersToParams(f: AppFilters, applied = false) {
  return {
    city: f.city,
    category: f.category,
    status: f.status,
    min_score: f.minScore,
    company: f.company,
    date_from: f.dateFrom ? `${f.dateFrom}T00:00:00` : undefined,
    date_to: f.dateTo ? `${f.dateTo}T23:59:59` : undefined,
    applied_only: applied || undefined,
  };
}

export function SkillChips({ items, variant = "secondary" }: { items: string[]; variant?: "secondary" | "success" | "danger" | "info" | "warning" }) {
  if (!items?.length) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((s) => (
        <Badge key={s} variant={variant}>
          {s}
        </Badge>
      ))}
    </div>
  );
}
