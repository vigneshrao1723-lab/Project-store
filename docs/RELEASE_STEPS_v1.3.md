# Releasing v1.1.0, v1.2.0 and v1.3.0

**Nothing in this file has been run.** It is run only after the owner replies "approved".

`main` is still v1.0.0 (`d04a0c4`). The three releases are stacked: `release-v1.1.0` (motion) → `v1.2-palette` (palette and 3D background, cut from release-v1.1.0) → `v1.3-contact` (contact block and order messages, cut from v1.2-palette). Each merge below is therefore a fast-forward, each release is tagged only after CI on `main` is green, and each can be reverted on its own.

Run from PowerShell in the project folder, one block at a time. Stop at the first block that does not do what its comments say.

## 0. Before you start

```powershell
cd "C:\Users\Vignesh T\Documents\Project Store"
git status                                   # must say: nothing to commit, working tree clean
git fetch origin
git log --oneline -1 origin/main             # d04a0c4
git log --oneline -1 origin/release-v1.1.0   # 81428c7
git log --oneline -1 origin/v1.2-palette     # 636ae8c
git log --oneline -1 origin/v1.3-contact     # the last commit of this branch
git merge-base --is-ancestor origin/release-v1.1.0 origin/v1.2-palette; $LASTEXITCODE   # 0
git merge-base --is-ancestor origin/v1.2-palette origin/v1.3-contact; $LASTEXITCODE     # 0
gh auth status                               # signed in, so the CI commands below work
```

## 1. v1.1.0: merge, wait for CI, tag

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only origin/release-v1.1.0
git push origin main
gh run list --branch main --limit 1
gh run watch                                 # test, security and build must all be green
git tag -a v1.1.0 -m "v1.1.0: site-wide scroll motion system, tuning layer, accessibility fixes"
git push origin v1.1.0
```

If CI is red, do not tag. Go to step 4 with `$base = "d04a0c4"`.

## 2. v1.2.0: merge, wait for CI, tag

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only origin/v1.2-palette
git push origin main
gh run list --branch main --limit 1
gh run watch                                 # must be green
git tag -a v1.2.0 -m "v1.2.0: warm palette, tokens, contrast checks, 3D background"
git push origin v1.2.0
```

If CI is red, do not tag. Go to step 4 with `$base = "v1.1.0"`.

## 3. v1.3.0: merge, wait for CI, tag

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only origin/v1.3-contact
git push origin main
gh run list --branch main --limit 1
gh run watch                                 # must be green (CI also runs the MySQL migration tests up to 0008)
git tag -a v1.3.0 -m "v1.3.0: home timeline, contact block, invoice and setup guide by email or WhatsApp"
git push origin v1.3.0
```

If CI is red, do not tag. Go to step 4 with `$base = "v1.2.0"`.

## 4. Only if CI is red: put main back with revert commits (no history rewrite)

`$base` is the last good point named in the step that failed. This reverts only the release that failed; the earlier, tagged ones stay.

```powershell
$base = "v1.2.0"                             # or "v1.1.0", or "d04a0c4", as the failed step says
git checkout main
git pull --ff-only origin main
git revert --no-edit "$base..main"           # one revert commit per commit of the failed release, newest first
git push origin main
gh run watch                                 # main must be green again
```

Fix the cause on the release branch, then merge it again with `git merge origin/v1.3-contact` (not `--ff-only`, because `main` has moved), wait for green and tag.

## 5. Rebuild the live stack from main (after step 3 is green and tagged)

The live stack at `http://localhost:8001` runs `release-v1.1.0` (`81428c7`) today, with its database at migration `0004`. Starting the new web container runs migrations `0005` to `0008` on that database (new tables `contact_messages`, `messages`, `contact_optouts`; new nullable columns on `orders` and `products`; nothing is dropped or rewritten) and `flask seed --if-empty` then corrects the seeded catalogue copy only where it was never edited. Take a backup first. **Never** run `docker compose down -v`.

```powershell
git checkout main
git pull --ff-only origin main
# the dump is written inside the container and copied out byte for byte (PowerShell 5.1's ">" would re-encode it as UTF-16)
docker compose exec -T db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines project_store > /tmp/before-v1.3.0.sql'
docker compose cp db:/tmp/before-v1.3.0.sql "..\ProjectStore-backups\before-v1.3.0.sql"
(Get-Item "..\ProjectStore-backups\before-v1.3.0.sql").Length    # must be well above zero
docker compose exec -T db rm /tmp/before-v1.3.0.sql
docker compose up -d --build --no-deps web sweeper
docker compose ps                            # web must show (healthy); wait up to a minute
docker compose exec web flask db current     # must print 0008 (head)
curl.exe -s http://localhost:8001/healthz    # {"status":"ok"}
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:8001/contact    # 200
```

To go back to the previous release after a bad rebuild: `git checkout v1.2.0` (or `v1.1.0`), then `docker compose exec web flask db downgrade 0004` **before** rebuilding with the older code, then `docker compose up -d --build --no-deps web sweeper`. The downgrade drops the v1.3 tables and columns (contact messages and outbox rows are lost; orders and payments are not touched). Restore from the backup only if something else went wrong.

## 6. After the rebuild (owner)

* Put `CONTACT_EMAIL`, `CONTACT_PHONE`, `CONTACT_CITY` (and `CONTACT_GITHUB`, `CONTACT_LINKEDIN` if you want those buttons) in `.env`, and `PUBLIC_BASE_URL` set to the address buyers use; rebuild with the same `docker compose up -d --build --no-deps web sweeper`.
* Switch on email and/or WhatsApp with `docs/NOTIFICATIONS.md`, then buy something with the practice gateway using your own address to see a real message arrive. Until then the order page truthfully says "Not sent".
* Set the real download links per product in Admin → Products.

## Commit hashes at the time of writing

| Branch | Commit |
|---|---|
| main (v1.0.0) | `d04a0c4` |
| release-v1.1.0 | `81428c7` |
| v1.2-palette | `636ae8c` |
| v1.3-contact | `git log --oneline -1 origin/v1.3-contact` (this file is on that branch, so its own hash cannot be written in it) |
