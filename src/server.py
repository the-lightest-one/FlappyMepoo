from __future__ import annotations

import json
import os
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import storage

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
DEFAULT_PORT = 8080
MAX_BODY_BYTES = 4096
BIND_ADDRESSES = ("127.0.0.1", "::1")


class BotappHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)


    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self) -> str:
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    def do_GET(self):
        if self._route() == "/top":
            self._send_json({"ok": True, "top": storage.leaderboard(limit=10)})
            return
        super().do_GET()

    def do_POST(self):
        if self._route() != "/score":
            self._send_json({"ok": False, "error": "не найдено"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json({"ok": False, "error": "неверный размер запроса"}, 400)
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"ok": False, "error": "ожидается JSON"}, 400)
            return

        if not isinstance(payload, dict):
            self._send_json({"ok": False, "error": "ожидается объект JSON"}, 400)
            return

        try:
            result = storage.save_score(payload.get("user"), payload.get("score"))
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, 400)
            return

        self._send_json(result)


class _LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _make_server(address: str, port: int) -> ThreadingHTTPServer:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET

    class _Server(_LocalServer):
        address_family = family

    return _Server((address, port), BotappHandler)


def main() -> None:
    try:
        port = int(os.environ.get("BOTAPP_PORT", DEFAULT_PORT))
    except ValueError:
        port = DEFAULT_PORT

    servers = []
    for address in BIND_ADDRESSES:
        try:
            servers.append(_make_server(address, port))
        except OSError:
            pass

    if not servers:
        raise SystemExit(f"Не удалось занять порт {port}. Освободи его или задай BOTAPP_PORT.")

    print(f"botapp: игра открыта на http://localhost:{port}")
    print("Остановить: Ctrl+C")

    for extra in servers[1:]:
        threading.Thread(target=extra.serve_forever, daemon=True).start()

    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        for server in servers:
            server.server_close()


if __name__ == "__main__":
    main()
