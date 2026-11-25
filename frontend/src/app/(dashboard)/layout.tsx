"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MobileNav, Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/top-bar";
import { useAuth } from "@/lib/store";
import type { Kpis } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuth((s) => s.token);
  const [mounted, setMounted] = useState(false);
  const { data: kpis } = useFetch<Kpis>(mounted && token ? "/analytics/overview" : null, { pollMs: 60000 });

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (mounted && !token) router.replace("/login");
  }, [mounted, token, router]);

  if (!mounted || !token) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  return (
    <div className="flex min-h-screen">
      <Sidebar queueCount={kpis?.awaiting_approval} />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav />
        <TopBar />
        <main className="flex-1 space-y-6 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
