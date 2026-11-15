#!/bin/bash
# Runs once, when MySQL initialises an EMPTY data volume (docker-entrypoint-initdb.d); an existing database is never
# touched by it. Creates the least-privilege account the web app and the sweeper connect as: rows only
# (SELECT, INSERT, UPDATE, DELETE) on the store's own schema. No CREATE, ALTER, DROP, INDEX, GRANT, FILE, SUPER or
# PROCESS, and nothing on any other schema. Schema changes run as the owner account in the one-shot "migrate" service.
# For an existing database the same two statements are in docs/RELEASE_STEPS_v1.4.md, to run by hand.
# The root password goes through the environment (MYSQL_PWD), never on a command line where `ps` would show it.
if [ -z "${DB_APP_PASSWORD:-}" ]; then
  echo "10-app-user.sh: DB_APP_PASSWORD is not set; refusing to create an account without a password" >&2
  exit 1
fi
if ! MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -uroot <<EOSQL
CREATE USER IF NOT EXISTS 'store_app'@'%' IDENTIFIED BY '${DB_APP_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${MYSQL_DATABASE}\`.* TO 'store_app'@'%';
EOSQL
then
  echo "10-app-user.sh: could not create store_app" >&2
  exit 1
fi
echo "10-app-user.sh: created store_app with SELECT, INSERT, UPDATE, DELETE on ${MYSQL_DATABASE}"
