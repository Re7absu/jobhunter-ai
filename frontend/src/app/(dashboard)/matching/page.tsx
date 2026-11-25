"use client";

import { Bot, Loader2 } from "lucide-react";
import { useState } from "react";

import { ApplicationDialog } from "@/components/application-panel";
import { Empty, PageHeader, Pagination, ScoreBadge, SkillChips, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, Select } from "@/components/ui/primitives";
import { get, post } from "@/lib/api";
import type { Job, JobDetail, Page } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { buildQuery, categoryLabel } from "@/lib/utils";

const CATS = ["Excellent Match", "Good Match", "Potential Match", "Low Match"];

export default function MatchingPage() {
  const [cat, setCat] = useState("all");
  const [city, setCity] = useState("all");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [details, setDetails] = useState<Record<number, JobDetail>>({});
  const { data, reload } = useFetch<Page<Job>>(
    `/jobs${buildQuery({ analyzed: true, sort: "score", match_category: cat, city, page, page_size: 15, active: "" })}`,
  );

  const expand = async (id: number) => {
    if (details[id]) return;
    const d = await get<JobDetail>(`/jobs/${id}`);
    setDetails((x) => ({ ...x, [id]: d }));
  };

  return (
    <>
      <PageHeader
        title="AI Job Matching"
        description="Every job compared against your CV: score, matching & missing skills, transferable skills and a recommendation."
        actions={
          <Button disabled={busy} onClick={async () => {
            setBusy(true);
            const r = await act(() => post<{ analyzed: number; qualified: number }>("/matches/analyze-pending?limit=50"));
            setBusy(false);
            if (r) { alert(`Analyzed ${r.analyzed} jobs · ${r.qualified} qualified`); reload(true); }
          }}>
            {busy ? <Loader2 className="animate-spin" /> : <Bot />} Analyze pending jobs
          </Button>
        }
      />
      <div className="flex flex-wrap gap-2">
        {["all", ...CATS].map((c) => (
          <Button key={c} size="sm" variant={cat === c ? "default" : "outline"} onClick={() => { setCat(c); setPage(1); }}>
            {c === "all" ? "All" : c}
          </Button>
        ))}
        <Select className="w-36" value={city} onChange={(e) => { setCity(e.target.value); setPage(1); }}>
          <option value="all">All cities</option><option>Riyadh</option><option>Jeddah</option>
        </Select>
      </div>
      {data && data.items.length === 0 && (
        <Card><Empty title="No analyzed jobs" hint="Upload your CV, discover jobs, then analyze them." /></Card>
      )}
      <div className="space-y-3">
        {data?.items.map((j) => {
          const d = details[j.id];
          return (
            <Card key={j.id} onMouseEnter={() => expand(j.id)}>
              <CardContent className="space-y-3 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <button className="font-semibold hover:underline" onClick={() => j.application_id && setOpen(j.application_id)}>{j.title}</button>
                    <div className="text-sm text-muted-foreground">{j.company_name} · {j.city} · {categoryLabel(j.category)}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <ScoreBadge score={j.match_score} />
                    <Badge variant="outline">{j.match_category}</Badge>
                    {j.application_status && <StatusBadge status={j.application_status} />}
                  </div>
                </div>
                {d?.match ? (
                  <div className="grid gap-3 md:grid-cols-3">
                    <p className="text-sm md:col-span-3">{d.match.explanation}</p>
                    <div><div className="mb-1 text-xs font-medium">Matching</div><SkillChips items={d.match.matching_skills} variant="success" /></div>
                    <div><div className="mb-1 text-xs font-medium">Missing</div><SkillChips items={d.match.missing_skills} variant="danger" /></div>
                    <div><div className="mb-1 text-xs font-medium">Transferable</div><SkillChips items={d.match.transferable_skills} variant="info" /></div>
                    <div className="text-xs text-muted-foreground md:col-span-3">
                      Recommendation: <b>{d.match.recommendation}</b> · {d.match.method}{d.match.model ? ` (${d.match.model})` : ""}
                    </div>
                  </div>
                ) : (
                  <button className="text-xs text-primary" onClick={() => expand(j.id)}>Show analysis</button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
      {data && <Card><Pagination page={page} pageSize={15} total={data.total} onPage={setPage} /></Card>}
      <ApplicationDialog appId={open} onClose={() => setOpen(null)} onChanged={() => reload(true)} />
    </>
  );
}
