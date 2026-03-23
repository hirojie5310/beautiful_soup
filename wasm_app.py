# wassm_app.py
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def run_dev_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(REPO_ROOT))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        print(f"Wasm static server: http://{host}:{port}/web_wasm/")
        httpd.serve_forever()


if __name__ == "__main__":
    run_dev_server()
