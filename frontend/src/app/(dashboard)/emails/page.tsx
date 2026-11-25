"use client";

import { useState } from "react";

import { ApplicationDialog } from "@/components/application-panel";
import { Empty, PageHeader, Pagination } from "@/components/common";
import { Badge, Card, CardContent, Input, Select } from "@/components/ui/primitives";
import type { EmailHistory, Page } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { buildQuery, fmtDate } from "@/lib/utils";

export default function EmailsPage() {
  const [direction, setDirection] = useState("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const { data } = useFetch<Page<EmailHistory>>(`/email-history${buildQuery({ direction, q, page, page_size: 25 })}`);

  return (
    <>
      <PageHeader title="Email History" description="Every email sent through Gmail and every reply detected on application threads." />
      <Card>
        <CardContent className="grid grid-cols-2 gap-2 p-3 md:grid-cols-4">
          <Input className="col-span-2" placeholder="Subject or address…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select value={direction} onChange={(e) => { setDirection(e.target.value); setPage(1); }}>
            <option value="all">Sent & received</option><option value="outbound">Sent</option><option value="inbound">Replies</option>
          </Select>
        </CardContent>
      </Card>
      <Card>
        {data && data.items.length === 0 ? (
          <Empty title="No emails yet" hint="Emails appear here after you send an approved application." />
        ) : (
          <div className="divide-y">
            {data?.items.map((e) => (
              <div key={e.id} className="p-4">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant={e.direction === "inbound" ? "violet" : e.status === "sent" ? "success" : "danger"}>
                    {e.direction === "inbound" ? "Reply" : e.status === "sent" ? "Sent" : "Failed"}
                  </Badge>
                  <button className="font-medium hover:underline" onClick={() => setExpanded(expanded === e.id ? null : e.id)}>{e.subject}</button>
                  <span className="ml-auto text-xs text-muted-foreground">{fmtDate(e.created_at, true)}</span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {e.direction === "inbound" ? `From ${e.from_email}` : `To ${e.to_email}`}
                  {e.company_name && (
                    <> · <button className="text-primary hover:underline" onClick={() => e.application_id && setOpen(e.application_id)}>{e.company_name} — {e.job_title}</button></>
                  )}
                  {e.attachment_name && ` · 📎 ${e.attachment_name}`}
                  {e.gmail_message_id && ` · Gmail ID ${e.gmail_message_id}`}
                </div>
                {e.error && <div className="mt-1 text-xs text-red-600">{e.error}</div>}
                {expanded === e.id && <pre className="mt-3 whitespace-pre-wrap rounded-md bg-muted/40 p-3 font-sans text-sm">{e.body}</pre>}
              </div>
            ))}
          </div>
        )}
        {data && <Pagination page={page} pageSize={25} total={data.total} onPage={setPage} />}
      </Card>
      <ApplicationDialog appId={open} onClose={() => setOpen(null)} />
    </>
  );
}
