"""Verified operator alert for a failed/blocked AEGIS run · CEO 2026-11-07.

WHAT WENT WRONG
---------------
India failed for ~5 days and USA repeatedly, and the operator received
nothing. The alert step reported `success` on every one of those runs.

This is why (aegis-daily.yml / aegis-usa.yml, verbatim):

    curl -sS -X POST ".../sendMessage" -d ... || true
    echo "[india_ci_alert] sent"

`|| true` swallows any failure, and the step then prints "sent"
UNCONDITIONALLY - without ever looking at what Telegram returned. On top
of that the step carried `continue-on-error: true`. So a rejected
message, a 403, a wrong chat id, a 429 - every one of them logged
"sent" and went green.

That is the same defect class as the freshness checks that certified
`age 0` over day-old bars: a check that passes without opening the
thing it claims to have checked. "The step executed" is not "Telegram
delivered", and the workflow had no way to tell the difference.

WHAT THIS DOES
--------------
Sends the alert and then PROVES it:

  · HTTP status checked
  · the JSON body's `ok` field checked - a 200 carrying {"ok": false}
    is a FAILURE here, which the old path could not see
  · message_id captured, or the send is not considered delivered
  · bounded retry on TRANSIENT faults only (timeout, connection reset,
    429, 5xx) with backoff - never an unbounded loop
  · CONFIGURATION faults (missing token/chat, 400/401/403/404) reported
    loudly and NOT retried, because retrying a wrong chat id forever
    just hides it
  · a receipt appended to the delivery ledger so the alert itself is
    auditable after the fact
  · the bot token never printed, logged, or written to the ledger

It is an ALERT path. It never attaches the XLSX, and it never changes a
run's verdict: a failed pipeline stays failed. Reporting a failure
reliably is not the same as fixing it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The message carries flag emoji. A console that cannot encode them must
# not take the notifier down with it: an alert that crashes while
# composing is strictly worse than the silent one it replaces.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parents[1]

ALERT_SCHEMA = "aegis.delivery.alert.v1"

#: Bounded. Four attempts over ~14s of backoff; a scheduled run must not
#: hang on a flapping API, and an unbounded retry is how a transient
#: fault becomes an outage.
MAX_ATTEMPTS = 4
BACKOFF_S = (2, 4, 8)

#: Telegram statuses that mean "the request itself is wrong". Retrying
#: these is pointless and hides the misconfiguration.
CONFIG_STATUSES = frozenset({400, 401, 403, 404})

OUTCOME_DELIVERED = "DELIVERED"
OUTCOME_TRANSIENT_FAILED = "TRANSIENT_FAILED"
OUTCOME_CONFIG_ERROR = "CONFIG_ERROR"

UNAVAILABLE = "unavailable"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _chat_fingerprint(chat_id: str) -> str:
    """Hashed chat target · identifies it without disclosing it."""
    if not chat_id:
        return ""
    return "sha256:" + hashlib.sha256(
        str(chat_id).encode("utf-8")).hexdigest()[:16]


def _redact(text: str, token: str) -> str:
    """Never let the token reach a log line, even inside an error body."""
    if token and token in text:
        text = text.replace(token, "***REDACTED***")
    return text


# ─────────────────────────────────────────────────────────────
# message · every field factual or explicitly unavailable
# ─────────────────────────────────────────────────────────────

def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def discover_failure_context(root: Path, market: str) -> dict:
    """Read the gate/reason from the artifacts the run actually wrote.

    Anything that cannot be read stays `unavailable`. A fabricated gate
    name in an alert is worse than an honest gap: it sends the operator
    to the wrong place.
    """
    mk = str(market).lower()
    out = {"gate": UNAVAILABLE, "reason": UNAVAILABLE,
           "stage": UNAVAILABLE, "asof": UNAVAILABLE}

    cert = root / "reports" / "context" / ("run_certification_%s.txt" % mk)
    if cert.exists():
        try:
            txt = cert.read_text(encoding="utf-8", errors="replace")
        except Exception:
            txt = ""
        for line in txt.splitlines():
            ls = line.strip()
            if ls.startswith("Requested ASOF:"):
                out["asof"] = ls.split(":", 1)[1].split("·")[0].strip()
            if ls.startswith("FIRST FAILURE:"):
                rest = ls.split(":", 1)[1].strip()
                out["gate"] = rest.split("(")[0].strip() or UNAVAILABLE
                if "(" in rest and ")" in rest:
                    out["stage"] = rest.split("(")[1].split(")")[0].strip()
            # the gate's own one-line explanation, e.g. the A23 detail
            if ls.startswith("[A") and "]" in ls:
                out["reason"] = ls[:300]

    st = root / "reports" / "context" / ("delivery_status_%s.json" % mk)
    d = _read_json(st) if st.exists() else None
    if isinstance(d, dict):
        if d.get("state"):
            out.setdefault("delivery_state", str(d["state"]))
            out["delivery_state"] = str(d["state"])
        if out["reason"] == UNAVAILABLE and d.get("reason"):
            out["reason"] = str(d["reason"])[:300]
        if out["asof"] == UNAVAILABLE and d.get("asof"):
            out["asof"] = str(d["asof"])[:10]
    return out


def build_message(market: str, run_id: str, sha: str, workflow: str,
                  status: str, ctx: dict, xlsx_sent: bool = False) -> str:
    flag = {"india": "\U0001F1EE\U0001F1F3",
            "usa": "\U0001F1FA\U0001F1F8"}.get(str(market).lower(), "")
    lines = [
        "%s AEGIS %s" % (flag, str(market).upper()),
        "STATUS: %s" % status,
        "Run: %s" % (run_id or UNAVAILABLE),
        "SHA: %s" % ((sha or "")[:12] or UNAVAILABLE),
        "As-of: %s" % ctx.get("asof", UNAVAILABLE),
        "Failed stage: %s" % ctx.get("stage", UNAVAILABLE),
        "Gate: %s" % ctx.get("gate", UNAVAILABLE),
        "Reason: %s" % ctx.get("reason", UNAVAILABLE),
    ]
    if ctx.get("delivery_state"):
        lines.append("Delivery: %s" % ctx["delivery_state"])
    lines += [
        "Workflow: %s" % (workflow or UNAVAILABLE),
        "Normal XLSX: %s" % ("SENT" if xlsx_sent else "NOT SENT"),
        "ACTION: investigate",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# send · and prove it
# ─────────────────────────────────────────────────────────────

def send_verified(token: str, chat_id: str, text: str) -> dict:
    """POST sendMessage and verify the outcome. Never raises."""
    if not token or not chat_id:
        missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", token),
                                  ("TELEGRAM_CHAT_ID", chat_id)) if not v]
        return {"outcome": OUTCOME_CONFIG_ERROR, "attempts": 0,
                "http_status": None, "telegram_ok": False, "message_id": None,
                "error": "missing configuration: %s" % ", ".join(missing)}

    url = "https://api.telegram.org/bot%s/sendMessage" % token
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:4080],
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    last = {"outcome": OUTCOME_TRANSIENT_FAILED, "attempts": 0,
            "http_status": None, "telegram_ok": False, "message_id": None,
            "error": "not attempted"}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        last["attempts"] = attempt
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                status = int(getattr(r, "status", 0) or 0)
                body = r.read().decode("utf-8", errors="replace")
            payload = {}
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}
            ok = bool(payload.get("ok"))
            mid = (payload.get("result") or {}).get("message_id")
            # A 200 carrying {"ok": false} is a FAILURE. The old curl
            # path could not see this at all.
            if status == 200 and ok and mid is not None:
                return {"outcome": OUTCOME_DELIVERED, "attempts": attempt,
                        "http_status": status, "telegram_ok": True,
                        "message_id": int(mid),
                        "delivered_at_utc": _utc(), "error": None}
            last = {"outcome": OUTCOME_TRANSIENT_FAILED, "attempts": attempt,
                    "http_status": status, "telegram_ok": ok,
                    "message_id": mid,
                    "error": "unexpected response: %s"
                             % _redact(body[:200], token)}
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(e)
            code = int(getattr(e, "code", 0) or 0)
            cfg = code in CONFIG_STATUSES
            last = {
                "outcome": (OUTCOME_CONFIG_ERROR if cfg
                            else OUTCOME_TRANSIENT_FAILED),
                "attempts": attempt, "http_status": code,
                "telegram_ok": False, "message_id": None,
                "error": _redact(body[:200], token),
            }
            if cfg:
                # Wrong token / wrong chat / blocked bot. Retrying forever
                # is how a misconfiguration stays invisible.
                return last
        except (urllib.error.URLError, socket.timeout, TimeoutError,
                ConnectionError, OSError) as e:
            last = {"outcome": OUTCOME_TRANSIENT_FAILED, "attempts": attempt,
                    "http_status": None, "telegram_ok": False,
                    "message_id": None,
                    "error": "%s: %s" % (type(e).__name__,
                                         _redact(str(e)[:160], token))}
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)])
    return last


# ─────────────────────────────────────────────────────────────
# receipt · the alert itself must be auditable
# ─────────────────────────────────────────────────────────────

def ledger_path(root: Path, on: str) -> Path:
    return root / "reports" / ("telegram_command_center_%s.jsonl" % on[:10])


def record_alert(root: Path, market: str, res: dict, chat_id: str,
                 run_id: str, sha: str, status: str, ctx: dict) -> Path:
    """Append the alert receipt. Never claims an attachment was sent."""
    rec = {
        "schema": ALERT_SCHEMA,
        "kind": "failure_alert",
        "ts_utc": _utc(),
        "market": str(market).lower(),
        "run_id": run_id or None,
        "sha": sha or None,
        "pipeline_status": status,
        "failed_stage": ctx.get("stage"),
        "gate": ctx.get("gate"),
        "reason": ctx.get("reason"),
        "delivery_state": ctx.get("delivery_state"),
        # ALERT path · there is no attachment, and saying so explicitly
        # keeps this record from ever being read as a delivery receipt.
        "attachment": None,
        "attachment_sha256": None,
        "attachment_bytes": None,
        "chat_fingerprint": _chat_fingerprint(chat_id),
        "http_status": res.get("http_status"),
        "telegram_ok": bool(res.get("telegram_ok")),
        "message_id": res.get("message_id"),
        "delivered_at_utc": res.get("delivered_at_utc"),
        "attempts": res.get("attempts"),
        "outcome": res.get("outcome"),
        "receipt_verified": res.get("outcome") == OUTCOME_DELIVERED,
        "error": res.get("error"),
    }
    p = ledger_path(root, datetime.now(timezone.utc).date().isoformat())
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="AEGIS · verified operator alert for a failed run")
    ap.add_argument("--market", required=True,
                    choices=["india", "usa"])
    ap.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    ap.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    ap.add_argument("--workflow", default=os.environ.get("GITHUB_WORKFLOW", ""))
    # Derived from the artifacts by default. Computing this in a GitHub
    # expression would put a second, divergent opinion of "what went
    # wrong" in the workflow file.
    ap.add_argument("--status", default=None)
    ap.add_argument("--root", default=str(_ROOT))
    ap.add_argument("--dry-run", action="store_true",
                    help="compose and print · send nothing")
    a = ap.parse_args(argv)

    root = Path(a.root)
    ctx = discover_failure_context(root, a.market)
    status = a.status
    if not status:
        ds = str(ctx.get("delivery_state") or "")
        status = ("DELIVERY BLOCKED"
                  if ("BLOCK" in ds.upper()
                      or str(ctx.get("gate") or "").upper().startswith(
                          "DELIVERY_GATE"))
                  else "FAILED")
    msg = build_message(a.market, a.run_id, a.sha, a.workflow,
                        status, ctx)
    print("[alert:%s] composed message:" % a.market)
    for line in msg.splitlines():
        print("    %s" % line)

    if a.dry_run:
        print("[alert:%s] dry-run · nothing sent" % a.market)
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    res = send_verified(token, chat, msg)
    try:
        p = record_alert(root, a.market, res, chat, a.run_id, a.sha,
                         status, ctx)
        print("[alert:%s] receipt -> %s"
              % (a.market, p.relative_to(root).as_posix()))
    except Exception as e:
        print("[alert:%s] receipt write failed · %s: %s"
              % (a.market, type(e).__name__, e))

    print("[alert:%s] outcome=%s http=%s telegram_ok=%s message_id=%s "
          "attempts=%s" % (a.market, res["outcome"], res.get("http_status"),
                           res.get("telegram_ok"), res.get("message_id"),
                           res.get("attempts")))

    if res["outcome"] == OUTCOME_DELIVERED:
        print("[alert:%s] DELIVERED · message_id=%s"
              % (a.market, res["message_id"]))
        return 0
    if res["outcome"] == OUTCOME_CONFIG_ERROR:
        # Loud, and specific about WHICH kind of wrong, without ever
        # printing the secret itself.
        print("::error::[alert:%s] TELEGRAM CONFIGURATION ERROR · %s · "
              "chat=%s · the operator was NOT notified"
              % (a.market, res.get("error"), _chat_fingerprint(chat)
                 or "(unset)"))
        return 2
    print("::error::[alert:%s] TELEGRAM NOT DELIVERED after %s attempt(s) "
          "· http=%s · %s · the operator was NOT notified"
          % (a.market, res.get("attempts"), res.get("http_status"),
             res.get("error")))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
