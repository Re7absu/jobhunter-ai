"use client";

import { FileSpreadsheet, FileText, RefreshCw } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ExtLink, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { download, post } from "@/lib/api";
import type { Charts, DailyReport } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { categoryLabel, fmtDate } from "@/lib/utils";

const COLORS = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"];

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const { data: c } = useFetch<Charts>(`/analytics/charts?days=${days}`);
  const { data: reports, reload } = useFetch<DailyReport[]>("/reports/daily?limit=30");
  const [selected, setSelected] = useState<string | null>(null);
  const report = reports?.find((r) => r.report_date === selected) ?? reports?.[0];

  return (
    <>
      <PageHeader
        title="Analytics & Reports"
        description="Application volume, conversion and match quality over time."
        actions={
          <>
            <Select className="w-32" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={14}>14 days</option><option value={30}>30 days</option><option value={90}>90 days</option>
            </Select>
            <Button variant="outline" onClick={() => act(() => download("/exports/applications.csv", "applications.csv"))}><FileText /> CSV</Button>
            <Button variant="outline" onClick={() => act(() => download("/exports/applications.xlsx", "applications.xlsx"))}><FileSpreadsheet /> Excel</Button>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Companies contacted" value={c?.companies_contacted} />
        <Stat label="Response rate" value={c ? `${c.response_rate}%` : undefined} />
        <Stat label="Interview conversion" value={c ? `${c.interview_rate}%` : undefined} />
        <Stat label="Average match score" value={c?.average_match_score != null ? `${c.average_match_score}%` : "—"} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard title="Applications per day">
          <LineChart data={c?.applications_per_day ?? []}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
            <YAxis allowDecimals={false} fontSize={11} />
            <Tooltip />
            <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot={false} />
          </LineChart>
        </ChartCard>
        <ChartCard title="Applications per week">
          <BarChart data={c?.applications_per_week ?? []}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="week" fontSize={11} />
            <YAxis allowDecimals={false} fontSize={11} />
            <Tooltip />
            <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Applications by city">
          <PieChart>
            <Pie data={c?.applications_by_city ?? []} dataKey="count" nameKey="city" outerRadius={90} label>
              {(c?.applications_by_city ?? []).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        </ChartCard>
        <ChartCard title="Applications by job category">
          <PieChart>
            <Pie data={(c?.applications_by_category ?? []).map((x) => ({ ...x, category: categoryLabel(x.category) }))} dataKey="count" nameKey="category" innerRadius={50} outerRadius={90} label>
              {(c?.applications_by_category ?? []).map((_, i) => <Cell key={i} fill={COLORS[(i + 2) % COLORS.length]} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        </ChartCard>
        <ChartCard title="Match score distribution">
          <BarChart data={c?.match_score_distribution ?? []}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="bucket" fontSize={11} />
            <YAxis allowDecimals={false} fontSize={11} />
            <Tooltip />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {(c?.match_score_distribution ?? []).map((_, i) => <Cell key={i} fill={["#ef4444", "#f59e0b", "#2563eb", "#10b981"][i]} />)}
            </Bar>
          </BarChart>
        </ChartCard>
        <ChartCard title="Pipeline by status">
          <BarChart data={(c?.status_breakdown ?? []).filter((s) => s.count > 0)} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" allowDecimals={false} fontSize={11} />
            <YAxis type="category" dataKey="status" width={130} fontSize={11} />
            <Tooltip />
            <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ChartCard>
      </div>

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle>Daily report</CardTitle>
            <CardDescription>Exactly which companies were contacted on a given day.</CardDescription>
          </div>
          <div className="flex gap-2">
            <Select className="w-44" value={report?.report_date ?? ""} onChange={(e) => setSelected(e.target.value)}>
              {reports?.map((r) => <option key={r.id} value={r.report_date}>{r.report_date}</option>)}
            </Select>
            <Button variant="outline" onClick={() => act(() => post("/reports/daily/today"), "Today's report refreshed").then(() => reload(true))}><RefreshCw /> Refresh today</Button>
          </div>
        </CardHeader>
        <CardContent>
          {report ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3 text-center md:grid-cols-7">
                {[["New companies", report.new_companies], ["New jobs", report.new_jobs], ["Analyzed", report.jobs_analyzed], ["Qualified", report.qualified],
                  ["Emails drafted", report.emails_generated], ["Applications sent", report.applications_sent], ["Responses", report.responses]].map(([l, v]) => (
                  <div key={l as string} className="rounded-lg border p-2"><div className="text-xl font-semibold">{v}</div><div className="text-[11px] text-muted-foreground">{l}</div></div>
                ))}
              </div>
              <Table>
                <THead><TR><TH>Company</TH><TH>Job</TH><TH>City</TH><TH>Method</TH><TH>Recipient</TH><TH>Time</TH><TH>Source</TH></TR></THead>
                <TBody>
                  {report.companies_contacted.length === 0 ? (
                    <TR><TD colSpan={7} className="py-6 text-center text-muted-foreground">No companies contacted on {report.report_date}.</TD></TR>
                  ) : report.companies_contacted.map((x) => (
                    <TR key={x.application_id}>
                      <TD className="font-medium">{x.company}</TD><TD>{x.job_title}</TD><TD>{x.city}</TD><TD className="capitalize">{x.method}</TD>
                      <TD className="text-xs">{x.recipient ?? "—"}</TD><TD className="text-xs">{x.applied_at.slice(11)}</TD><TD><ExtLink href={x.source_url} /></TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <p className="text-xs text-muted-foreground">Last updated {fmtDate(report.updated_at, true)}</p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No reports yet — press “Refresh today”.</p>
          )}
        </CardContent>
      </Card>
    </>
  );
}

function Stat({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <Card><CardContent className="p-4"><div className="text-2xl font-semibold tabular-nums">{value ?? "…"}</div><div className="text-xs text-muted-foreground">{label}</div></CardContent></Card>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactElement }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader>
      <CardContent className="h-64">
        <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
