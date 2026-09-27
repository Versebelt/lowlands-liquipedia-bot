#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /opt/lowlands-bot
if [[ ! -d /opt/lowlands-bot/app/.git ]]; then
  git clone https://github.com/Versebelt/lowlands-liquipedia-bot.git /opt/lowlands-bot/app
else
  git -C /opt/lowlands-bot/app pull --ff-only
fi

id lowlands-bot >/dev/null 2>&1 || useradd --system --home /opt/lowlands-bot --shell /usr/sbin/nologin lowlands-bot
python3 -m venv /opt/lowlands-bot/venv
/opt/lowlands-bot/venv/bin/pip install --no-cache-dir --upgrade pip
/opt/lowlands-bot/venv/bin/pip install --no-cache-dir -r /opt/lowlands-bot/app/requirements.txt
chown -R lowlands-bot:lowlands-bot /opt/lowlands-bot/app /opt/lowlands-bot/venv

install -m 0644 /opt/lowlands-bot/app/deploy/lowlands-bot.service /etc/systemd/system/lowlands-bot.service
systemctl daemon-reload
systemctl enable lowlands-bot.service
if [[ -f /opt/lowlands-bot/bot.env ]]; then
  chmod 0600 /opt/lowlands-bot/bot.env
  systemctl restart lowlands-bot.service
fi
