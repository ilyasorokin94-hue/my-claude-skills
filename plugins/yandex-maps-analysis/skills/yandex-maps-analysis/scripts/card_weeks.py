#!/usr/bin/env python3
"""Недельные цифры карточки Яндекс Бизнеса из её счётчика в Метрике.

Счётчик карточки (у каждой организации свой, вида yandex.ru/maps) клиника
или Яндекс выдаёт агентству с правом просмотра. Скрипт делит визиты по
поверхностям (приложение Карт, Навигатор, веб-Карты, Поиск) и на рекламные и
нерекламные, а действия (звонок, маршрут, кнопка, сайт) считает так же.

Роботов не вычитаем: на счётчике карточки фильтр Метрики «не робот» убирает
и живые визиты из приложения Карт вместе со звонками, потому что признак
робота у них пустой (проверено 19.11.2026: 96 визитов без фильтра, 59 с ним).
Сколько из них Метрика считает роботами, видно в колонке karty_roboty.

Только чтение, Python 3 без зависимостей. Токен: YANDEX_METRIKA_TOKEN
(в облачной среде агентства его подставляет прокси, в файлы не писать).

Пример:
  python3 card_weeks.py --counter 12345678 --weeks 8
  python3 card_weeks.py --counter 12345678 --from 2026-09-28 --to 2026-11-15
Полная таблица уходит в cache/card_<counter>_<from>_<to>.tsv.
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api-metrika.yandex.net"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(os.path.dirname(HERE), "cache")

# Стандартные цели счётчика карточки: ищем по началу названия, потому что
# Яндекс добавляет к нему адрес организации.
GOALS = [
    ("zvonok", "клик на позвонить"),
    ("marshrut", "построить маршрут"),
    ("knopka", "кнопка действия"),
    ("sayt", "переход на сайт"),
    ("istorii", "кнопка в историях"),
]

SURFACES = ["prilozhenie", "navigator", "veb_karty", "poisk", "drugoe"]


def surface(url):
    """Поверхность по стартовой странице визита."""
    u = (url or "").lower()
    host = urllib.parse.urlsplit(u).netloc or u.split("/")[0]
    if host in ("ru.yandex.traffic", "ru.yandex.yandexmaps"):
        return "prilozhenie"
    if host in ("ru.yandex.mobile.navigator", "ru.yandex.yandexnavi"):
        return "navigator"
    if "/maps/" in u:
        return "veb_karty"
    if host.startswith(("yandex.", "ya.ru", "www.yandex.", "m.yandex.")):
        return "poisk"
    return "drugoe"


def call(path, params, token):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "OAuth " + token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pick_goals(counter, token):
    goals = call(f"/management/v1/counter/{counter}/goals", None, token).get("goals", [])
    found = {}
    for key, prefix in GOALS:
        for g in goals:
            if g.get("name", "").lower().startswith(prefix):
                found[key] = g["id"]
                break
    return found


def _query(counter, token, d1, d2, metrics, extra=None):
    params = {
        "ids": counter,
        "date1": d1.isoformat(),
        "date2": d2.isoformat(),
        "metrics": ",".join(metrics),
        "dimensions": "ym:s:trafficSource,ym:s:startURL",
        "accuracy": "full",
        "limit": 10000,
    }
    params.update(extra or {})
    return call("/stat/v1/data", params, token).get("data", [])


def week_rows(counter, token, d1, d2, goals):
    # Без фильтра и без измерения isRobot: у визитов из приложения Карт признак
    # робота часто пустой, и Метрика выбрасывает такие строки целиком.
    metrics = ["ym:s:visits"] + [f"ym:s:goal{gid}reaches" for gid in goals.values()]
    keys = ["vizity"] + list(goals.keys())
    agg = {}

    def cell_for(row):
        src = row["dimensions"][0].get("id") or ""
        url = row["dimensions"][1].get("name") or ""
        ad = "reklama" if src == "ad" else "bez_reklamy"
        return agg.setdefault((surface(url), ad), dict.fromkeys(keys + ["roboty"], 0.0))

    for row in _query(counter, token, d1, d2, metrics):
        cell = cell_for(row)
        for name, val in zip(keys, row["metrics"]):
            cell[name] += val or 0
    for row in _query(counter, token, d1, d2, ["ym:s:visits"], {"filters": "ym:s:isRobot=='Yes'"}):
        cell_for(row)["roboty"] += row["metrics"][0] or 0
    return agg, keys + ["roboty"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--counter", required=True, help="ID счётчика карточки")
    p.add_argument("--weeks", type=int, default=6, help="сколько полных недель назад (по умолчанию 6)")
    p.add_argument("--from", dest="d_from", help="понедельник первой недели, ГГГГ-ММ-ДД")
    p.add_argument("--to", dest="d_to", help="воскресенье последней недели, ГГГГ-ММ-ДД")
    a = p.parse_args()

    token = os.environ.get("YANDEX_METRIKA_TOKEN", "")
    if not token:
        sys.exit("Нет YANDEX_METRIKA_TOKEN в окружении. Ключ задаёт руководитель в настройках среды, Claude его не вводит.")

    today = dt.date.today()
    last_sunday = today - dt.timedelta(days=today.weekday() + 1)
    end = dt.date.fromisoformat(a.d_to) if a.d_to else last_sunday
    start = dt.date.fromisoformat(a.d_from) if a.d_from else end - dt.timedelta(days=7 * a.weeks - 1)
    start -= dt.timedelta(days=start.weekday())  # всегда с понедельника

    goals = pick_goals(a.counter, token)
    missing = [k for k, _ in GOALS if k not in goals]
    if missing:
        print("Не нашёл цели:", ", ".join(missing), file=sys.stderr)

    header = ["nedelya", "poverhnost", "reklama", "vizity"] + list(goals.keys()) + ["roboty"]
    lines = ["\t".join(header)]
    summary = []
    w = start
    while w <= end:
        w_end = min(w + dt.timedelta(days=6), end)
        agg, keys = week_rows(a.counter, token, w, w_end, goals)
        for (surf, ad), cell in sorted(agg.items()):
            lines.append("\t".join([w.isoformat(), surf, ad] + [str(int(cell[k])) for k in keys]))

        def s(pred, key):
            return int(sum(c[key] for (sf, ad), c in agg.items() if pred(sf, ad)))

        maps = lambda sf: sf in ("prilozhenie", "navigator", "veb_karty")
        row = {
            "nedelya": f"{w:%d.%m}–{w_end:%d.%m}",
            "karty_bez_rekl": s(lambda sf, ad: maps(sf) and ad == "bez_reklamy", "vizity"),
            # Чистая заработанная часть: приложение + Навигатор. Веб-Карты отдельно,
            # туда попадают замеры и проверки агентства с ПК (Z-07).
            "karty_pn_bez_rekl": s(lambda sf, ad: sf in ("prilozhenie", "navigator") and ad == "bez_reklamy", "vizity"),
            "veb_bez_rekl": s(lambda sf, ad: sf == "veb_karty" and ad == "bez_reklamy", "vizity"),
            "karty_rekl": s(lambda sf, ad: maps(sf) and ad == "reklama", "vizity"),
            "poisk_bez_rekl": s(lambda sf, ad: sf == "poisk" and ad == "bez_reklamy", "vizity"),
            "poisk_rekl": s(lambda sf, ad: sf == "poisk" and ad == "reklama", "vizity"),
            "karty_roboty": s(lambda sf, ad: maps(sf), "roboty"),
        }
        for g in ("zvonok", "marshrut", "knopka", "sayt"):
            if g in goals:
                row[g] = s(lambda sf, ad: True, g)
                row[g + "_bez_rekl"] = s(lambda sf, ad: ad == "bez_reklamy", g)
        summary.append(row)
        w += dt.timedelta(days=7)

    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"card_{a.counter}_{start}_{end}.tsv")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    cols = list(summary[0].keys()) if summary else []
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in summary[-30:]:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    print(f"\nКарты = приложение + Навигатор + веб-Карты; karty_pn_bez_rekl = только приложение + Навигатор (чистая заработанная часть), veb_bez_rekl = веб-Карты (сюда попадают замеры агентства). Роботов не вычитаем (фильтр Метрики режет живые визиты из приложения), karty_roboty = сколько из визитов Карт Метрика считает роботами. Полная таблица: {out}")


if __name__ == "__main__":
    main()
