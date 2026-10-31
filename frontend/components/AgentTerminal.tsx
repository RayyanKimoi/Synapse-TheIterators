"use client";

import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { CornerDownLeft, Terminal, X } from "lucide-react";

import { API_BASE, streamAgent } from "@/lib/api";
import type { AgentEvent, AgentTone, WorkflowSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const ARENA = ["race", "baseline", "compiled"] as const;
type ArenaAction = (typeof ARENA)[number];

/** Agent tools (backend) plus the commands the terminal answers itself. */
const COMMANDS = [
  "help", "health", "workflows", "inspect", "compile", "passes", "run", "race",
  "judge", "cache", "explain", "select", "arena", "clear", "history", "exit",
];

const MAX_LINES = 2000;

type Line = { id: number; text: string; tone: AgentTone | "cmd" };

const TONE: Record<Line["tone"], string> = {
  cmd: "text-foreground",
  text: "text-foreground/85",
  muted: "text-muted-foreground",
  info: "text-state-running",
  ok: "text-state-cached",
  warn: "text-state-blocking",
  error: "text-state-failed",
  accent: "text-state-completed",
};

type AgentTerminalProps = {
  open: boolean;
  onOpenChange: Dispatch<SetStateAction<boolean>>;
  workflowId: string | null;
  workflows: WorkflowSummary[];
  /** The arena is mid-run; arena commands wait rather than restart it. */
  busy: boolean;
  onSelectWorkflow: (workflowId: string) => void;
  onArena: (action: ArenaAction) => void;
};

/**
 * A terminal onto the SYNAPSE agent. Plain English or commands go to
 * POST /api/v1/agent/run, which plans them into steps and runs each against the
 * real compiler, runtime and cache, streaming output back line by line.
 *
 * `clear`, `history`, `exit` and `arena …` are answered here: the arena is
 * dashboard state, so replaying a race live has to start from the browser.
 */
export function AgentTerminal({
  open,
  onOpenChange,
  workflowId,
  workflows,
  busy,
  onSelectWorkflow,
  onArena,
}: AgentTerminalProps) {
  const [lines, setLines] = useState<Line[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);

  const nextId = useRef(0);
  const history = useRef<string[]>([]);
  const cursor = useRef(-1); // -1: editing a fresh line, not recalling one
  const abort = useRef<AbortController | null>(null);
  const greeted = useRef(false);
  const stick = useRef(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  // Streamed events arrive long after the render that started them, so they
  // read the dashboard's current state through refs, never a stale closure.
  const live = useRef({ workflowId, busy, onSelectWorkflow, onArena });
  live.current = { workflowId, busy, onSelectWorkflow, onArena };

  const print = useCallback((text: string, tone: Line["tone"] = "text") => {
    setLines((current) => {
      const next = [...current, { id: nextId.current++, text, tone }];
      return next.length > MAX_LINES ? next.slice(next.length - MAX_LINES) : next;
    });
  }, []);

  // ` toggles the terminal from anywhere except another text field.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "`" || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const editing =
        target &&
        (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      if (editing && target !== inputRef.current) return;
      event.preventDefault();
      onOpenChange((value) => !value);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onOpenChange]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    if (!greeted.current) {
      greeted.current = true;
      print("SYNAPSE agent · commands or plain English, run against the live compiler", "accent");
      print(`connected to ${API_BASE} · type \`help\`, or try: compile and race the market workflow`, "muted");
    }
  }, [open, print]);

  // Follow the output unless the reader has scrolled up to look at something.
  useEffect(() => {
    const element = outputRef.current;
    if (element && stick.current) element.scrollTop = element.scrollHeight;
  }, [lines]);

  // Closing the page mid-run must not leave a race executing server-side.
  useEffect(() => () => abort.current?.abort(), []);

  const onEvent = useCallback(
    (event: AgentEvent) => {
      switch (event.type) {
        case "plan":
          if (event.steps.length > 1) {
            print(`plan · ${event.steps.map((s, i) => `${i + 1}. ${s.title}`).join("   ")}`, "accent");
          }
          break;
        case "step":
          print(`→ ${event.title}`, "info");
          break;
        case "line":
          print(event.text, event.tone);
          break;
        case "ui":
          if (event.action === "select" && event.workflow_id !== live.current.workflowId) {
            live.current.onSelectWorkflow(event.workflow_id);
            print(`↳ dashboard switched to ${event.workflow_id}`, "muted");
          }
          break;
        case "done":
          print(
            event.ok ? `done · ${(event.elapsed_ms / 1000).toFixed(2)}s` : "stopped",
            event.ok ? "muted" : "warn",
          );
          break;
      }
    },
    [print],
  );

  const runArena = (argument: string | undefined) => {
    const action = (argument ?? "race").toLowerCase() as ArenaAction;
    if (!ARENA.includes(action)) {
      print(`arena takes ${ARENA.join(" | ")}`, "warn");
    } else if (!live.current.workflowId) {
      print("no workflow is selected yet", "warn");
    } else if (live.current.busy) {
      print("the arena is already running; wait for it to finish", "warn");
    } else {
      live.current.onArena(action);
      print(`arena ${action} started on ${live.current.workflowId}; watch the canvas`, "ok");
    }
  };

  const submit = async (raw: string) => {
    const text = raw.trim();
    if (!text || running) return;
    history.current = [text, ...history.current.filter((entry) => entry !== text)].slice(0, 100);
    cursor.current = -1;
    setInput("");
    stick.current = true;
    print(text, "cmd");

    const [head, ...rest] = text.split(/\s+/);
    switch (head.toLowerCase()) {
      case "clear":
      case "cls":
        setLines([]);
        return;
      case "exit":
      case "close":
        onOpenChange(false);
        return;
      case "history":
        history.current
          .slice()
          .reverse()
          .forEach((entry, index) => print(`  ${String(index + 1).padStart(3)}  ${entry}`, "muted"));
        return;
      case "arena":
        runArena(rest[0]);
        return;
    }

    const controller = new AbortController();
    abort.current = controller;
    setRunning(true);
    try {
      await streamAgent(text, live.current.workflowId, controller.signal, onEvent);
    } catch (error) {
      if (controller.signal.aborted) {
        print("^C · stopped", "warn");
      } else {
        print(
          `can't reach the SYNAPSE backend at ${API_BASE} (${error instanceof Error ? error.message : String(error)})`,
          "error",
        );
        print("start it in backend/: uvicorn app.main:app --reload --port 8000", "muted");
      }
    } finally {
      abort.current = null;
      setRunning(false);
    }
  };

  /** Completes a command name, then a workflow id (or an arena action). */
  const complete = () => {
    const parts = input.split(" ");
    const last = parts[parts.length - 1];
    const pool =
      parts.length === 1
        ? COMMANDS
        : parts[0].toLowerCase() === "arena"
          ? [...ARENA]
          : workflows.map((workflow) => workflow.workflow_id);
    const matches = pool.filter((option) => option.startsWith(last.toLowerCase()));
    if (matches.length === 1) {
      setInput([...parts.slice(0, -1), matches[0]].join(" ") + " ");
    } else if (matches.length > 1) {
      print(matches.join("   "), "muted");
    }
  };

  const recall = (step: 1 | -1) => {
    const next = Math.max(-1, Math.min(history.current.length - 1, cursor.current + step));
    cursor.current = next;
    setInput(next === -1 ? "" : history.current[next]);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      recall(1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      recall(-1);
    } else if (event.key === "Tab") {
      event.preventDefault();
      complete();
    } else if (event.key === "Escape") {
      onOpenChange(false);
    } else if (event.ctrlKey && event.key.toLowerCase() === "l") {
      event.preventDefault();
      setLines([]);
    } else if (event.ctrlKey && event.key.toLowerCase() === "c") {
      // Copy still works when text is selected; otherwise Ctrl+C interrupts.
      if (window.getSelection()?.toString()) return;
      event.preventDefault();
      if (abort.current) abort.current.abort();
      else {
        print(`${input}^C`, "cmd");
        setInput("");
      }
    }
  };

  if (!open) return null;

  return (
    <section
      aria-label="Agent terminal"
      className="fixed inset-x-3 bottom-3 z-40 flex h-[min(48vh,480px)] flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-background/95 shadow-[0_-24px_70px_-30px_hsl(var(--state-running)/0.45)] backdrop-blur-xl"
    >
      <header className="flex items-center gap-3 border-b border-white/[0.07] liquid-chrome px-4 py-2">
        <Terminal className="h-3.5 w-3.5 text-state-running" aria-hidden="true" />
        <span className="font-mono text-[11px] text-foreground">agent@synapse</span>
        <span className="truncate rounded-md border border-white/[0.08] bg-background/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {workflowId ?? "no workflow"}
        </span>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              running ? "animate-pulse bg-state-running" : "bg-state-cached",
            )}
            aria-hidden="true"
          />
          {running ? "running · Ctrl+C stops" : "ready"}
        </span>
        <span className="ml-auto hidden font-mono text-[10px] text-muted-foreground/70 sm:inline">
          Tab completes · ↑↓ history · ` toggles
        </span>
        <button
          type="button"
          onClick={() => setLines([])}
          className="rounded-md px-2 py-1 font-mono text-[10px] text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
        >
          clear
        </button>
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          aria-label="Close the agent terminal"
          className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </header>

      <div
        ref={outputRef}
        role="log"
        aria-live="polite"
        onScroll={(event) => {
          const element = event.currentTarget;
          stick.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
        }}
        onMouseUp={() => {
          // Clicking the log focuses the prompt, unless the reader is selecting text.
          if (!window.getSelection()?.toString()) inputRef.current?.focus();
        }}
        className="pixel-canvas flex-1 overflow-y-auto px-4 py-3 font-mono text-[12.5px] leading-[1.65]"
      >
        {lines.map((line) => (
          <div key={line.id} className={cn("whitespace-pre-wrap break-words", TONE[line.tone])}>
            {line.tone === "cmd" ? (
              <>
                <span className="select-none text-state-running">synapse ❯ </span>
                {line.text}
              </>
            ) : (
              line.text
            )}
          </div>
        ))}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit(input);
        }}
        className="flex items-center gap-2 border-t border-white/[0.07] bg-card/40 px-4 py-2.5 font-mono text-[12.5px] focus-within:bg-card/70"
      >
        <span className="select-none text-state-running">synapse ❯</span>
        <input
          ref={inputRef}
          value={input}
          onChange={(event) => {
            setInput(event.target.value);
            cursor.current = -1;
          }}
          onKeyDown={onKeyDown}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          aria-label="Agent terminal input"
          placeholder={running ? "running… Ctrl+C to stop" : "compile and race the market workflow"}
          className="min-w-0 flex-1 bg-transparent text-foreground caret-state-running outline-none placeholder:text-muted-foreground/45"
        />
        <CornerDownLeft className="h-3.5 w-3.5 text-muted-foreground/60" aria-hidden="true" />
      </form>
    </section>
  );
}
