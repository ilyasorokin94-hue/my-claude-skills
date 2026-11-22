"""Тесты без сети: python -m unittest discover -s scripts/tests"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sroki_zamerov  # noqa: E402
import sverka_stranic  # noqa: E402

HTML = """<!doctype html><html><head>
<meta charset="utf-8">
<title>  Брекеты в Городе
 от 100 руб </title>
<meta name="Description" content="Ставим брекеты. Консультация ортодонта.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="/services/brekety/">
<script>var title = "<h1>не считать</h1>";</script>
</head><body>
<h1>Брекеты <span>в Городе</span></h1>
<style>.a{color:red}</style>
<p>Три слова тут.</p>
</body></html>"""

ZHURNAL = """# Журнал правок

```
### П-99 · /shablon/ · пример в рамке не считается
Выложено: 2026-01-01
```

### П-1 · /services/a/ · цены на странице
Статус: выложена
Выложено: 2026-12-01 (отметка проекта)
D+14: 2026-12-15, робот был, всё на месте
D+28:
D+56:
Итог:

### П-2 · /services/b/ · новый заголовок
Статус: в ТЗ с 2026-12-01
Выложено:
Итог:

### П-3 · /services/c/ · ссылки из прайса
Статус: закрыта
Выложено: не позже 2026-10-01
D+14: снят
D+28: снят
D+56: снят
Итог: сбылось
"""


class Sverka(unittest.TestCase):
    def test_razbor_html(self):
        s = sverka_stranic.razobrat_html(HTML)
        self.assertEqual(s["title"], "Брекеты в Городе от 100 руб")
        self.assertEqual(s["description"], "Ставим брекеты. Консультация ортодонта.")
        self.assertEqual(s["h1_shtuk"], 1)
        self.assertEqual(s["h1"], "Брекеты в Городе")
        self.assertEqual(s["canonical"], "/services/brekety/")
        self.assertIn("index, follow", s["robots"])
        self.assertEqual(s["slov"], 6)  # H1 (3 слова) + абзац (3 слова), без script и style

    def test_normalizaciya_kirillicy(self):
        url = sverka_stranic.normalizovat("пример.рф/услуги/")
        self.assertTrue(url.startswith("https://xn--"))
        self.assertIn("%D1%83", url)

    def test_zamechaniya(self):
        s = dict.fromkeys(sverka_stranic.POLYA, "")
        s.update(sverka_stranic.razobrat_html("<html><body><h1>А</h1><h1>Б</h1></body></html>"))
        s.update({"itog_url": "https://example.ru/", "redirektov": 0, "kod": 200})
        z = sverka_stranic.zamechaniya(s, 200)
        self.assertIn("нет title", z)
        self.assertIn("нет description", z)
        self.assertIn("H1: 2", z)
        self.assertIn("нет canonical", z)

    def test_noindex_i_chuzhoy_canonical(self):
        s = dict.fromkeys(sverka_stranic.POLYA, "")
        s.update(sverka_stranic.razobrat_html(
            '<html><head><title>Т</title><meta name="description" content="О">'
            '<meta name="robots" content="noindex"><link rel="canonical" href="https://example.ru/drugaya/">'
            "</head><body><h1>А</h1></body></html>"))
        s.update({"itog_url": "https://example.ru/eta/", "redirektov": 0, "kod": 200})
        z = sverka_stranic.zamechaniya(s, 200)
        self.assertIn("запрет индексации", z)
        self.assertIn("canonical на другой адрес", z)

    def test_sravnenie(self):
        starye = {"https://a/": {"url": "https://a/", "kod": "200", "title": "Было"},
                  "https://b/": {"url": "https://b/", "kod": "200", "title": "Б"}}
        novye = [{"url": "https://a/", "kod": 200, "title": "Стало"},
                 {"url": "https://c/", "kod": 200, "title": "В"}]
        izm = "\n".join(sverka_stranic.sravnit(novye, starye))
        self.assertIn("новый адрес: https://c/", izm)
        self.assertIn("адрес пропал из списка: https://b/", izm)
        self.assertIn("«Было» -> «Стало»", izm)


class Sroki(unittest.TestCase):
    def setUp(self):
        self.pravki = sroki_zamerov.razobrat(ZHURNAL)

    def test_razbor(self):
        self.assertEqual([p["nomer"] for p in self.pravki], ["П-1", "П-2", "П-3"])
        self.assertEqual(self.pravki[0]["polya"]["Статус"], "выложена")

    def test_sroki(self):
        s = sroki_zamerov.sostoyanie(self.pravki[0], date(2026, 12, 30))
        self.assertEqual(s["vylozheno"], date(2026, 12, 1))
        self.assertEqual(s["zamery"][14], "снят")
        self.assertTrue(s["zamery"][28].startswith("пора"))
        self.assertTrue(s["zamery"][56].startswith("через 27"))
        self.assertEqual(s["pora"], [28])

    def test_zhdet_vykladki(self):
        s = sroki_zamerov.sostoyanie(self.pravki[1], date(2026, 12, 15))
        self.assertIsNone(s["vylozheno"])
        self.assertEqual(s["zhdet_dney"], 14)
        self.assertFalse(s["zakryta"])

    def test_zakrytaya(self):
        s = sroki_zamerov.sostoyanie(self.pravki[2], date(2026, 12, 15))
        self.assertTrue(s["zakryta"])
        self.assertEqual(s["vylozheno"], date(2026, 10, 1))
        self.assertEqual(s["pora"], [])


if __name__ == "__main__":
    unittest.main()
