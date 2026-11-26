"""Тесты zayavki_svodka.py. Запуск: python -m unittest discover -s scripts/tests

Данные в тестах выдуманные: телефоны вида +7 000 000-00-0N, таких номеров не существует.
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import zayavki_svodka as z  # noqa: E402

SOL = "sol-dlya-testa"
NA_DATU = dt.date(2026, 11, 26)

KOLONKI = {"data": "Дата", "telefon": "Телефон", "istochnik": "Источник",
           "utm": "utm_term", "status": "Этап", "vizit": "Визит"}
STATUSY_ZAPIS = {"записан", "подтверждён"}

VYGRUZKA = (
    "Дата;Телефон;Источник;utm_term;Этап;Визит\n"
    # 2 недели: плитка, записан, пришёл
    "20.11.2026;+7 000 000-00-01;yandex_business;vitrina_03;Записан;да\n"
    # тот же человек, вторая сделка — дубль
    "21.11.2026;8 000 000 00 01;yandex_business;vitrina_03;Новая;нет\n"
    # кнопка записи
    "22.11.2026;+7 000 000-00-02;yandex_maps;knopka_zapisatsya;Подтверждён;нет\n"
    # звонок подменного номера
    "23.11.2026;+7 000 000-00-03;Подменный номер подписки;;Новая;нет\n"
    # не Карты
    "24.11.2026;+7 000 000-00-04;prodoctorov;;Записан;да\n"
    # старше 2 недель, но внутри месяца
    "05.11.2026;+7 000 000-00-05;yandex_maps;vitrina_01;Записан;да\n"
    # старше месяца — не считаем
    "01.09.2026;+7 000 000-00-06;yandex_maps;vitrina_01;Записан;да\n"
    # без даты
    ";+7 000 000-00-07;yandex_maps;vitrina_01;Новая;нет\n"
)


class TestHesh(unittest.TestCase):
    def test_vosmerka_i_semerka_odin_chelovek(self):
        self.assertEqual(z.hesh("+7 000 000-00-01", SOL), z.hesh("8 000 000 00 01", SOL))

    def test_raznye_nomera_raznye_heshi(self):
        self.assertNotEqual(z.hesh("+70000000001", SOL), z.hesh("+70000000002", SOL))

    def test_sol_menyaet_hesh(self):
        self.assertNotEqual(z.hesh("+70000000001", SOL), z.hesh("+70000000001", "другая"))

    def test_pustoy_nomer(self):
        self.assertIsNone(z.hesh("", SOL))
        self.assertIsNone(z.hesh(None, SOL))

    def test_hesh_ne_soderzhit_nomer(self):
        h = z.hesh("+7 000 000-00-01", SOL)
        self.assertNotIn("0000000001", h)
        self.assertEqual(len(h), 64)


class TestDaty(unittest.TestCase):
    def test_formaty(self):
        self.assertEqual(z.razobrat_datu("2026-11-26"), dt.date(2026, 11, 26))
        self.assertEqual(z.razobrat_datu("26.11.2026"), dt.date(2026, 11, 26))
        self.assertEqual(z.razobrat_datu("2026-11-26 14:30:00"), dt.date(2026, 11, 26))
        self.assertEqual(z.razobrat_datu("26.11.2026 14:30"), dt.date(2026, 11, 26))

    def test_musor(self):
        self.assertIsNone(z.razobrat_datu(""))
        self.assertIsNone(z.razobrat_datu("вчера"))


class TestKorzina(unittest.TestCase):
    def test_plitka(self):
        self.assertEqual(z.korzina("yandex_business", "vitrina_03"), "Карты, плитка")

    def test_knopka(self):
        self.assertEqual(z.korzina("yandex_maps", "knopka_zapisatsya"), "Карты, кнопка")

    def test_zvonok(self):
        self.assertEqual(z.korzina("Подменный номер подписки", ""), "Карты, звонок")

    def test_sayt_s_kart(self):
        self.assertEqual(z.korzina("yandex_maps", "card"), "Карты, сайт")

    def test_prochee(self):
        self.assertEqual(z.korzina("prodoctorov", ""), "Прочее")
        self.assertEqual(z.korzina("", ""), "Прочее")


class TestSvodka(unittest.TestCase):
    def setUp(self):
        stroki = z.chitat_csv(VYGRUZKA)
        self.s = z.svodka(stroki, KOLONKI, NA_DATU, STATUSY_ZAPIS, SOL)

    def test_chitat_csv_tochkoy_s_zapyatoy(self):
        self.assertEqual(len(z.chitat_csv(VYGRUZKA)), 8)

    def test_korziny(self):
        k = self.s["po_korzinam"]
        self.assertEqual(k["Карты, плитка"]["zayavki_2n"], 2)
        self.assertEqual(k["Карты, кнопка"]["zayavki_2n"], 1)
        self.assertEqual(k["Карты, звонок"]["zayavki_2n"], 1)
        self.assertEqual(k["Прочее"]["zayavki_2n"], 1)

    def test_mesyac_shire_dvuh_nedel(self):
        k = self.s["po_korzinam"]
        self.assertEqual(k["Карты, плитка"]["zayavki_mes"], 3)

    def test_starshe_mesyaca_ne_schitaem(self):
        self.assertEqual(self.s["itogo"]["zayavki_mes"], 6)

    def test_bez_daty_otdelno(self):
        self.assertEqual(self.s["bez_daty"], 1)

    def test_dubli_po_heshu(self):
        self.assertEqual(self.s["dubli_2n"], 1)

    def test_zapisi_i_vizity(self):
        self.assertEqual(self.s["itogo"]["zapisi_2n"], 3)
        self.assertEqual(self.s["itogo"]["vizity_2n"], 2)
        self.assertEqual(self.s["itogo"]["vizity_mes"], 3)

    def test_po_plitkam(self):
        self.assertEqual(self.s["po_plitkam"]["vitrina_03"]["zayavki_2n"], 2)
        self.assertEqual(self.s["po_plitkam"]["vitrina_01"]["zayavki_2n"], 0)

    def test_otchet_bez_telefonov(self):
        tekst = z.otchet(self.s)
        self.assertNotIn("999", tekst)
        self.assertIn("Карты, плитка", tekst)
        self.assertIn("vitrina_03", tekst)
        self.assertIn("Дублей за 2 недели", tekst)


class TestXlsx(unittest.TestCase):
    def test_chitaet_xlsx_s_obshchimi_strokami(self):
        import tempfile
        import zipfile
        shared = ('<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'
                  'spreadsheetml/2006/main" count="4" uniqueCount="4">'
                  "<si><t>Дата</t></si><si><t>Источник</t></si>"
                  "<si><t>26.11.2026</t></si><si><t>yandex_maps</t></si></sst>")
        sheet = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
                 'spreadsheetml/2006/main"><sheetData>'
                 '<row r="1"><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
                 '<row r="2"><c t="s"><v>2</v></c><c t="s"><v>3</v></c></row>'
                 "</sheetData></worksheet>")
        put = os.path.join(tempfile.mkdtemp(), "vygruzka.xlsx")
        with zipfile.ZipFile(put, "w") as zf:
            zf.writestr("xl/sharedStrings.xml", shared)
            zf.writestr("xl/worksheets/sheet1.xml", sheet)
        stroki = z.chitat_xlsx(put)
        self.assertEqual(stroki, [{"Дата": "26.11.2026", "Источник": "yandex_maps"}])


if __name__ == "__main__":
    unittest.main()
