#!/bin/sh
# Install the skills from this repository into ~/.claude/skills so that every
# Claude Code session on this machine/environment can use them.
#
# Usage:
#   sh install.sh                      # all skills
#   sh install.sh yandex-wordstat ...  # only the listed skills
#
# No secrets are stored here. Yandex Cloud (Wordstat, Search API) works through
# an API key injected by the environment's network proxy; Webmaster and Metrika
# read YANDEX_WEBMASTER_TOKEN / YANDEX_METRIKA_TOKEN from the environment.
# google-search-console reads GSC_SERVICE_ACCOUNT_JSON from the environment;
# its PageSpeed/CrUX key can be injected by the proxy (X-Goog-Api-Key).
set -eu

REPO_DIR=$(cd "$(dirname "$0")" && pwd)
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$DEST"

if [ "$#" -gt 0 ]; then
    SKILLS="$*"
else
    SKILLS=$(ls "$REPO_DIR/plugins")
fi

for s in $SKILLS; do
    src="$REPO_DIR/plugins/$s/skills/$s"
    if [ ! -d "$src" ]; then
        echo "skip: $s (not found)" >&2
        continue
    fi
    rm -rf "${DEST:?}/$s"
    cp -R "$src" "$DEST/$s"
    echo "installed: $s"
done

# Wordstat: API-key mode. The real key is injected by the proxy, so the local
# value only has to be non-empty. Do not put a real key here.
if [ -d "$DEST/yandex-wordstat" ]; then
    cfg="$DEST/yandex-wordstat/config"
    [ -f "$cfg/config.json" ] || printf '{\n  "auth": { "mode": "api_key" }\n}\n' > "$cfg/config.json"
    if [ ! -f "$cfg/.env" ]; then
        printf 'YANDEX_AI_API_KEY="injected-by-proxy"\n' > "$cfg/.env"
        chmod 600 "$cfg/.env"
    fi
fi
