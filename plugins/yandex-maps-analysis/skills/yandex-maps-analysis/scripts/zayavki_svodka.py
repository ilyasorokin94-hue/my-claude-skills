#!/usr/bin/env python3
"""Сводка заявок из выгрузки CRM или таблицы клиники (модуль 01, блок 13).

Раскладывает заявки по источникам и по плиткам витрины (`utm_term`) и считает
цепочку заявка → запись → визит за 2 недели и за месяц.

**Данные пациентов отсюда не выходят.** Телефон нужен только для склейки дублей:
скрипт превращает его в хеш SHA-256 с солью из переменной окружения и дальше
работает с хешем. Имена, телефоны и адреса не печатаются и не записываются, сырой
файл не копируется. На выходе только агрегаты.

Запуск:

    export AUDIT_HASH_SALT=...   # задаёт руководитель, в файлы не попадает
    python3 zayavki_svodka.py vygruzka.csv \\
        --kol-data "Дата создания" --kol-telefon "Телефон" \\
        --kol-istochnik "Источник" --kol-utm "utm_term" \\
        --kol-status "Этап" --statusy-zapis "Записан,Подтверждён" \\
        --kol-vizit "Визит"

Читает CSV (разделитель определяется сам) и XLSX (через zipfile, без сторонних
библиотек). Какие колонки в выгрузке этой клиники играют какую роль, записано в
её audit-nastroyki.md; формат — shablony/vygruzka-zayavok.md.
"""

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

SOL_PEREMENNAYA = "AUDIT_HASH_SALT"

# Корзины источников. Сначала метка плитки, потом кнопка, потом звонок:
# заявка с плитки — это тоже переход из карточки, но считать её надо отдельно.
KORZINY = (
    ("Карты, плитка", lambda ist, utm: bool(re.match(r"vitrina|plitka|obyavlenie", utm))),
    ("Карты, кнопка", lambda ist, utm: "knopka" in utm or "zapisatsya" in utm),
    ("Карты, звонок", lambda ist, utm: "подмен" in ist or "звон" in ist),
    ("Карты, сайт", lambda ist, utm: "yandex" in ist or "карт" in ist or "maps" in ist
     or "yandex" in utm or utm.startswith("card")),
)

FORMATY_DAT = ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M",
               "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def hesh(telefon, sol):
    """Хеш телефона: нужен только чтобы увидеть дубли, обратно не раскрывается."""
    cifry = "".join(s for s in str(telefon or "") if s.isdigit())
    if not cifry:
        return None
    # Российские номера пишут и с 7, и с 8 — приводим к одному виду,
    # иначе один человек выглядит двумя заявками.
    if len(cifry) == 11 and cifry[0] == "8":
        cifry = "7" + cifry[1:]
    return hashlib.sha256((sol + cifry).encode("utf-8")).hexdigest()


def razobrat_datu(znachenie):
    s = str(znachenie or "").strip()
    if not s:
        return None
    for f in FORMATY_DAT:
        try:
            return dt.datetime.strptime(s[:len(dt.datetime.now().strftime(f))], f).date()
        except ValueError:
            continue
    return None


def korzina(istochnik, utm):
    ist = str(istochnik or "").lower()
    utm = str(utm or "").lower()
    for imya, proverka in KORZINY:
        if proverka(ist, utm):
            return imya
    return "Прочее"


def chitat_csv(tekst):
    obrazec = tekst[:4096]
    try:
        dialekt = csv.Sniffer().sniff(obrazec, delimiters=",;\t")
    except csv.Error:
        dialekt = csv.excel
    return list(csv.DictReader(io.StringIO(tekst), dialect=dialekt))


