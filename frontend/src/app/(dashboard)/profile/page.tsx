"use client";

import { AlertTriangle, Download, Loader2, Plus, RefreshCw, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Textarea } from "@/components/ui/primitives";
import { del, download, post, put, upload } from "@/lib/api";
import type { CV, Profile } from "@/lib/types";
import { act, useFetch } from "@/lib/use-fetch";
import { fmtDate } from "@/lib/utils";

export default function ProfilePage() {
  const { data: profile, reload, setData } = useFetch<Profile>("/profile");
  const { data: cvs, reload: reloadCvs } = useFetch<CV[]>("/cv");
  const [uploading, setUploading] = useState(false);
  const [skill, setSkill] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  async function onFile(file?: File) {
    if (!file) return;
    setUploading(true);
    const p = await act(() => upload<Profile>("/cv/upload", file), "CV uploaded and analyzed");
    setUploading(false);
    if (p) setData(p);
    reloadCvs(true);
  }

  return (
    <>
      <PageHeader
        title="My CV & Profile"
        description="Your profile is extracted from your actual CV. Nothing is invented — items not found in the CV text are dropped."
        actions={
          <>
            <input ref={fileRef} type="file" accept=".pdf,.docx" hidden onChange={(e) => onFile(e.target.files?.[0])} />
            <Button disabled={uploading} onClick={() => fileRef.current?.click()}>
              {uploading ? <Loader2 className="animate-spin" /> : <Upload />} Upload CV (PDF/DOCX)
            </Button>
          </>
        }
      />
      {profile && !profile.active_cv_id && (
        <Card className="border-amber-300 bg-amber-50 dark:bg-amber-900/20">
          <CardContent className="p-4 text-sm">
            Upload your latest CV to start. Until then the profile below is the initial one you described; matching and emails use only CV-extracted data.
          </CardContent>
        </Card>
      )}
      {profile?.extraction_warnings?.length ? (
        <Card>
          <CardContent className="space-y-1 p-4 text-xs text-amber-700 dark:text-amber-300">
            {profile.extraction_warnings.map((w) => <div key={w} className="flex gap-1"><AlertTriangle className="h-3 w-3 shrink-0" />{w}</div>)}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          {profile && <ContactCard profile={profile} onSaved={setData} />}
          <Card>
            <CardHeader><CardTitle>Skills ({profile?.skills.length ?? 0})</CardTitle><CardDescription>Green = from CV · blue = added by you · grey = initial profile</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {profile?.skills.map((s) => (
                  <Badge key={s.id} variant={s.source === "cv" ? "success" : s.source === "manual" ? "info" : "secondary"} title={s.evidence ?? undefined}>
                    {s.name}
                    <button onClick={() => act(() => del(`/profile/skills/${s.id}`)).then(() => reload(true))}><X className="h-3 w-3" /></button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-2">
                <Input placeholder="Add a skill you genuinely have" value={skill} onChange={(e) => setSkill(e.target.value)} />
                <Button variant="outline" disabled={!skill} onClick={() => act(() => post("/profile/skills", { name: skill }), "Skill added").then(() => { setSkill(""); reload(true); })}><Plus /> Add</Button>
              </div>
            </CardContent>
          </Card>
          <Section title="Experience" items={profile?.experience.map((e) => ({ title: [e.title, e.company].filter(Boolean).join(" — "), sub: [e.start, e.end].filter(Boolean).join(" – "), body: [e.description, ...(e.highlights ?? [])].filter(Boolean).join("\n") }))} />
          <Section title="Education" items={profile?.education.map((e) => ({ title: [e.degree, e.field].filter(Boolean).join(", "), sub: [e.institution, e.end].filter(Boolean).join(" · "), body: "" }))} />
          <Section title="Projects" items={profile?.projects.map((p) => ({ title: p.name ?? "", sub: (p.technologies ?? []).join(", "), body: p.description ?? "" }))} />
          <Section title="Certifications" items={profile?.certifications.map((c) => ({ title: c.name ?? "", sub: [c.issuer, c.date].filter(Boolean).join(" · "), body: "" }))} />
        </div>
        <Card className="h-fit">
          <CardHeader><CardTitle>Uploaded CVs</CardTitle><CardDescription>Encrypted at rest. The active CV is attached to applications.</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {cvs?.length === 0 && <p className="text-sm text-muted-foreground">No CV uploaded yet.</p>}
            {cvs?.map((cv) => (
              <div key={cv.id} className="rounded-md border p-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{cv.original_filename}</span>
                  {cv.is_active && <Badge variant="success">active</Badge>}
                </div>
                <div className="text-xs text-muted-foreground">
                  {fmtDate(cv.created_at, true)} · {(cv.size_bytes / 1024).toFixed(0)} KB · {cv.parse_status}{cv.parse_method ? ` (${cv.parse_method})` : ""}
                </div>
                {cv.parse_error && <div className="text-xs text-red-600">{cv.parse_error}</div>}
                <div className="mt-1 flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => act(() => download(`/cv/${cv.id}/download`, cv.original_filename))}><Download /> Download</Button>
                  <Button size="sm" variant="ghost" onClick={() => act(() => post<Profile>(`/cv/${cv.id}/reparse`), "Re-analyzed").then((p) => { if (p) setData(p); reloadCvs(true); })}><RefreshCw /> {cv.is_active ? "Re-parse" : "Make active"}</Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function ContactCard({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const fields = ["full_name", "headline", "email", "phone", "location", "linkedin_url", "github_url", "portfolio_url"] as const;
  const [f, setF] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const [roles, setRoles] = useState("");
  useEffect(() => {
    setF(Object.fromEntries(fields.map((k) => [k, profile[k] ?? ""])));
    setSummary(profile.summary ?? "");
    setRoles(profile.target_roles.join(", "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.id, profile.updated_at]);
  return (
    <Card>
      <CardHeader><CardTitle>Contact & summary</CardTitle><CardDescription>Used in email signatures and online form assistance. Years of experience: {profile.years_experience ?? "—"}</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          {fields.map((k) => (
            <div key={k} className="space-y-1">
              <Label className="text-xs capitalize">{k.replace(/_/g, " ")}</Label>
              <Input value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
            </div>
          ))}
        </div>
        <div className="space-y-1"><Label className="text-xs">Target roles (comma separated)</Label><Input value={roles} onChange={(e) => setRoles(e.target.value)} /></div>
        <div className="space-y-1"><Label className="text-xs">Summary</Label><Textarea value={summary} onChange={(e) => setSummary(e.target.value)} /></div>
        <div className="flex justify-end">
          <Button onClick={() => act(() => put<Profile>("/profile", {
            ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v || null])),
            summary: summary || null,
            target_roles: roles.split(",").map((r) => r.trim()).filter(Boolean),
          }), "Profile saved").then((p) => p && onSaved(p))}>Save profile</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Section({ title, items }: { title: string; items?: { title: string; sub: string; body: string }[] }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {!items?.length ? <p className="text-sm text-muted-foreground">Nothing extracted.</p> : items.map((it, i) => (
          <div key={i} className="border-l-2 border-primary/40 pl-3">
            <div className="font-medium">{it.title || "—"}</div>
            {it.sub && <div className="text-xs text-muted-foreground">{it.sub}</div>}
            {it.body && <p className="mt-1 whitespace-pre-wrap text-sm">{it.body}</p>}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
