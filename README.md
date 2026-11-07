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

Облачная среда Claude Code → Edit → Setup script. Полный вариант, как в рабочей среде агентства:

```bash
git clone --depth 1 https://github.com/ilyasorokin94-hue/my-claude-skills /opt/my-claude-skills
sh /opt/my-claude-skills/install.sh
python3 -c "import json,os;p=os.path.expanduser('~/.claude/skills/yandex-search-api/config/');c=json.load(open(p+'config.example.json'));c['yandex_cloud_folder_id']='<ID каталога Yandex Cloud>';c['auth']={'mode':'api_key'};json.dump(c,open(p+'config.json','w'),ensure_ascii=False,indent=2)"
(cd ~/.claude/skills/crawl4ai-seo && UV=$(command -v uv || echo ~/.local/bin/uv) && PWV=$(node -p "require('playwright/package.json').version") && $UV venv .venv --python 3.12 && $UV pip install --python .venv/bin/python "crawl4ai>=0.8,<0.9" "playwright==$PWV" beautifulsoup4)
```

Третья строка пишет настройки yandex-search-api (ID каталога не секрет, но в репозиторий его не кладём). Четвёртая собирает окружение краулера с playwright той же версии, что браузер, предустановленный в среде; краулер запускается через `.venv/bin/python` (см. SKILL.md crawl4ai-seo).

Только часть скиллов: `sh install.sh yandex-wordstat crawl4ai-seo`.

### Что ещё настроить в среде

| Где | Что | Для чего |
|---|---|---|
| Environment variables | `YANDEX_METRIKA_TOKEN`, `YANDEX_WEBMASTER_TOKEN` | Метрика и Вебмастер; значение подставляет прокси, в переменной заглушка |
| Environment variables | `YANDEX_AI_API_KEY` | Вордстат и поиск Яндекса (Yandex Cloud); значение подставляет прокси |
| Environment variables | `GSC_SERVICE_ACCOUNT_JSON` | ключ сервисного аккаунта Google Search Console |
| Network secrets | заголовок `Authorization` для api-metrika.yandex.net, api.webmaster.yandex.net и searchapi.api.cloud.yandex.net | настоящие токены и ключи; их вписывает владелец, не Claude |
| Network access → Allowed domains | домены сайтов клиентов и их конкурентов | без этого краулер и проверки живых сайтов получают 403 |

Токен Метрики и Вебмастера выпускается на аккаунт агентства в Яндексе: новый клиент даёт этому аккаунту доступ к счётчику и сайту, и токен видит их без новых ключей.

Локально: `git clone` и `sh install.sh` — скиллы попадут в `~/.claude/skills`.

## Секреты

Никаких ключей в репозитории. Токены задаются в настройках среды (Network secrets
или переменные окружения). Файлы `config/.env`, `config/config.json` и ключи
сервисных аккаунтов внутри скиллов игнорируются git.
