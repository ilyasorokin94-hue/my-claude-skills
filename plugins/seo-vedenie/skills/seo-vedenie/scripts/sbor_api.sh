#!/usr/bin/env bash
# Сбор цифр клиники через API-скиллы агентства за один запуск. Только чтение.
#
#   bash sbor_api.sh --host <домен> --counter <id Метрики> --brand '<регулярка бренда>' \
#        --out <папка seo/dannye/ГГГГ-ММ/api-ДД базы клиники> \
#        [--goals 'id,id'] [--gsc-site <домен>] [--region <id Вордстата>] \
#        [--phrases 'фраза1;фраза2'] [--date2 ГГГГ-ММ-ДД]
#
# Нужны токены API-скиллов в окружении (YANDEX_WEBMASTER_TOKEN, YANDEX_METRIKA_TOKEN,
# YANDEX_AI_API_KEY, GSC_SERVICE_ACCOUNT_FILE или _JSON). Ключи не выводятся.
# Чего нет в API (запрос индексации в Google, ссылки и статистика сканирования Google,
# часть отчётов Вебмастера), скрипт не трогает: это Chrome по компасу 2.
set -u
S="${S:-$HOME/.claude/skills}"
HOST="" COUNTER="" BRAND="" OUT="" GOALS="" GSC="" REGION="" PHRASES="" DATE2=""
while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --counter) COUNTER="$2"; shift 2 ;;
        --brand) BRAND="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        --goals) GOALS="$2"; shift 2 ;;
        --gsc-site) GSC="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --phrases) PHRASES="$2"; shift 2 ;;
        --date2) DATE2="$2"; shift 2 ;;
        *) echo "неизвестный параметр: $1" >&2; exit 2 ;;
    esac
done
[ -n "$HOST" ] && [ -n "$OUT" ] || { echo "нужны --host и --out" >&2; exit 2; }
GSC="${GSC:-$HOST}"
mkdir -p "$OUT"

# На Windows «python3» бывает заглушкой Microsoft Store, а скиллы зовут python3.
if ! python3 -c "" >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
    python3() { python "$@"; }
    export -f python3
fi
export PYTHONIOENCODING=utf-8

# Периоды: 28 полных дней, закончившихся 3 дня назад, и предыдущие 28.
D2="${DATE2:-$(python3 -c 'import datetime as d;print(d.date.today()-d.timedelta(days=3))')}"
D1=$(python3 -c "import datetime as d;print(d.date.fromisoformat('$D2')-d.timedelta(days=27))")
P2=$(python3 -c "import datetime as d;print(d.date.fromisoformat('$D1')-d.timedelta(days=1))")
P1=$(python3 -c "import datetime as d;print(d.date.fromisoformat('$P2')-d.timedelta(days=27))")
H1=$(python3 -c "import datetime as d;print(d.date.fromisoformat('$P1')-d.timedelta(days=28))")
echo "Период: $D1..$D2 против $P1..$P2"

sec() { echo; echo "### $*"; }
log() { tee -a "$OUT/sbor.log"; }
: > "$OUT/sbor.log"

if [ -n "${YANDEX_WEBMASTER_TOKEN:-}" ]; then
    W="$S/yandex-webmaster"
    ( cd "$W" || exit
      sec "Вебмастер: сводка и диагностика"; bash scripts/summary.sh --host "$HOST" 2>&1 | head -20
      sec "Вебмастер: все запросы по дням (показы, клики, позиция)"; bash scripts/queries_history.sh --host "$HOST" --date-from "$H1" --date-to "$D2" 2>&1 | tail -4
      f=$(ls -t cache/host_*"${HOST}"*/queries/history_*.tsv 2>/dev/null | head -1); [ -n "$f" ] && cp "$f" "$OUT/yandex-vse-zaprosy-po-dnyam.tsv"
      sec "Вебмастер: запросы за 14 дней (средние в день)"; bash scripts/query_analytics.sh --host "$HOST" --text-indicator QUERY --limit 500 --no-cache 2>&1 | tail -2
      f=$(ls -t cache/host_*"${HOST}"*/queries/analytics_*.tsv 2>/dev/null | head -1); [ -n "$f" ] && cp "$f" "$OUT/yandex-zaprosy-14dn.tsv"
      bash scripts/query_analytics.sh --host "$HOST" --text-indicator URL --limit 500 --no-cache 2>&1 | tail -2
      f=$(ls -t cache/host_*"${HOST}"*/queries/analytics_*.tsv 2>/dev/null | head -1); [ -n "$f" ] && cp "$f" "$OUT/yandex-stranicy-14dn.tsv"
      sec "Вебмастер: страницы в поиске"; bash scripts/insearch.sh --host "$HOST" --action history --date-from "$P1" 2>&1 | tail -6
      sec "Вебмастер: появление и выпадение страниц"; bash scripts/search_events.sh --host "$HOST" --action samples --limit 100 2>&1 | head -30
      sec "Вебмастер: ИКС"; bash scripts/sqi_history.sh --host "$HOST" --date-from "$P1" 2>&1 | tail -3
      sec "Вебмастер: sitemap"; bash scripts/sitemaps.sh --host "$HOST" --action list 2>&1 | head -6
      sec "Вебмастер: квота переобхода"; bash scripts/recrawl.sh --host "$HOST" --action quota 2>&1 | head -4
    ) 2>&1 | log
