"""Serve the Executive Dashboard locally.

Runs an ordinary Python static HTTP server rooted at the repo root so
the dashboard can fetch reports/*.json via relative URLs.

Usage:
    python ux/dashboard/frontend/serve.py           # default port 8765
    python ux/dashboard/frontend/serve.py 9000      # custom port
"""
from __future__ import annotations

import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Force reload of reports/*.json every fetch — dashboard reads
        # freshly-written files during a session.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()


def main() -> int:
    port = 8765
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"invalid port: {sys.argv[1]}")
            return 1

    import os
    os.chdir(str(_ROOT))

    server = HTTPServer(("127.0.0.1", port), NoCacheHandler)
    url = f"http://127.0.0.1:{port}/ux/dashboard/frontend/index.html"
    print(f"AEGIS Executive Dashboard")
    print(f"  serving from: {_ROOT}")
    print(f"  open:         {url}")
    print(f"  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
