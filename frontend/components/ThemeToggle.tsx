"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";

const STORAGE_KEY = "synapse-theme";

/** Flips `.dark` on <html> and persists the choice. The no-flash script in the
 *  root layout applies the stored value before paint; this just keeps it in sync. */
export function ThemeToggle({ className }: { className?: string }) {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      /* private mode / blocked storage: the toggle still works for this view */
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={!dark}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
      className={cn(
        "grid h-9 w-9 place-items-center rounded-xl border border-white/[0.09] text-muted-foreground transition-colors hover:text-foreground",
        className,
      )}
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
