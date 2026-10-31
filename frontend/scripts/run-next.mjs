/**
 * Launches the Next CLI with a bounded V8 semi-space.
 *
 * Node 24 + Next 14 crashes on Windows with "Committing semi space failed"
 * well below the heap limit. The flag has to travel in NODE_OPTIONS rather
 * than argv, because Next forks build/compile workers that inherit the
 * environment but not the parent's command line.
 */
import { spawn } from "node:child_process";

const FLAG = "--max-semi-space-size=16";
const existing = process.env.NODE_OPTIONS ?? "";

const child = spawn(
  process.execPath,
  ["./node_modules/next/dist/bin/next", ...process.argv.slice(2)],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      NODE_OPTIONS: existing.includes("max-semi-space-size")
        ? existing
        : `${existing} ${FLAG}`.trim(),
    },
  },
);

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 0);
});
