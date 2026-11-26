#!/usr/bin/env python3
"""Сравнение двух снимков одной карточки: что добавилось, пропало и
поменялось (модуль 01, блок 2).

Снимки делает snimok_kartochki.js, разбирает snimok_razbor.py. Здесь считается
разница, которую аудит раскладывает по авторам: мы, Яндекс, пользователи,
модерация. Сам скрипт автора не знает — он показывает, что именно изменилось,
а кто это сделал, решает аудит по журналу правок.

Запуск:

    python3 sravnit_snimki.py snimki-kartochki/2026-11-12.json snimki-kartochki/2026-11-26.json
    python3 sravnit_snimki.py staryy.json novyy.json --csv dlya-otcheta.csv

Печатает markdown для отчёта и строку «Колонки snimki.csv: …».
"""

import argparse
import json
import sys

# Поля карточки, изменение которых всегда заметно пациенту и всегда идёт в отчёт.
POLYA = (
    ("nazvanie", "название"),
    ("adres", "адрес"),
    ("rubrika_glavnaya", "главная рубрика"),
    ("chasy", "часы"),
    ("specrezhim", "спецрежим"),
    ("tarif", "тариф"),
    ("vladelec_podtverzhden", "отметка владельца"),
    ("horoshee_mesto", "«Хорошее место»"),
    ("rejting", "рейтинг"),
    ("ocenok", "оценок"),
    ("otzyvov", "отзывов с текстом"),
)


def _spisok(kartochka, pole):
    return list((kartochka or {}).get(pole) or [])


def _po_nazvaniyu(pozicii):
    """Позиции каталога и плитки сравниваем по названию: id у них нет."""
    out = {}
    for p in pozicii:
        imya = p.get("nazvanie")
        if imya:
            out[imya] = p
    return out


def sravnit_polya(staraya, novaya):
    out = []
    for pole, imya in POLYA:
        bylo, stalo = (staraya or {}).get(pole), (novaya or {}).get(pole)
        if bylo != stalo:
            out.append((imya, bylo, stalo))
    return out


def sravnit_nabor(staraya, novaya, pole):
    """Для рубрик и особенностей: что добавилось, что пропало."""
    bylo, stalo = set(_spisok(staraya, pole)), set(_spisok(novaya, pole))
    return sorted(stalo - bylo), sorted(bylo - stalo)


def sravnit_pozicii(staraya, novaya, pole):
    """Каталог и плитки: добавились, пропали, сменилась цена или порядок."""
    s, n = _po_nazvaniyu(_spisok(staraya, pole)), _po_nazvaniyu(_spisok(novaya, pole))
    dobavilis = [imya for imya in n if imya not in s]
    propali = [imya for imya in s if imya not in n]
    izmenilis = []
    for imya in n:
        if imya not in s:
            continue
        for k, podpis in (("cena", "цена"), ("foto", "фото"),
                          ("razdel", "раздел"), ("populyarnoe", "«Популярное»"),
                          ("utm_term", "метка"), ("nomer", "место в витрине"),
                          ("source_url", "источник позиции")):
            if s[imya].get(k) != n[imya].get(k):
                izmenilis.append((imya, podpis, s[imya].get(k), n[imya].get(k)))
    return dobavilis, propali, izmenilis


def schetchiki(staraya, novaya):
    """Счётчики разницы для snimki.csv."""
    out = {}
    bylo = ((staraya or {}).get("foto") or {}).get("vsego")
    stalo = ((novaya or {}).get("foto") or {}).get("vsego")
    if bylo is not None and stalo is not None:
        out["foto_novyh_2n"] = stalo - bylo
    return out


def _znachenie(v):
    if v is None:
        return "пусто"
    if v is True:
        return "да"
    if v is False:
        return "нет"
    return str(v)


def otchet(staryy, novyy):
    staraya = (staryy or {}).get("nasha") or {}
    novaya = (novyy or {}).get("nasha") or {}
    stroki = ["# Что изменилось в карточке: %s → %s" % (
        (staryy or {}).get("snyato") or "без даты",
        (novyy or {}).get("snyato") or "без даты")]

    polya = sravnit_polya(staraya, novaya)
    stroki += ["", "## Данные карточки"]
    if polya:
        stroki.append("")
        stroki.append("| Что | Было | Стало |")
        stroki.append("|---|---|---|")
        for imya, bylo, stalo in polya:
            stroki.append("| %s | %s | %s |" % (imya, _znachenie(bylo), _znachenie(stalo)))
    else:
        stroki.append("Без изменений.")

    for pole, imya in (("rubriki", "Рубрики"), ("osobennosti", "Особенности")):
        dob, prop = sravnit_nabor(staraya, novaya, pole)
        stroki += ["", "## %s" % imya]
        if dob:
            stroki.append("Добавилось: %s." % ", ".join(dob))
        if prop:
            stroki.append("Пропало: %s." % ", ".join(prop))
        if not dob and not prop:
            stroki.append("Без изменений.")

    for pole, imya in (("katalog", "Каталог"), ("plitki", "Витрина и объявления")):
        dob, prop, izm = sravnit_pozicii(staraya, novaya, pole)
        stroki += ["", "## %s" % imya]
        if dob:
            stroki.append("Добавилось (%d): %s." % (len(dob), ", ".join(dob)))
        if prop:
            stroki.append("Пропало (%d): %s." % (len(prop), ", ".join(prop)))
        if izm:
            stroki.append("")
            stroki.append("| Позиция | Что | Было | Стало |")
            stroki.append("|---|---|---|---|")
            for pozicia, podpis, bylo, stalo in izm:
                stroki.append("| %s | %s | %s | %s |" % (
                    pozicia, podpis, _znachenie(bylo), _znachenie(stalo)))
        if not dob and not prop and not izm:
            stroki.append("Без изменений.")

    sch = schetchiki(staraya, novaya)
    stroki += ["", "## Фото"]
    if "foto_novyh_2n" in sch:
        stroki.append("Фото стало на %+d." % sch["foto_novyh_2n"])
    else:
        stroki.append("Нет данных: в одном из снимков не прочитано число фото.")

    stroki += ["", "Пропало то, чего нет в журнале правок, — это не наша правка: "
                   "ищи Яндекс, пользователей или модерацию (блок 2 модуля 01)."]
    stroki += ["", "Колонки snimki.csv: " + "; ".join(
        "%s=%s" % (k, v) for k, v in sorted(sch.items()))]
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
    p.add_argument("staryy", help="прошлый снимок")
    p.add_argument("novyy", help="свежий снимок")
    p.add_argument("--csv", dest="csv_fayl", help="куда записать счётчики разницы")
    a = p.parse_args()

    with open(a.staryy, encoding="utf-8") as f:
        staryy = json.load(f)
    with open(a.novyy, encoding="utf-8") as f:
        novyy = json.load(f)

    print(otchet(staryy, novyy))

    if a.csv_fayl:
        sch = schetchiki((staryy or {}).get("nasha") or {}, (novyy or {}).get("nasha") or {})
        with open(a.csv_fayl, "w", encoding="utf-8") as f:
            f.write(",".join(sorted(sch)) + "\n")
            f.write(",".join(str(sch[k]) for k in sorted(sch)) + "\n")


if __name__ == "__main__":
    main()
