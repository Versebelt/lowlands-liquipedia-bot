#!/usr/bin/env bash
set -euo pipefail
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git python3 python3-venv
curl -fsSL https://raw.githubusercontent.com/Versebelt/lowlands-liquipedia-bot/main/deploy/install-native.sh -o /tmp/install-lowlands-bot.sh
bash /tmp/install-lowlands-bot.sh
