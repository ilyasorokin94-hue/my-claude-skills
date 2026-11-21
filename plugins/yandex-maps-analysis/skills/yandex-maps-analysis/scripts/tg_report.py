#!/usr/bin/env python3
"""Сводка обхода отзывов в рабочий чат агентства (Telegram Bot API).

Запуск:
    python tg_report.py --file svodka.txt
    python tg_report.py < svodka.txt
    python tg_report.py --proverka            # проверить настройки, ничего не отправлять

Настройки берутся только из переменных окружения ПК:
    TG_BOT_TOKEN   токен бота (секрет, в файлы и в чат не попадает)
    TG_CHAT_ID     номер рабочего чата
    TG_API_BASE    необязательно, по умолчанию https://api.telegram.org

Коды выхода: 0 отправлено, 2 нет настроек или текста, 3 отправка не прошла.
Только стандартная библиотека Python.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

LIMIT = 4000  # предел Telegram 4096 знаков, оставляем запас
TIMEOUT = 20


def read_text(path):
    if path:
        with open(path, "rb") as f:
            raw = f.read()
    else:
        raw = sys.stdin.buffer.read()
    return raw.decode("utf-8-sig", errors="replace").strip()


def split_text(text, limit=LIMIT):
    """Режет длинную сводку по строкам, чтобы каждое сообщение влезало в предел."""
    parts, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # одна строка длиннее предела
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else current + "\n" + line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate
    if current.strip():
        parts.append(current)
    return parts


def mask(message, token):
    """Токен не должен попасть в вывод ни при какой ошибке."""
    return message.replace(token, "<токен скрыт>") if token else message


def send(base, token, chat_id, text):
    url = "{}/bot{}/sendMessage".format(base.rstrip("/"), token)
    body = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("description", "")
        except Exception:
            detail = ""
        return False, "Telegram ответил {}: {}".format(error.code, detail or "без описания")
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        return False, "нет связи с Telegram: {}".format(reason)
    except ValueError:
        return False, "Telegram вернул не JSON"
    if not answer.get("ok"):
        return False, "Telegram отказал: {}".format(answer.get("description", "без описания"))
    return True, ""


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Сводка обхода в рабочий чат")
    parser.add_argument("--file", help="файл со сводкой в UTF-8; без него текст читается со стандартного входа")
    parser.add_argument("--proverka", action="store_true", help="проверить настройки и текст, ничего не отправлять")
    args = parser.parse_args(argv)

    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    base = os.environ.get("TG_API_BASE", "https://api.telegram.org").strip()

    missing = [name for name, value in (("TG_BOT_TOKEN", token), ("TG_CHAT_ID", chat_id)) if not value]

    if args.proverka:
        print("TG_BOT_TOKEN: {}".format("задан" if token else "НЕ ЗАДАН"))
        print("TG_CHAT_ID: {}".format("задан" if chat_id else "НЕ ЗАДАН"))
        if args.file:
            text = read_text(args.file)
            print("Текст: {} знаков, сообщений: {}".format(len(text), len(split_text(text)) if text else 0))
        return 2 if missing else 0

    if missing:
        print(
            "Не заданы переменные окружения: {}. Их задаёт руководитель на ПК; "
            "после этого перезапустите приложение.".format(", ".join(missing)),
            file=sys.stderr,
        )
        return 2

    text = read_text(args.file)
    if not text:
        print("Пустая сводка, отправлять нечего.", file=sys.stderr)
        return 2
    if token in text:
        print("В тексте сводки найден токен бота. Отправка отменена.", file=sys.stderr)
        return 2

    parts = split_text(text)
    for number, part in enumerate(parts, 1):
        ok, problem = send(base, token, chat_id, part)
        if not ok:
            print(
                mask("Сводка не отправлена (сообщение {} из {}): {}".format(number, len(parts), problem), token),
                file=sys.stderr,
            )
            return 3
    print("Отправлено сообщений: {}".format(len(parts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
