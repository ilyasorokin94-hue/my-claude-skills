# Доступ к Google Search Console и PageSpeed

Нужно один раз, ~15 минут, в браузере на ПК. Биллинг (карта) не нужен: все три API
бесплатные. Ключи вставляешь ты сам, Claude их не видит в чате.

## 1. Проект Google Cloud

1. https://console.cloud.google.com/ → войти своим Google-аккаунтом (агентства).
2. Сверху «Выбрать проект» → «Создать проект», имя `claude-seo`. Организацию не
   выбирать. Если просит подключить оплату — пропустить.
3. «API и сервисы» → «Библиотека», включить три API:
   - Google Search Console API
   - PageSpeed Insights API
   - Chrome UX Report API

## 2. Сервисный аккаунт (для Search Console)

1. «IAM и администрирование» → «Сервисные аккаунты» → «Создать», имя `gsc-reader`.
   Роли проекта не давать, «Готово».
2. Открыть аккаунт → вкладка «Ключи» → «Добавить ключ» → «Создать» → JSON.
   Скачается файл вида `claude-seo-xxxx.json`. Это секрет: никуда не пересылать.
3. Скопировать e-mail аккаунта вида `gsc-reader@claude-seo-xxxx.iam.gserviceaccount.com`
   (e-mail не секрет).

## 3. Доступ в Search Console

https://search.google.com/search-console → ресурс сайта → «Настройки» →
«Пользователи и разрешения» → «Добавить пользователя» → e-mail из шага 2.3 →
разрешение «Ограниченный». Добавлять может только владелец ресурса.
Для каждого клиента агентства — то же самое, ключ один на все сайты.

## 4. Ключ API (для PageSpeed и CrUX)

«API и сервисы» → «Учётные данные» → «Создать учётные данные» → «Ключ API».
Затем «Изменить ключ» → «Ограничения API» → разрешить только PageSpeed Insights
API и Chrome UX Report API → «Сохранить».

## 5. Вставить в облачную среду Claude

Настройки проекта → облачная среда («Yandex api») → шестерёнка.

**Переменная окружения** (ключ сервисного аккаунта). Файл ключа многострочный,
поэтому вставляем его в base64. В PowerShell на ПК:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$HOME\Downloads\claude-seo-xxxx.json")) | Set-Clipboard
```

Потом в переменных среды новая строка:

```
GSC_SERVICE_ACCOUNT_JSON=<вставить из буфера>
```

**Network secret** (ключ API):
- хосты: `pagespeedonline.googleapis.com`, `chromeuxreport.googleapis.com`
- заголовок: `X-Goog-Api-Key`
- значение: ключ из шага 4

Файл JSON после этого удалить из «Загрузок».

## 6. Проверка

Новая сессия в этой среде → `python3 scripts/gsc.py doctor`.
Ожидается: «токен: Google выдал» и строка с ресурсом сайта.

## Если не получилось

- «invalid_grant / account not found» — ключ удалён или вставлен не целиком.
- HTTP 403 на ресурсе — e-mail сервисного аккаунта не добавлен в Search Console
  или выключен Search Console API.
- Нельзя создать ключ («Service account key creation is disabled») — проект создан
  внутри организации Google Workspace; создать проект без организации.
- Google Cloud не пускает аккаунт (проверка телефона, ограничения для РФ) —
  написать Claude: попробуем другой Google-аккаунт агентства.
