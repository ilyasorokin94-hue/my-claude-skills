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

Скиллы взяты из [artwist-polyakov/polyakov-claude-skills](https://github.com/artwist-polyakov/polyakov-claude-skills)
(MIT, см. `LICENSE`) и адаптированы (кроме `google-search-console`: написан здесь, идеи взяты из
[AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo), MIT):

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
