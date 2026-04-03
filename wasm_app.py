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
    def end_headers(self) -> None:
        # 開発中に JS/HTML の古いキャッシュを掴み続けないよう、常に no-store を付与する。
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

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
        elif request_path.startswith("/web_wasm/enemy_sprites/"):
            file_name = Path(request_path).name
            if not file_name:
                self.send_error(404, "File not found")
                return
            image_path = REPO_ROOT / "assets" / "images" / "enemy_sprites" / file_name
            if not image_path.is_file():
                self.send_error(404, "File not found")
                return
            self.path = f"/assets/images/enemy_sprites/{file_name}"
        elif request_path.startswith("/web_wasm/maps/"):
            file_name = Path(request_path).name
            if not file_name:
                self.send_error(404, "File not found")
                return
            image_path = REPO_ROOT / "assets" / "images" / "maps" / file_name
            if not image_path.is_file():
                self.send_error(404, "File not found")
                return
            self.path = f"/assets/images/maps/{file_name}"
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
