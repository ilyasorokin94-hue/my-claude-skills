# my-claude-skills

Набор скиллов Claude Code для работы с сайтами: семантика, SEO, Яндекс и Google.

| Скилл | Назначение | Доступ |
|---|---|---|
| `yandex-wordstat` | Спрос, семантика, сезонность, регионы | Ключ Yandex Cloud (через прокси среды) |
| `yandex-search-api` | Выдача Яндекса, конкуренты | Ключ Yandex Cloud |
| `crawl4ai-seo` | Технический SEO-аудит сайта | Не нужен |
| `yandex-webmaster` | Индексация, запросы, сайтмапы, переобход | `YANDEX_WEBMASTER_TOKEN` |
| `yandex-metrika` | Трафик и конверсии | `YANDEX_METRIKA_TOKEN` |
| `google-search-console` | Google: запросы, страницы, индексация, sitemap, PageSpeed | `GSC_SERVICE_ACCOUNT_JSON`, ключ API (network secret) |
| `yandex-maps-analysis` | Яндекс Карты: один цикл ведения карточки клиники (знакомство, накопление базы, разбор раз в 2 недели, пересмотр раз в квартал), отзывы, новости, фото; база знаний растёт после каждого запуска | `YANDEX_METRIKA_TOKEN` (счётчик карточки); кабинет и карточки через Chrome на ПК; `TG_BOT_TOKEN` и `TG_CHAT_ID` на ПК для сводки обхода отзывов |
| `seo-vedenie` | SEO-ведение сайта клиники: один цикл (знакомство со стартовым аудитом, разбор раз в 2 недели, пересмотр раз в квартал), сверка внесённых правок, замеры через 14, 28 и 56 дней, ТЗ на правки для менеджера проекта; база знаний растёт после каждого запуска | Свой не нужен: цифры берёт через `yandex-webmaster`, `yandex-metrika`, `google-search-console` (их токены) или через Chrome на ПК; спрос и выдача из облака |

Скиллы взяты из [artwist-polyakov/polyakov-claude-skills](https://github.com/artwist-polyakov/polyakov-claude-skills)
(MIT, см. `LICENSE`) и адаптированы (кроме `google-search-console`: написан здесь, идеи взяты из
[AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo), MIT; `yandex-maps-analysis` и `seo-vedenie`: написаны здесь
по опыту агентства):

- `yandex-wordstat`: в режиме API-ключа ID каталога Yandex Cloud необязателен.

## Установка

Облачная среда Claude Code → Edit → Setup script:

```bash
git clone --depth 1 https://github.com/ilyasorokin94-hue/my-claude-skills /opt/my-claude-skills
sh /opt/my-claude-skills/install.sh
```

Только часть скиллов: `sh install.sh yandex-wordstat crawl4ai-seo`.

Локально: `git clone` и `sh install.sh` — скиллы попадут в `~/.claude/skills`.

## Секреты

Никаких ключей в репозитории. Токены задаются в настройках среды (Network secrets
или переменные окружения). Файлы `config/.env`, `config/config.json` и ключи
сервисных аккаунтов внутри скиллов игнорируются git.
