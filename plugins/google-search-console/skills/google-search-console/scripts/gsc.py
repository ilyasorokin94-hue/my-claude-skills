#!/usr/bin/env python3
"""Google Search Console + PageSpeed Insights / CrUX, read-only, stdlib only.

Subcommands:
  doctor     check config, token and access (no secrets printed)
  sites      list Search Console properties of the service account
  perf       search analytics: clicks, impressions, CTR, position
  quickwins  queries/pages on positions 4-20 with impressions
  inspect    URL Inspection: is the page in Google's index and why not
  sitemaps   sitemaps known to Search Console (submit with --submit)
  psi        PageSpeed Insights (lab + field data) for URLs
  crux       Chrome UX Report field data for an origin or URL

Auth for Search Console: a service account key (JSON) in one of
  GSC_SERVICE_ACCOUNT_JSON  raw JSON or base64 of it (env or config/.env)
  GSC_SERVICE_ACCOUNT_FILE  path to the JSON file
  config/service-account.json
The service account e-mail must be added as a user of the property in
Search Console. The JWT is signed with the `openssl` CLI; the key is written
to a private temp file only for the duration of the signing call.

Auth for PageSpeed / CrUX: API key in PSI_API_KEY (or GOOGLE_API_KEY), sent as
the X-Goog-Api-Key header. If it is not set, the request goes without a key, so
a network secret of the environment (header X-Goog-Api-Key on
pagespeedonline.googleapis.com / chromeuxreport.googleapis.com) can supply it.

Output: at most ~30 lines to stdout, full tables as TSV in ../cache/.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from xml.etree import ElementTree

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(SKILL_DIR, "cache")
CONFIG_DIR = os.path.join(SKILL_DIR, "config")

TOKEN_URI = "https://oauth2.googleapis.com/token"
GSC_V3 = "https://www.googleapis.com/webmasters/v3"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
PSI_URL = "https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"
CRUX_URL = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
SCOPE_RO = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPE_RW = "https://www.googleapis.com/auth/webmasters"
PLACEHOLDERS = {"", "injected-by-proxy", "changeme", "your_key_here"}
STDOUT_ROWS = 25


class GscError(Exception):
    pass


# --------------------------------------------------------------------------- config

def _dotenv() -> dict:
    path = os.path.join(CONFIG_DIR, ".env")
    out = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def setting(name: str) -> str:
    val = os.environ.get(name)
    if val is None:
        val = _dotenv().get(name, "")
    return val.strip()


def load_service_account() -> dict:
    raw = setting("GSC_SERVICE_ACCOUNT_JSON")
    source = "GSC_SERVICE_ACCOUNT_JSON"
    if raw.lower() in PLACEHOLDERS:
        raw = ""
    if not raw:
        path = setting("GSC_SERVICE_ACCOUNT_FILE") or os.path.join(CONFIG_DIR, "service-account.json")
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
            source = path
    if not raw:
        raise GscError(
            "Нет ключа сервисного аккаунта. Задай GSC_SERVICE_ACCOUNT_JSON (JSON или base64) "
            "в переменных среды, или положи файл в config/service-account.json. "
            "Инструкция: config/README.md")
    text = raw.strip()
    if not text.startswith("{"):
        try:
            text = base64.b64decode(text + "=" * (-len(text) % 4)).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise GscError(f"{source}: не JSON и не base64 ({type(exc).__name__})") from None
    try:
        sa = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GscError(f"{source}: JSON не читается (строка {exc.lineno})") from None
    if sa.get("type") != "service_account" or not sa.get("private_key") or not sa.get("client_email"):
        raise GscError(f"{source}: это не ключ сервисного аккаунта (нужны type=service_account, "
                       "client_email, private_key)")
    return sa


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_rs256(message: bytes, private_key_pem: str) -> bytes:
    if not shutil.which("openssl"):
        raise GscError("Нужен openssl в PATH для подписи JWT")
    tmpdir = tempfile.mkdtemp(prefix="gsc-")
    keyfile = os.path.join(tmpdir, "k.pem")
    try:
        fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(private_key_pem)
        proc = subprocess.run(["openssl", "dgst", "-sha256", "-sign", keyfile],
                              input=message, capture_output=True, check=False)
        if proc.returncode != 0 or not proc.stdout:
            raise GscError("openssl не смог подписать JWT: ключ повреждён?")
        return proc.stdout
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def build_jwt(sa: dict, scope: str, now: int | None = None) -> str:
    now = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    if sa.get("private_key_id"):
        header["kid"] = sa["private_key_id"]
    claims = {"iss": sa["client_email"], "scope": scope,
              "aud": sa.get("token_uri") or TOKEN_URI, "iat": now, "exp": now + 3600}
    signing_input = (b64url(json.dumps(header, separators=(",", ":")).encode()) + "." +
                     b64url(json.dumps(claims, separators=(",", ":")).encode())).encode()
    return signing_input.decode() + "." + b64url(sign_rs256(signing_input, sa["private_key"]))


_TOKENS: dict = {}


def access_token(scope: str = SCOPE_RO) -> str:
    if scope in _TOKENS:
        return _TOKENS[scope]
    sa = load_service_account()
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": build_jwt(sa, scope),
    }).encode()
    req = urllib.request.Request(sa.get("token_uri") or TOKEN_URI, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            tok = json.loads(resp.read().decode())["access_token"]
    except urllib.error.HTTPError as exc:
        detail = _error_text(exc)
        raise GscError(f"Google не выдал токен (HTTP {exc.code}): {detail}. "
                       "Проверь, что ключ не удалён в Google Cloud и включён Search Console API.") from None
    _TOKENS[scope] = tok
    return tok


# --------------------------------------------------------------------------- http

def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return exc.reason or "error"
    err = payload.get("error")
    if isinstance(err, dict):
        return f"{err.get('status', '')} {err.get('message', '')}".strip()
    return f"{err} {payload.get('error_description', '')}".strip()


def http_json(method: str, url: str, body=None, headers=None, timeout=60, retries=3):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Accept": "application/json"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    delay = 2.0
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            if exc.code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise GscHttpError(exc.code, _error_text(exc)) from None
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise GscError(f"Сеть: {exc.reason}") from None
    raise GscError("unreachable")


class GscHttpError(GscError):
    def __init__(self, code: int, message: str):
        super().__init__(f"HTTP {code}: {message}")
        self.code = code
        self.message = message


def gsc(method: str, url: str, body=None, scope: str = SCOPE_RO):
    try:
        return http_json(method, url, body, {"Authorization": "Bearer " + access_token(scope)})
    except GscHttpError as exc:
        if exc.code == 403:
            raise GscError(
                f"{exc}. Сервисный аккаунт не добавлен пользователем этого ресурса в Search Console "
                "(Настройки → Пользователи и разрешения), или выключен Search Console API в проекте.") from None
        if exc.code == 429:
            raise GscError(f"{exc}. Квота Search Console исчерпана, повтори позже.") from None
        raise


def google_key_headers() -> dict:
    key = setting("PSI_API_KEY") or setting("GOOGLE_API_KEY")
    if key.lower() in PLACEHOLDERS:
        return {}
    return {"X-Goog-Api-Key": key}


# --------------------------------------------------------------------------- helpers

def ensure_cache() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.-]+", "_", text).strip("_")[:80]


def write_tsv(name: str, header: list, rows: list) -> str:
    ensure_cache()
    path = os.path.join(CACHE_DIR, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\t".join(header) + "\n")
        for r in rows:
            fh.write("\t".join("" if v is None else str(v).replace("\t", " ").replace("\n", " ") for v in r) + "\n")
    return path


def print_table(header: list, rows: list, limit: int = STDOUT_ROWS) -> None:
    shown = rows[:limit]
    cols = [[str(h)] + ["" if r[i] is None else str(r[i]) for r in shown] for i, h in enumerate(header)]
    widths = [min(max(len(c) for c in col), 70) for col in cols]
    for line_no in range(len(shown) + 1):
        cells = []
        for i, col in enumerate(cols):
            cell = col[line_no]
            if len(cell) > widths[i]:
                cell = cell[: widths[i] - 1] + "…"
            cells.append(cell.ljust(widths[i]))
        print("  ".join(cells).rstrip())
    if len(rows) > limit:
        print(f"… ещё {len(rows) - limit} строк в файле")


def list_sites(refresh: bool = False) -> list:
    ensure_cache()
    path = os.path.join(CACHE_DIR, "sites.json")
    if not refresh and os.path.isfile(path) and time.time() - os.path.getmtime(path) < 86400:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    entries = gsc("GET", f"{GSC_V3}/sites").get("siteEntry", [])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)
    return entries


def bare_domain(text: str) -> str:
    text = text.strip()
    if text.startswith("sc-domain:"):
        return text[len("sc-domain:"):].lower()
    host = urllib.parse.urlparse(text if "://" in text else "https://" + text).hostname or text
    host = host.lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    return host[4:] if host.startswith("www.") else host


def resolve_site(arg: str) -> str:
    if arg.startswith("sc-domain:") or (arg.startswith("http") and arg.endswith("/")):
        return arg
    domain = bare_domain(arg)
    try:
        sites = [s["siteUrl"] for s in list_sites()]
    except GscError:
        sites = []
    for cand in (f"sc-domain:{domain}", f"https://{domain}/", f"https://www.{domain}/",
                 f"http://{domain}/", f"http://www.{domain}/"):
        if cand in sites:
            return cand
    if sites:
        raise GscError(f"Ресурса для {domain} нет среди доступных: {', '.join(sites)}")
    return f"sc-domain:{domain}"


def site_enc(site: str) -> str:
    return urllib.parse.quote(site, safe="")


def date_range(args) -> tuple:
    lag = 1 if getattr(args, "fresh", False) else 3
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=lag)
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=args.days - 1)
    if start > end:
        raise GscError("start позже end")
    return start, end


def analytics(site: str, start: date, end: date, dims: list, filters: list, args,
              max_rows: int = 100000) -> list:
    rows, start_row = [], 0
    while True:
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims,
                "rowLimit": 25000, "startRow": start_row, "type": args.type,
                "dataState": "all" if getattr(args, "fresh", False) else "final"}
        if filters:
            body["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]
        resp = gsc("POST", f"{GSC_V3}/sites/{site_enc(site)}/searchAnalytics/query", body)
        batch = resp.get("rows", [])
        rows.extend(batch)
        if len(batch) < 25000 or len(rows) >= max_rows:
            return rows
        start_row += 25000


def build_filters(args) -> list:
    f = []
    if args.country:
        f.append({"dimension": "country", "operator": "equals", "expression": args.country.lower()})
    if args.device:
        f.append({"dimension": "device", "operator": "equals", "expression": args.device.upper()})
    if args.page_contains:
        f.append({"dimension": "page", "operator": "contains", "expression": args.page_contains})
    if args.query_contains:
        f.append({"dimension": "query", "operator": "contains", "expression": args.query_contains})
    return f


def totals(site, start, end, filters, args) -> dict:
    rows = analytics(site, start, end, [], filters, args)
    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    return rows[0]


def fmt_row(r: dict) -> tuple:
    return (int(r.get("clicks", 0)), int(r.get("impressions", 0)),
            round(100 * r.get("ctr", 0.0), 1), round(r.get("position", 0.0), 1))


# --------------------------------------------------------------------------- commands

def cmd_doctor(args) -> int:
    ok = True
    print("== Search Console")
    try:
        sa = load_service_account()
        print(f"ключ: найден, сервисный аккаунт {sa['client_email']} (проект {sa.get('project_id', '?')})")
        access_token()
        print("токен: Google выдал")
        sites = list_sites(refresh=True)
        if sites:
            for s in sites:
                print(f"ресурс: {s['siteUrl']}  права: {s.get('permissionLevel')}")
        else:
            ok = False
            print("ресурсов нет: добавь e-mail сервисного аккаунта пользователем в Search Console")
    except GscError as exc:
        ok = False
        print(f"ошибка: {exc}")
    print("== PageSpeed / CrUX")
    if google_key_headers():
        print("ключ API: задан в PSI_API_KEY / GOOGLE_API_KEY")
    else:
        print("ключ API: в переменных нет; сработает, только если его подставляет прокси среды "
              "(network secret, заголовок X-Goog-Api-Key). Проверка: gsc.py psi <url>")
    print("== openssl:", "есть" if shutil.which("openssl") else "НЕТ")
    return 0 if ok else 1


def cmd_sites(args) -> int:
    sites = list_sites(refresh=args.refresh)
    rows = [(s["siteUrl"], s.get("permissionLevel", "")) for s in sites]
    print_table(["siteUrl", "permission"], rows)
    if not rows:
        print("Нет ресурсов. Добавь e-mail сервисного аккаунта в Search Console → Пользователи и разрешения.")
    return 0


def cmd_perf(args) -> int:
    site = resolve_site(args.site)
    start, end = date_range(args)
    dims = [d.strip() for d in args.dims.split(",") if d.strip()]
    filters = build_filters(args)
    tot = totals(site, start, end, filters, args)
    rows = analytics(site, start, end, dims, filters, args)
    prev_map, ptot = {}, None
    if args.compare:
        span = (end - start).days + 1
        pend, pstart = start - timedelta(days=1), start - timedelta(days=span)
        ptot = totals(site, pstart, pend, filters, args)
        for r in analytics(site, pstart, pend, dims, filters, args):
            prev_map[tuple(r["keys"])] = r
    brand = re.compile(args.brand, re.I) if args.brand else None
    out = []
    for r in rows:
        keys = r["keys"]
        c, i, ctr, pos = fmt_row(r)
        line = list(keys) + [c, i, ctr, pos]
        if brand is not None and "query" in dims:
            line.append("brand" if brand.search(keys[dims.index("query")]) else "nonbrand")
        if args.compare:
            p = prev_map.get(tuple(keys), {})
            line += [int(p.get("clicks", 0)), c - int(p.get("clicks", 0)),
                     round(p.get("position", 0.0), 1) if p else ""]
        out.append(line)
    if dims == ["date"]:
        out.sort(key=lambda x: x[0])
    else:
        out.sort(key=lambda x: (-x[len(dims)], -x[len(dims) + 1]))
    header = dims + ["clicks", "impressions", "ctr%", "position"]
    if brand is not None and "query" in dims:
        header.append("segment")
    if args.compare:
        header += ["clicks_prev", "clicks_delta", "position_prev"]
    name = f"perf_{slug(site)}_{'-'.join(dims) or 'total'}_{start}_{end}.tsv"
    path = write_tsv(name, header, out)
    c, i, ctr, pos = fmt_row(tot)
    print(f"{site}  {start}..{end}  ({args.type}{', ' + args.country if args.country else ''})")
    print(f"Итого: клики {c}, показы {i}, CTR {ctr}%, ср. позиция {pos}")
    if ptot is not None:
        pc, pi, _, ppos = fmt_row(ptot)
        print(f"Прошлый период: клики {pc}, показы {pi}, ср. позиция {ppos}")
    if "query" in dims and c:
        seen = sum(x[len(dims)] for x in out)
        print(f"Клики с видимыми запросами: {seen} из {c} ({round(100 * seen / c)}%), "
              "остальное Google скрывает (редкие запросы)")
        if brand is not None:
            bc = sum(x[len(dims)] for x in out if x[len(dims) + 4] == "brand")
            bi = sum(x[len(dims) + 1] for x in out if x[len(dims) + 4] == "brand")
            print(f"Бренд: клики {bc}, показы {bi}; небрендовые видимые: клики {seen - bc}, "
                  f"показы {sum(x[len(dims) + 1] for x in out) - bi}")
    print_table(header, out, args.limit)
    print(f"Файл: {path}")
    return 0


def cmd_quickwins(args) -> int:
    site = resolve_site(args.site)
    start, end = date_range(args)
    dims = ["query", "page"] if args.by == "query-page" else [args.by]
    rows = analytics(site, start, end, dims, build_filters(args), args)
    brand = re.compile(args.brand, re.I) if args.brand else None
    out = []
    for r in rows:
        c, i, ctr, pos = fmt_row(r)
        if not (args.min_pos <= pos <= args.max_pos) or i < args.min_impr:
            continue
        if brand is not None and "query" in dims and brand.search(r["keys"][0]):
            continue
        out.append(list(r["keys"]) + [c, i, ctr, pos])
    out.sort(key=lambda x: -x[len(dims) + 1])
    header = dims + ["clicks", "impressions", "ctr%", "position"]
    path = write_tsv(f"quickwins_{slug(site)}_{args.by}_{start}_{end}.tsv", header, out)
    print(f"{site}  {start}..{end}: позиции {args.min_pos}-{args.max_pos}, показов ≥ {args.min_impr}"
          f"{', без бренда' if brand else ''}: {len(out)}")
    print_table(header, out, args.limit)
    print(f"Файл: {path}")
    return 0


def sitemap_urls(url: str, depth: int = 0) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "gsc-skill/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        tree = ElementTree.fromstring(resp.read())
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [e.text.strip() for e in tree.iter(f"{ns}loc") if e.text]
    if tree.tag == f"{ns}sitemapindex" and depth < 1:
        out = []
        for child in locs:
            out.extend(sitemap_urls(child, depth + 1))
        return out
    return locs


def cmd_inspect(args) -> int:
    site = resolve_site(args.site)
    urls = list(args.urls)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            urls += [ln.strip() for ln in fh if ln.strip().startswith("http")]
    if args.sitemap:
        urls += sitemap_urls(args.sitemap)
    urls = list(dict.fromkeys(urls))
    if not urls:
        raise GscError("Нет URL: передай адреса, --file или --sitemap")
    if len(urls) > args.max:
        print(f"URL {len(urls)}, проверю первые {args.max} (--max; квота Google 2000 в день на ресурс)")
        urls = urls[: args.max]
    header = ["url", "verdict", "coverageState", "indexingState", "pageFetchState", "robotsTxtState",
              "lastCrawlTime", "crawledAs", "googleCanonical", "userCanonical", "canonicalMismatch",
              "inSitemaps", "referringUrls"]
    out = []
    for n, url in enumerate(urls, 1):
        try:
            resp = gsc("POST", INSPECT_URL, {"inspectionUrl": url, "siteUrl": site, "languageCode": "ru"})
            ix = resp.get("inspectionResult", {}).get("indexStatusResult", {})
            gc, uc = ix.get("googleCanonical", ""), ix.get("userCanonical", "")
            out.append([url, ix.get("verdict", ""), ix.get("coverageState", ""), ix.get("indexingState", ""),
                        ix.get("pageFetchState", ""), ix.get("robotsTxtState", ""),
                        ix.get("lastCrawlTime", ""), ix.get("crawledAs", ""), gc, uc,
                        "yes" if gc and uc and gc != uc else "", len(ix.get("sitemap", []) or []),
                        len(ix.get("referringUrls", []) or [])])
        except GscError as exc:
            out.append([url, "ERROR", str(exc)[:200]] + [""] * 10)
            if "403" in str(exc) or "429" in str(exc):
                print(f"стоп на {n}-м URL: {exc}")
                break
        time.sleep(0.15)
    path = write_tsv(f"inspect_{slug(site)}_{date.today()}.tsv", header, out)
    counts: dict = {}
    for r in out:
        counts[r[2] or r[1]] = counts.get(r[2] or r[1], 0) + 1
    print(f"{site}: проверено {len(out)} URL")
    for state, k in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:4d}  {state}")
    bad = [r for r in out if r[1] != "PASS" or r[10]]
    if bad:
        print("Не в индексе или канонический не совпадает:")
        print_table(["url", "verdict", "coverageState", "googleCanonical"],
                    [[r[0], r[1], r[2], r[8] if r[10] else ""] for r in bad], 15)
    print(f"Файл: {path}")
    return 0


def cmd_sitemaps(args) -> int:
    site = resolve_site(args.site)
    if args.submit:
        gsc("PUT", f"{GSC_V3}/sites/{site_enc(site)}/sitemaps/{site_enc(args.submit)}", scope=SCOPE_RW)
        print(f"Отправлен: {args.submit} (нужны права «Полный доступ» у сервисного аккаунта)")
    items = gsc("GET", f"{GSC_V3}/sites/{site_enc(site)}/sitemaps").get("sitemap", [])
    rows = []
    for s in items:
        contents = "; ".join(f"{c.get('type')}: {c.get('submitted')}" for c in s.get("contents", []))
        rows.append([s.get("path"), (s.get("lastSubmitted") or "")[:10], (s.get("lastDownloaded") or "")[:10],
                     s.get("isPending"), s.get("errors"), s.get("warnings"), contents])
    header = ["path", "submitted", "downloaded", "pending", "errors", "warnings", "contents"]
    print_table(header, rows)
    if not rows:
        print("В Search Console нет ни одного sitemap. Отправить: gsc.py sitemaps --site ... --submit <url>")
    return 0


def _ms(v):
    return "" if v is None else int(round(v))


def psi_one(url: str, strategy: str) -> list:
    params = [("url", url), ("strategy", strategy.upper())]
    params += [("category", c) for c in ("PERFORMANCE", "SEO", "ACCESSIBILITY", "BEST_PRACTICES")]
    try:
        data = http_json("GET", PSI_URL + "?" + urllib.parse.urlencode(params),
                         headers=google_key_headers(), timeout=180, retries=1)
    except GscHttpError as exc:
        if exc.code == 429 and "583797351490" in exc.message:
            raise GscError("PageSpeed без своего ключа: общая квота исчерпана. Нужен PSI_API_KEY "
                           "или network secret X-Goog-Api-Key (config/README.md)") from None
        raise
    lh = data.get("lighthouseResult", {})
    cats = lh.get("categories", {})
    aud = lh.get("audits", {})

    def score(k):
        s = (cats.get(k) or {}).get("score")
        return "" if s is None else int(round(100 * s))

    def num(k):
        return (aud.get(k) or {}).get("numericValue")

    field = data.get("loadingExperience", {}) or {}
    fm = field.get("metrics", {}) or {}

    def p75(k):
        return (fm.get(k) or {}).get("percentile", "")

    field_src = "" if not fm else ("origin" if field.get("origin_fallback") else "url")
    opps = []
    for a in aud.values():
        det = a.get("details") or {}
        saving = det.get("overallSavingsMs") or 0
        if saving and saving >= 100 and (a.get("score") is not None and a.get("score") < 0.9):
            opps.append((saving, a.get("title", "")))
    opps.sort(reverse=True)
    cls = num("cumulative-layout-shift")
    return [url, strategy, score("performance"), score("seo"), score("accessibility"),
            score("best-practices"), _ms(num("first-contentful-paint")), _ms(num("largest-contentful-paint")),
            _ms(num("total-blocking-time")), "" if cls is None else round(cls, 3),
            _ms(num("speed-index")), field_src, p75("LARGEST_CONTENTFUL_PAINT_MS"),
            p75("INTERACTION_TO_NEXT_PAINT"), p75("CUMULATIVE_LAYOUT_SHIFT_SCORE"),
            field.get("overall_category", ""), " | ".join(f"{t} (-{int(s)} мс)" for s, t in opps[:3])]


def cmd_psi(args) -> int:
    strategies = ["mobile", "desktop"] if args.strategy == "both" else [args.strategy]
    header = ["url", "strategy", "perf", "seo", "a11y", "bp", "FCP_ms", "LCP_ms", "TBT_ms", "CLS",
              "SI_ms", "field", "f_LCP_p75", "f_INP_p75", "f_CLSx100_p75", "f_overall", "top_opportunities"]
    out = []
    for url in args.urls:
        for st in strategies:
            try:
                out.append(psi_one(url, st))
            except GscError as exc:
                out.append([url, st, "ERROR", str(exc)[:200]] + [""] * 13)
                if "квота" in str(exc):
                    break
    path = write_tsv(f"psi_{date.today()}_{int(time.time())}.tsv", header, out)
    print_table(header[:11] + ["field"], [r[:12] for r in out])
    for r in out:
        if r[2] != "ERROR" and r[16]:
            print(f"{r[0]} [{r[1]}]: {r[16]}")
    ok_rows = [r for r in out if r[2] != "ERROR"]
    if ok_rows and not any(r[11] for r in ok_rows):
        print("Полевых данных Chrome (CrUX) нет: у сайта мало посетителей в Chrome.")
    print(f"Файл: {path}")
    return 0


def cmd_crux(args) -> int:
    body = {"formFactor": args.form_factor.upper()}
    if args.url:
        body["url"] = args.url
    else:
        body["origin"] = args.origin.rstrip("/")
    try:
        data = http_json("POST", CRUX_URL, body, headers=google_key_headers(), retries=1)
    except GscHttpError as exc:
        if exc.code == 404:
            print("CrUX: данных нет (у сайта мало посетителей в Chrome за 28 дней).")
            return 0
        if exc.code in (400, 401, 403):
            raise GscError(f"{exc}. Для CrUX нужен ключ API (PSI_API_KEY или network secret).") from None
        raise
    rec = data.get("record", {})
    rows = []
    for name, m in sorted(rec.get("metrics", {}).items()):
        p = (m.get("percentiles") or {}).get("p75", "")
        dens = [round(100 * (h.get("density") or 0)) for h in m.get("histogram", [])]
        rows.append([name, p, "/".join(map(str, dens))])
    period = rec.get("collectionPeriod", {})
    print(f"CrUX {body.get('url') or body.get('origin')} {body['formFactor']} "
          f"{period.get('firstDate', {})}..{period.get('lastDate', {})}")
    print_table(["metric", "p75", "good/ni/poor %"], rows)
    return 0


# --------------------------------------------------------------------------- cli

def add_period(p):
    p.add_argument("--days", type=int, default=28, help="длина периода, по умолчанию 28")
    p.add_argument("--start", help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD (по умолчанию сегодня-3: окончательные данные)")
    p.add_argument("--fresh", action="store_true", help="включить свежие неокончательные данные")
    p.add_argument("--type", default="web", choices=["web", "image", "video", "news", "discover", "googleNews"])
    p.add_argument("--country", help="ISO-3, например rus")
    p.add_argument("--device", choices=["desktop", "mobile", "tablet"])
    p.add_argument("--page-contains")
    p.add_argument("--query-contains")
    p.add_argument("--limit", type=int, default=STDOUT_ROWS, help="строк в выводе (файл полный)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    p = sub.add_parser("sites")
    p.add_argument("--refresh", action="store_true")
    p = sub.add_parser("perf")
    p.add_argument("--site", required=True)
    p.add_argument("--dims", default="query", help="query,page,date,device,country через запятую")
    p.add_argument("--compare", action="store_true", help="сравнить с прошлым периодом той же длины")
    p.add_argument("--brand", help="regex бренда, делит запросы на brand/nonbrand")
    add_period(p)
    p = sub.add_parser("quickwins")
    p.add_argument("--site", required=True)
    p.add_argument("--by", default="query", choices=["query", "page", "query-page"])
    p.add_argument("--min-pos", type=float, default=4)
    p.add_argument("--max-pos", type=float, default=20)
    p.add_argument("--min-impr", type=int, default=10)
    p.add_argument("--brand", help="regex бренда: такие запросы исключить")
    add_period(p)
    p.set_defaults(days=90)
    p = sub.add_parser("inspect")
    p.add_argument("--site", required=True)
    p.add_argument("urls", nargs="*")
    p.add_argument("--file")
    p.add_argument("--sitemap", help="URL sitemap.xml: проверить все адреса из него")
    p.add_argument("--max", type=int, default=100)
    p = sub.add_parser("sitemaps")
    p.add_argument("--site", required=True)
    p.add_argument("--submit", help="URL sitemap для отправки (нужен «Полный доступ»)")
    p = sub.add_parser("psi")
    p.add_argument("urls", nargs="+")
    p.add_argument("--strategy", default="mobile", choices=["mobile", "desktop", "both"])
    p = sub.add_parser("crux")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--origin")
    g.add_argument("--url")
    p.add_argument("--form-factor", default="phone", choices=["phone", "desktop", "tablet"])
    args = ap.parse_args(argv)
    handler = globals()["cmd_" + args.cmd]
    try:
        return handler(args)
    except GscError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
