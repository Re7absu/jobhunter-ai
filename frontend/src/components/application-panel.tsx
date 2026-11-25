"use client";

import { AlertTriangle, Check, Copy, ExternalLink, Loader2, RefreshCw, Send, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ExtLink, ScoreBadge, SkillChips, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge, Input, Label, Select, Textarea } from "@/components/ui/primitives";
import { get, patch, post, put } from "@/lib/api";
import { type ApplicationDetail, type FormAssist, STATUSES } from "@/lib/types";
import { act } from "@/lib/use-fetch";
import { categoryLabel, cn, fmtDate, levelLabel, methodLabel, sourceLabel } from "@/lib/utils";

type Tab = "email" | "job" | "history";

/** Only reachable through Approve / Send / Mark as applied — never by a manual status change. */
const GUARDED: string[] = ["Approved", "Ready to Apply", "Applied"];

export function ApplicationDialog({
  appId,
  onClose,
  onChanged,
}: {
  appId: number | null;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [tab, setTab] = useState<Tab>("email");

  useEffect(() => {
    if (appId == null) return setApp(null);
    setTab("email");
    get<ApplicationDetail>(`/applications/${appId}`)
      .then(setApp)
      .catch((e) => toast.error((e as Error).message));
  }, [appId]);

  const update = (a: ApplicationDetail | undefined) => {
    if (a) {
      setApp(a);
      onChanged?.();
    }
  };

  return (
    <Dialog open={appId != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        {!app ? (
          <div className="flex justify-center py-16">
            <DialogTitle className="sr-only">Loading application</DialogTitle>
            <DialogDescription className="sr-only">Loading application details</DialogDescription>
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex flex-wrap items-center gap-2">
                {app.job_title} <span className="font-normal text-muted-foreground">at</span> {app.company_name}
              </DialogTitle>
              <DialogDescription asChild>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <StatusBadge status={app.status} />
                  <ScoreBadge score={app.match_score} />
                  {app.match_category && <Badge variant="outline">{app.match_category}</Badge>}
                  <Badge variant="outline">{app.city ?? "—"}</Badge>
                  <Badge variant="outline">{categoryLabel(app.category)}</Badge>
                  <Badge variant="outline">{levelLabel(app.experience_level)}</Badge>
                  <Badge variant="outline">Method: {app.method ?? "not set"}</Badge>
                </div>
              </DialogDescription>
            </DialogHeader>

            <div className="flex gap-1 border-b">
              {(["email", "job", "history"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={cn(
                    "-mb-px border-b-2 px-3 py-2 text-sm capitalize",
                    tab === t ? "border-primary font-medium" : "border-transparent text-muted-foreground",
                  )}
                >
                  {t === "email" ? "Application" : t === "job" ? "Job & match" : "History"}
                </button>
              ))}
            </div>

            {tab === "email" && <EmailTab app={app} onUpdate={update} />}
            {tab === "job" && <JobTab app={app} />}
            {tab === "history" && <HistoryTab app={app} onUpdate={update} />}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function EmailTab({ app, onUpdate }: { app: ApplicationDetail; onUpdate: (a?: ApplicationDetail) => void }) {
  const live = [...app.emails].reverse().find((e) => e.status === "draft" || e.status === "approved");
  const sent = [...app.emails].reverse().find((e) => e.status === "sent");
  const shown = live ?? sent;
  const [subject, setSubject] = useState(shown?.subject ?? "");
  const [body, setBody] = useState(shown?.body ?? "");
  const [instructions, setInstructions] = useState("");
  const [recipient, setRecipient] = useState(app.recipient_email ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmSend, setConfirmSend] = useState(false);
  const [assist, setAssist] = useState<FormAssist | null>(null);

  useEffect(() => {
    setSubject(shown?.subject ?? "");
    setBody(shown?.body ?? "");
    setRecipient(app.recipient_email ?? "");
  }, [shown?.id, shown?.subject, shown?.body, app.recipient_email]);

  const reload = async () => onUpdate(await get<ApplicationDetail>(`/applications/${app.id}`));
  const run = async (key: string, fn: () => Promise<unknown>, msg?: string) => {
    setBusy(key);
    const r = await act(fn, msg);
    setBusy(null);
    return r;
  };
  const dirty = !!live && (subject !== live.subject || body !== live.body);
  const submitted = !!app.applied_at;
  const canDecide = ["Discovered", "Analyzed", "Awaiting Approval"].includes(app.status);

  return (
    <div className="space-y-4">
      {!submitted && (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1">
            <Label>Application method</Label>
            <Select
              value={app.method ?? ""}
              onChange={(e) =>
                run("method", async () => onUpdate(await patch<ApplicationDetail>(`/applications/${app.id}`, { method: e.target.value })))
              }
            >
              <option value="" disabled>
                Choose…
              </option>
              <option value="email">Email (Gmail)</option>
              <option value="online">Online (company site)</option>
            </Select>
          </div>
          {app.method === "email" && (
            <div className="space-y-1 md:col-span-2">
              <Label>Recipient (verified public recruitment email)</Label>
              <div className="flex gap-2">
                <Input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="careers@company.com" />
                {recipient !== (app.recipient_email ?? "") && (
                  <Button
                    variant="outline"
                    onClick={() =>
                      run("recipient", async () =>
                        onUpdate(await patch<ApplicationDetail>(`/applications/${app.id}`, { recipient_email: recipient || null })),
                        "Recipient saved",
                      )
                    }
                  >
                    Save
                  </Button>
                )}
              </div>
              {app.job.company?.email_source_url && (
                <p className="text-xs text-muted-foreground">
                  Source: <ExtLink href={app.job.company.email_source_url.startsWith("http") ? app.job.company.email_source_url : null}>{app.job.company.email_source_url}</ExtLink>
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {shown ? (
        <div className="space-y-2 rounded-lg border p-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant={shown.status === "approved" ? "info" : shown.status === "sent" ? "success" : "outline"}>{shown.status}</Badge>
            v{shown.version} · {shown.generation_method === "llm" ? `AI (${shown.model})` : shown.generation_method}
            {shown.edited && " · edited"} · {fmtDate(shown.updated_at, true)}
          </div>
          {shown.warnings?.length > 0 && (
            <div className="rounded-md bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
              {shown.warnings.map((w) => (
                <div key={w} className="flex gap-1">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {w}
                </div>
              ))}
            </div>
          )}
          <Input value={subject} disabled={!live || submitted} onChange={(e) => setSubject(e.target.value)} className="font-medium" />
          <Textarea value={body} disabled={!live || submitted} onChange={(e) => setBody(e.target.value)} className="min-h-[260px] font-mono text-[13px] leading-relaxed" />
          {dirty && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy === "save"}
              onClick={() => run("save", async () => { await put(`/emails/${live!.id}`, { subject, body }); await reload(); }, "Email saved — re-approval required")}
            >
              Save edits
            </Button>
          )}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">No email generated yet.</div>
      )}

      {!submitted && (
        <div className="flex flex-wrap items-end gap-2">
          <Input
            className="min-w-[220px] flex-1"
            placeholder="Optional instructions for regeneration (e.g. emphasise data engineering)"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
          <Button
            variant="outline"
            disabled={!!busy}
            onClick={() => run("gen", async () => { await post(`/applications/${app.id}/generate-email`, { instructions: instructions || null }); await reload(); }, "New personalized email generated")}
          >
            {busy === "gen" ? <Loader2 className="animate-spin" /> : <RefreshCw />} {shown ? "Regenerate" : "Generate email"}
          </Button>
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
        {canDecide && (
          <>
            <Button variant="outline" disabled={!!busy} onClick={() => run("reject", async () => onUpdate(await post<ApplicationDetail>(`/applications/${app.id}/reject`, { note: "Rejected in review" })), "Application rejected")}>
              <X /> Reject
            </Button>
            <Button disabled={!!busy || dirty} onClick={() => run("approve", async () => onUpdate(await post<ApplicationDetail>(`/applications/${app.id}/approve`)), "Approved")}>
              <Check /> Approve
            </Button>
          </>
        )}
        {app.status === "Approved" && app.method === "email" && (
          <Button variant="success" disabled={!!busy} onClick={() => setConfirmSend(true)}>
            <Send /> Send via Gmail
          </Button>
        )}
        {app.status === "Ready to Apply" && (
          <>
            <Button variant="outline" disabled={!!busy} onClick={() => run("assist", async () => setAssist(await get<FormAssist>(`/applications/${app.id}/form-assist`)))}>
              {busy === "assist" && <Loader2 className="animate-spin" />} Form assistant
            </Button>
            <Button variant="success" disabled={!!busy} onClick={() => {
              if (confirm("Confirm you submitted this application on the company's site?"))
                run("applied", async () => onUpdate(await post<ApplicationDetail>(`/applications/${app.id}/mark-applied`, { confirm: true })), "Marked as applied");
            }}>
              <Check /> Mark as applied
            </Button>
          </>
        )}
      </div>

      {assist && <FormAssistView data={assist} />}

      <Dialog open={confirmSend} onOpenChange={setConfirmSend}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Send this application?</DialogTitle>
            <DialogDescription>
              The approved email will be sent from your Gmail to <b>{app.recipient_email}</b> with your active CV attached. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmSend(false)}>Cancel</Button>
            <Button
              variant="success"
              disabled={busy === "send"}
              onClick={async () => {
                await run("send", async () => onUpdate(await post<ApplicationDetail>(`/applications/${app.id}/send`, { confirm: true })), "Application sent");
                setConfirmSend(false);
              }}
            >
              {busy === "send" ? <Loader2 className="animate-spin" /> : <Send />} Send now
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function FormAssistView({ data }: { data: FormAssist }) {
  const copy = (v: string | null) => v && navigator.clipboard.writeText(v).then(() => toast.success("Copied"));
  const rows = data.fields.length
    ? data.fields.map((f) => ({ label: `${f.label}${f.required ? " *" : ""}`, value: f.suggested_value }))
    : Object.entries(data.profile_values).map(([k, v]) => ({ label: k.replace(/_/g, " "), value: v }));
  return (
    <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Form assistant</div>
        <a href={data.application_url} target="_blank" rel="noopener noreferrer">
          <Button size="sm"><ExternalLink /> Open official application page</Button>
        </a>
      </div>
      {data.notes.map((n) => (
        <p key={n} className="text-xs text-muted-foreground">{n}</p>
      ))}
      <div className="divide-y rounded-md border bg-background">
        {rows.map((r) => (
          <div key={r.label} className="flex items-start gap-3 px-3 py-2 text-sm">
            <div className="w-44 shrink-0 capitalize text-muted-foreground">{r.label}</div>
            <div className="flex-1 whitespace-pre-wrap break-words">{r.value ? (r.value.length > 300 ? `${r.value.slice(0, 300)}…` : r.value) : "—"}</div>
            {r.value && (
              <Button size="icon" variant="ghost" onClick={() => copy(r.value)}>
                <Copy />
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function JobTab({ app }: { app: ApplicationDetail }) {
  const j = app.job;
  const m = j.match;
  return (
    <div className="grid gap-4 md:grid-cols-5">
      <div className="space-y-3 md:col-span-3">
        <div className="flex flex-wrap gap-3 text-sm">
          <ExtLink href={j.source_url}>Source{j.publisher ? ` (${j.publisher})` : ""}</ExtLink>
          <ExtLink href={j.application_url}>Apply link</ExtLink>
          {j.company?.website && <ExtLink href={j.company.website}>Company site</ExtLink>}
          {j.company?.linkedin_url && <ExtLink href={j.company.linkedin_url}>LinkedIn</ExtLink>}
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
          <div>Source: <span className="text-foreground">{j.publisher ? `${j.publisher} via ${sourceLabel(j.source)}` : sourceLabel(j.source)}</span></div>
          <div>Discovery method: <span className="text-foreground">{methodLabel(j.discovery_method)}</span></div>
          <div>Posted: {fmtDate(j.posted_at)}</div>
          <div>Discovered: {fmtDate(j.discovered_at, true)}</div>
          <div>Last seen: {fmtDate(j.last_verified_at, true)}</div>
          <div>Last updated: {fmtDate(j.updated_at, true)}</div>
          {j.seen_sources?.length > 0 && (
            <div className="col-span-2">
              Also found on:{" "}
              {j.seen_sources.map((x, i) => (
                <span key={x.url}>
                  {i > 0 && ", "}
                  <ExtLink href={x.url}>{x.publisher ?? sourceLabel(x.source)}</ExtLink>
                </span>
              ))}
            </div>
          )}
          <div>Experience: {j.experience_text ?? levelLabel(j.experience_level)}</div>
          <div>Salary: {j.salary_text ?? "not published"}</div>
        </div>
        <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/20 p-3 text-sm">{j.description ?? "No description."}</div>
      </div>
      <div className="space-y-3 md:col-span-2">
        {m ? (
          <>
            <div className="flex items-center gap-2">
              <ScoreBadge score={m.score} /> <span className="text-sm font-medium">{m.category}</span>
              <Badge variant="outline">{m.recommendation}</Badge>
            </div>
            <p className="text-sm">{m.explanation}</p>
            <div className="space-y-1"><Label className="text-xs">Matching skills</Label><SkillChips items={m.matching_skills} variant="success" /></div>
            <div className="space-y-1"><Label className="text-xs">Missing skills</Label><SkillChips items={m.missing_skills} variant="danger" /></div>
            <div className="space-y-1"><Label className="text-xs">Transferable</Label><SkillChips items={m.transferable_skills} variant="info" /></div>
            <p className="text-[11px] text-muted-foreground">Analysis: {m.method}{m.model ? ` · ${m.model}` : ""}</p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Not analyzed yet.</p>
        )}
        {j.company?.description && (
          <div className="rounded-md border p-3 text-xs text-muted-foreground">
            <div className="mb-1 font-medium text-foreground">{j.company.name}{j.company.industry ? ` · ${j.company.industry}` : ""}</div>
            {j.company.description}
          </div>
        )}
      </div>
    </div>
  );
}

function HistoryTab({ app, onUpdate }: { app: ApplicationDetail; onUpdate: (a?: ApplicationDetail) => void }) {
  const [status, setStatus] = useState<string>(app.status);
  const [note, setNote] = useState("");
  const [interview, setInterview] = useState("");
  return (
    <div className="space-y-4">
      <div className="grid gap-2 rounded-lg border p-3 md:grid-cols-4">
        <Select value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s} disabled={GUARDED.includes(s) && s !== app.status}>
              {s}{GUARDED.includes(s) && s !== app.status ? " (use review buttons)" : ""}
            </option>
          ))}
        </Select>
        <Input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        {status === "Interview Scheduled" ? (
          <Input type="datetime-local" value={interview} onChange={(e) => setInterview(e.target.value)} />
        ) : (
          <div />
        )}
        <Button
          disabled={status === app.status}
          onClick={async () =>
            onUpdate(
              await act(
                () => patch<ApplicationDetail>(`/applications/${app.id}/status`, {
                  status,
                  note: note || null,
                  interview_at: interview ? new Date(interview).toISOString().slice(0, 19) : null,
                }),
                "Status updated",
              ),
            )
          }
        >
          Update status
        </Button>
      </div>
      <div className="space-y-2">
        <Label>Status timeline</Label>
        <ol className="space-y-2 border-l pl-4">
          {[...app.history].reverse().map((h, i) => (
            <li key={i} className="relative text-sm">
              <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-primary" />
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={h.to_status} />
                <span className="text-xs text-muted-foreground">
                  {fmtDate(h.created_at, true)} · by {h.changed_by}
                </span>
              </div>
              {h.note && <div className="text-xs text-muted-foreground">{h.note}</div>}
            </li>
          ))}
        </ol>
      </div>
      {app.email_history.length > 0 && (
        <div className="space-y-2">
          <Label>Emails</Label>
          {app.email_history.map((e) => (
            <div key={e.id} className="rounded-md border p-2 text-xs">
              <div className="flex flex-wrap gap-2">
                <Badge variant={e.direction === "inbound" ? "violet" : e.status === "sent" ? "success" : "danger"}>
                  {e.direction} · {e.status}
                </Badge>
                <span>{e.direction === "inbound" ? e.from_email : e.to_email}</span>
                <span className="text-muted-foreground">{fmtDate(e.created_at, true)}</span>
                {e.gmail_message_id && <span className="text-muted-foreground">id {e.gmail_message_id}</span>}
              </div>
              <div className="mt-1 font-medium">{e.subject}</div>
              {e.error && <div className="text-red-600">{e.error}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
