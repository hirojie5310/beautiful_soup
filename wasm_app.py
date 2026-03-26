# wassm_app.py
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class WasmRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        request_path = unquote(self.path.split("?", 1)[0])
        if request_path.startswith("/web_wasm/faces/"):
            file_name = Path(request_path).name
            if not file_name:
                self.send_error(404, "File not found")
                return
            image_path = REPO_ROOT / "assets" / "images" / "faces" / file_name
            if not image_path.is_file():
                self.send_error(404, "File not found")
                return
            self.path = f"/assets/images/faces/{file_name}"
        super().do_GET()


def run_dev_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    handler = partial(WasmRequestHandler, directory=str(REPO_ROOT))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        print(f"Wasm static server: http://{host}:{port}/web_wasm/")
        httpd.serve_forever()


if __name__ == "__main__":
    run_dev_server()
