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

После таблицы скрипт печатает коридор шума: по базовым неделям (все полные
недели, кроме двух последних и исключённых) среднее, разброс и в каких
пределах обычно гуляет сумма двух недель, и где против этого стоят две
последние недели. И предупреждает, если много визитов не разложилось по
поверхностям (drugoe): так бывает, когда Яндекс меняет адреса приложений.

Пример:
  python3 card_weeks.py --counter 12345678 --weeks 10
  python3 card_weeks.py --counter 12345678 --from 2026-09-28 --to 2026-11-15
  python3 card_weeks.py --counter 12345678 --weeks 12 --isklyuchit 2026-09-28,2026-10-05
Полная таблица уходит в cache/card_<counter>_<from>_<to>.tsv, недельная
сводка в cache/card_<counter>_<from>_<to>_svodka.csv.
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import statistics
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

# Цифры, для которых печатаем коридор шума.
KORIDOR = ["karty_pn_bez_rekl", "zvonok_bez_rekl", "marshrut_bez_rekl"]
DRUGOE_PREDEL = 0.05


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


def koridor(summary, polnye, isklyuchit):
    """Коридор шума: сколько обычно гуляет сумма двух недель.

    База = полные недели, кроме двух последних полных и исключённых. Сумма двух
    недель при обычных колебаниях лежит в 2m ± 2·√2·sd. Сдвиг двух недель против
    двух прошлых заметен примерно от 2 × коэффициента вариации недели.
    Это стартовый способ: сезон и спрос он не учитывает (см. компас 2).
    """
    full = [i for i, (_, ok) in enumerate(polnye) if ok]
    if len(full) < 2:
        return
    last2 = full[-2:]
    base = [i for i in full[:-2] if polnye[i][0] not in isklyuchit]
    print("\nКоридор шума (база: %d полных недель, без двух последних%s)" % (
        len(base), " и исключённых" if isklyuchit else ""))
    if len(base) < 4:
        print("Мало недель для коридора (нужно от 4, лучше от 8): выводы о росте пока не делаем, это этап накопления базы.")
        return
    if len(base) < 8:
        print("База короче 8 недель: разброс посчитан грубо, итог «выше/ниже» читай как подсказку, а не вывод.")
    print("| цифра | среднее в неделю | разброс | колебание недели | сумма 2 недель обычно | последние 2 недели | итог |")
    print("|---|---|---|---|---|---|---|")
    for col in KORIDOR:
        if col not in summary[0]:
            continue
        xs = [summary[i][col] for i in base]
        m = statistics.mean(xs)
        sd = statistics.stdev(xs)
        lo, hi = 2 * m - 2 * math.sqrt(2) * sd, 2 * m + 2 * math.sqrt(2) * sd
        fact = sum(summary[i][col] for i in last2)
        itog = "выше коридора" if fact > hi else "ниже коридора" if fact < lo else "внутри: не отличить от шума"
        cv = sd / m if m else 0
        print(f"| {col} | {m:.1f} | {sd:.1f} | {cv:.0%} | {max(lo, 0):.0f}–{hi:.0f} | {fact} | {itog} |")
    print("Сдвиг 2 недель против 2 прошлых заметен примерно от 2 × колебания недели. "
          "Если в базе есть старт подписки, сбой или накрутка, исключи их: --isklyuchit <понедельник>,...")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--counter", required=True, help="ID счётчика карточки")
    p.add_argument("--weeks", type=int, default=6, help="сколько полных недель назад (по умолчанию 6)")
    p.add_argument("--from", dest="d_from", help="понедельник первой недели, ГГГГ-ММ-ДД")
    p.add_argument("--to", dest="d_to", help="воскресенье последней недели, ГГГГ-ММ-ДД")
    p.add_argument("--isklyuchit", default="", help="понедельники недель, которые не берём в коридор шума (старт подписки, сбой, накрутка), через запятую")
    a = p.parse_args()
    isklyuchit = {x.strip() for x in a.isklyuchit.split(",") if x.strip()}

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
    polnye = []  # для коридора: (понедельник, полная ли неделя)
    vsego = drugoe = 0
    w = start
    while w <= end:
        w_end = min(w + dt.timedelta(days=6), end)
        agg, keys = week_rows(a.counter, token, w, w_end, goals)
        vsego += sum(c["vizity"] for c in agg.values())
        drugoe += sum(c["vizity"] for (sf, _), c in agg.items() if sf == "drugoe")
        polnye.append((w.isoformat(), (w_end - w).days == 6))
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
    out_csv = out[:-4] + "_svodka.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["ponedelnik"] + cols)
        wr.writeheader()
        for (mon, _), r in zip(polnye, summary):
            wr.writerow({"ponedelnik": mon, **r})

    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in summary[-30:]:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")

    koridor(summary, polnye, isklyuchit)
    if vsego and drugoe / vsego > DRUGOE_PREDEL:
        print(f"\nВНИМАНИЕ: {drugoe / vsego:.0%} визитов не разложились по поверхностям (drugoe, норма до {DRUGOE_PREDEL:.0%}). "
              "Похоже, Яндекс поменял стартовые адреса приложения или Навигатора: посмотри строки poverhnost=drugoe в TSV "
              "и поправь surface(), иначе заработанная часть занижена.")
    print(f"\nСводка по неделям: {out_csv}")
    print(f"Карты = приложение + Навигатор + веб-Карты; karty_pn_bez_rekl = только приложение + Навигатор (чистая заработанная часть), veb_bez_rekl = веб-Карты (сюда попадают замеры агентства). Роботов не вычитаем (фильтр Метрики режет живые визиты из приложения), karty_roboty = сколько из визитов Карт Метрика считает роботами. Полная таблица: {out}")


if __name__ == "__main__":
    main()
