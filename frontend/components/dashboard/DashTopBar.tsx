"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";

import { IconChevron, IconSearch } from "./icons";

/**
 * The global bar above every dashboard view: where you are, what you are
 * searching, and which workspace you are in. Run controls stay with the
 * arena, since they act on a workflow rather than on the whole dashboard.
 */

const CRUMBS: Record<string, string> = {
  "/dashboard": "Analytics",
  "/dashboard/history": "Usage history",
  "/dashboard/models": "Models",
  "/dashboard/keys": "API keys",
  "/dashboard/billing": "Billing",
  "/dashboard/settings": "Settings",
};

const WORKSPACES = ["The Iterators", "Personal sandbox"];

export function DashTopBar() {
  const pathname = usePathname();
  const crumb = CRUMBS[pathname] ?? "Analytics";

  const [workspace, setWorkspace] = useState(WORKSPACES[0]);
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement | null>(null);
  const search = useRef<HTMLInputElement | null>(null);

  // Click-away and Escape, so the menu is dismissible by pointer and keyboard.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (menu.current && !menu.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Slash focuses search, the convention in developer tools.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey) return;
      const node = document.activeElement;
      const typing =
        node instanceof HTMLInputElement ||
        node instanceof HTMLTextAreaElement ||
        (node instanceof HTMLElement && node.isContentEditable);
      if (typing) return;
      event.preventDefault();
      search.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className="flex h-16 shrink-0 items-center gap-4 border-b border-white/10 bg-void/60 px-5 backdrop-blur-xl">
      <nav aria-label="Breadcrumb" className="hidden shrink-0 items-center gap-2 sm:flex">
        <Link
          href="/dashboard"
          className="font-head text-[13px] font-medium text-white/45 transition-colors hover:text-white"
        >
          Dashboard
        </Link>
        <IconChevron className="h-3.5 w-3.5 text-white/25" />
        <span aria-current="page" className="font-head text-[13px] font-semibold text-white">
          {crumb}
        </span>
      </nav>

      <div className="void-input ml-auto flex h-9 min-w-0 flex-1 items-center gap-2.5 rounded-xl px-3 sm:max-w-sm">
        <IconSearch className="h-4 w-4 shrink-0 text-white/40" />
        <input
          ref={search}
          type="search"
          placeholder="Search anything…"
          aria-label="Search the workspace"
          className="min-w-0 flex-1 bg-transparent font-sans text-[13px] text-white placeholder:text-white/35 focus:outline-none"
        />
        <kbd className="hidden shrink-0 rounded border border-white/15 px-1.5 py-0.5 font-sans text-[10px] text-white/40 sm:block">
          /
        </kbd>
      </div>

      <ThemeToggle className="shrink-0" />

      <div ref={menu} className="relative shrink-0">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-haspopup="listbox"
          aria-expanded={open}
          className="void-card void-card-hover flex h-9 items-center gap-2.5 rounded-xl px-3"
        >
          <span
            aria-hidden
            className="grid h-5 w-5 place-items-center rounded-md bg-stream/20 font-head text-[10px] font-bold text-stream"
          >
            {workspace.slice(0, 1)}
          </span>
          <span className="hidden font-head text-[13px] font-medium text-white md:block">
            {workspace}
          </span>
          <IconChevron className={`h-3.5 w-3.5 text-white/40 ${open ? "-rotate-90" : "rotate-90"}`} />
        </button>

        {open && (
          <ul
            role="listbox"
            aria-label="Select a workspace"
            className="void-card absolute right-0 top-11 z-50 w-56 overflow-hidden rounded-xl p-1"
          >
            {WORKSPACES.map((name) => (
              <li key={name}>
                <button
                  type="button"
                  role="option"
                  aria-selected={name === workspace}
                  onClick={() => {
                    setWorkspace(name);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left font-head text-[13px] transition-colors ${
                    name === workspace
                      ? "bg-stream/10 text-white"
                      : "text-white/60 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <span
                    aria-hidden
                    className="grid h-5 w-5 place-items-center rounded-md bg-white/10 font-head text-[10px] font-bold text-white/70"
                  >
                    {name.slice(0, 1)}
                  </span>
                  {name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </header>
  );
}
