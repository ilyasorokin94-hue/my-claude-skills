#!/usr/bin/env python3
"""Сверка страниц живого сайта: что реально отдаёт сервер.

Для каждой страницы: код ответа, редиректы, title, description, H1, canonical,
запрет индексации, число слов. Только чтение, без зависимостей и без
выполнения скриптов страницы.

Примеры:
  python sverka_stranic.py https://example.ru/ https://example.ru/ceny/
  python sverka_stranic.py --sitemap https://example.ru/sitemap.xml --out stranicy.tsv
  python sverka_stranic.py --file adresa.txt --sravnit proshlaya.tsv

В консоль идёт короткая сводка (до 30 строк), полная таблица в TSV.
"""
import argparse
import csv
import gzip
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

UA = "Mozilla/5.0 (compatible; seo-vedenie-sverka/1.0; read-only site check)"
POLYA = [
    "url", "kod", "itog_url", "redirektov", "title", "title_dlina",
    "description", "description_dlina", "h1_shtuk", "h1", "canonical",
    "robots", "slov", "zamechaniya",
]
TITLE_MAX = 70
DESCRIPTION_MAX = 160


class Stranica(HTMLParser):
    """Достаёт из HTML то, что видит робот без выполнения скриптов."""

    PROPUSK = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.robots = ""
        self.canonical = ""
        self.h1 = []
        self.slov = 0
        self._v_title = False
        self._v_h1 = False
        self._propusk = 0
        self._v_body = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.PROPUSK:
            self._propusk += 1
        elif tag == "title" and not self.title:
            self._v_title = True
        elif tag == "h1":
            self._v_h1 = True
            self.h1.append("")
        elif tag == "body":
            self._v_body = True
        elif tag == "meta":
            imya = a.get("name", "").lower()
            if imya == "description" and not self.description:
                self.description = szhat(a.get("content", ""))
            elif imya in ("robots", "yandex", "googlebot"):
                znachenie = szhat(a.get("content", "")).lower()
                if znachenie:
                    self.robots = (self.robots + "; " if self.robots else "") + imya + ": " + znachenie
        elif tag == "link":
            if "canonical" in a.get("rel", "").lower().split() and not self.canonical:
                self.canonical = a.get("href", "").strip()

    def handle_endtag(self, tag):
        if tag in self.PROPUSK and self._propusk:
            self._propusk -= 1
        elif tag == "title":
            self._v_title = False
        elif tag == "h1":
            self._v_h1 = False

    def handle_data(self, data):
        if self._propusk:
            return
        if self._v_title:
            self.title += data
        if self._v_h1 and self.h1:
            self.h1[-1] += data
        if self._v_body:
            self.slov += len(re.findall(r"\w+", data))


def szhat(tekst):
    return re.sub(r"\s+", " ", tekst or "").strip()


def razobrat_html(html):
    """HTML -> словарь полей страницы."""
    p = Stranica()
    try:
        p.feed(html)
        p.close()
    except Exception:  # битая вёрстка не должна ронять сверку
        pass
    h1 = [szhat(x) for x in p.h1]
    title = szhat(p.title)
    return {
        "title": title,
        "title_dlina": len(title),
        "description": p.description,
        "description_dlina": len(p.description),
        "h1_shtuk": len(h1),
        "h1": h1[0] if h1 else "",
        "canonical": p.canonical,
        "robots": p.robots,
        "slov": p.slov,
    }


def normalizovat(url):
    """Кириллический домен и путь -> адрес, который примет urllib."""
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    ch = urllib.parse.urlsplit(url)
    host = ch.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    netloc = host + (":%d" % ch.port if ch.port else "")
    put = urllib.parse.quote(ch.path or "/", safe="/%:@!$&'()*+,;=~-._")
    zapros = urllib.parse.quote(ch.query, safe="=&%:@!$'()*+,;/?~-._")
    return urllib.parse.urlunsplit((ch.scheme.lower(), netloc, put, zapros, ""))


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OTKRYVATEL = urllib.request.build_opener(BezRedirekta)


