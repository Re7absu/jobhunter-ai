"use client";

import { Bot, Search } from "lucide-react";
import { useState } from "react";

import { ApplicationDialog } from "@/components/application-panel";
import { Empty, ExtLink, PageHeader, Pagination, ScoreBadge, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge, Card, CardContent, CardHeader, CardTitle, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import type { Job, Page } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { buildQuery, categoryLabel, fmtDate, levelLabel, methodLabel, methodShort, sourceLabel, timeAgo } from "@/lib/utils";

interface SearchRow { id: number; source: string; query: string; city: string | null; results_count: number; new_jobs_count: number; status: string; error: string | null; created_at: string }

export default function JobsPage() {
  const [f, setF] = useState({ q: "", city: "all", category: "all", level: "all", source: "all", discovery_method: "all", sort: "discovered", active: "true" });
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const set = (k: keyof typeof f, v: string) => { setF({ ...f, [k]: v }); setPage(1); };
  const { data, reload } = useFetch<Page<Job>>(`/jobs${buildQuery({ ...f, page, page_size: 25 })}`);
  const { data: history } = useFetch<SearchRow[]>("/discovery/history?limit=15", { pollMs: 20000 });

  return (
    <>
      <PageHeader
        title="Job Opportunities"
        description="Validated, de-duplicated vacancies in Riyadh & Jeddah from licensed job APIs and company career boards."
        actions={<Button onClick={() => setSearchOpen(true)}><Search /> Search now</Button>}
      />
      <Card>
        <CardContent className="grid grid-cols-2 gap-2 p-3 md:grid-cols-4 xl:grid-cols-8">
          <Input className="col-span-2" placeholder="Title or company…" value={f.q} onChange={(e) => set("q", e.target.value)} />
          <Select value={f.city} onChange={(e) => set("city", e.target.value)}><option value="all">All cities</option><option>Riyadh</option><option>Jeddah</option></Select>
          <Select value={f.category} onChange={(e) => set("category", e.target.value)}>
            <option value="all">All categories</option><option value="technology">Technology</option><option value="product_management">Product Management</option>
          </Select>
          <Select value={f.level} onChange={(e) => set("level", e.target.value)}>
            <option value="all">All levels</option>
            {["internship", "coop", "graduate", "entry", "junior", "mid"].map((l) => <option key={l} value={l}>{levelLabel(l)}</option>)}
          </Select>
          <Select value={f.discovery_method} onChange={(e) => set("discovery_method", e.target.value)}>
            <option value="all">All discovery methods</option>
            <option value="search_api">Job search API</option>
            <option value="ats_board">Company ATS boards</option>
            <option value="careers_page">Company career pages</option>
          </Select>
          <Select value={f.source} onChange={(e) => set("source", e.target.value)}>
            <option value="all">All sources</option>
            {["jsearch", "serpapi", "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "careers_page"].map((x) => (
              <option key={x} value={x}>{sourceLabel(x)}</option>
            ))}
          </Select>
          <Select value={f.sort} onChange={(e) => set("sort", e.target.value)}>
            <option value="discovered">Newest discovered</option><option value="posted">Newest posted</option><option value="score">Best match</option>
          </Select>
        </CardContent>
      </Card>
      <Card>
        {data && data.items.length === 0 ? (
          <Empty title="No jobs found" hint="Configure a job-search API key in backend/.env, then press “Search now” or “Run now”." />
        ) : (
          <Table>
            <THead><TR><TH>Job</TH><TH>Company</TH><TH>City</TH><TH>Category</TH><TH>Level</TH><TH>Match</TH><TH>Status</TH><TH>Posted</TH><TH>Source · method</TH><TH /></TR></THead>
            <TBody>
              {data?.items.map((j) => (
                <TR key={j.id}>
                  <TD className="max-w-[260px]">
                    <button className="text-left font-medium hover:underline" onClick={() => j.application_id && setOpen(j.application_id)}>{j.title}</button>
                    {j.salary_text && <div className="text-xs text-muted-foreground">{j.salary_text}</div>}
                  </TD>
                  <TD>{j.company_name}</TD>
                  <TD>{j.city}</TD>
                  <TD className="text-xs">{categoryLabel(j.category)}</TD>
                  <TD><Badge variant="outline">{levelLabel(j.experience_level)}</Badge></TD>
                  <TD><ScoreBadge score={j.match_score} /></TD>
                  <TD>{j.application_status && <StatusBadge status={j.application_status} />}</TD>
                  <TD className="text-xs text-muted-foreground">{j.posted_at ? timeAgo(j.posted_at) : fmtDate(j.discovered_at)}</TD>
                  <TD className="text-xs">
                    <ExtLink href={j.source_url}>{j.publisher ?? sourceLabel(j.source)}</ExtLink>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1">
                      <Badge variant={j.discovery_method === "search_api" ? "outline" : "info"} title={methodLabel(j.discovery_method)}>
                        {methodShort(j.discovery_method)}{j.discovery_method.endsWith("_auto") ? " · auto" : ""}
                      </Badge>
                      {j.seen_sources?.length > 0 && (
                        <Badge variant="secondary" title={j.seen_sources.map((x) => x.publisher ?? sourceLabel(x.source)).join(", ")}>
                          +{j.seen_sources.length} more
                        </Badge>
                      )}
                    </div>
                  </TD>
                  <TD>
                    <Button size="sm" variant="ghost" title="Analyze against CV" onClick={() => act(() => post(`/jobs/${j.id}/analyze`), "Analyzed").then(() => reload(true))}><Bot /></Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {data && <Pagination page={page} pageSize={25} total={data.total} onPage={setPage} />}
      </Card>
      <Card>
        <CardHeader><CardTitle>Recent searches</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <THead><TR><TH>When</TH><TH>Source</TH><TH>Query</TH><TH>Results</TH><TH>New jobs</TH><TH>Status</TH></TR></THead>
            <TBody>
              {history?.map((h) => (
                <TR key={h.id}>
                  <TD className="text-xs">{fmtDate(h.created_at, true)}</TD>
                  <TD className="text-xs">{h.source}</TD>
                  <TD className="text-xs" dir="auto">{h.query}</TD>
                  <TD className="tabular-nums">{h.results_count}</TD>
                  <TD className="tabular-nums">{h.new_jobs_count}</TD>
                  <TD className="text-xs">{h.status === "ok" ? "ok" : <span className="text-red-600" title={h.error ?? ""}>error</span>}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
      <ApplicationDialog appId={open} onClose={() => setOpen(null)} onChanged={() => reload(true)} />
    </>
  );
}

function SearchDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [titles, setTitles] = useState("");
  const [max, setMax] = useState("10");
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Search for new vacancies</DialogTitle>
          <DialogDescription>Leave titles empty to rotate through all configured titles (English & Arabic) in Riyadh and Jeddah.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1"><Label>Specific titles (comma separated, optional)</Label><Input placeholder="Data Engineer, AI Engineer" value={titles} onChange={(e) => setTitles(e.target.value)} /></div>
          <div className="space-y-1"><Label>Max API queries</Label><Input type="number" min={1} max={100} value={max} onChange={(e) => setMax(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => act(() => post("/discovery/run", {
            titles: titles ? titles.split(",").map((t) => t.trim()).filter(Boolean) : null,
            max_queries: Number(max) || 10,
          }), "Search started — results appear as they arrive").then(onClose)}>
            <Search /> Start search
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
