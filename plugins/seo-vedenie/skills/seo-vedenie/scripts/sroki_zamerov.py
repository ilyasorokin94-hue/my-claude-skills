#!/usr/bin/env python3
"""Сроки замеров по журналу правок клиники.

Читает seo/zhurnal-pravok.md (формат: shablony/zhurnal-pravok.md) и
показывает, какие правки ждут выкладки, у каких наступили D+14, D+28 и D+56,
какие замеры ещё не вписаны и с какой даты страница открыта для новых правок.

Отсчёт замера (компас 1, «Как правки и замер живут вместе»): от даты «Робот
увидел», но не позже 14-го дня после выкладки. Страница открыта через 28 дней
от начала отсчёта, то есть не позже чем через 42 дня после выкладки.

Примеры:
  python sroki_zamerov.py путь/к/базе/seo/zhurnal-pravok.md
  python sroki_zamerov.py zhurnal-pravok.md --segodnya 2026-12-15
"""
import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ZAMERY = (14, 28, 56)
ZHDAT_ROBOTA = 14   # дней после выкладки, после которых отсчёт идёт без робота
OTKRYTA_CHEREZ = 28  # дней от начала отсчёта до открытия страницы
DATA = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
ZAGOLOVOK = re.compile(r"^###\s+(П-\d+)\s*·\s*(.*)$")
POLE = re.compile(r"^([^:\n]{1,40}):\s*(.*)$")