def chitat_xlsx(put):
    """Минимальное чтение XLSX: первый лист, первая строка — заголовки."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(put) as z:
        stroki_obshchie = []
        if "xl/sharedStrings.xml" in z.namelist():
            korneviy = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in korneviy.findall("%ssi" % ns):
                stroki_obshchie.append("".join(t.text or "" for t in si.iter("%st" % ns)))
        imena = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        if not imena:
            raise ValueError("в XLSX не нашлось листа")
        korneviy = ET.fromstring(z.read(sorted(imena)[0]))

    tablica = []
    for row in korneviy.iter("%srow" % ns):
        stroka = []
        for c in row.findall("%sc" % ns):
            v = c.find("%sv" % ns)
            tekst = "" if v is None else (v.text or "")
            if c.get("t") == "s" and tekst.isdigit():
                tekst = stroki_obshchie[int(tekst)]
            elif c.get("t") == "inlineStr":
                tekst = "".join(t.text or "" for t in c.iter("%st" % ns))
            stroka.append(tekst)
        tablica.append(stroka)

    if not tablica:
        return []
    zagolovki = tablica[0]
    return [dict(zip(zagolovki, s + [""] * (len(zagolovki) - len(s))))
            for s in tablica[1:]]


def svodka(stroki, kol, na_datu, statusy_zapis, sol, dney=14):
    """Агрегаты по корзинам, плиткам и шагам воронки. Ни одного телефона."""
    nachalo_2n = na_datu - dt.timedelta(days=dney)
    nachalo_mes = na_datu - dt.timedelta(days=30)

    po_korzinam, po_plitkam = {}, {}
    heshi_2n, bez_daty, bez_istochnika = [], 0, 0
    itogo = {"zayavki_2n": 0, "zayavki_mes": 0, "zapisi_2n": 0,
             "vizity_2n": 0, "vizity_mes": 0}

    for s in stroki:
        data = razobrat_datu(s.get(kol.get("data")))
        if data is None:
            bez_daty += 1
            continue
        if data < nachalo_mes or data > na_datu:
            continue

        istochnik = s.get(kol.get("istochnik")) or ""
        utm = s.get(kol.get("utm")) or ""
        if not str(istochnik).strip() and not str(utm).strip():
            bez_istochnika += 1
        imya = korzina(istochnik, utm)

        status = str(s.get(kol.get("status")) or "").strip().lower()
        zapis = status in statusy_zapis
        vizit = str(s.get(kol.get("vizit")) or "").strip().lower() in (
            "да", "yes", "1", "true", "пришёл", "пришел")

        v_2n = data >= nachalo_2n
        k = po_korzinam.setdefault(imya, {"zayavki_2n": 0, "zayavki_mes": 0,
                                          "zapisi_2n": 0, "vizity_mes": 0})
        k["zayavki_mes"] += 1
        itogo["zayavki_mes"] += 1
        if vizit:
            k["vizity_mes"] += 1
            itogo["vizity_mes"] += 1
        if v_2n:
            k["zayavki_2n"] += 1
            itogo["zayavki_2n"] += 1
            if zapis:
                k["zapisi_2n"] += 1
                itogo["zapisi_2n"] += 1
            if vizit:
                itogo["vizity_2n"] += 1
            h = hesh(s.get(kol.get("telefon")), sol)
            if h:
                heshi_2n.append(h)

        if utm:
            p = po_plitkam.setdefault(str(utm), {"zayavki_2n": 0, "vizity_mes": 0})
            if v_2n:
                p["zayavki_2n"] += 1
            if vizit:
                p["vizity_mes"] += 1

    dubli = len(heshi_2n) - len(set(heshi_2n))
    return {
        "na_datu": na_datu.isoformat(),
        "po_korzinam": po_korzinam,
        "po_plitkam": po_plitkam,
        "itogo": itogo,
        "dubli_2n": dubli,
        "bez_daty": bez_daty,
        "bez_istochnika": bez_istochnika,
        "telefonov_v_rabote": len(heshi_2n),
    }


def otchet(s):
    stroki = ["# Заявки с Карт на %s" % s["na_datu"], ""]
    stroki.append("| Источник | Заявки 2 недели | Заявки месяц | Записи 2 недели | Визиты месяц |")
    stroki.append("|---|---|---|---|---|")
    for imya in sorted(s["po_korzinam"]):
        k = s["po_korzinam"][imya]
        stroki.append("| %s | %d | %d | %d | %d |" % (
            imya, k["zayavki_2n"], k["zayavki_mes"], k["zapisi_2n"], k["vizity_mes"]))

    if s["po_plitkam"]:
        stroki += ["", "## По плиткам и кнопкам (`utm_term`)", "",
                   "| Метка | Заявки 2 недели | Визиты месяц |", "|---|---|---|"]
        for metka in sorted(s["po_plitkam"]):
            p = s["po_plitkam"][metka]
            stroki.append("| %s | %d | %d |" % (metka, p["zayavki_2n"], p["vizity_mes"]))
        stroki += ["", "Метка без заявок 14 дней — кандидат на замену или тест цены "
                       "(H-02). Звонки и маршруты к плитке не привязываются вообще."]

    i = s["itogo"]
    stroki += ["", "## Путь до визита", "",
               "За 2 недели: заявок %d → записей %d → визитов %d." % (
                   i["zayavki_2n"], i["zapisi_2n"], i["vizity_2n"]),
               "За месяц: заявок %d → визитов %d." % (i["zayavki_mes"], i["vizity_mes"])]
    if i["zayavki_2n"] and i["zapisi_2n"] * 2 < i["zayavki_2n"]:
        stroki.append("Между заявкой и записью теряется больше половины: "
                      "чинить с этого конца (перезвон, подтверждение записи).")

    stroki += ["", "## Качество выгрузки", "",
               "Дублей за 2 недели (один и тот же хеш телефона): %d." % s["dubli_2n"],
               "Строк без читаемой даты: %d." % s["bez_daty"],
               "Строк без источника и метки: %d." % s["bez_istochnika"]]
    if s["bez_istochnika"] * 2 > i["zayavki_mes"] and i["zayavki_mes"]:
        stroki.append("Источника не видно больше чем у половины заявок — это флаг "
                      "учёта (N-14), а не вывод о Картах.")
    stroki += ["", "Визиты смотрим за месяц: за 2 недели их слишком мало, чтобы "
                   "отличить сдвиг от шума."]
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
    p.add_argument("vhod", help="выгрузка CSV или XLSX")
    p.add_argument("--kol-data", required=True)
    p.add_argument("--kol-telefon")
    p.add_argument("--kol-istochnik")
    p.add_argument("--kol-utm")
    p.add_argument("--kol-status")
    p.add_argument("--kol-vizit")
    p.add_argument("--statusy-zapis", default="",
                   help="значения колонки статуса, которые считаем записью, через запятую")
    p.add_argument("--na-datu", help="конец периода, ГГГГ-ММ-ДД (по умолчанию сегодня)")
    p.add_argument("--dney", type=int, default=14, help="длина короткого периода")
    p.add_argument("--json", dest="vyhod", help="куда записать агрегаты")
    a = p.parse_args()

    sol = os.environ.get(SOL_PEREMENNAYA)
    if not sol and a.kol_telefon:
        sys.exit("Нет переменной %s: без соли телефоны не хешируем и дубли не считаем. "
                 "Соль задаёт руководитель." % SOL_PEREMENNAYA)

    if a.vhod.lower().endswith(".xlsx"):
        stroki = chitat_xlsx(a.vhod)
    else:
        with open(a.vhod, encoding="utf-8-sig") as f:
            stroki = chitat_csv(f.read())

    kol = {"data": a.kol_data, "telefon": a.kol_telefon, "istochnik": a.kol_istochnik,
           "utm": a.kol_utm, "status": a.kol_status, "vizit": a.kol_vizit}
    statusy = {s.strip().lower() for s in a.statusy_zapis.split(",") if s.strip()}
    na_datu = (dt.date.fromisoformat(a.na_datu) if a.na_datu else dt.date.today())

    s = svodka(stroki, kol, na_datu, statusy, sol or "", a.dney)
    print(otchet(s))

    if a.vyhod:
        with open(a.vyhod, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
