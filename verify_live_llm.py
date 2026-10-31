#!/usr/bin/env python3
"""Prove the tunneled model is really generating tokens.

Standalone on purpose: it imports nothing from `app`, so a pass here is
evidence about the tunnel and the model, not about SYNAPSE. It reads the repo
.env, sends one plain prompt, and prints the raw response body and the exact
text the model produced.

    python verify_live_llm.py
    python verify_live_llm.py "Write one sentence about compilers."

Exit code is 0 only if the model returned non-empty text.
"""

import json
import sys
import time
from pathlib import Path
from urllib import error, request

ENV_PATH = Path(__file__).resolve().parent / ".env"
DEFAULT_PROMPT = "In one short sentence, say what an AI workflow compiler does."
TIMEOUT_S = 120


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


def main() -> int:
    env = read_env(ENV_PATH)
    base = env.get("LITELLM_PROXY_URL", "").rstrip("/")
    key = env.get("OPENAI_API_KEY", "")
    model = env.get("LIVE_MODEL", "openai/qwen2.5-3b-instruct")
    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT

    if not base or not key:
        print(f"FAIL: LITELLM_PROXY_URL / OPENAI_API_KEY missing from {ENV_PATH}")
        return 1

    url = f"{base}/chat/completions"
    print("=" * 72)
    print("SYNAPSE live model verification")
    print("=" * 72)
    print(f"  endpoint : {url}")
    print(f"  model    : {model}")
    print(f"  api key  : {key[:6]}{'*' * max(len(key) - 6, 0)}")
    print(f"  prompt   : {prompt}")
    print("-" * 72)

    body = json.dumps(
        {
            "model": model,
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    post = request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # ngrok serves a browser interstitial to some user agents.
            "ngrok-skip-browser-warning": "true",
        },
        method="POST",
    )

    started = time.perf_counter()
    try:
        with request.urlopen(post, timeout=TIMEOUT_S) as response:
            status = response.status
            payload = json.loads(response.read().decode())
    except error.HTTPError as exc:
        print(f"FAIL: HTTP {exc.code}")
        print(exc.read().decode(errors="replace")[:2000])
        return 1
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    print("RAW RESPONSE BODY")
    print("-" * 72)
    print(json.dumps(payload, indent=2))

    choice = (payload.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    usage = payload.get("usage") or {}

    print("-" * 72)
    print("GENERATED TEXT (verbatim)")
    print("-" * 72)
    print(text)
    print("-" * 72)
    print(f"  http status     : {status}")
    print(f"  model reported  : {payload.get('model')}")
    print(f"  finish_reason   : {choice.get('finish_reason')}")
    print(f"  prompt tokens   : {usage.get('prompt_tokens')}")
    print(f"  completion tok  : {usage.get('completion_tokens')}")
    print(f"  characters      : {len(text)}")
    print(f"  round trip      : {elapsed_ms} ms")
    print("=" * 72)

    if not text.strip():
        print("FAIL: the model returned an empty completion.")
        return 1
    print("PASS: the model generated real text over the tunnel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