def data_iz(tekst):
    m = DATA.search(tekst or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def vse_daty(tekst):
    daty = []
    for m in DATA.finditer(tekst or ""):
        try:
            daty.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    return daty


def nachalo_otscheta(vylozheno, robot):
    """Начало замера: «робот увидел» (последний поисковик), но не позже выкладки + 14 дней."""
    predel = vylozheno + timedelta(days=ZHDAT_ROBOTA)
    if robot:
        return min(max(robot), predel)
    return predel


def razobrat(tekst):
    """Текст журнала -> список правок (словари)."""
    pravki, tekushchaya, v_kode = [], None, False
    for stroka in tekst.splitlines():
        if stroka.strip().startswith("```"):
            v_kode = not v_kode
            continue
        if v_kode:
            continue
        m = ZAGOLOVOK.match(stroka)
        if m:
            tekushchaya = {"nomer": m.group(1), "nazvanie": m.group(2).strip(), "polya": {}}
            pravki.append(tekushchaya)
            continue
        if stroka.startswith("#"):
            tekushchaya = None
            continue
        if tekushchaya is not None:
            m = POLE.match(stroka)
            if m:
                tekushchaya["polya"][m.group(1).strip()] = m.group(2).strip()
    return pravki


def sostoyanie(pravka, segodnya):
    """Правка -> словарь для печати: статус, выложено, отметки по замерам."""
    p = pravka["polya"]
    status = p.get("Статус", "")
    itog = p.get("Итог", "")
    vylozheno = data_iz(p.get("Выложено", ""))
    s = {
        "nomer": pravka["nomer"],
        "nazvanie": pravka["nazvanie"],
        "status": status,
        "vylozheno": vylozheno,
        "zakryta": status.lower().startswith("закрыта") or bool(itog and "рано" not in itog.lower()),
        "zhdet_dney": None,
        "zamery": {},
        "pora": [],
        "nachalo": None,
        "robot_vidyel": False,
        "otkryta_s": None,
    }
    if vylozheno is None:
        s_tz = data_iz(status)
        if s_tz and "тз" in status.lower():
            s["zhdet_dney"] = (segodnya - s_tz).days
        return s
    robot = [d for d in vse_daty(p.get("Робот увидел", "")) if d >= vylozheno]
    s["robot_vidyel"] = bool(robot)
    s["nachalo"] = nachalo_otscheta(vylozheno, robot)
    s["otkryta_s"] = s["nachalo"] + timedelta(days=OTKRYTA_CHEREZ)
    for d in ZAMERY:
        srok = s["nachalo"] + timedelta(days=d)
        vpisan = bool(p.get("D+%d" % d, "").strip())
        if vpisan:
            otmetka = "снят"
        elif srok <= segodnya:
            otmetka = "пора (срок %s)" % srok.isoformat()
            if not s["zakryta"]:
                s["pora"].append(d)
        else:
            otmetka = "через %d дн. (%s)" % ((srok - segodnya).days, srok.isoformat())
        s["zamery"][d] = otmetka
    return s


def main(argv=None):
    for potok in (sys.stdout, sys.stderr):
        try:
            potok.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Сроки замеров по журналу правок.")
    ap.add_argument("zhurnal", help="путь к seo/zhurnal-pravok.md")
    ap.add_argument("--segodnya", help="дата разбора ГГГГ-ММ-ДД (по умолчанию сегодня)")
    a = ap.parse_args(argv)

    segodnya = data_iz(a.segodnya) if a.segodnya else date.today()
    if segodnya is None:
        ap.error("--segodnya: нужна дата ГГГГ-ММ-ДД")
    pravki = razobrat(Path(a.zhurnal).read_text(encoding="utf-8"))
    if not pravki:
        print("В журнале нет правок (блоков «### П-N · …»).")
        return 0

    sost = [sostoyanie(p, segodnya) for p in pravki]
    otkrytye = [s for s in sost if not s["zakryta"]]
    print("Дата: %s. Правок: %d, открытых: %d." % (segodnya.isoformat(), len(sost), len(otkrytye)))

    pora = [s for s in otkrytye if s["pora"]]
    print("\nПора снять замер: %d" % len(pora))
    for s in pora:
        print("  %s · %s | выложено %s | %s" % (
            s["nomer"], s["nazvanie"], s["vylozheno"].isoformat(),
            ", ".join("D+%d" % d for d in s["pora"])))

    zhdut = [s for s in otkrytye if s["vylozheno"] is None]
    print("\nЖдут выкладки: %d" % len(zhdut))
    for s in zhdut:
        skolko = "%d дн." % s["zhdet_dney"] if s["zhdet_dney"] is not None else "срок неизвестен"
        print("  %s · %s | %s | ждёт %s" % (s["nomer"], s["nazvanie"], s["status"] or "нет статуса", skolko))

    vperedi = [s for s in otkrytye if s["vylozheno"] is not None and not s["pora"]]
    print("\nВыложены, замер впереди: %d" % len(vperedi))
    for s in vperedi:
        print("  %s · %s | выложено %s | отсчёт с %s%s | %s" % (
            s["nomer"], s["nazvanie"], s["vylozheno"].isoformat(), s["nachalo"].isoformat(),
            "" if s["robot_vidyel"] else " (робот не отмечен)",
            "; ".join("D+%d %s" % (d, s["zamery"][d]) for d in ZAMERY)))

    bez_robota = [s for s in otkrytye if s["vylozheno"] is not None and not s["robot_vidyel"]]
    if bez_robota:
        print("\nРобот не отмечен (проверить индекс, IndexNow, переобход): %d" % len(bez_robota))
        for s in bez_robota:
            print("  %s · %s | выложено %s" % (s["nomer"], s["nazvanie"], s["vylozheno"].isoformat()))

    na_zamere = {}
    v_tz = set()
    for s in otkrytye:
        stranica = s["nazvanie"].split("·")[0].strip()
        if s["vylozheno"] is None:
            v_tz.add(stranica)
        elif s["otkryta_s"] > segodnya:
            na_zamere[stranica] = max(na_zamere.get(stranica, s["otkryta_s"]), s["otkryta_s"])
    if na_zamere:
        print("\nСтраницы на замере (до даты только ремонт; в списке «Как поднять позиции» правка с датой «не раньше»):")
        for stranica in sorted(na_zamere):
            print("  %s | открыта с %s" % (stranica, na_zamere[stranica].isoformat()))
    if v_tz:
        print("\nСтраницы с правкой в ТЗ, ждут выкладки (новое на них не дублируем):")
        for stranica in sorted(v_tz):
            print("  " + stranica)
    return 0


if __name__ == "__main__":
    sys.exit(main())
