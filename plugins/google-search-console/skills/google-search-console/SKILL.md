---
name: google-search-console
description: |
  Google Search Console API и PageSpeed Insights / CrUX: клики, показы, CTR и
  позиции в Google по запросам и страницам, бренд/небренд, сравнение периодов,
  точки роста (позиции 4–20), проверка индексации страниц (URL Inspection),
  sitemap, скорость страниц. Только чтение, Python без зависимостей.
  Google Analytics не использует. Связка с yandex-webmaster, yandex-metrika,
  crawl4ai-seo.
  Triggers: google search console, gsc, search console api, позиции в google,
  запросы google, индексация google, url inspection, проверка индексации google,
  pagespeed, page speed, скорость сайта, core web vitals, crux, гугл вебмастер.
---

# google-search-console

Один скрипт `scripts/gsc.py`, Python 3 стандартной библиотеки + `openssl`.
Выводит в консоль не больше ~30 строк, полные таблицы кладёт в `cache/*.tsv`.

## Config

- Search Console: ключ сервисного аккаунта в `GSC_SERVICE_ACCOUNT_JSON`
  (JSON или base64) или `GSC_SERVICE_ACCOUNT_FILE`. E-mail сервисного аккаунта
  должен быть пользователем ресурса в Search Console (хватает «Ограниченного»).
- PageSpeed / CrUX: ключ API в `PSI_API_KEY` или network secret среды
  (заголовок `X-Goog-Api-Key` для `pagespeedonline.googleapis.com` и
  `chromeuxreport.googleapis.com`). Без ключа общая квота Google почти всегда
  исчерпана.
- Пошагово: [config/README.md](config/README.md).

Ключи не печатать, не записывать в файлы репозитория, не просить вставить в чат.

## Workflow

1. `python3 scripts/gsc.py doctor` — ключ, токен, список ресурсов, права.
2. Ресурс: `--site dentalharmony.ru` (скрипт сам выберет `sc-domain:` или
   `https://…/` из доступных) или точное имя ресурса.
3. Нужный отчёт ниже. Данные Search Console отстают на 2–3 дня, поэтому по
   умолчанию период заканчивается «сегодня − 3». `--fresh` берёт и свежие.

## Команды

| Команда | Что даёт | Ключевые параметры |
|---|---|---|
| `doctor` | проверка доступа | — |
| `sites` | ресурсы и права | `--refresh` |
| `perf` | клики, показы, CTR, позиция | `--dims query,page,date,device,country`, `--days 28`, `--start/--end`, `--compare`, `--brand REGEX`, `--country rus`, `--device mobile`, `--page-contains`, `--query-contains` |
| `quickwins` | запросы/страницы на позициях 4–20 | `--by query\|page\|query-page`, `--min-impr 10`, `--brand REGEX` (исключить), период 90 дней |
| `inspect` | в индексе ли страница, почему нет, канонический | URL списком, `--file`, `--sitemap URL`, `--max 100` |
| `sitemaps` | sitemap в Search Console | `--submit URL` (нужен «Полный доступ») |
| `psi` | PageSpeed: баллы, LCP/CLS/TBT, полевые данные, топ-3 улучшения | URL списком, `--strategy mobile\|desktop\|both` |
| `crux` | полевые данные Chrome за 28 дней | `--origin` или `--url`, `--form-factor phone` |

## Примеры

```bash
python3 scripts/gsc.py perf --site dentalharmony.ru --brand 'гармони|harmony|реутовская' --compare
python3 scripts/gsc.py perf --site dentalharmony.ru --dims page --days 90
python3 scripts/gsc.py perf --site dentalharmony.ru --dims date --days 90
python3 scripts/gsc.py quickwins --site dentalharmony.ru --brand 'гармони|harmony'
python3 scripts/gsc.py inspect --site dentalharmony.ru --sitemap https://dentalharmony.ru/sitemap.xml
python3 scripts/gsc.py psi https://dentalharmony.ru/ https://dentalharmony.ru/zapis/ --strategy both
```

## Как читать

- **Скрытые запросы.** Google не показывает редкие запросы ни в интерфейсе, ни в
  API. `perf --dims query` печатает, какая доля кликов видна. Небрендовый спрос
  малого сайта часто почти весь скрыт: смотри страницы (`--dims page`).
- **Бренд.** `--brand` делит видимые запросы на brand/nonbrand. Главная метрика
  SEO — небрендовые клики за 28 дней, Яндекс и Google отдельно.
- **inspect.** `verdict=PASS` — в индексе. Частые причины вне индекса:
  «Discovered – currently not indexed» (Google знает, но не обходил),
  «Crawled – currently not indexed» (обошёл, счёл слабой/дублем),
  «Page with redirect», «Not found (404)», «Alternate page with proper canonical
  tag». `canonicalMismatch=yes` — Google выбрал другой канонический.
- **Квоты.** URL Inspection: 2000 в день и 600 в минуту на ресурс. Search
  Analytics: до 25 000 строк за запрос, скрипт листает сам.
- **CrUX.** У сайтов с малым трафиком полевых данных нет (HTTP 404) — это норма,
  тогда опирайся на лабораторные цифры `psi`.

## Чего скилл не делает

- Не трогает Google Analytics (не подключаем: 152-ФЗ, трансграничная передача).
- Не использует Indexing API: Google разрешает его только для вакансий и
  трансляций.
- Не удаляет ресурсы, sitemap и не отправляет URL на удаление.
