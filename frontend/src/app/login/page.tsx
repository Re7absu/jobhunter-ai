"use client";

import { Briefcase, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@/components/ui/primitives";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/store";

export default function LoginPage() {
  const router = useRouter();
  const setToken = useAuth((s) => s.setToken);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<{ has_users: boolean }>("/auth/setup-status")
      .then((s) => !s.has_users && setMode("register"))
      .catch(() => toast.error("Backend not reachable — is the API running on port 8000?"));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      const res = await post<{ access_token: string }>(`/auth/${mode}`, body);
      setToken(res.access_token);
      router.replace(mode === "register" ? "/profile" : "/overview");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Briefcase className="h-5 w-5" />
          </div>
          <CardTitle className="text-xl">JobHunter AI</CardTitle>
          <CardDescription>
            {mode === "register" ? "Create your owner account" : "Sign in to your job-hunting assistant"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <div className="space-y-1.5">
                <Label htmlFor="name">Full name</Label>
                <Input id="name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw">Password</Label>
              <Input
                id="pw"
                type="password"
                required
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            <Button type="submit" className="w-full" disabled={busy}>
              {busy && <Loader2 className="animate-spin" />}
              {mode === "register" ? "Create account" : "Sign in"}
            </Button>
            <button
              type="button"
              className="w-full text-center text-xs text-muted-foreground hover:underline"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
            >
              {mode === "login" ? "First time? Create the owner account" : "Already have an account? Sign in"}
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
