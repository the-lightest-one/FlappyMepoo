from __future__ import annotations

import html
import json
import os
import time
import urllib.error
import urllib.request

import storage

API_ROOT = os.environ.get("BOTAPP_API_BASE", "https://api.telegram.org").rstrip("/")
API_BASE = API_ROOT + "/bot{token}/{method}"
POLL_TIMEOUT_S = 30      
HTTP_TIMEOUT_S = 45      
RETRY_DELAY_S = 5
MAX_MESSAGE_LEN = 4000

GAME_URL = os.environ.get("BOTAPP_GAME_URL", "http://localhost:8080").rstrip("/")


class TelegramError(Exception):
    """Telegram ответил ok=false."""


# ---------------------------------------------------------------- Telegram API

def api_call(token: str, method: str, params: dict | None = None, timeout: int = HTTP_TIMEOUT_S):


    url = API_BASE.format(token=token, method=method)
    body = json.dumps(params if params is not None else {}).encode("utf-8")
    request = urllib.request.Request(url, data=body)
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise TelegramError(payload.get("description") or "неизвестная ошибка Telegram")
    return payload.get("result")


def send_message(token: str, chat_id, text: str, keyboard: dict | None = None) -> None:
    params = {
        "chat_id": chat_id,
        "text": text[:MAX_MESSAGE_LEN],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard is not None:
        params["reply_markup"] = keyboard
    api_call(token, "sendMessage", params)


# ------------------------------------------------------------------- Контент

def game_url_for(user_id) -> str:
    return f"{GAME_URL}/?user={user_id}"


def play_keyboard(user_id) -> dict:
    url = game_url_for(user_id)
    if url.startswith("https://"):
        return {"inline_keyboard": [[{"text": "🎮 Играть", "web_app": {"url": url}}]]}
    return {"inline_keyboard": [[{"text": "🎮 Открыть игру в браузере", "url": url}]]}


HELP_TEXT = (
    "<b>Bot — Flappy Meepo</b>\n\n"
    "/play — открыть игру\n"
    "/top — таблица лидеров\n"
    "/help — эта справка\n\n"
    "Управление: клик, тап или Пробел — взмах лопатой."
)


def format_top(limit: int = 10) -> str:
    rows = storage.leaderboard(limit=limit)
    if not rows:
        return "Пока никто не играл. Напиши /play — займи первое место."
    lines = ["<b>🏆 Таблица лидеров</b>", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for index, row in enumerate(rows, start=1):
        mark = medals.get(index, f"{index}.")
        lines.append(f"{mark} <code>{html.escape(row['user'])}</code> — {row['best']} (попыток: {row['plays']})")
    return "\n".join(lines)


# ------------------------------------------------------------------- Логика

def handle_message(token: str, message: dict) -> None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    sender = message.get("from") or {}
    user_id = sender.get("id")
    text = (message.get("text") or "").strip()

    if chat_id is None or not text:
        return


    if chat_type and chat_type != "private":
        send_message(token, chat_id, "Игра работает в личном чате со мной — напиши мне в лс.")
        return

    command = text.split()[0].lower().split("@", 1)[0]

    if command in ("/start", "/play"):
        if command == "/start":
            send_message(
                token,
                chat_id,
                "Привет! Это <b>botapp</b> — Flappy Meepo прямо в Telegram.\n"
                "Жми кнопку, лети между трубами, результат попадёт в таблицу лидеров.\n\n"
                "Команды: /play, /top, /help",
                keyboard=play_keyboard(user_id),
            )
        else:
            send_message(
                token,
                chat_id,
                "Открывай игру 👇\nПроиграешь — счёт сам прилетит мне.",
                keyboard=play_keyboard(user_id),
            )
        return

    if command == "/top":
        send_message(token, chat_id, format_top())
        return

    if command == "/help":
        send_message(token, chat_id, HELP_TEXT)
        return

    send_message(token, chat_id, "Не знаю такой команды.\n\n" + HELP_TEXT)


def handle_update(token: str, update: dict) -> None:
    message = update.get("message") or update.get("edited_message")
    if message:
        handle_message(token, message)


# --------------------------------------------------------------------- Запуск

def resolve_offset(token: str):
    try:
        updates = api_call(token, "getUpdates", {"offset": -1, "timeout": 0}, timeout=15)
    except (TelegramError, urllib.error.URLError, OSError):
        return None
    if updates:
        return updates[-1]["update_id"] + 1
    return None


def run(token: str) -> None:
    me = api_call(token, "getMe", timeout=15)
    username = me.get("username") or me.get("first_name") or "бот"
    print(f"botapp: подключился как @{username}")
    print(f"botapp: игра — {GAME_URL}")
    if not GAME_URL.startswith("https://"):
        print("botapp: адрес http, кнопка будет открывать игру в браузере на этом компьютере")
    print("Остановить: Ctrl+C")

    offset = resolve_offset(token)
    while True:
        params = {"timeout": POLL_TIMEOUT_S}
        if offset is not None:
            params["offset"] = offset
        try:
            updates = api_call(token, "getUpdates", params)
        except TelegramError as exc:
            print(f"Telegram отклонил запрос: {exc}. Повтор через {RETRY_DELAY_S} с")
            time.sleep(RETRY_DELAY_S)
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Сеть недоступна ({exc}). Повтор через {RETRY_DELAY_S} с")
            time.sleep(RETRY_DELAY_S)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            try:
                handle_update(token, update)
            except TelegramError as exc:
                print(f"Не удалось ответить: {exc}")
            except Exception as exc:  # бот не должен падать от одного плохого апдейта
                print(f"Ошибка обработки апдейта: {exc!r}")


def main() -> None:
    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        print("Не задан токен бота.")
        print('PowerShell:  $env:BOT_TOKEN="123456:ABC..."; py src/bot.py')
        raise SystemExit(1)

    try:
        run(token)
    except KeyboardInterrupt:
        print("\nОстановлено.")
    except TelegramError as exc:
        print(f"Telegram ответил ошибкой: {exc}")
        print("Проверьте, что BOT_TOKEN скопирован целиком и бот не удалён у @BotFather.")
        raise SystemExit(1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Нет связи с {API_ROOT}: {exc}")
        print("Похоже, доступ к Telegram заблокирован провайдером или нет интернета.")
        print("Что делать: включить VPN или указать прокси, например")
        print('  $env:HTTPS_PROXY="http://127.0.0.1:10809"; py src/bot.py')
        raise SystemExit(1)


if __name__ == "__main__":
    main()
