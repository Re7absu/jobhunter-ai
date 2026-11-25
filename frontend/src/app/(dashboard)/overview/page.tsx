"use client";

import { Briefcase, Building2, CalendarCheck, CalendarDays, Clock, MailCheck, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ApplicationDialog } from "@/components/application-panel";
import { Empty, ExtLink, PageHeader, ScoreBadge, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import type { ApplicationRow, ContactedCompany, Kpis, Page, Run } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { categoryLabel, fmtDate, timeAgo } from "@/lib/utils";

const CARDS: { key: keyof Kpis; label: string; icon: React.ElementType; tone: string; href: string }[] = [
  { key: "total_companies", label: "Companies Discovered", icon: Building2, tone: "text-blue-600 bg-blue-50", href: "/companies" },
  { key: "total_jobs", label: "Jobs Found", icon: Briefcase, tone: "text-indigo-600 bg-indigo-50", href: "/jobs" },
  { key: "qualified_opportunities", label: "Qualified Opportunities", icon: Sparkles, tone: "text-emerald-600 bg-emerald-50", href: "/matching" },
  { key: "applications_today", label: "Applications Sent Today", icon: Send, tone: "text-sky-600 bg-sky-50", href: "/analytics" },
  { key: "applications_this_week", label: "Applications This Week", icon: CalendarDays, tone: "text-cyan-600 bg-cyan-50", href: "/applications" },
  { key: "pending_applications", label: "Pending Applications", icon: Clock, tone: "text-amber-600 bg-amber-50", href: "/queue" },
  { key: "responses_received", label: "Responses Received", icon: MailCheck, tone: "text-violet-600 bg-violet-50", href: "/applications" },
  { key: "interviews_scheduled", label: "Interviews Scheduled", icon: CalendarCheck, tone: "text-fuchsia-600 bg-fuchsia-50", href: "/applications" },
];

export default function OverviewPage() {
  const { data: k } = useFetch<Kpis>("/analytics/overview", { pollMs: 30000 });
  const { data: recent, reload } = useFetch<Page<ApplicationRow>>("/applications?sort=updated&page_size=8&statuses=Awaiting%20Approval&statuses=Approved&statuses=Ready%20to%20Apply&statuses=Applied&statuses=Response%20Received&statuses=Interview%20Scheduled&statuses=Follow-up%20Required");
  const { data: today } = useFetch<{ date: string; count: number; companies: ContactedCompany[] }>("/reports/contacted", { pollMs: 30000 });
  const { data: runs } = useFetch<Run[]>("/automation/runs?limit=5", { pollMs: 15000 });
  const [open, setOpen] = useState<number | null>(null);

  return (
    <>
      <PageHeader title="Overview" description="Your autonomous job search for Riyadh & Jeddah at a glance." />
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {CARDS.map(({ key, label, icon: Icon, tone, href }) => (
          <Link key={key} href={href}>
            <Card className="transition-shadow hover:shadow-md">
              <CardContent className="flex items-center gap-3 p-4">
                <div className={`flex h-10 w-10 items-center justify-center rounded-lg dark:bg-white/5 ${tone}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-2xl font-semibold tabular-nums">{k ? k[key] : <Skeleton className="h-7 w-10" />}</div>
                  <div className="text-xs text-muted-foreground">{label}</div>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Active applications</CardTitle>
              <CardDescription>Latest movement in your pipeline</CardDescription>
            </div>
            <Link href="/applications"><Button variant="outline" size="sm">View all</Button></Link>
          </CardHeader>
          <CardContent className="p-0">
            {recent && recent.items.length === 0 ? (
              <Empty title="No active applications yet" hint="Upload your CV, then click “Run now” to discover and analyze jobs." />
            ) : (
              <Table>
                <THead>
                  <TR><TH>Company</TH><TH>Job</TH><TH>City</TH><TH>Category</TH><TH>Score</TH><TH>Status</TH><TH>Updated</TH></TR>
                </THead>
                <TBody>
                  {recent?.items.map((a) => (
                    <TR key={a.id} className="cursor-pointer" onClick={() => setOpen(a.id)}>
                      <TD className="font-medium">{a.company_name}</TD>
                      <TD>{a.job_title}</TD>
                      <TD>{a.city}</TD>
                      <TD className="text-xs">{categoryLabel(a.category)}</TD>
                      <TD><ScoreBadge score={a.match_score} /></TD>
                      <TD><StatusBadge status={a.status} /></TD>
                      <TD className="text-xs text-muted-foreground">{timeAgo(a.status_changed_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Contacted today ({today?.count ?? 0})</CardTitle>
              <CardDescription>Exactly which companies you applied to today</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {today?.companies.length ? (
                today.companies.map((c) => (
                  <div key={c.application_id} className="flex items-center justify-between gap-2 text-sm">
                    <div>
                      <div className="font-medium">{c.company}</div>
                      <div className="text-xs text-muted-foreground">{c.job_title} · {c.method}</div>
                    </div>
                    <ExtLink href={c.source_url} />
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No applications sent today.</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Automation runs</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {runs?.length ? (
                runs.map((r) => (
                  <div key={r.id} className="flex items-center justify-between gap-2">
                    <span className="text-xs text-muted-foreground">{fmtDate(r.started_at, true)} · {r.trigger}</span>
                    <span className={r.status === "failed" ? "text-red-600" : r.status === "running" ? "text-blue-600" : ""}>
                      {r.status}{r.current_step ? ` (${r.current_step})` : ""}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground">No runs yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      <ApplicationDialog appId={open} onClose={() => setOpen(null)} onChanged={() => reload(true)} />
    </>
  );
}
