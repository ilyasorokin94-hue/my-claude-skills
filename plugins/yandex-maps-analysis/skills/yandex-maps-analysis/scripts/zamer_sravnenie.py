#!/usr/bin/env python3
"""Сравнение двух замеров позиций в выдаче Яндекс Карт (модуль 07).

    python3 zamer_sravnenie.py BAZA.csv NOVYY.csv [--csv SVODKA.csv]

Формат CSV описан в moduli/07-zamer-poziciy.md. Старые таблицы с русскими
заголовками (точка, запрос, место, реклама, бесплатное место, первый, всего в
списке) читаются тоже. Без зависимостей, только стандартная библиотека.
"""
import argparse
import csv
import io
import sys

STARYE = {
    "точка": "tochka",
    "запрос": "zapros",
    "место": "_mesto",
    "реклама": "_reklama",
    "бесплатное место": "besplatnoe_mesto",
    "первый": "pervyy",
    "всего в списке": "vsego",
}


def _chislo(v):
    v = (v or "").strip()
    return int(v) if v.isdigit() else None


def _klyuch(s):
    return " ".join((s or "").lower().replace("ё", "е").split())


def normalizuy(stroka):
    """Приводит строку старого или нового формата к новому."""
    r = {}
    for k, v in stroka.items():
        if k is None:
            continue
        k = k.strip().lstrip("﻿").strip()
        r[STARYE.get(k.lower(), k)] = (v or "").strip()
    if "_mesto" in r:  # старый формат: одно место + признак рекламы
        mesto = _chislo(r.pop("_mesto"))
        reklama = r.pop("_reklama", "").lower() == "да"
        r["v_spiske"] = "да" if mesto else "нет"
        r["platnoe_mesto"] = str(mesto) if (mesto and reklama) else ""
        if "besplatnoe_mesto" not in r:
            r["besplatnoe_mesto"] = str(mesto) if (mesto and not reklama) else ""
        r.setdefault("pervyy_platnyy", "да" if "(реклама)" in r.get("pervyy", "") else "")
    if _chislo(r.get("besplatnoe_mesto")) is None:
        r["besplatnoe_mesto"] = ""
    if not r.get("v_spiske"):
        r["v_spiske"] = "да" if (_chislo(r.get("platnoe_mesto")) or _chislo(r.get("besplatnoe_mesto"))) else "нет"
    return r


def prochitay(put):
    with open(put, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    return [normalizuy(s) for s in csv.DictReader(io.StringIO(text))]


def luchshee(r):
    mesta = [m for m in (_chislo(r.get("platnoe_mesto")), _chislo(r.get("besplatnoe_mesto"))) if m]
    return min(mesta) if mesta else None


def schet_tochki(stroki):
    n = len(stroki)
    v_spiske = sum(1 for r in stroki if r.get("v_spiske", "").lower() == "да")
    top3 = sum(1 for r in stroki if (luchshee(r) or 99) <= 3)
    top5 = sum(1 for r in stroki if (luchshee(r) or 99) <= 5)
    bespl = [_chislo(r.get("besplatnoe_mesto")) for r in stroki]
    bespl_top5 = sum(1 for m in bespl if m and m <= 5)
    bespl_vse = sum(1 for m in bespl if m)
    return {"zaprosov": n, "v_spiske": v_spiske, "top3": top3, "top5": top5,
            "bespl_top5": bespl_top5, "bespl_vse": bespl_vse}


def po_tochkam(stroki):
    gruppy = {}
    for r in stroki:
        gruppy.setdefault(_klyuch(r.get("tochka")), []).append(r)
    return gruppy


def _m(v):
    return "нет" if v is None else str(v)


def sravni(baza, novyy):
    gb, gn = po_tochkam(baza), po_tochkam(novyy)
    imena = {}
    for r in baza + novyy:
        imena.setdefault(_klyuch(r.get("tochka")), r.get("tochka", ""))
    itog = []
    for k in list(dict.fromkeys(list(gb) + list(gn))):
        sb = schet_tochki(gb[k]) if k in gb else None
        sn = schet_tochki(gn[k]) if k in gn else None
        sdvigi = []
        if sb and sn:
            zb = {_klyuch(r.get("zapros")): r for r in gb[k]}
            for r in gn[k]:
                rb = zb.get(_klyuch(r.get("zapros")))
                if not rb:
                    continue
                lb, ln = luchshee(rb), luchshee(r)
                bb, bn = _chislo(rb.get("besplatnoe_mesto")), _chislo(r.get("besplatnoe_mesto"))
                if lb != ln or bb != bn:
                    sdvigi.append({"zapros": r.get("zapros", ""), "bylo": lb, "stalo": ln,
                                   "bespl_bylo": bb, "bespl_stalo": bn})
        itog.append({"tochka": imena[k], "baza": sb, "novyy": sn, "sdvigi": sdvigi})
    return itog


def _stroka_scheta(s):
    if not s:
        return "нет замера"
    return (f"в списке {s['v_spiske']}/{s['zaprosov']}, топ-3 {s['top3']}, топ-5 {s['top5']}, "
            f"бесплатно в топ-5 {s['bespl_top5']} (бесплатно всего {s['bespl_vse']})")


def pechat(itog, out=sys.stdout):
    for t in itog:
        print(f"\n## {t['tochka']}", file=out)
        print(f"  было:  {_stroka_scheta(t['baza'])}", file=out)
        print(f"  стало: {_stroka_scheta(t['novyy'])}", file=out)
        for s in t["sdvigi"]:
            b = ""
            if s["bespl_bylo"] != s["bespl_stalo"]:
                b = f"; бесплатно {_m(s['bespl_bylo'])} → {_m(s['bespl_stalo'])}"
            print(f"  - {s['zapros']}: {_m(s['bylo'])} → {_m(s['stalo'])}{b}", file=out)
    print("\nОдин срез случаен: сдвиг в 1–2 места на одной паре не вывод (модуль 07).", file=out)


def zapishi_csv(itog, put):
    polya = ["tochka", "zaprosov", "v_spiske_bylo", "v_spiske_stalo", "top3_bylo", "top3_stalo",
             "top5_bylo", "top5_stalo", "bespl_top5_bylo", "bespl_top5_stalo"]
    with open(put, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=polya)
        w.writeheader()
        for t in itog:
            b, n = t["baza"] or {}, t["novyy"] or {}
            w.writerow({
                "tochka": t["tochka"], "zaprosov": n.get("zaprosov", b.get("zaprosov", "")),
                "v_spiske_bylo": b.get("v_spiske", ""), "v_spiske_stalo": n.get("v_spiske", ""),
                "top3_bylo": b.get("top3", ""), "top3_stalo": n.get("top3", ""),
                "top5_bylo": b.get("top5", ""), "top5_stalo": n.get("top5", ""),
                "bespl_top5_bylo": b.get("bespl_top5", ""), "bespl_top5_stalo": n.get("bespl_top5", ""),
            })


def main(argv=None):
    p = argparse.ArgumentParser(description="Сравнение двух замеров выдачи Карт")
    p.add_argument("baza")
    p.add_argument("novyy")
    p.add_argument("--csv", help="записать сводку по точкам в CSV")
    a = p.parse_args(argv)
    itog = sravni(prochitay(a.baza), prochitay(a.novyy))
    pechat(itog)
    if a.csv:
        zapishi_csv(itog, a.csv)
        print(f"Сводка: {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
