# Releasing v1.1.0, v1.2.0, v1.3.0 and v1.4.0

**Nothing in this file has been run.** It is run only after the owner replies "approved".

`main` is still v1.0.0 (`d04a0c4`). The four releases are stacked: `release-v1.1.0` (motion) -> `v1.2-palette`
(palette and 3D background) -> `v1.3-contact` (contact block and order messages) -> `v1.4-final` (policies, cookie
notice, map, shelf loop, security re-check, least-privilege database account). Each merge below is a fast-forward, each
release is tagged only after CI on `main` is green, and each can be reverted on its own.

Run from PowerShell in the project folder, one block at a time. Stop at the first block that does not do what its
comments say.

## 0. Before you start (owner)

1. Install the GitHub CLI (`winget install GitHub.cli`) and sign in (`gh auth login`); the CI commands below need it.
2. Add the rows-only database password to `.env` (any long URL-safe random value):
   ```powershell
   python -c "import secrets; print('DB_APP_PASSWORD=' + secrets.token_urlsafe(24))"
   ```
   Paste the printed line into `.env`. Until it is there, every `docker compose` command in this folder stops with
   "Set DB_APP_PASSWORD in .env" (the running containers are not affected).
3. Check `.env` also has `CONTACT_NAME`, `CONTACT_EMAIL`, `CONTACT_PHONE`, `CONTACT_CITY`, `SELLER_NAME`,
   `SELLER_ADDRESS` (written there in v1.4) and set `PUBLIC_BASE_URL` to the address buyers use (for the live stack on
   this machine: `http://localhost:8001`).

```powershell
cd "C:\Users\Vignesh T\Documents\Project Store"
git status                                   # must say: nothing to commit, working tree clean
git fetch origin
git log --oneline -1 origin/main             # d04a0c4
git log --oneline -1 origin/release-v1.1.0   # 81428c7
git log --oneline -1 origin/v1.2-palette     # 636ae8c
git log --oneline -1 origin/v1.3-contact     # 2ce0925
git log --oneline -1 origin/v1.4-final       # the last commit of this branch
git merge-base --is-ancestor origin/release-v1.1.0 origin/v1.2-palette; $LASTEXITCODE   # 0
git merge-base --is-ancestor origin/v1.2-palette origin/v1.3-contact; $LASTEXITCODE     # 0
git merge-base --is-ancestor origin/v1.3-contact origin/v1.4-final; $LASTEXITCODE       # 0
gh auth status
```

## 1 to 4. Merge, wait for CI, tag, one release at a time

For each row, in order:

| Step | Branch | Tag | Message |
|---|---|---|---|
| 1 | `origin/release-v1.1.0` | `v1.1.0` | `v1.1.0: site-wide scroll motion system, tuning layer, accessibility fixes` |
| 2 | `origin/v1.2-palette` | `v1.2.0` | `v1.2.0: warm palette, tokens, contrast checks, 3D background` |
| 3 | `origin/v1.3-contact` | `v1.3.0` | `v1.3.0: home timeline, contact block, invoice and setup guide by email or WhatsApp` |
| 4 | `origin/v1.4-final` | `v1.4.0` | `v1.4.0: policies, cookie notice, map, shelf loop, security re-check, rows-only database account` |

```powershell
$branch = "origin/v1.4-final"; $tag = "v1.4.0"; $msg = "v1.4.0: policies, cookie notice, map, shelf loop, security re-check, rows-only database account"
git checkout main
git pull --ff-only origin main
git merge --ff-only $branch
git push origin main
gh run list --branch main --limit 1
gh run watch                                 # test, security, secrets and build must all be green
git tag -a $tag -m $msg
git push origin $tag
```

If CI is red, do not tag; go to step 5 with `$base` = the previous tag (`d04a0c4` for v1.1.0).

## 5. Only if CI is red: put main back with revert commits (no history rewrite)

```powershell
$base = "v1.3.0"                             # the last good tag before the failed release
git checkout main
git pull --ff-only origin main
git revert --no-edit "$base..main"
git push origin main
gh run watch                                 # main must be green again
```

Fix the cause on the release branch, merge it again with `git merge` (not `--ff-only`), wait for green and tag.

## 6. Rebuild the live stack from main (after step 4 is green and tagged)

The live stack at `http://localhost:8001` runs `release-v1.1.0` (`81428c7`) with its database at migration `0004`.
v1.4 brings migrations `0005` to `0009` (new tables `contact_messages`, `messages`, `contact_optouts`; new nullable
columns on `orders` and `products`; nothing dropped or rewritten) and a new database account. Take a backup first.
**Never** run `docker compose down -v`.

