#!/usr/bin/env python3
"""Разбор снимка карточки: приводит вывод snimok_kartochki.js к одному виду
и считает счётчики для строки snimki.csv (модуль 01, блок 1).

Зачем отдельный скрипт: сам снимок делает браузерный snimok_kartochki.js, а
считать по нему и проверять тестами надо здесь. Все выводы, которые попадают в
отчёт, считаются в этом файле.

Запуск:

    python3 snimok_razbor.py snimki-kartochki/2026-11-26.json
    python3 snimok_razbor.py snimok.json --kabinet-poziciy 93 --json razobrano.json

Печатает короткую сводку и строку «Колонки snimki.csv: …». Нет данных — пусто,
а не ноль: пустая колонка честнее выдуманного нуля.
"""

import argparse
import json
import sys

# Поля карточки, без которых снимок считается неполным: по ним идут блоки
# 1 и 8 аудита, и их отсутствие надо видеть сразу, а не искать в отчёте.
OBYAZATELNYE = ("nazvanie", "rubriki", "rejting", "ocenok", "foto", "katalog")


def _chislo(znachenie):
    """Цена и счётчики приходят то числом, то строкой вида «от … ₽»."""
    if znachenie is None:
        return None
    if isinstance(znachenie, bool):
        return None
    if isinstance(znachenie, (int, float)):
        return znachenie
    cifry = "".join(s for s in str(znachenie) if s.isdigit())
    return int(cifry) if cifry else None


def normalizovat(kartochka):
    """Дополняет карточку пустыми полями, чтобы сравнение снимков не падало."""
    out = dict(kartochka)
    out.setdefault("oshibki", [])
    for pole in OBYAZATELNYE:
        if out.get(pole) in (None, [], {}):
            out["oshibki"].append("нет поля: %s" % pole)
    out["katalog"] = list(out.get("katalog") or [])
    out["plitki"] = list(out.get("plitki") or [])
    out["foto"] = dict(out.get("foto") or {})
    return out


def schetchiki(kartochka, kabinet_poziciy=None):
    """Счётчики для snimki.csv. Нет данных — None, а не 0."""
    katalog = kartochka.get("katalog") or []
    plitki = kartochka.get("plitki") or []
    foto = kartochka.get("foto") or {}

    out = {
        "tarif_kartochki": kartochka.get("tarif"),
        "ocenok": kartochka.get("ocenok"),
        "foto": foto.get("vsego"),
        "poziciy_kataloga": len(katalog) if katalog else None,
        "plitok_vsego": len(plitki) if plitki else None,
        "obyavleniy_vsego": len(plitki) if plitki else None,
    }

    if katalog:
        out["poziciy_bez_foto"] = sum(1 for p in katalog if not p.get("foto"))
        out["poziciy_bez_ceny"] = sum(1 for p in katalog if _chislo(p.get("cena")) is None)
    if plitki:
        out["plitok_bez_ceny"] = sum(1 for p in plitki if _chislo(p.get("cena")) is None)
        out["plitok_s_cenoy"] = len(plitki) - out["plitok_bez_ceny"]

    if kabinet_poziciy is not None and katalog:
        # R-16: публично позиций обычно больше, часть Яндекс добавил сам с сайта.
        out["poziciy_publichno_vs_kabinet"] = "%d/%d" % (len(katalog), kabinet_poziciy)

    return out


def plitki_bez_metki(kartochka):
    """Плитки без utm_term: по ним заявки не посчитать (N-05, N-09)."""
    return [p.get("nomer") for p in (kartochka.get("plitki") or [])
            if not p.get("utm_term")]


def pozicii_yandeksa(kartochka):
    """Позиции каталога, которые Яндекс подтянул с сайтов сам (R-16)."""
    return [p.get("nazvanie") for p in (kartochka.get("katalog") or [])
            if p.get("source_url")]


