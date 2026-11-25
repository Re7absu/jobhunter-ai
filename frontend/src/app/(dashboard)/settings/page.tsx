"use client";

import { CheckCircle2, Mail, Save, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { Switch } from "@/components/ui/switch";
import { get, post, put } from "@/lib/api";
import type { AutomationSettings, AutomationStatus, Run } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { fmtDate, levelLabel } from "@/lib/utils";

const LEVELS = ["internship", "coop", "graduate", "entry", "junior", "mid", "senior"];
const SOURCES: [string, string][] = [["jsearch", "JSearch (Google Jobs: LinkedIn, Indeed, Bayt…)"], ["serpapi", "SerpAPI Google Jobs"], ["ats", "Company ATS boards (Greenhouse, Lever, Ashby, Workable, SmartRecruiters)"], ["careers_page", "Company career pages"]];

export default function SettingsPage() {
  const { data, setData } = useFetch<AutomationSettings>("/automation/settings");
  const { data: status, reload: reloadStatus } = useFetch<AutomationStatus>("/automation/status");
  const { data: gmail, reload: reloadGmail } = useFetch<{ configured: boolean; connected: boolean; email: string | null }>("/gmail/status");
  const { data: runs } = useFetch<Run[]>("/automation/runs?limit=10", { pollMs: 15000 });
  const { data: audit } = useFetch<{ id: number; action: string; entity_type: string | null; entity_id: number | null; created_at: string; ip_address: string | null }[]>("/audit-logs?limit=50");
  const [s, setS] = useState<AutomationSettings | null>(null);
  const [titles, setTitles] = useState("");

  useEffect(() => {
    if (data) { setS(data); setTitles(data.custom_job_titles.join(", ")); }
  }, [data]);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("gmail");
    if (p === "connected") toast.success("Gmail connected");
    if (p === "error") toast.error("Gmail connection failed");
  }, []);

  if (!s) return null;
  const toggle = (k: "preferred_cities" | "job_categories" | "experience_levels" | "sources_enabled", v: string) =>
    setS({ ...s, [k]: s[k].includes(v) ? s[k].filter((x) => x !== v) : [...s[k], v] });
  const num = (k: keyof AutomationSettings) => (e: React.ChangeEvent<HTMLInputElement>) => setS({ ...s, [k]: Number(e.target.value) });

  async function save() {
    const { last_run_at: _a, next_run_at: _b, paused: _c, ...body } = s!;
    const r = await act(() => put<AutomationSettings>("/automation/settings", { ...body, custom_job_titles: titles.split(",").map((t) => t.trim()).filter(Boolean) }), "Settings saved");
    if (r) { setData(r); reloadStatus(true); }
  }

  return (
    <>
      <PageHeader title="Settings" description="Automation, approval rules and integrations." actions={<Button onClick={save}><Save /> Save settings</Button>} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Automation</CardTitle><CardDescription>Daily discovery → analysis → email drafts → approval queue.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <Row label="Pause ALL automation" hint="Kill-switch: no searches, analysis or sending.">
              <Switch checked={s.paused} onCheckedChange={(v) => act(() => post<AutomationSettings>(v ? "/automation/pause" : "/automation/resume"), v ? "Paused" : "Resumed").then((r) => r && (setS(r), setData(r), reloadStatus(true)))} />
            </Row>
            <Row label="Automatic discovery" hint="Run the pipeline on a schedule."><Switch checked={s.auto_discovery} onCheckedChange={(v) => setS({ ...s, auto_discovery: v })} /></Row>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Search frequency (hours)"><Input type="number" min={1} max={168} value={s.search_frequency_hours} onChange={num("search_frequency_hours")} /></Field>
              <Field label="First run hour (Riyadh time)"><Input type="number" min={0} max={23} value={s.run_hour} onChange={num("run_hour")} /></Field>
              <Field label="API queries per run"><Input type="number" min={1} max={200} value={s.max_queries_per_run} onChange={num("max_queries_per_run")} /></Field>
              <Field label="Company boards scanned per run"><Input type="number" min={0} max={200} value={s.max_boards_per_run} onChange={num("max_boards_per_run")} /></Field>
              <Field label="Jobs analyzed per run"><Input type="number" min={1} max={500} value={s.max_jobs_to_analyze_per_run} onChange={num("max_jobs_to_analyze_per_run")} /></Field>
              <Field label="Ignore postings older than (days)"><Input type="number" min={1} max={120} value={s.job_max_age_days} onChange={num("job_max_age_days")} /></Field>
              <Field label="Follow up after (days)"><Input type="number" min={1} max={60} value={s.follow_up_after_days} onChange={num("follow_up_after_days")} /></Field>
            </div>
            <p className="text-xs text-muted-foreground">Last run {fmtDate(s.last_run_at, true)} · next {fmtDate(s.next_run_at, true)}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Targeting</CardTitle><CardDescription>What the engine searches for.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <Chips label="Preferred cities" options={[["Riyadh", "Riyadh"], ["Jeddah", "Jeddah"]]} value={s.preferred_cities} onToggle={(v) => toggle("preferred_cities", v)} />
            <Chips label="Job categories" options={[["technology", "Technology"], ["product_management", "Product Management"]]} value={s.job_categories} onToggle={(v) => toggle("job_categories", v)} />
            <Chips label="Experience levels" options={LEVELS.map((l) => [l, levelLabel(l)])} value={s.experience_levels} onToggle={(v) => toggle("experience_levels", v)} />
            <Chips label="Sources" options={SOURCES} value={s.sources_enabled} onToggle={(v) => toggle("sources_enabled", v)} />
            <Row label="Also search Arabic job titles"><Switch checked={s.include_arabic_titles} onCheckedChange={(v) => setS({ ...s, include_arabic_titles: v })} /></Row>
            <Field label="Extra job titles (comma separated)"><Input value={titles} onChange={(e) => setTitles(e.target.value)} placeholder="Solutions Engineer, Integration Developer" /></Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Matching & applications</CardTitle><CardDescription>Automation only drafts. Nothing is ever sent or submitted without your approval of that specific application.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Minimum match score"><Input type="number" min={0} max={100} value={s.min_match_score} onChange={num("min_match_score")} /></Field>
              <Field label="Max applications per day"><Input type="number" min={0} max={100} value={s.max_daily_applications} onChange={num("max_daily_applications")} /></Field>
            </div>
            <Row label="Auto-generate emails for qualified jobs"><Switch checked={s.auto_generate_emails} onCheckedChange={(v) => setS({ ...s, auto_generate_emails: v })} /></Row>
            <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">
              <b>Approval guarantee:</b> every email needs you to <b>Approve</b> that exact version and then confirm
              <b> Send now</b>. Editing or regenerating cancels the approval. The daily run never sends emails or submits forms.
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Integrations</CardTitle><CardDescription>Credentials are configured in backend/.env — never in the browser.</CardDescription></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between rounded-md border p-3">
              <div className="flex items-center gap-2"><Mail className="h-4 w-4" /> Gmail {gmail?.connected && <span className="text-muted-foreground">({gmail.email})</span>}</div>
              {!gmail?.configured ? (
                <Badge variant="warning">Set GOOGLE_CLIENT_ID/SECRET</Badge>
              ) : gmail.connected ? (
                <Button size="sm" variant="outline" onClick={() => act(() => post("/gmail/disconnect"), "Disconnected").then(() => reloadGmail(true))}>Disconnect</Button>
              ) : (
                <Button size="sm" onClick={() => act(async () => { const r = await get<{ url: string }>("/gmail/auth-url"); window.location.href = r.url; })}>Connect Gmail</Button>
              )}
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <span>OpenAI connection</span>
              <Button size="sm" variant="outline" onClick={async () => {
                const r = await act(() => post<{ ok: boolean; error: string | null }>("/automation/check-openai"));
                if (r) (r.ok ? toast.success("OpenAI key works") : toast.error(r.error ?? "OpenAI check failed"));
                reloadStatus(true);
              }}>Test OpenAI</Button>
            </div>
            {status && Object.entries(status.integrations).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className="capitalize text-muted-foreground">{k.replace(/_/g, " ")}</span>
                {v ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-red-500" />}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Automation runs</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <THead><TR><TH>Started</TH><TH>Trigger</TH><TH>Status</TH><TH>Stats</TH></TR></THead>
            <TBody>
              {runs?.map((r) => (
                <TR key={r.id}>
                  <TD className="text-xs">{fmtDate(r.started_at, true)}</TD>
                  <TD className="text-xs">{r.trigger}</TD>
                  <TD className="text-xs">{r.status}{r.current_step ? ` · ${r.current_step}` : ""}{r.error && <div className="text-red-600">{r.error}</div>}</TD>
                  <TD className="max-w-xl truncate font-mono text-[11px] text-muted-foreground" title={JSON.stringify(r.stats)}>{JSON.stringify(r.stats)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Card id="audit">
        <CardHeader><CardTitle>Audit log</CardTitle><CardDescription>Security-relevant actions on your account.</CardDescription></CardHeader>
        <CardContent className="p-0">
          <Table>
            <THead><TR><TH>When</TH><TH>Action</TH><TH>Entity</TH><TH>IP</TH></TR></THead>
            <TBody>
              {audit?.map((a) => (
                <TR key={a.id}>
                  <TD className="text-xs">{fmtDate(a.created_at, true)}</TD>
                  <TD className="font-mono text-xs">{a.action}</TD>
                  <TD className="text-xs">{a.entity_type ? `${a.entity_type} #${a.entity_id ?? ""}` : "—"}</TD>
                  <TD className="text-xs">{a.ip_address ?? "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div><div className="text-sm font-medium">{label}</div>{hint && <div className="text-xs text-muted-foreground">{hint}</div>}</div>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1"><Label className="text-xs">{label}</Label>{children}</div>;
}

function Chips({ label, options, value, onToggle }: { label: string; options: [string, string][]; value: string[]; onToggle: (v: string) => void }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([v, l]) => (
          <Button key={v} type="button" size="sm" variant={value.includes(v) ? "default" : "outline"} onClick={() => onToggle(v)}>{l}</Button>
        ))}
      </div>
    </div>
  );
}
