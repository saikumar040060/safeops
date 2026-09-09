"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bot,
  ClipboardCheck,
  LayoutDashboard,
  ListTree,
  LogOut,
  Menu,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { usePublicConfig } from "@/hooks/use-safeops";
import { useAuth } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/executions", label: "Executions", icon: ListTree },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { href: "/security", label: "Security", icon: ShieldAlert },
  { href: "/audit", label: "Audit", icon: ScrollText },
];

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href as never}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
            )}
          >
            <Icon className="size-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

function BrandMark() {
  return (
    <div className="flex items-center gap-2 px-1">
      <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <ShieldCheck className="size-4" />
      </div>
      <div className="flex flex-col leading-none">
        <span className="text-sm font-semibold tracking-tight">SafeOps</span>
        <span className="text-[10px] font-medium text-muted-foreground">control plane</span>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { status, operator, logout } = useAuth();
  const { data: config } = usePublicConfig();

  const isLoginRoute = pathname === "/login";

  useEffect(() => {
    if (!isLoginRoute && status === "unauthenticated") {
      router.replace("/login");
    }
  }, [isLoginRoute, status, router]);

  if (isLoginRoute) {
    return <>{children}</>;
  }

  // Backend remains authoritative regardless of what renders here: this
  // only avoids showing protected content/chrome before the redirect
  // effect above fires, or while the stored token is still being validated.
  if (status !== "authenticated") {
    return null;
  }

  return (
    <div className="flex min-h-svh w-full">
      <aside className="hidden w-60 shrink-0 flex-col gap-4 border-r bg-sidebar px-3 py-4 md:flex">
        <BrandMark />
        <NavLinks pathname={pathname} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-background px-4">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger render={<Button variant="ghost" size="icon" className="md:hidden" />}>
              <Menu className="size-4" />
            </SheetTrigger>
            <SheetContent side="left" className="w-64 bg-sidebar p-4">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              <div className="flex flex-col gap-4">
                <BrandMark />
                <NavLinks pathname={pathname} onNavigate={() => setMobileOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>
          <div className="flex-1" />
          {config?.demo_mode && (
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-600 dark:text-amber-400">
              Local demo mode — no production auth
            </span>
          )}
          {operator && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{operator.display_name}</span>
              <span className="rounded-full border px-2 py-0.5 font-mono">{operator.role}</span>
            </div>
          )}
          <Button variant="ghost" size="icon" title="Sign out" onClick={logout}>
            <LogOut className="size-4" />
          </Button>
        </header>
        <main className="flex-1 overflow-y-auto bg-muted/20 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
