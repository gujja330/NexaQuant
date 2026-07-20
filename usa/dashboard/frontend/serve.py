"""Serve the AEGIS USA Dashboard locally.

Runs a static HTTP server rooted at the repo root so the SPA can
fetch `usa/reports/*.json` via relative URLs. Uses port 8766 (India
uses 8765).

    python usa\dashboard\frontend\serve.py           # default 8766
    python usa\dashboard\frontend\serve.py 9001      # custom port
"""
from __future__ import annotations

import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()


def main() -> int:
    port = 8766
    if len(sys.argv) > 1:
        try:    port = int(sys.argv[1])
        except: pass

    import os
    os.chdir(_ROOT)
    server = HTTPServer(("localhost", port), NoCacheHandler)
    print(f"AEGIS USA Dashboard  →  http://localhost:{port}/usa/dashboard/frontend/")
    print(f"                          Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
