"""Тесты sravnit_snimki.py. Запуск: python -m unittest discover -s scripts/tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sravnit_snimki as s  # noqa: E402

# Выдуманные снимки одной карточки с разницей в 2 недели.
STARAYA = {
    "nazvanie": "Клиника «Пример»",
    "rubrika_glavnaya": "Стоматологическая клиника",
    "rubriki": ["Стоматологическая клиника", "Стоматологическая поликлиника"],
    "osobennosti": ["Парковка", "Оплата картой"],
    "tarif": "Базовый",
    "rejting": 4.8,
    "ocenok": 270,
    "foto": {"vsego": 110},
    "katalog": [
        {"nazvanie": "Чистка зубов", "cena": 4500, "foto": True, "razdel": "Гигиена"},
        {"nazvanie": "Удаление зуба", "cena": 3000, "foto": False, "razdel": "Хирургия"},
    ],
    "plitki": [
        {"nomer": 1, "nazvanie": "Имплант", "cena": None, "utm_term": "vitrina_01"},
    ],
}
NOVAYA = {
    "nazvanie": "Клиника «Пример»",
    "rubrika_glavnaya": "Стоматологическая клиника",
    "rubriki": ["Стоматологическая клиника", "Детская стоматология"],
    "osobennosti": ["Парковка", "Оплата картой", "Доступно для детей"],
    "tarif": "Продвинутый",
    "rejting": 4.9,
    "ocenok": 281,
    "foto": {"vsego": 124},
    "katalog": [
        {"nazvanie": "Чистка зубов", "cena": 4900, "foto": True, "razdel": "Гигиена"},
        {"nazvanie": "Коронка", "cena": 19300, "foto": True, "razdel": "Протезы"},
    ],
    "plitki": [
        {"nomer": 1, "nazvanie": "Имплант", "cena": 17500, "utm_term": "vitrina_01"},
    ],
}
STARYY = {"snyato": "2026-11-12T06:30", "nasha": STARAYA}
NOVYY = {"snyato": "2026-11-26T06:35", "nasha": NOVAYA}


class TestPolya(unittest.TestCase):
    def test_izmenilsya_tarif_i_rejting(self):
        izm = dict((imya, (bylo, stalo)) for imya, bylo, stalo
                   in s.sravnit_polya(STARAYA, NOVAYA))
        self.assertEqual(izm["тариф"], ("Базовый", "Продвинутый"))
        self.assertEqual(izm["рейтинг"], (4.8, 4.9))
        self.assertNotIn("название", izm)

    def test_odinakovye_kartochki_bez_izmeneniy(self):
        self.assertEqual(s.sravnit_polya(STARAYA, STARAYA), [])


class TestNabory(unittest.TestCase):
    def test_rubriki(self):
        dob, prop = s.sravnit_nabor(STARAYA, NOVAYA, "rubriki")
        self.assertEqual(dob, ["Детская стоматология"])
        self.assertEqual(prop, ["Стоматологическая поликлиника"])

    def test_osobennosti_tolko_dobavilis(self):
        dob, prop = s.sravnit_nabor(STARAYA, NOVAYA, "osobennosti")
        self.assertEqual(dob, ["Доступно для детей"])
        self.assertEqual(prop, [])


class TestPozicii(unittest.TestCase):
    def test_katalog(self):
        dob, prop, izm = s.sravnit_pozicii(STARAYA, NOVAYA, "katalog")
        self.assertEqual(dob, ["Коронка"])
        self.assertEqual(prop, ["Удаление зуба"])
        self.assertEqual(izm, [("Чистка зубов", "цена", 4500, 4900)])

    def test_plitka_poluchila_cenu(self):
        dob, prop, izm = s.sravnit_pozicii(STARAYA, NOVAYA, "plitki")
        self.assertEqual((dob, prop), ([], []))
        self.assertEqual(izm, [("Имплант", "цена", None, 17500)])

    def test_pustye_snimki_ne_padayut(self):
        self.assertEqual(s.sravnit_pozicii({}, {}, "katalog"), ([], [], []))


class TestSchetchiki(unittest.TestCase):
    def test_foto_novyh(self):
        self.assertEqual(s.schetchiki(STARAYA, NOVAYA)["foto_novyh_2n"], 14)

    def test_bez_chisla_foto_net_kolonki(self):
        self.assertEqual(s.schetchiki({"foto": {}}, NOVAYA), {})


class TestOtchet(unittest.TestCase):
    def test_otchet_pokazyvaet_glavnoe(self):
        tekst = s.otchet(STARYY, NOVYY)
        self.assertIn("Продвинутый", tekst)
        self.assertIn("Коронка", tekst)
        self.assertIn("Детская стоматология", tekst)
        self.assertIn("foto_novyh_2n=14", tekst)

    def test_otchet_na_odinakovyh_snimkah(self):
        tekst = s.otchet(STARYY, STARYY)
        self.assertIn("Без изменений.", tekst)


if __name__ == "__main__":
    unittest.main()
