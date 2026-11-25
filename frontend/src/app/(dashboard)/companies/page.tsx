"use client";

import { BadgeCheck, Plus, RefreshCw, ScanSearch, Trash2 } from "lucide-react";
import { useState } from "react";

import { Empty, ExtLink, PageHeader, Pagination } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge, Card, CardContent, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { del, patch, post } from "@/lib/api";
import type { Company, Page } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { buildQuery, fmtDate, sourceLabel } from "@/lib/utils";

export default function CompaniesPage() {
  const [q, setQ] = useState("");
  const [city, setCity] = useState("all");
  const [hasEmail, setHasEmail] = useState("all");
  const [board, setBoard] = useState("all");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Company | null>(null);
  const path = `/companies${buildQuery({ q, city, has_email: hasEmail, page, page_size: 25,
    ...(board === "tracked" ? { tracked: true } : board === "auto" ? { tracked: true, tracking_source: "auto" } : {}) })}`;
  const { data, reload } = useFetch<Page<Company>>(path);

  return (
    <>
      <PageHeader
        title="Discover Companies"
        description="Companies found through job sources, enriched only from their own official websites."
        actions={<Button onClick={() => setAdding(true)}><Plus /> Track a company</Button>}
      />
      <Card>
        <CardContent className="grid grid-cols-2 gap-2 p-3 md:grid-cols-5">
          <Input className="col-span-2" placeholder="Search name, domain, industry…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select value={city} onChange={(e) => { setCity(e.target.value); setPage(1); }}>
            <option value="all">All cities</option><option>Riyadh</option><option>Jeddah</option>
          </Select>
          <Select value={hasEmail} onChange={(e) => { setHasEmail(e.target.value); setPage(1); }}>
            <option value="all">Any contact</option><option value="true">Verified recruitment email</option><option value="false">No verified email</option>
          </Select>
          <Select value={board} onChange={(e) => { setBoard(e.target.value); setPage(1); }}>
            <option value="all">All companies</option><option value="tracked">Job board tracked</option><option value="auto">Board auto-detected</option>
          </Select>
        </CardContent>
      </Card>
      <Card>
        {data && data.items.length === 0 ? (
          <Empty title="No companies yet" hint="Run discovery (Run now) or track a company's career board." />
        ) : (
          <Table>
            <THead>
              <TR><TH>Company</TH><TH>City</TH><TH>Industry</TH><TH>Recruitment email</TH><TH>Links</TH><TH>Jobs</TH><TH>Discovered</TH><TH /></TR>
            </THead>
            <TBody>
              {data?.items.map((c) => (
                <TR key={c.id}>
                  <TD>
                    <button className="text-left font-medium hover:underline" onClick={() => setEditing(c)}>{c.name}</button>
                    <div className="text-xs text-muted-foreground">{c.domain ?? "no website yet"}</div>
                    {c.ats_type && (
                      <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px]">
                        <Badge variant={c.tracked ? "info" : "secondary"} title={c.board_detected_from ?? undefined}>
                          {sourceLabel(c.ats_type)}{c.ats_slug ? `: ${c.ats_slug}` : ""} · {c.tracked ? (c.tracking_source === "auto" ? "auto-tracked" : "tracked") : "not tracked"}
                        </Badge>
                        <span className="text-muted-foreground">{c.last_scanned_at ? `scanned ${fmtDate(c.last_scanned_at, true)}` : "not scanned yet"}</span>
                        {c.scan_error && <span className="max-w-[260px] truncate text-red-600" title={c.scan_error}>⚠ {c.scan_error}</span>}
                      </div>
                    )}
                  </TD>
                  <TD>{c.city ?? "—"}</TD>
                  <TD className="max-w-[180px] truncate text-xs">{c.industry ?? "—"}</TD>
                  <TD className="text-xs">
                    {c.recruitment_email ? (
                      <span className="inline-flex items-center gap-1">
                        {c.email_verified && <BadgeCheck className="h-3.5 w-3.5 text-emerald-600" />}
                        {c.recruitment_email}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">{c.enrichment_error ?? (c.last_enriched_at ? "none published" : "not researched")}</span>
                    )}
                  </TD>
                  <TD className="space-x-2 text-xs">
                    {c.website && <ExtLink href={c.website}>Site</ExtLink>}
                    {c.careers_url && <ExtLink href={c.careers_url}>Careers</ExtLink>}
                    {c.linkedin_url && <ExtLink href={c.linkedin_url}>LinkedIn</ExtLink>}
                  </TD>
                  <TD className="tabular-nums">{c.job_count}</TD>
                  <TD className="text-xs text-muted-foreground">{fmtDate(c.discovered_at)}</TD>
                  <TD className="whitespace-nowrap text-right">
                    <Button size="icon" variant="ghost" title="Research company website" onClick={() => act(() => post(`/companies/${c.id}/enrich`), "Company researched").then(() => reload(true))}><RefreshCw /></Button>
                    {c.ats_type && (
                      <Button size="icon" variant="ghost" title="Scan career board now" onClick={() => act(async () => { const r = await post<{ found: number; new_jobs: number; duplicates: number; filtered: number }>(`/companies/${c.id}/scan-board`); return r as { found: number; new_jobs: number; duplicates: number; filtered: number }; }).then((r) => { if (r) alert(`Found ${r.found} postings: ${r.new_jobs} new relevant jobs, ${r.duplicates} duplicates, ${r.filtered} filtered out`); reload(true); })}><ScanSearch /></Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {data && <Pagination page={page} pageSize={25} total={data.total} onPage={setPage} />}
      </Card>
      <AddCompanyDialog open={adding} onClose={() => setAdding(false)} onSaved={() => reload(true)} />
      <EditCompanyDialog company={editing} onClose={() => setEditing(null)} onSaved={() => reload(true)} />
    </>
  );
}

function AddCompanyDialog({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: "", website: "", careers_url: "", city: "Riyadh", ats_type: "greenhouse", ats_slug: "" });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Track a company career board</DialogTitle>
          <DialogDescription>
            Monitors a real company's public job board. For Greenhouse/Lever/Ashby/Workable/SmartRecruiters use the board slug from the URL
            (e.g. jobs.lever.co/<b>company</b>, jobs.smartrecruiters.com/<b>Company</b>). Boards are also detected automatically from job links. For other sites choose “Careers page” — it reads standard JobPosting data.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="space-y-1"><Label>Company name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="space-y-1"><Label>Official website</Label><Input placeholder="https://company.sa" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>Board type</Label>
              <Select value={f.ats_type} onChange={(e) => setF({ ...f, ats_type: e.target.value })}>
                <option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option>
                <option value="workable">Workable</option><option value="smartrecruiters">SmartRecruiters</option><option value="careers_page">Careers page (JSON-LD)</option>
              </Select>
            </div>
            <div className="space-y-1"><Label>City</Label>
              <Select value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}><option>Riyadh</option><option>Jeddah</option></Select>
            </div>
          </div>
          {f.ats_type === "careers_page" ? (
            <div className="space-y-1"><Label>Careers page URL</Label><Input value={f.careers_url} onChange={(e) => setF({ ...f, careers_url: e.target.value })} /></div>
          ) : (
            <div className="space-y-1"><Label>Board slug</Label><Input value={f.ats_slug} onChange={(e) => setF({ ...f, ats_slug: e.target.value })} /></div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!f.name}
            onClick={() =>
              act(() => post("/companies", { ...f, website: f.website || null, careers_url: f.careers_url || null, ats_slug: f.ats_slug || null, tracked: true }), "Company added").then((r) => {
                if (r) { onSaved(); onClose(); }
              })
            }
          >
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditCompanyDialog({ company, onClose, onSaved }: { company: Company | null; onClose: () => void; onSaved: () => void }) {
  const [email, setEmail] = useState("");
  const [desc, setDesc] = useState("");
  if (!company) return null;
  return (
    <Dialog open={!!company} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{company.name}</DialogTitle>
          <DialogDescription>{company.description ?? "No description collected yet."}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
            <div>Source: {company.source}</div>
            <div>Researched: {fmtDate(company.last_enriched_at)}</div>
            <div className="col-span-2">Email source: {company.email_source_url ?? "—"}</div>
          </div>
          <div className="space-y-1">
            <Label>Recruitment email (only enter an address the company publishes publicly)</Label>
            <Input placeholder={company.recruitment_email ?? "careers@company.com"} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Description</Label>
            <Input placeholder="Optional" value={desc} onChange={(e) => setDesc(e.target.value)} />
          </div>
        </div>
        <DialogFooter className="sm:justify-between">
          <Button variant="ghost" className="text-red-600" onClick={() => confirm(`Delete ${company.name} and its jobs?`) && act(() => del(`/companies/${company.id}`), "Deleted").then(() => { onSaved(); onClose(); })}>
            <Trash2 /> Delete
          </Button>
          <Button
            onClick={() =>
              act(() => patch(`/companies/${company.id}`, { ...(email ? { recruitment_email: email } : {}), ...(desc ? { description: desc } : {}) }), "Saved").then((r) => {
                if (r) { setEmail(""); setDesc(""); onSaved(); onClose(); }
              })
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