```powershell
git checkout main
git pull --ff-only origin main
# 6a. Backup FIRST: the dump is written inside the container and copied out byte for byte
New-Item -ItemType Directory -Force "..\ProjectStore-backups" | Out-Null
# row counts before, to compare after (the root password stays in the container's environment, never on the screen)
docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -e "SELECT (SELECT COUNT(*) FROM project_store.users), (SELECT COUNT(*) FROM project_store.orders), (SELECT COUNT(*) FROM project_store.products), (SELECT COUNT(*) FROM project_store.inventory_log)"'
docker compose exec -T db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines project_store > /tmp/before-v1.4.0.sql'
docker compose cp db:/tmp/before-v1.4.0.sql "..\ProjectStore-backups\before-v1.4.0.sql"
(Get-Item "..\ProjectStore-backups\before-v1.4.0.sql").Length    # must be well above zero
docker compose exec -T db rm /tmp/before-v1.4.0.sql
(Select-String -Path "..\ProjectStore-backups\before-v1.4.0.sql" -Pattern "CREATE TABLE").Count   # must be 9 or more (one per table)

# 6b. The rows-only account. An init script only runs on a NEW volume, so on the live database run the same script by
#     hand. Recreating the db container (the data volume stays; this is NOT down -v) gives it the script mount and
#     DB_APP_PASSWORD from .env. The script reads the passwords from the container's environment; nothing is typed or shown.
docker compose up -d --no-deps --force-recreate db
docker compose ps db                         # wait for (healthy)
docker compose exec -T db bash /docker-entrypoint-initdb.d/10-app-user.sh
#   10-app-user.sh: created store_app with SELECT, INSERT, UPDATE, DELETE on project_store
"SHOW GRANTS FOR store_app;" | docker compose exec -T db bash -c 'MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql -uroot -N'
#   GRANT USAGE ON *.* TO `store_app`@`%`
#   GRANT SELECT, INSERT, UPDATE, DELETE ON `project_store`.* TO `store_app`@`%`

# 6c. Migrate as the owner (one-shot), then start web and sweeper as store_app
docker compose up -d --build migrate web sweeper
docker compose logs migrate | Select-Object -Last 3   # ends with: 0009 (head)
docker compose ps                            # web (healthy), sweeper running, migrate exited 0
curl.exe -s http://localhost:8001/healthz    # {"status":"ok"}
foreach ($p in "/", "/contact", "/privacy", "/cookies", "/sitemap.xml") { curl.exe -s -o NUL -w "$p %{http_code}`n" "http://localhost:8001$p" }   # all 200
docker compose exec web python -c "from app import create_app; from app.extensions import db; a=create_app(); c=a.app_context(); c.push(); print(db.session.execute(db.text('SELECT CURRENT_USER()')).scalar())"   # store_app@%
# row counts after: the same four numbers as before 6a (nothing is rewritten; only new tables and columns are added)
docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -e "SELECT (SELECT COUNT(*) FROM project_store.users), (SELECT COUNT(*) FROM project_store.orders), (SELECT COUNT(*) FROM project_store.products), (SELECT COUNT(*) FROM project_store.inventory_log)"'
```

### Going back after a bad rebuild

Run the downgrade with the **new** code (the old code does not know migrations 0005 to 0009), as the owner account:

```powershell
docker compose run --rm migrate flask db downgrade 0004
git checkout v1.1.0                          # or the release you want
docker compose up -d --build --no-deps web sweeper
```

The downgrade drops the v1.3 and v1.4 tables and columns (contact messages, the outbox, opt-outs and the terms
timestamp are lost; orders and payments are not touched). Restore `before-v1.4.0.sql` only if something else went
wrong (`Get-Content -Raw "..\ProjectStore-backups\before-v1.4.0.sql" | docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" project_store'`).

## 7. After the rebuild (owner)

* Switch on email and/or WhatsApp with `docs/NOTIFICATIONS.md`, then buy something with the practice gateway using your
  own address to see a real message arrive.
* Optional: enable the secret-scanning hook in your clone: `git config core.hooksPath scripts/hooks`.
* Read the policy pages (`/privacy`, `/terms`, `/refunds`, `/delivery`, `/cookies`) and have them reviewed; each says it
  is an unreviewed template until you change that line.

## Commit hashes at the time of writing

| Branch | Commit |
|---|---|
| main (v1.0.0) | `d04a0c4` |
| release-v1.1.0 | `81428c7` |
| v1.2-palette | `636ae8c` |
| v1.3-contact | `2ce0925` |
| v1.4-final | `git log --oneline -1 origin/v1.4-final` (this file is on that branch, so its own hash cannot be written in it) |