else
    echo "Вебмастер: токена нет, шаги Я1-Я12 в Chrome" | log
fi

if [ -n "${YANDEX_METRIKA_TOKEN:-}" ] && [ -n "$COUNTER" ]; then
    ( cd "$S/yandex-metrika" || exit
      for P in "$D1 $D2" "$P1 $P2"; do
          set -- $P
          sec "Метрика $1..$2: поисковые системы"
          bash scripts/search_engines.sh --counter "$COUNTER" --date1 "$1" --date2 "$2" --csv "$OUT/metrika-poisk-$1.csv" 2>&1 | head -8
          if [ -n "$GOALS" ]; then
              sec "Метрика $1..$2: цели по переходам из поиска"
              bash scripts/conversions.sh --counter "$COUNTER" --date1 "$1" --date2 "$2" --goals "$GOALS" --source organic --csv "$OUT/metrika-celi-poisk-$1.csv" 2>&1 | head -6
          fi
      done
      sec "Метрика: источники за период"; bash scripts/traffic_summary.sh --counter "$COUNTER" --date1 "$D1" --date2 "$D2" --csv "$OUT/metrika-istochniki.csv" 2>&1 | head -10
    ) 2>&1 | log
else
    echo "Метрика: нет токена или номера счётчика, шаги в Chrome" | log
fi

if [ -n "${GSC_SERVICE_ACCOUNT_FILE:-}${GSC_SERVICE_ACCOUNT_JSON:-}" ]; then
    ( cd "$S/google-search-console" || exit
      sec "Search Console: запросы, сравнение периодов, бренд отдельно"
      python3 scripts/gsc.py perf --site "$GSC" --start "$D1" --end "$D2" --compare ${BRAND:+--brand "$BRAND"} 2>&1 | head -12
      sec "Search Console: страницы"
      python3 scripts/gsc.py perf --site "$GSC" --start "$D1" --end "$D2" --dims page 2>&1 | head -30
      f=$(ls -t cache/perf_*"${GSC}"*_page_*.tsv 2>/dev/null | head -1); [ -n "$f" ] && cp "$f" "$OUT/google-stranicy.tsv"
      sec "Search Console: точки роста"
      python3 scripts/gsc.py quickwins --site "$GSC" ${BRAND:+--brand "$BRAND"} 2>&1 | head -15
      sec "Search Console: индекс по адресам sitemap"
      python3 scripts/gsc.py inspect --site "$GSC" --sitemap "https://$GSC/sitemap.xml" --max 300 2>&1 | head -40
      f=$(ls -t cache/inspect_*"${GSC}"*.tsv 2>/dev/null | head -1); [ -n "$f" ] && cp "$f" "$OUT/google-indeks.tsv"
      sec "Search Console: sitemap"; python3 scripts/gsc.py sitemaps --site "$GSC" 2>&1 | head -5
    ) 2>&1 | log
else
    echo "Search Console: ключа нет, шаги G1-G9 в Chrome" | log
fi

if [ -n "${YANDEX_AI_API_KEY:-}" ] && [ -n "$REGION" ] && [ -n "$PHRASES" ]; then
    ( cd "$S/yandex-wordstat" || exit
      sec "Вордстат, регион $REGION"
      IFS=';'
      for ph in $PHRASES; do
          bash scripts/top_requests.sh --phrase "$ph" --regions "$REGION" --limit 10 2>&1 \
              | awk '/^=== Associations/{exit} /^Phrase:|^Total count|^\| [0-9]+ \|/'
      done
    ) 2>&1 | log
fi

echo
echo "Готово. Выгрузки: $OUT, полный вывод: $OUT/sbor.log"
