"use client";

import { RefreshCw, Send, X } from "lucide-react";
import { useState } from "react";

import { Empty, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, Input, Select, Textarea } from "@/components/ui/primitives";
import { post, put } from "@/lib/api";
import type { FollowUp } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { buildQuery, fmtDate, parseUtc } from "@/lib/utils";

export default function FollowupsPage() {
  const [status, setStatus] = useState("pending");
  const { data, reload } = useFetch<FollowUp[]>(`/followups${buildQuery({ status })}`);

  return (
    <>
      <PageHeader
        title="Follow-ups"
        description="Applications with no reply after your configured delay get a drafted follow-up. Sending always requires your confirmation."
        actions={
          <>
            <Select className="w-36" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="pending">Pending</option><option value="sent">Sent</option><option value="dismissed">Dismissed</option><option value="all">All</option>
            </Select>
            <Button variant="outline" onClick={() => act(() => post<{ replies_detected: number; followups_due: number }>("/followups/refresh")).then((r) => { if (r) alert(`${r.replies_detected} new replies · ${r.followups_due} follow-ups due`); reload(true); })}>
              <RefreshCw /> Check replies & due items
            </Button>
          </>
        }
      />
      {data && data.length === 0 && <Card><Empty title="Nothing here" hint="Follow-ups are scheduled automatically after each application is sent." /></Card>}
      <div className="space-y-3">
        {data?.map((f) => <FollowUpCard key={f.id} f={f} onChange={() => reload(true)} />)}
      </div>
    </>
  );
}

function FollowUpCard({ f, onChange }: { f: FollowUp; onChange: () => void }) {
  const [subject, setSubject] = useState(f.subject ?? "");
  const [body, setBody] = useState(f.body ?? "");
  const due = (parseUtc(f.due_at)?.getTime() ?? 0) <= Date.now();
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="font-medium">{f.company_name} — {f.job_title}</div>
          <Badge variant={f.status === "sent" ? "success" : f.status === "dismissed" ? "secondary" : due ? "warning" : "outline"}>
            {f.status === "pending" ? (due ? "due" : "scheduled") : f.status}
          </Badge>
          <span className="text-xs text-muted-foreground">Due {fmtDate(f.due_at)}{f.sent_at ? ` · sent ${fmtDate(f.sent_at, true)}` : ""}</span>
        </div>
        {f.status === "pending" && (
          f.body || body ? (
            <>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
              <Textarea value={body} onChange={(e) => setBody(e.target.value)} className="min-h-[140px]" />
              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="ghost" onClick={() => act(() => post(`/followups/${f.id}/dismiss`), "Dismissed").then(onChange)}><X /> Dismiss</Button>
                {(subject !== f.subject || body !== f.body) && (
                  <Button variant="outline" onClick={() => act(() => put(`/followups/${f.id}`, { subject, body }), "Saved").then(onChange)}>Save</Button>
                )}
                {f.method === "email" ? (
                  <Button variant="success" onClick={() => confirm("Send this follow-up from your Gmail in the original thread?") &&
                    act(async () => { await put(`/followups/${f.id}`, { subject, body }); return post(`/followups/${f.id}/send`, { confirm: true }); }, "Follow-up sent").then(onChange)}>
                    <Send /> Send follow-up
                  </Button>
                ) : (
                  <span className="self-center text-xs text-muted-foreground">Online application — follow up via the company's portal or LinkedIn.</span>
                )}
              </div>
            </>
          ) : (
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => act(() => post(`/followups/${f.id}/dismiss`), "Dismissed").then(onChange)}><X /> Dismiss</Button>
              <Button variant="outline" onClick={() => act(async () => {
                const r = await post<FollowUp>(`/followups/${f.id}/draft`);
                setSubject(r.subject ?? ""); setBody(r.body ?? "");
              })}>Draft now</Button>
            </div>
          )
        )}
        {f.status !== "pending" && f.body && <pre className="whitespace-pre-wrap font-sans text-sm text-muted-foreground">{f.body}</pre>}
      </CardContent>
    </Card>
  );
}
