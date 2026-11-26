"""Тесты snimok_razbor.py. Запуск: python -m unittest discover -s scripts/tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import snimok_razbor as s  # noqa: E402

# Выдуманная карточка: никакой клиники за этими данными нет.
KARTOCHKA = {
    "id": "12345678",
    "nazvanie": "Клиника «Пример»",
    "rubriki": ["Стоматологическая клиника", "Детская стоматология"],
    "rubrika_glavnaya": "Стоматологическая клиника",
    "tarif": "Продвинутый",
    "vladelec_podtverzhden": True,
    "horoshee_mesto": 2026,
    "rejting": 4.9,
    "ocenok": 280,
    "otzyvov": 95,
    "foto": {"vsego": 120, "video": 2, "oblozhka": "oblozhka", "pervye": ["a", "b"]},
    "katalog": [
        {"nazvanie": "Чистка зубов", "cena": "от 4 500", "foto": True,
         "razdel": "Гигиена", "populyarnoe": True, "source_url": None},
        {"nazvanie": "Удаление зуба", "cena": None, "foto": False,
         "razdel": "Хирургия", "populyarnoe": False, "source_url": "staryy-sayt"},
        {"nazvanie": "Коронка", "cena": 19300, "foto": False,
         "razdel": "Протезы", "populyarnoe": False, "source_url": None},
    ],
    "plitki": [
        {"nomer": 1, "nazvanie": "Имплант", "cena": 17500, "kartinka": True,
         "ssylka": "https://primer.test/u?utm_term=vitrina_01", "utm_term": "vitrina_01"},
        {"nomer": 2, "nazvanie": "Брекеты", "cena": None, "kartinka": True,
         "ssylka": "https://primer.test/b", "utm_term": None},
    ],
}

SNIMOK = {"snyato": "2026-11-26T06:35", "versiya_skripta": "1.0",
          "nasha": KARTOCHKA, "sosedi": []}


class TestChislo(unittest.TestCase):
    def test_cena_stroka_s_ot(self):
        self.assertEqual(s._chislo("от 4 500 ₽"), 4500)

    def test_cena_chislo(self):
        self.assertEqual(s._chislo(19300), 19300)

    def test_net_ceny(self):
        self.assertIsNone(s._chislo(None))
        self.assertIsNone(s._chislo(""))
        self.assertIsNone(s._chislo("по запросу"))

    def test_logicheskoe_ne_cena(self):
        # True не должен превратиться в цену 1: это поле «фото», а не «цена».
        self.assertIsNone(s._chislo(True))


class TestSchetchiki(unittest.TestCase):
    def setUp(self):
        self.sch = s.schetchiki(s.normalizovat(KARTOCHKA))

    def test_katalog(self):
        self.assertEqual(self.sch["poziciy_kataloga"], 3)
        self.assertEqual(self.sch["poziciy_bez_foto"], 2)
        self.assertEqual(self.sch["poziciy_bez_ceny"], 1)

    def test_plitki(self):
        self.assertEqual(self.sch["plitok_vsego"], 2)
        self.assertEqual(self.sch["plitok_bez_ceny"], 1)
        self.assertEqual(self.sch["plitok_s_cenoy"], 1)

    def test_tarif_i_foto(self):
        self.assertEqual(self.sch["tarif_kartochki"], "Продвинутый")
        self.assertEqual(self.sch["foto"], 120)

    def test_pustoy_katalog_daet_pusto_a_ne_nol(self):
        sch = s.schetchiki(s.normalizovat({"nazvanie": "X"}))
        self.assertIsNone(sch["poziciy_kataloga"])
        self.assertNotIn("poziciy_bez_ceny", sch)

    def test_sravnenie_s_kabinetom(self):
        sch = s.schetchiki(s.normalizovat(KARTOCHKA), kabinet_poziciy=2)
        self.assertEqual(sch["poziciy_publichno_vs_kabinet"], "3/2")


class TestFlagi(unittest.TestCase):
    def test_plitka_bez_metki(self):
        self.assertEqual(s.plitki_bez_metki(KARTOCHKA), [2])

    def test_pozicii_ot_yandeksa(self):
        self.assertEqual(s.pozicii_yandeksa(KARTOCHKA), ["Удаление зуба"])


class TestNormalizovat(unittest.TestCase):
    def test_nehvatka_polya_popadaet_v_oshibki(self):
        k = s.normalizovat({"nazvanie": "X", "rubriki": ["Y"]})
        self.assertTrue(any("rejting" in o for o in k["oshibki"]))
        self.assertEqual(k["katalog"], [])

    def test_polnaya_kartochka_bez_oshibok(self):
        self.assertEqual(s.normalizovat(KARTOCHKA)["oshibki"], [])


class TestSvodka(unittest.TestCase):
    def test_svodka_soderzhit_kolonki_i_flagi(self):
        tekst = s.svodka(SNIMOK)
        self.assertIn("Колонки snimki.csv:", tekst)
        self.assertIn("plitok_vsego=2", tekst)
        self.assertIn("Плитки без", tekst)

    def test_sosedi_v_svodke(self):
        snimok = dict(SNIMOK, sosedi=[{"id": "999", "nazvanie": "Сосед",
                                       "rejting": 4.7, "ocenok": 500}])
        self.assertIn("Сосед", s.svodka(snimok))


if __name__ == "__main__":
    unittest.main()