def zaprosit(url, timeout):
    """Один запрос без следования редиректам: (код, заголовки, тело-байты)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip",
        "Accept-Language": "ru,en;q=0.8",
    })
    try:
        with OTKRYVATEL.open(req, timeout=timeout) as otvet:
            telo = otvet.read()
            return otvet.status, otvet.headers, telo
    except urllib.error.HTTPError as e:
        try:
            telo = e.read()
        except Exception:
            telo = b""
        return e.code, e.headers, telo


def raskodirovat(telo, zagolovki):
    if (zagolovki.get("Content-Encoding") or "").lower() == "gzip":
        try:
            telo = gzip.decompress(telo)
        except OSError:
            pass
    kodirovka = None
    m = re.search(r"charset=([\w-]+)", zagolovki.get("Content-Type") or "", re.I)
    if m:
        kodirovka = m.group(1)
    else:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", telo[:4096], re.I)
        if m:
            kodirovka = m.group(1).decode("ascii", "replace")
    for k in (kodirovka, "utf-8", "cp1251"):
        if not k:
            continue
        try:
            return telo.decode(k)
        except (LookupError, UnicodeDecodeError):
            continue
    return telo.decode("utf-8", "replace")


def proverit(url, timeout=20, max_redirektov=5):
    """Страница -> строка таблицы (словарь по POLYA)."""
    stroka = dict.fromkeys(POLYA, "")
    stroka["url"] = url
    tekushchiy = normalizovat(url)
    redirektov = 0
    try:
        while True:
            kod, zagolovki, telo = zaprosit(tekushchiy, timeout)
            if kod in (301, 302, 303, 307, 308) and zagolovki.get("Location") and redirektov < max_redirektov:
                if redirektov == 0:
                    stroka["kod"] = kod
                tekushchiy = normalizovat(urllib.parse.urljoin(tekushchiy, zagolovki["Location"]))
                redirektov += 1
                continue
            break
    except Exception as e:
        stroka["kod"] = "oshibka"
        stroka["zamechaniya"] = "не открылась: %s" % szhat(str(e))[:120]
        return stroka

    if not stroka["kod"]:
        stroka["kod"] = kod
    stroka["itog_url"] = tekushchiy
    stroka["redirektov"] = redirektov
    x_robots = szhat(zagolovki.get("X-Robots-Tag") or "").lower()
    tip = (zagolovki.get("Content-Type") or "").lower()
    if kod == 200 and ("html" in tip or not tip):
        stroka.update(razobrat_html(raskodirovat(telo, zagolovki)))
    if x_robots:
        stroka["robots"] = (stroka["robots"] + "; " if stroka["robots"] else "") + "x-robots-tag: " + x_robots
    stroka["zamechaniya"] = "; ".join(zamechaniya(stroka, kod))
    return stroka


def bez_slesha(url):
    return url.rstrip("/").lower()


def zamechaniya(s, itog_kod):
    z = []
    if s["redirektov"]:
        z.append("редирект %s -> код %s" % (s["kod"], itog_kod))
    if itog_kod != 200:
        z.append("ответ %s" % itog_kod)
        return z
    if not s["title"]:
        z.append("нет title")
    elif s["title_dlina"] > TITLE_MAX:
        z.append("title длиннее %d" % TITLE_MAX)
    if not s["description"]:
        z.append("нет description")
    elif s["description_dlina"] > DESCRIPTION_MAX:
        z.append("description длиннее %d" % DESCRIPTION_MAX)
    if s["h1_shtuk"] == 0:
        z.append("нет H1")
    elif s["h1_shtuk"] > 1:
        z.append("H1: %d" % s["h1_shtuk"])
    if "noindex" in s["robots"] or re.search(r":\s*none", s["robots"]):
        z.append("запрет индексации")
    if not s["canonical"]:
        z.append("нет canonical")
    elif bez_slesha(normalizovat(urllib.parse.urljoin(s["itog_url"], s["canonical"]))) != bez_slesha(s["itog_url"]):
        z.append("canonical на другой адрес")
    return z


def adresa_iz_sitemap(url, timeout=20, glubina=0, predel=5000):
    """Адреса из sitemap.xml, в том числе из индекса sitemap."""
    kod, zagolovki, telo = zaprosit(normalizovat(url), timeout)
    for _ in range(5):
        if kod in (301, 302, 303, 307, 308) and zagolovki.get("Location"):
            url = urllib.parse.urljoin(url, zagolovki["Location"])
            kod, zagolovki, telo = zaprosit(normalizovat(url), timeout)
        else:
            break
    if kod != 200:
        raise RuntimeError("sitemap %s: ответ %s" % (url, kod))
    if (zagolovki.get("Content-Encoding") or "").lower() == "gzip" or url.endswith(".gz"):
        try:
            telo = gzip.decompress(telo)
        except OSError:
            pass
    koren = ElementTree.fromstring(telo)
    imya = koren.tag.rsplit("}", 1)[-1]
    locs = [el.text.strip() for el in koren.iter() if el.tag.rsplit("}", 1)[-1] == "loc" and el.text]
    if imya == "sitemapindex" and glubina < 3:
        vse = []
        for vlozhennyy in locs:
            vse.extend(adresa_iz_sitemap(vlozhennyy, timeout, glubina + 1, predel))
            if len(vse) >= predel:
                break
        return vse[:predel]
    return locs[:predel]


def prochitat_tsv(put):
    with open(put, encoding="utf-8", newline="") as f:
        return {s["url"]: s for s in csv.DictReader(f, delimiter="\t")}


def sravnit(novye, starye):
    """Список строк «что изменилось» между двумя сверками."""
    izmeneniya = []
    novye_po_url = {s["url"]: s for s in novye}
    for url in sorted(set(novye_po_url) - set(starye)):
        izmeneniya.append("новый адрес: %s" % url)
    for url in sorted(set(starye) - set(novye_po_url)):
        izmeneniya.append("адрес пропал из списка: %s" % url)
    for url, s in novye_po_url.items():
        st = starye.get(url)
        if not st:
            continue
        for pole in ("kod", "itog_url", "title", "description", "h1", "canonical", "robots"):
            bylo, stalo = str(st.get(pole, "")), str(s.get(pole, ""))
            if bylo != stalo:
                izmeneniya.append("%s | %s: «%s» -> «%s»" % (url, pole, bylo[:90], stalo[:90]))
    return izmeneniya


def main(argv=None):
    for potok in (sys.stdout, sys.stderr):
        try:
            potok.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Сверка страниц живого сайта (только чтение).")
    ap.add_argument("urls", nargs="*", help="адреса страниц")
    ap.add_argument("--file", help="файл со списком адресов, по одному в строке")
    ap.add_argument("--sitemap", help="адрес sitemap.xml: проверить все страницы из него")
    ap.add_argument("--max", type=int, default=300, help="не больше стольких страниц (по умолчанию 300)")
    ap.add_argument("--out", help="куда положить TSV (по умолчанию cache/sverka-<дата>.tsv)")
    ap.add_argument("--sravnit", help="TSV прошлой сверки: показать, что изменилось")
    ap.add_argument("--delay", type=float, default=0.5, help="пауза между запросами, секунд")
    ap.add_argument("--timeout", type=float, default=20)
    a = ap.parse_args(argv)

    adresa = list(a.urls)
    if a.file:
        for stroka in Path(a.file).read_text(encoding="utf-8").splitlines():
            stroka = stroka.strip()
            if stroka and not stroka.startswith("#"):
                adresa.append(stroka)
    if a.sitemap:
        adresa.extend(adresa_iz_sitemap(a.sitemap, a.timeout))
    vidennye, spisok = set(), []
    for u in adresa:
        if u not in vidennye:
            vidennye.add(u)
            spisok.append(u)
    if not spisok:
        ap.error("нет адресов: укажи адреса, --file или --sitemap")
    if len(spisok) > a.max:
        print("Адресов %d, проверяю первые %d (--max)." % (len(spisok), a.max))
        spisok = spisok[:a.max]

    stroki = []
    for i, url in enumerate(spisok):
        if i:
            time.sleep(a.delay)
        stroki.append(proverit(url, a.timeout))

    if a.out:
        vyhod = Path(a.out)
    else:
        vyhod = Path(__file__).resolve().parent.parent / "cache" / ("sverka-%s.tsv" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    vyhod.parent.mkdir(parents=True, exist_ok=True)
    with open(vyhod, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=POLYA, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(stroki)

    s_zamechaniyami = [s for s in stroki if s["zamechaniya"]]
    print("Страниц: %d. С ответом 200: %d. С замечаниями: %d." % (
        len(stroki), sum(1 for s in stroki if str(s["kod"]) == "200" and not s["redirektov"]), len(s_zamechaniyami)))
    if len(stroki) <= 8:
        for s in stroki:
            print("\n%s\n  код %s%s\n  title (%s): %s\n  description (%s): %s\n  H1 (%s шт.): %s\n  canonical: %s\n  директивы роботам: %s\n  замечания: %s" % (
                s["url"], s["kod"], (" -> " + s["itog_url"]) if s["redirektov"] else "",
                s["title_dlina"], s["title"], s["description_dlina"], s["description"],
                s["h1_shtuk"], s["h1"], s["canonical"] or "нет", s["robots"] or "нет", s["zamechaniya"] or "нет"))
    else:
        for s in s_zamechaniyami[:22]:
            print("  %s | %s" % (s["url"], s["zamechaniya"]))
        if len(s_zamechaniyami) > 22:
            print("  … ещё %d, все в таблице" % (len(s_zamechaniyami) - 22))
    if a.sravnit:
        izm = sravnit(stroki, prochitat_tsv(a.sravnit))
        print("\nИзменилось с прошлой сверки: %d" % len(izm))
        for stroka in izm[:20]:
            print("  " + stroka)
        if len(izm) > 20:
            print("  … ещё %d" % (len(izm) - 20))
    print("\nТаблица: %s" % vyhod)
    return 0


if __name__ == "__main__":
    sys.exit(main())
