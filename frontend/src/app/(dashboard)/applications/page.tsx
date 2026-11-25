"use client";

import { FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";

import { ApplicationDialog } from "@/components/application-panel";
import { Empty, ExtLink, FiltersBar, PageHeader, Pagination, ScoreBadge, StatusBadge, filtersToParams } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { download } from "@/lib/api";
import { useFilters } from "@/lib/store";
import type { ApplicationRow, Page } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { buildQuery, categoryLabel, fmtDate } from "@/lib/utils";

export default function ApplicationsPage() {
  const { filters, setFilter, reset } = useFilters();
  const [scope, setScope] = useState<"applied" | "all">("applied");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const params = { ...filtersToParams(filters, scope === "applied"), sort: scope === "applied" ? "applied" : "updated" };
  const { data, reload } = useFetch<Page<ApplicationRow>>(`/applications${buildQuery({ ...params, page, page_size: 25 })}`);
  const exportQ = buildQuery({ ...filtersToParams(filters), applied_only: scope === "applied" });

  return (
    <>
      <PageHeader
        title="Sent Applications"
        description="Every company you applied to, with full status tracking."
        actions={
          <>
            <Select className="w-44" value={scope} onChange={(e) => { setScope(e.target.value as "applied" | "all"); setPage(1); }}>
              <option value="applied">Submitted only</option>
              <option value="all">All pipeline items</option>
            </Select>
            <Button variant="outline" onClick={() => act(() => download(`/exports/applications.csv${exportQ}`, "applications.csv"))}><FileText /> CSV</Button>
            <Button variant="outline" onClick={() => act(() => download(`/exports/applications.xlsx${exportQ}`, "applications.xlsx"))}><FileSpreadsheet /> Excel</Button>
          </>
        }
      />
      <FiltersBar filters={filters} set={(k, v) => { setFilter(k, v); setPage(1); }} reset={reset} />
      <Card>
        {data && data.items.length === 0 ? (
          <Empty title="No applications match" hint="Approved applications appear here once sent or marked as applied." />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Company Name</TH><TH>Job Title</TH><TH>City</TH><TH>Job Category</TH><TH>Match Score</TH>
                <TH>Method</TH><TH>Application Date</TH><TH>Status</TH><TH>Source URL</TH>
              </TR>
            </THead>
            <TBody>
              {data?.items.map((a) => (
                <TR key={a.id} className="cursor-pointer" onClick={() => setOpen(a.id)}>
                  <TD className="font-medium">{a.company_name}</TD>
                  <TD>{a.job_title}</TD>
                  <TD>{a.city}</TD>
                  <TD className="text-xs">{categoryLabel(a.category)}</TD>
                  <TD><ScoreBadge score={a.match_score} /></TD>
                  <TD className="text-xs capitalize">{a.method ?? "—"}</TD>
                  <TD className="text-xs">{fmtDate(a.applied_at, true)}</TD>
                  <TD><StatusBadge status={a.status} /></TD>
                  <TD className="text-xs" onClick={(e) => e.stopPropagation()}><ExtLink href={a.source_url}>View</ExtLink></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {data && <Pagination page={page} pageSize={25} total={data.total} onPage={setPage} />}
      </Card>
      <ApplicationDialog appId={open} onClose={() => setOpen(null)} onChanged={() => reload(true)} />
    </>
  );
}
