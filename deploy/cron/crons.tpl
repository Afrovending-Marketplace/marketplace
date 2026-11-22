# Same schedule as the preview scheduler (UTC). Each endpoint acknowledges 202 and runs the job in the background.
*/15 * * * * curl -fsS -m 20 -X POST -H "Authorization: Bearer __SECRET__" http://backend:8001/api/v1/cron/ops-tick > /dev/null
0 9 * * 1 curl -fsS -m 20 -X POST -H "Authorization: Bearer __SECRET__" http://backend:8001/api/v1/cron/low-stock-digest > /dev/null
0 10 * * * curl -fsS -m 20 -X POST -H "Authorization: Bearer __SECRET__" http://backend:8001/api/v1/cron/payout-release > /dev/null
