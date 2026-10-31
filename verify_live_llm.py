#!/usr/bin/env python3
"""Prove the tunneled model is really generating tokens.

Standalone on purpose: it imports nothing from `app`, so a pass here is
evidence about the tunnel and the model, not about SYNAPSE. It reads the repo
.env, sends each prompt, and prints the text the model produced plus the token
usage it reported -- so the tally here can be checked against the server's own
counters at the other end of the tunnel.

    python verify_live_llm.py
    python verify_live_llm.py --raw
    python verify_live_llm.py --max-tokens 400 "Task one." "Task two."
    python verify_live_llm.py --tasks            # a few real token-burning jobs

Exit code is 0 only if every prompt came back with non-empty text.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib import error, request

ENV_PATH = Path(__file__).resolve().parent / ".env"
DEFAULT_PROMPT = "In one short sentence, say what an AI workflow compiler does."
TIMEOUT_S = 120

# Real jobs, sized to actually consume tokens rather than just prove a route.
TASK_SUITE = [
    "Analyse this server event and give a short mitigation plan: multiple failed "
    "SSH logins from 203.0.113.42, then a successful root login at 02:00.",
    "Explain in one paragraph why running independent agent nodes concurrently "
    "beats running them one after another.",
    "List four concrete risks of caching LLM responses by semantic similarity, "
    "one line each.",
]


def read_env(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader. No dependency on pydantic or dotenv."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ask(url: str, key: str, model: str, prompt: str, max_tokens: int) -> dict:
    """One completion. Returns the decoded response body."""
    post = request.Request(
        url,
        data=json.dumps(
            {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # ngrok serves a browser interstitial to some user agents.
            "ngrok-skip-browser-warning": "true",
        },
        method="POST",
    )
    with request.urlopen(post, timeout=TIMEOUT_S) as response:
        return json.loads(response.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser(description="Send real prompts to the tunneled model.")
    parser.add_argument("prompts", nargs="*", help="prompts to send (default: one short probe)")
    parser.add_argument("--tasks", action="store_true", help="send the built-in task suite")
    parser.add_argument("--max-tokens", type=int, default=200)
    parser.add_argument("--raw", action="store_true", help="also print each raw response body")
    args = parser.parse_args()

    env = read_env(ENV_PATH)
    base = env.get("LITELLM_PROXY_URL", "").rstrip("/")
    key = env.get("OPENAI_API_KEY", "")
    model = env.get("LIVE_MODEL", "openai/qwen2.5-3b-instruct")
    if not base or not key:
        print(f"FAIL: LITELLM_PROXY_URL / OPENAI_API_KEY missing from {ENV_PATH}")
        return 1

    prompts = args.prompts or (TASK_SUITE if args.tasks else [DEFAULT_PROMPT])
    url = f"{base}/chat/completions"

    print("=" * 72)
    print("SYNAPSE live model verification")
    print("=" * 72)
    print(f"  endpoint   : {url}")
    print(f"  model      : {model}")
    print(f"  api key    : {key[:6]}{'*' * max(len(key) - 6, 0)}")
    print(f"  prompts    : {len(prompts)}   max_tokens: {args.max_tokens}")

    prompt_total = completion_total = 0
    empty: list[int] = []
    started_all = time.perf_counter()

    for index, prompt in enumerate(prompts, start=1):
        print("-" * 72)
        print(f"[{index}/{len(prompts)}] {prompt}")
        print("-" * 72)
        started = time.perf_counter()
        try:
            payload = ask(url, key, model, prompt, args.max_tokens)
        except error.HTTPError as exc:
            print(f"FAIL: HTTP {exc.code}")
            print(exc.read().decode(errors="replace")[:2000])
            return 1
        except Exception as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}")
            return 1
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if args.raw:
            print(json.dumps(payload, indent=2))
            print("-" * 72)

        choice = (payload.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = payload.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens") or 0
        completion_tokens = usage.get("completion_tokens") or 0
        prompt_total += prompt_tokens
        completion_total += completion_tokens
        if not text.strip():
            empty.append(index)

        print(text)
        print(
            f"  -> prompt {prompt_tokens} tok | completion {completion_tokens} tok | "
            f"total {usage.get('total_tokens')} tok | {elapsed_ms} ms | "
            f"finish={choice.get('finish_reason')}"
        )

    wall_ms = int((time.perf_counter() - started_all) * 1000)
    print("=" * 72)
    print("TOKEN TALLY  (compare against your server's own counters)")
    print(f"  calls            : {len(prompts)}")
    print(f"  prompt tokens    : {prompt_total}")
    print(f"  completion tokens: {completion_total}")
    print(f"  total tokens     : {prompt_total + completion_total}")
    print(f"  wall clock       : {wall_ms} ms")
    print("=" * 72)

    if empty:
        print(f"FAIL: prompts {empty} returned an empty completion.")
        return 1
    print("PASS: the model generated real text for every prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