def svodka(snimok, kabinet_poziciy=None):
    nasha = normalizovat(snimok.get("nasha") or {})
    stroki = ["# Снимок карточки %s" % (snimok.get("snyato") or "без даты")]

    sch = schetchiki(nasha, kabinet_poziciy)
    stroki.append("")
    stroki.append("Карточка: %s, тариф %s, рубрик %d, рейтинг %s при %s оценках." % (
        nasha.get("nazvanie") or "название не прочитано",
        nasha.get("tarif") or "неизвестен (смотри кабинет)",
        len(nasha.get("rubriki") or []),
        nasha.get("rejting") if nasha.get("rejting") is not None else "—",
        nasha.get("ocenok") if nasha.get("ocenok") is not None else "—",
    ))
    stroki.append("Владелец подтверждён: %s. «Хорошее место»: %s." % (
        "да" if nasha.get("vladelec_podtverzhden") else "нет",
        nasha.get("horoshee_mesto") or "нет",
    ))
    stroki.append("Каталог: %s позиций, без фото %s, без цены %s." % (
        sch.get("poziciy_kataloga", "—"),
        sch.get("poziciy_bez_foto", "—"),
        sch.get("poziciy_bez_ceny", "—"),
    ))
    stroki.append("Плитки: %s, без цены %s." % (
        sch.get("plitok_vsego", "—"), sch.get("plitok_bez_ceny", "—"),
    ))

    bez_metki = plitki_bez_metki(nasha)
    if bez_metki:
        stroki.append("Плитки без `utm_term` (заявки по ним не посчитать): %s." %
                      ", ".join(str(n) for n in bez_metki))
    ot_yandeksa = pozicii_yandeksa(nasha)
    if ot_yandeksa:
        stroki.append("Позиций с чужим sourceUrl (Яндекс добавил сам, R-16): %d." %
                      len(ot_yandeksa))

    sosedi = [normalizovat(s) for s in (snimok.get("sosedi") or [])]
    if sosedi:
        stroki.append("")
        stroki.append("## Соседи")
        for s in sosedi:
            stroki.append("- %s: рейтинг %s, оценок %s, позиций %d, плиток %d." % (
                s.get("nazvanie") or s.get("id"),
                s.get("rejting") if s.get("rejting") is not None else "—",
                s.get("ocenok") if s.get("ocenok") is not None else "—",
                len(s.get("katalog") or []), len(s.get("plitki") or []),
            ))

    if nasha.get("oshibki"):
        stroki.append("")
        stroki.append("## Чего не прочитали")
        for o in nasha["oshibki"]:
            stroki.append("- %s" % o)
        stroki.append("")
        stroki.append("Эти поля добери глазами и напиши в «Как улучшить скилл»: "
                      "приёмы стареют вместе с разметкой Яндекса.")

    stroki.append("")
    stroki.append("Колонки snimki.csv: " + "; ".join(
        "%s=%s" % (k, "" if v is None else v) for k, v in sorted(sch.items())))
    return "\n".join(stroki)


def main():
    # На Windows консоль бывает в cp1251, и вывод с «→» падает на кодировке.
    for potok in (sys.stdout, sys.stderr):
        try:
            potok.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("vhod", help="JSON от snimok_kartochki.js; «-» читает стандартный ввод")
    p.add_argument("--kabinet-poziciy", type=int,
                   help="сколько позиций каталога в кабинете (для сравнения с публичной, R-16)")
    p.add_argument("--json", dest="vyhod",
                   help="куда записать разобранный снимок, чтобы сравнивать его дальше")
    a = p.parse_args()

    tekst = sys.stdin.read() if a.vhod == "-" else open(a.vhod, encoding="utf-8").read()
    snimok = json.loads(tekst)

    if a.vyhod:
        snimok["nasha"] = normalizovat(snimok.get("nasha") or {})
        snimok["sosedi"] = [normalizovat(s) for s in (snimok.get("sosedi") or [])]
        with open(a.vyhod, "w", encoding="utf-8") as f:
            json.dump(snimok, f, ensure_ascii=False, indent=2)

    print(svodka(snimok, a.kabinet_poziciy))


if __name__ == "__main__":
    main()
