# Releasing v1.1.0

Nothing here has been run. `main` is still v1.0.0 (`d04a0c4`). `release-v1.1.0` is 20 commits ahead of it and `main` is its ancestor, so the merge is a fast-forward: no merge commit, and `main`'s existing history is untouched.

Run these from PowerShell in the project folder, one block at a time, and read each result before the next.

## 0. Before you start

```powershell
cd "C:\Users\Vignesh T\Documents\Project Store"
git status                      # must say: nothing to commit, working tree clean
git fetch origin
git log --oneline -1 origin/main        # must be d04a0c4
git log --oneline -1 origin/release-v1.1.0
```

Optional rehearsal that does not touch `main`: open a pull request from `release-v1.1.0` into `main` (`gh pr create --base main --head release-v1.1.0 --title "v1.1.0" --body "Scroll motion system, tuning layer, accessibility fixes."`). CI runs on pull requests, so you see the result before anything merges. Close it afterwards (`gh pr close <number>`) if you then merge by hand as below.

## 1. Fast-forward merge into main and push

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only release-v1.1.0     # refuses to run unless it can fast-forward
git push origin main
```

## 2. Watch CI

```powershell
gh run list --branch main --limit 1
gh run watch                            # pick the newest run; it follows the test, security and build jobs
```

CI on `main` also runs `deploy`, which pushes the image to GitHub Container Registry. It must go green before you tag.

## 3. If CI is red: put main back, without rewriting history

Do not force-push. Add revert commits instead:

```powershell
git revert --no-edit d04a0c4..main      # one revert commit per release commit, newest first
git push origin main
```

`main` then has the v1.0.0 content again, plus the history of what happened. Fix the cause on `release-v1.1.0`, then start again at step 1 (merge with `git merge release-v1.1.0`, not `--ff-only`, because `main` has moved).

## 4. Tag v1.1.0 (only when CI on main is green)

```powershell
git tag -a v1.1.0 -m "v1.1.0: site-wide scroll motion system, tuning layer, accessibility fixes"
git push origin v1.1.0
```

Optional: `gh release create v1.1.0 --title "v1.1.0" --notes-file CHANGELOG.md` (the notes would be the whole changelog; edit down to the 1.1.0 section if you prefer).

## 5. Rebuild the live stack from main

The live stack is the Docker Compose stack on `localhost:8001` (the port comes from `WEB_PORT` in your `.env`). Its database lives in a Docker volume and the build does not touch it. **Never** run `docker compose down -v`.

```powershell
git checkout main
docker compose up -d --build --no-deps web sweeper    # --no-deps leaves the database container alone
docker compose ps                       # web must show (healthy); wait up to a minute
docker compose exec web flask db current     # must print 0004 (head), the same as before
curl.exe -s http://localhost:8001/healthz     # {"status":"ok"}
```

## What to check in the browser afterwards

Open `http://localhost:8001`, scroll the home page (the pinned showcase has three scenes), add a project to the cart, check out, and use "Simulate a declined card" and then "Pay (test)" on the pay page. The page should look like `docs/screenshots/*.png`.

## Commit hashes at the time of writing

| Branch | Commit |
|---|---|
| main (v1.0.0) | `d04a0c4` |
| motion-2 (unmerged, kept) | `462b067` |
| motion-3 | `2687ec9` |
| release-v1.1.0 | see `git log --oneline -1 release-v1.1.0` (it holds the docs, screenshots and this file on top of motion-3) |
