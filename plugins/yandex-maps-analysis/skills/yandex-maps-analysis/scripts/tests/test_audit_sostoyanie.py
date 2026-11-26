"""Тесты audit_sostoyanie.py. Запуск: python -m unittest discover -s scripts/tests"""
import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import audit_sostoyanie as a  # noqa: E402

# Выдуманный список: клиники обозначены буквами, как в обезличенной базе.
SPISOK = """# Клиники аудита Карт
Обновлён: 26.11.2026
Неделя А с: 2026-11-23

| № | Клиника | Код | Папка базы | Неделя | День | Статус |
|---|---|---|---|---|---|---|
| 1 | Клиника А | a-baza | clients\\a-baza | А | пн | в работе |
| 2 | Клиника Б | b-baza | clients\\b-baza | А | ср | в работе |
| 3 | Клиника В | v-baza | clients\\v-baza | А | пт | пауза |
| 4 | Клиника Г | g-baza | clients\\g-baza | Б | пн | в работе |
"""


class TestKalendar(unittest.TestCase):
    def test_nedelya_a_i_b_cheredueutsya(self):
        a_s = dt.date(2026, 11, 23)
        self.assertEqual(a.nedelya_po_date(a_s, dt.date(2026, 11, 23)), "А")
        self.assertEqual(a.nedelya_po_date(a_s, dt.date(2026, 11, 27)), "А")
        self.assertEqual(a.nedelya_po_date(a_s, dt.date(2026, 11, 30)), "Б")
        self.assertEqual(a.nedelya_po_date(a_s, dt.date(2026, 12, 7)), "А")

    def test_nedelya_schitaetsya_i_nazad(self):
        a_s = dt.date(2026, 11, 23)
        self.assertEqual(a.nedelya_po_date(a_s, dt.date(2026, 11, 16)), "Б")

    def test_yakor_v_seredine_nedeli_ne_lomaet_schet(self):
        # Якорь — четверг той же недели А: ответ не меняется.
        self.assertEqual(a.nedelya_po_date(dt.date(2026, 11, 26), dt.date(2026, 11, 23)), "А")

    def test_den_kod(self):
        self.assertEqual(a.den_kod(dt.date(2026, 11, 23)), "pn")
        self.assertEqual(a.den_kod(dt.date(2026, 11, 27)), "pt")


class TestSpisok(unittest.TestCase):
    def setUp(self):
        self.stroki, self.nedelya_a_s = a.razobrat_spisok(SPISOK)

    def test_data_nedeli_a(self):
        self.assertEqual(self.nedelya_a_s, dt.date(2026, 11, 23))

    def test_chetyre_stroki_bez_razdelitelya(self):
        self.assertEqual(len(self.stroki), 4)

    def test_vybor_kliniki(self):
        s = a.vybrat_kliniku(self.stroki, "А", "pn")
        self.assertEqual(a._pole(s, "код"), "a-baza")

    def test_pauza_propuskaetsya(self):
        self.assertIsNone(a.vybrat_kliniku(self.stroki, "А", "pt"))

    def test_net_kliniki_na_den(self):
        self.assertIsNone(a.vybrat_kliniku(self.stroki, "Б", "sr"))

    def test_drugaya_nedelya(self):
        s = a.vybrat_kliniku(self.stroki, "Б", "pn")
        self.assertEqual(a._pole(s, "код"), "g-baza")


class TestSostoyanie(unittest.TestCase):
    def setUp(self):
        self.put = os.path.join(tempfile.mkdtemp(), "tmp", "sostoyanie.json")

    def test_zapis_i_chtenie(self):
        s = a.novoe_sostoyanie("a-baza", "А", "pn", dt.date(2026, 11, 23), "4.0.0")
        a.zapisat_sostoyanie(self.put, s)
        self.assertEqual(a.prochitat_sostoyanie(self.put)["klinika"], "a-baza")

    def test_net_fayla(self):
        self.assertIsNone(a.prochitat_sostoyanie(self.put))

    def test_prodolzhit_s_pervogo_neproydennogo(self):
        s = a.novoe_sostoyanie("a-baza", "А", "pn", dt.date(2026, 11, 23), "4.0.0")
        s["bloki_proydeny"] = [0, 1, 2]
        self.assertEqual(a.prodolzhit_s_bloka(s), 3)

    def test_propushchennyy_blok_ne_derzhit_obhod(self):
        s = a.novoe_sostoyanie("a-baza", "А", "pn", dt.date(2026, 11, 23), "4.0.0")
        s["bloki_proydeny"] = [0, 1, 2, 4]
        s["bloki_propushcheny"] = {"3": "подписки нет"}
        self.assertEqual(a.prodolzhit_s_bloka(s), 5)

    def test_vse_bloki_proydeny(self):
        s = a.novoe_sostoyanie("a-baza", "А", "pn", dt.date(2026, 11, 23), "4.0.0")
        s["bloki_proydeny"] = list(range(s["blokov_vsego"]))
        self.assertIsNone(a.prodolzhit_s_bloka(s))

    def test_bez_sostoyaniya_nachinaem_s_nulya(self):
        self.assertEqual(a.prodolzhit_s_bloka(None), 0)


if __name__ == "__main__":
    unittest.main()
