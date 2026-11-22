#!/bin/sh
# Builds the crontab from crons.tpl with the secret injected, then runs busybox crond in the foreground.
set -eu
apk add --no-cache curl >/dev/null
sed "s|__SECRET__|${WEBHOOK_CRON_SECRET}|g" /cron/crons.tpl > /etc/crontabs/root
chmod 600 /etc/crontabs/root
exec crond -f -l 8
