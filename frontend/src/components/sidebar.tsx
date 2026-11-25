"use client";

import {
  BarChart3,
  Bell,
  Bot,
  Briefcase,
  Building2,
  CheckSquare,
  FileUser,
  History,
  LayoutDashboard,
  LogOut,
  Mail,
  Send,
  Settings,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/store";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/companies", label: "Discover Companies", icon: Building2 },
  { href: "/jobs", label: "Job Opportunities", icon: Briefcase },
  { href: "/matching", label: "AI Job Matching", icon: Bot },
  { href: "/queue", label: "Approval Queue", icon: CheckSquare },
  { href: "/applications", label: "Sent Applications", icon: Send },
  { href: "/emails", label: "Email History", icon: Mail },
  { href: "/followups", label: "Follow-ups", icon: Bell },
  { href: "/analytics", label: "Analytics & Reports", icon: BarChart3 },
  { href: "/profile", label: "My CV & Profile", icon: FileUser },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ queueCount }: { queueCount?: number }) {
  const path = usePathname();
  const router = useRouter();
  const logout = useAuth((s) => s.logout);
  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-sidebar text-slate-300 lg:flex">
      <div className="flex items-center gap-2 px-5 py-5 text-white">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600">
          <Briefcase className="h-4 w-4" />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">JobHunter AI</div>
          <div className="text-[11px] text-slate-400">Riyadh · Jeddah</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = path === href || path.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active ? "bg-white/10 font-medium text-white" : "hover:bg-white/5 hover:text-white",
              )}
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1">{label}</span>
              {href === "/queue" && !!queueCount && (
                <span className="rounded-full bg-amber-500 px-1.5 text-[11px] font-semibold text-black">{queueCount}</span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-white/10 p-3">
        <Link href="/settings#audit" className="flex items-center gap-3 rounded-md px-3 py-2 text-xs hover:bg-white/5">
          <History className="h-4 w-4" /> Audit log
        </Link>
        <button
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-xs hover:bg-white/5"
        >
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </aside>
  );
}

export function MobileNav() {
  const path = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto border-b bg-sidebar px-2 py-2 lg:hidden">
      {NAV.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "whitespace-nowrap rounded-md px-3 py-1.5 text-xs text-slate-300",
            path.startsWith(href) && "bg-white/10 text-white",
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
