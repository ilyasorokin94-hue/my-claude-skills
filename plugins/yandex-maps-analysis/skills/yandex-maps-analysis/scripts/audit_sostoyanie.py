#!/usr/bin/env python3
"""Какая клиника сегодня и с какого блока продолжать (модуль 08).

Отвечает на три вопроса обхода аудита: неделя А или Б, какая клиника на этот
день, и если прошлый запуск оборвался — с какого блока его продолжать.

Запуск:

    python3 audit_sostoyanie.py --spisok spisok-klinik.md --tmp tmp/sostoyanie.json
    python3 audit_sostoyanie.py --tmp tmp/sostoyanie.json --otmetit-blok 3
    python3 audit_sostoyanie.py --tmp tmp/sostoyanie.json --propustit 5 "подписки нет"
    python3 audit_sostoyanie.py --tmp tmp/sostoyanie.json --zakryt

Список клиник лежит на ПК агентства и в публичный репозиторий не попадает:
скрипт только читает его таблицу. Нужные колонки: код, неделя, день, статус;
путь к базе — любая колонка со словом «папка» или «путь». Дату начала недели А
скрипт берёт из строки «Неделя А с: ГГГГ-ММ-ДД» того же файла.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys

DNI = ("pn", "vt", "sr", "cht", "pt", "sb", "vs")
DNI_RU = {"пн": "pn", "вт": "vt", "ср": "sr", "чт": "cht", "чет": "cht",
          "пт": "pt", "сб": "sb", "вс": "vs"}
BLOKOV_VSEGO = 16  # блоки 0–15 модуля 01


def den_kod(data):
    return DNI[data.weekday()]


def nedelya_po_date(nedelya_a_s, data):
    """Недели чередуются от якорной даты: чётное число недель — А, иначе Б."""
    nachalo_a = nedelya_a_s - dt.timedelta(days=nedelya_a_s.weekday())
    nachalo = data - dt.timedelta(days=data.weekday())
    nedel = (nachalo - nachalo_a).days // 7
    return "А" if nedel % 2 == 0 else "Б"


def razobrat_spisok(tekst):
    """Таблица клиник из markdown. Возвращает (строки, дата начала недели А)."""
    nedelya_a_s = None
    m = re.search(r"Неделя\s+А\s+с\s*:\s*(\d{4}-\d{2}-\d{2})", tekst)
    if m:
        nedelya_a_s = dt.date.fromisoformat(m.group(1))

    zagolovki, stroki = None, []
    for stroka in tekst.splitlines():
        s = stroka.strip()
        if not s.startswith("|"):
            continue
        kletki = [k.strip() for k in s.strip("|").split("|")]
        if set("".join(kletki)) <= set("-: "):
            continue  # строка-разделитель
        if zagolovki is None:
            zagolovki = [k.lower() for k in kletki]
            continue
        stroki.append(dict(zip(zagolovki, kletki)))
    return stroki, nedelya_a_s


def _pole(stroka, *slova):
    for imya, znachenie in stroka.items():
        if any(s in imya for s in slova):
            return znachenie
    return ""


def vybrat_kliniku(stroki, nedelya, den):
    """Клиника этого дня. Пауза и пустой код — не берём."""
    for s in stroki:
        status = _pole(s, "статус").lower()
        if "пауза" in status:
            continue
        if _pole(s, "недел").strip().upper() not in (nedelya, nedelya.upper()):
            continue
        den_stroki = _pole(s, "день").strip().lower()
        if DNI_RU.get(den_stroki[:3], DNI_RU.get(den_stroki[:2], den_stroki)) != den:
            continue
        kod = _pole(s, "код") or _pole(s, "папка", "путь")
        if not kod:
            continue
        return s
    return None


def prochitat_sostoyanie(put):
    if not put or not os.path.exists(put):
        return None
    with open(put, encoding="utf-8") as f:
        return json.load(f)


def zapisat_sostoyanie(put, sostoyanie):
    os.makedirs(os.path.dirname(os.path.abspath(put)), exist_ok=True)
    with open(put, "w", encoding="utf-8") as f:
        json.dump(sostoyanie, f, ensure_ascii=False, indent=2)


def prodolzhit_s_bloka(sostoyanie):
    """Первый блок, который ещё не пройден и не пропущен."""
    if not sostoyanie:
        return 0
    proydeny = set(sostoyanie.get("bloki_proydeny") or [])
    propushcheny = {int(k) for k in (sostoyanie.get("bloki_propushcheny") or {})}
    for n in range(sostoyanie.get("blokov_vsego") or BLOKOV_VSEGO):
        if n not in proydeny and n not in propushcheny:
            return n
    return None


def novoe_sostoyanie(klinika, nedelya, den, data, versiya):
    return {
        "data": data.isoformat(),
        "nedelya": nedelya,
        "den": den,
        "klinika": klinika,
        "versiya_skilla": versiya,
        "blokov_vsego": BLOKOV_VSEGO,
        "bloki_proydeny": [],
        "bloki_propushcheny": {},
        "prichina_ostanovki": None,
        "nachato": dt.datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "proverok_sdelano": 0,
        "proverok_vsego": 2,
    }


def main():
    # На Windows консоль бывает в cp1251, и вывод с «→» падает на кодировке.
    for potok in (sys.stdout, sys.stderr):
        try:
            potok.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spisok", help="список клиник аудита (markdown с таблицей)")
    p.add_argument("--tmp", help="файл состояния, обычно tmp/sostoyanie.json")
    p.add_argument("--na-datu", help="дата запуска, ГГГГ-ММ-ДД (по умолчанию сегодня)")
    p.add_argument("--nedelya-a-s", help="понедельник недели А, если его нет в списке")
    p.add_argument("--versiya", default="", help="версия скилла для записи в состояние")
    p.add_argument("--otmetit-blok", type=int, help="блок пройден")
    p.add_argument("--propustit", nargs=2, metavar=("БЛОК", "ПРИЧИНА"),
                   help="блок пропущен, с причиной")
    p.add_argument("--ostanovka", help="записать причину остановки")
    p.add_argument("--zakryt", action="store_true",
                   help="запуск закончен: удалить файл состояния")
    a = p.parse_args()

    data = dt.date.fromisoformat(a.na_datu) if a.na_datu else dt.date.today()
    sostoyanie = prochitat_sostoyanie(a.tmp)

    if a.zakryt:
        if a.tmp and os.path.exists(a.tmp):
            os.remove(a.tmp)
            print("Состояние удалено: запуск закончен.")
        else:
            print("Файла состояния нет, удалять нечего.")
        return

    if a.otmetit_blok is not None or a.propustit or a.ostanovka:
        if not sostoyanie:
            sys.exit("Нет файла состояния: сначала запусти без отметок.")
        if a.otmetit_blok is not None:
            proydeny = sostoyanie.setdefault("bloki_proydeny", [])
            if a.otmetit_blok not in proydeny:
                proydeny.append(a.otmetit_blok)
        if a.propustit:
            sostoyanie.setdefault("bloki_propushcheny", {})[str(int(a.propustit[0]))] = \
                a.propustit[1]
        if a.ostanovka:
            sostoyanie["prichina_ostanovki"] = a.ostanovka
        zapisat_sostoyanie(a.tmp, sostoyanie)
        print("Состояние обновлено. Продолжать с блока: %s" %
              prodolzhit_s_bloka(sostoyanie))
        return

    # Прерванный запуск продолжаем, а не начинаем заново.
    if sostoyanie and sostoyanie.get("data") == data.isoformat():
        blok = prodolzhit_s_bloka(sostoyanie)
        print("Продолжаем прерванный запуск.")
        print("klinika=%s; nedelya=%s; den=%s; prodolzhit_s_bloka=%s" % (
            sostoyanie.get("klinika"), sostoyanie.get("nedelya"),
            sostoyanie.get("den"), blok))
        return

    if not a.spisok:
        sys.exit("Нет файла состояния на сегодня и не задан --spisok: "
                 "какую клинику брать, непонятно.")

    with open(a.spisok, encoding="utf-8") as f:
        stroki, nedelya_a_s = razobrat_spisok(f.read())
    if a.nedelya_a_s:
        nedelya_a_s = dt.date.fromisoformat(a.nedelya_a_s)
    if not nedelya_a_s:
        sys.exit("Не нашёл дату начала недели А: добавь в список строку "
                 "«Неделя А с: ГГГГ-ММ-ДД» или передай --nedelya-a-s.")

    nedelya, den = nedelya_po_date(nedelya_a_s, data), den_kod(data)
    stroka = vybrat_kliniku(stroki, nedelya, den)
    if not stroka:
        print("Неделя %s, день %s: клиники на сегодня нет. Тихий выход, "
              "строка в журнал запусков." % (nedelya, den))
        print("klinika=; nedelya=%s; den=%s" % (nedelya, den))
        return

    kod = _pole(stroka, "код") or _pole(stroka, "папка", "путь")
    if a.tmp:
        zapisat_sostoyanie(a.tmp, novoe_sostoyanie(kod, nedelya, den, data, a.versiya))
    print("Неделя %s, день %s. Клиника: %s" % (nedelya, den, kod))
    print("klinika=%s; put=%s; nedelya=%s; den=%s; prodolzhit_s_bloka=0" % (
        kod, _pole(stroka, "папка", "путь"), nedelya, den))


if __name__ == "__main__":
    main()
