"use client";

import { Loader2, Pause, Play, Rocket } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import type { AutomationStatus } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { fmtDate } from "@/lib/utils";

export function TopBar() {
  const { data, reload } = useFetch<AutomationStatus>("/automation/status", { pollMs: 10000 });
  const missing = data
    ? [
        !data.integrations.openai && "OpenAI",
        !data.integrations.source_jsearch && !data.integrations.source_serpapi && "Job search API",
        !data.integrations.gmail_connected && "Gmail",
      ].filter(Boolean)
    : [];
  return (
    <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b bg-background/80 px-4 py-3 backdrop-blur md:px-6">
      <div className="flex flex-1 flex-wrap items-center gap-2 text-sm">
        {data?.running ? (
          <Badge variant="info">
            <Loader2 className="h-3 w-3 animate-spin" /> Automation running
          </Badge>
        ) : data?.paused ? (
          <Badge variant="danger">Automation paused</Badge>
        ) : (
          <Badge variant="success">Automation active</Badge>
        )}
        {data?.next_run_at && !data.paused && (
          <span className="text-xs text-muted-foreground">Next run {fmtDate(data.next_run_at, true)}</span>
        )}
        {data?.openai_error && (
          <a href="/settings" className="text-xs font-medium text-red-600 hover:underline" title={data.openai_error}>
            OpenAI error: {data.openai_error}
          </a>
        )}
        {missing.length > 0 && (
          <a href="/settings" className="text-xs text-amber-600 hover:underline">
            Not configured: {missing.join(", ")}
          </a>
        )}
      </div>
      <div className="flex gap-2">
        {data?.paused ? (
          <Button size="sm" variant="outline" onClick={() => act(() => post("/automation/resume"), "Automation resumed").then(() => reload())}>
            <Play /> Resume
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={() => act(() => post("/automation/pause"), "All automation paused").then(() => reload())}>
            <Pause /> Pause all
          </Button>
        )}
        <Button
          size="sm"
          disabled={data?.running || data?.paused}
          onClick={() => act(() => post("/automation/run"), "Daily run started").then(() => reload())}
        >
          <Rocket /> Run now
        </Button>
      </div>
    </header>
  );
}
