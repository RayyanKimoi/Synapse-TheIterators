"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  IconArena,
  IconBilling,
  IconCollapse,
  IconKeys,
  IconLedger,
  IconModels,
  IconSettings,
} from "./icons";

/**
 * The dashboard's slim, collapsible rail.
 *
 * Navigation is real routes rather than tab state, so every view deep-links,
 * the browser's back button behaves, and the shell itself never re-mounts
 * between views (it lives in the layout above these routes).
 */

const NAV = [
  { href: "/dashboard", label: "Analytics", Icon: IconArena },
  { href: "/dashboard/history", label: "Usage history", Icon: IconLedger },
  { href: "/dashboard/models", label: "Models", Icon: IconModels },
  { href: "/dashboard/keys", label: "API keys", Icon: IconKeys },
  { href: "/dashboard/billing", label: "Billing", Icon: IconBilling },
  { href: "/dashboard/settings", label: "Settings", Icon: IconSettings },
];

const STORAGE_KEY = "synapse.sidebar.collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  // Restore after mount so the server and client first paint agree.
  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      /* private mode: the rail just starts open */
    }
  }, []);

  const toggle = () => {
    setCollapsed((value) => {
      const next = !value;
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* nothing to persist to; the choice still applies this session */
      }
      return next;
    });
  };

  return (
    <aside
      data-collapsed={collapsed ? "" : undefined}
      className={`relative z-30 flex shrink-0 flex-col border-r border-white/10 bg-black/60 backdrop-blur-xl transition-[width] duration-300 ease-out ${
        collapsed ? "w-[68px]" : "w-[232px]"
      }`}
    >
      <div className="flex h-16 items-center gap-2.5 px-4">
        <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="SYNAPSE home">
          <Image
            src="/synapse-logo.png"
            alt="SYNAPSE"
            width={30}
            height={30}
            priority
            style={{ width: 30, height: 30 }}
          />
          {!collapsed && (
            <span className="whitespace-nowrap font-head text-[15px] font-bold tracking-[-0.01em] text-white">
              SYNAPSE
            </span>
          )}
        </Link>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3 pt-2">
        {NAV.map(({ href, label, Icon }) => {
          // `/dashboard` would otherwise match every child route.
          const active = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              title={collapsed ? label : undefined}
              className={`group relative flex items-center gap-3 rounded-xl px-2.5 py-2.5 font-head text-[13px] font-medium transition-colors ${
                active ? "text-white" : "text-white/55 hover:text-white"
              }`}
            >
              {active && (
                <span
                  aria-hidden
                  className="absolute inset-0 rounded-xl border border-stream/25 bg-stream/[0.08]"
                />
              )}
              <Icon
                className={`relative h-[18px] w-[18px] shrink-0 transition-colors ${
                  active ? "text-stream" : ""
                }`}
              />
              {!collapsed && <span className="relative whitespace-nowrap">{label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 pb-4">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex w-full items-center gap-3 rounded-xl px-2.5 py-2.5 font-head text-[13px] font-medium text-white/45 transition-colors hover:text-white"
        >
          <IconCollapse className={`h-[18px] w-[18px] shrink-0 ${collapsed ? "rotate-180" : ""}`} />
          {!collapsed && <span className="whitespace-nowrap">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
