import type { Metadata } from "next";

import { DashTopBar } from "@/components/dashboard/DashTopBar";
import { Sidebar } from "@/components/dashboard/Sidebar";

export const metadata: Metadata = {
  title: "SYNAPSE — Dashboard",
  description: "Execution arena, usage history, model registry and workspace settings.",
};

/**
 * The dashboard shell. It wraps every view under /dashboard, so the rail and
 * the top bar persist across navigation instead of re-mounting per route.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-void font-sans text-white antialiased">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <DashTopBar />
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
