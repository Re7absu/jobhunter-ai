"use client";

import { Mail, MousePointerClick } from "lucide-react";
import { useState } from "react";

import { ApplicationDialog } from "@/components/application-panel";
import { Empty, PageHeader, ScoreBadge, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent } from "@/components/ui/primitives";
import type { ApplicationRow, Page } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { categoryLabel, timeAgo } from "@/lib/utils";

const TABS = [
  { key: "Awaiting Approval", label: "Awaiting approval" },
  { key: "Approved", label: "Approved — ready to send" },
  { key: "Ready to Apply", label: "Ready to apply online" },
  { key: "Analyzed", label: "Analyzed (no email yet)" },
];

export default function QueuePage() {
  const [tab, setTab] = useState(TABS[0].key);
  const [open, setOpen] = useState<number | null>(null);
  const { data, reload } = useFetch<Page<ApplicationRow>>(
    `/applications?status=${encodeURIComponent(tab)}&sort=score&page_size=100`,
  );

  return (
    <>
      <PageHeader
        title="Application Approval Queue"
        description="Nothing is sent or submitted without your explicit approval. Review, edit, regenerate, approve or reject each application."
      />
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <Button key={t.key} size="sm" variant={tab === t.key ? "default" : "outline"} onClick={() => setTab(t.key)}>
            {t.label}
          </Button>
        ))}
      </div>
      {data && data.items.length === 0 ? (
        <Card><Empty title="Queue is empty" hint="Qualified opportunities (match ≥ your minimum score) land here after each run." /></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {data?.items.map((a) => (
            <Card key={a.id} className="cursor-pointer transition-shadow hover:shadow-md" onClick={() => setOpen(a.id)}>
              <CardContent className="space-y-2 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold">{a.job_title}</div>
                    <div className="text-sm text-muted-foreground">{a.company_name}</div>
                  </div>
                  <ScoreBadge score={a.match_score} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <StatusBadge status={a.status} />
                  <Badge variant="outline">{a.city}</Badge>
                  <Badge variant="outline">{categoryLabel(a.category)}</Badge>
                  <Badge variant="outline">
                    {a.method === "email" ? <Mail className="h-3 w-3" /> : <MousePointerClick className="h-3 w-3" />}
                    {a.method ?? "no method"}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">
                  {a.recipient_email ? `To: ${a.recipient_email} · ` : ""}updated {timeAgo(a.status_changed_at)}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <ApplicationDialog appId={open} onClose={() => setOpen(null)} onChanged={() => reload(true)} />
    </>
  );
}
