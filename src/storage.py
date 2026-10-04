
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "scores.json"

MAX_SCORE = 100_000          # защита от мусора в файле
MAX_ATTEMPTS_PER_USER = 100  # храним только последние попытки

_lock = threading.Lock()


def _load() -> dict:
    """Читает файл. Битый или отсутствующий файл — не ошибка, начинаем с пустого."""
    try:
        with DATA_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save(data: dict) -> None:
    """Атомарная запись: сначала во временный файл, потом подмена."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_name(DATA_FILE.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(DATA_FILE)


def _clean_user(user) -> str:
    if user is None:
        raise ValueError("не указан игрок")
    name = str(user).strip()[:64]
    if not name:
        raise ValueError("пустой идентификатор игрока")
    return name


def _clean_score(score) -> int:
    try:
        value = int(score)
    except (TypeError, ValueError):
        raise ValueError("счёт должен быть целым числом") from None
    if value < 0 or value > MAX_SCORE:
        raise ValueError(f"счёт вне диапазона 0..{MAX_SCORE}")
    return value


def best_score(user) -> int:
    """Личный рекорд игрока (0, если он ещё не играл)."""
    user = _clean_user(user)
    attempts = _load().get(user) or []
    return max((int(a.get("score", 0)) for a in attempts if isinstance(a, dict)), default=0)


def leaderboard(limit=None) -> list:
    """Список игроков по рекорду: [{"user", "best", "plays"}], лучший первым."""
    data = _load()
    rows = []
    for user, attempts in data.items():
        if not isinstance(attempts, list):
            continue
        scores = [int(a.get("score", 0)) for a in attempts if isinstance(a, dict)]
        if not scores:
            continue
        rows.append({"user": user, "best": max(scores), "plays": len(scores)})
    rows.sort(key=lambda row: (-row["best"], row["user"]))
    return rows if limit is None else rows[:limit]


def rank_of(user) -> int:
    """Место игрока в общем зачёте (1 — лучший; если не играл — место после всех)."""
    user = _clean_user(user)
    my_best = best_score(user)
    better = sum(1 for row in leaderboard() if row["best"] > my_best)
    return better + 1


def save_score(user, score) -> dict:
    """Сохраняет попытку и возвращает сводку для игрока."""
    name = _clean_user(user)
    value = _clean_score(score)

    with _lock:
        data = _load()
        attempts = data.get(name)
        if not isinstance(attempts, list):
            attempts = []
        attempts.append({"score": value, "ts": int(time.time())})
        data[name] = attempts[-MAX_ATTEMPTS_PER_USER:]
        _save(data)

    return {
        "ok": True,
        "user": name,
        "score": value,
        "best": best_score(name),
        "rank": rank_of(name),
        "total": len(leaderboard()),
        "top": leaderboard(limit=5),
    }


if __name__ == "__main__":  # быстрая проверка файла из консоли
    print(json.dumps(leaderboard(limit=10), ensure_ascii=False, indent=2))
