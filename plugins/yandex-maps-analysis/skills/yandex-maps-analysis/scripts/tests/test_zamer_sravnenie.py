"""Тесты zamer_sravnenie.py. Запуск: python -m unittest discover -s scripts/tests"""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import zamer_sravnenie as z  # noqa: E402

STARYY = (
    "﻿точка,запрос,место,реклама,первый,всего в списке\n"
    "У двери,стоматология,1,да,Клиника (реклама),14\n"
    "У двери,брекеты,4,,Сосед,12\n"
    "Город,стоматология,нет,,Сосед (реклама),25\n"
)
STARYY_KOLCO = (
    "точка,запрос,место,реклама,бесплатное место,первый,всего в списке\n"
    "Кольцо,стоматология,6,да,нет,Сосед,10\n"
)
NOVYY = (
    "data,vremya,tochka,lat,lon,zapros,v_spiske,platnoe_mesto,besplatnoe_mesto,pervyy,pervyy_platnyy,vsego,podstavleno,primechanie\n"
    "22.11.2026,11:00,У двери,0,0,стоматология,да,1,3,Клиника,да,14,,\n"
    "22.11.2026,11:00,у двери,0,0,Брекеты,да,,2,Сосед,,12,,\n"
    "22.11.2026,11:00,Город,0,0,стоматология,да,2,,Сосед,да,25,,\n"
    "22.11.2026,11:00,Кольцо,0,0,стоматология,да,4,,Сосед,,10,,\n"
)


def _fayl(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return f.name


class TestNormalizaciya(unittest.TestCase):
    def test_staryy_format(self):
        r = z.prochitay(_fayl(STARYY))
        self.assertEqual(r[0]["tochka"], "У двери")
        self.assertEqual(r[0]["platnoe_mesto"], "1")
        self.assertEqual(r[0]["besplatnoe_mesto"], "")
        self.assertEqual(r[0]["pervyy_platnyy"], "да")
        self.assertEqual(r[1]["besplatnoe_mesto"], "4")
        self.assertEqual(r[2]["v_spiske"], "нет")

    def test_staryy_kolco_bespl_net(self):
        r = z.prochitay(_fayl(STARYY_KOLCO))[0]
        self.assertEqual(r["platnoe_mesto"], "6")
        self.assertEqual(r["besplatnoe_mesto"], "")


class TestSravnenie(unittest.TestCase):
    def setUp(self):
        baza = z.prochitay(_fayl(STARYY)) + z.prochitay(_fayl(STARYY_KOLCO))
        self.itog = {t["tochka"].lower(): t for t in z.sravni(baza, z.prochitay(_fayl(NOVYY)))}

    def test_schet(self):
        d = self.itog["у двери"]
        self.assertEqual(d["baza"]["top3"], 1)
        self.assertEqual(d["novyy"]["top3"], 2)
        self.assertEqual(d["novyy"]["bespl_top5"], 2)

    def test_sdvigi_registr_i_bespl(self):
        sd = {s["zapros"].lower(): s for s in self.itog["у двери"]["sdvigi"]}
        self.assertEqual(sd["брекеты"]["bylo"], 4)
        self.assertEqual(sd["брекеты"]["stalo"], 2)
        self.assertEqual(sd["стоматология"]["bespl_stalo"], 3)

    def test_poyavilis_v_gorode(self):
        g = self.itog["город"]
        self.assertEqual(g["baza"]["v_spiske"], 0)
        self.assertEqual(g["novyy"]["v_spiske"], 1)

    def test_pechat_i_csv(self):
        out = io.StringIO()
        z.pechat(list(self.itog.values()), out)
        self.assertIn("брекеты: 4 → 2", out.getvalue().lower())
        put = tempfile.mktemp(suffix=".csv")
        z.zapishi_csv(list(self.itog.values()), put)
        with open(put, encoding="utf-8") as f:
            self.assertIn("top5_stalo", f.readline())


if __name__ == "__main__":
    unittest.main()
