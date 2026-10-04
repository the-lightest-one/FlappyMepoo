
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import bot  # noqa: E402
import storage  # noqa: E402

TOKEN = "test:token"


class _FakeTelegram(BaseHTTPRequestHandler):


    sent: list = []
    queue: list = []
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        params = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        method = self.path.rsplit("/", 1)[-1]

        if method == "getMe":
            result = {"id": 1, "username": "botapp_test", "first_name": "Test"}
        elif method == "getUpdates":
            with _FakeTelegram.lock:
                if params.get("offset") == -1:
                    result = []          
                else:
                    result = list(_FakeTelegram.queue)
                    _FakeTelegram.queue.clear()
            time.sleep(0.05)             
        elif method == "sendMessage":
            with _FakeTelegram.lock:
                _FakeTelegram.sent.append(params)
            result = {"message_id": len(_FakeTelegram.sent)}
        else:
            result = {}

        body = json.dumps({"ok": True, "result": result}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BotIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeTelegram)
        cls.port = cls.server.server_address[1]
        cls.server.daemon_threads = True
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

        cls._original_api_base = bot.API_BASE
        bot.API_BASE = f"http://127.0.0.1:{cls.port}/bot{{token}}/{{method}}"

        cls.counter = 1000
        cls.bot_thread = threading.Thread(target=bot.run, args=(TOKEN,), daemon=True)
        cls.bot_thread.start()
        time.sleep(0.4)  
    @classmethod
    def tearDownClass(cls) -> None:
        bot.API_BASE = cls._original_api_base
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_data = storage.DATA_FILE
        storage.DATA_FILE = Path(self.tmpdir.name) / "scores.json"
        self.addCleanup(lambda: setattr(storage, "DATA_FILE", self._original_data))

    # ---- вспомогательное ----

    def send_update(self, text: str, chat_type: str = "private", user_id: int = 42) -> None:
        BotIntegrationTestCase.counter += 1
        update = {
            "update_id": BotIntegrationTestCase.counter,
            "message": {
                "message_id": BotIntegrationTestCase.counter,
                "chat": {"id": user_id, "type": chat_type},
                "from": {"id": user_id, "first_name": "Тест"},
                "text": text,
            },
        }
        with _FakeTelegram.lock:
            _FakeTelegram.queue.append(update)

    def wait_for_text(self, needle: str, timeout: float = 8.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with _FakeTelegram.lock:
                for message in _FakeTelegram.sent:
                    if needle in (message.get("text") or ""):
                        return message
            time.sleep(0.05)
        with _FakeTelegram.lock:
            got = [m.get("text", "")[:60] for m in _FakeTelegram.sent]
        self.fail(f"не дождались ответа со словами {needle!r}. Получено: {got}")



    def test_start_replies_with_play_button(self):
        self.send_update("/start")
        message = self.wait_for_text("Flappy Bird")

        keyboard = message.get("reply_markup", {}).get("inline_keyboard")
        self.assertIsNotNone(keyboard, "у /start должна быть кнопка запуска игры")
        button = keyboard[0][0]
        self.assertIn("http://localhost:8080/?user=42", button.get("url", ""))

    def test_play_answers_with_hint(self):
        self.send_update("/play")
        message = self.wait_for_text("Открывай игру")
        self.assertIn("inline_keyboard", message.get("reply_markup", {}))

    def test_top_shows_empty_state(self):
        self.send_update("/top")
        self.wait_for_text("Пока никто не играл")

    def test_top_shows_saved_scores(self):
        storage.save_score("42", 12)
        storage.save_score("7", 30)

        self.send_update("/top")
        message = self.wait_for_text("Таблица лидеров")

        self.assertLess(message["text"].index("7"), message["text"].index("42"))
        self.assertIn("30", message["text"])

    def test_unknown_command_gets_help(self):
        self.send_update("/фигня")
        self.wait_for_text("Не знаю такой команды")

    def test_group_chat_is_redirected_to_private(self):
        self.send_update("/play", chat_type="group")
        self.wait_for_text("в личном чате")


if __name__ == "__main__":
    unittest.main()
