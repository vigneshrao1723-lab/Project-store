# Releasing v1.2.0 (palette and 3D background)

Nothing here has been run. `v1.2-palette` was cut from `release-v1.1.0`, so it contains v1.1.0 plus the palette work. `main` is still v1.0.0. The order matters: v1.1.0 goes first, then v1.2.0, so each release is a fast-forward and each can be tagged and, if CI turns red, reverted on its own.

Read `docs/RELEASE_STEPS.md` (v1.1.0) first; this file repeats only the commands. Run from PowerShell in the project folder, one block at a time.

## 0. Before you start

```powershell
cd "C:\Users\Vignesh T\Documents\Project Store"
git status                              # must say: nothing to commit, working tree clean
git fetch origin
git log --oneline -1 origin/main        # d04a0c4 until v1.1.0 is merged
git log --oneline -1 origin/release-v1.1.0
git log --oneline -1 origin/v1.2-palette
git merge-base --is-ancestor origin/release-v1.1.0 origin/v1.2-palette; $LASTEXITCODE    # 0 means v1.2-palette contains release-v1.1.0
```

## 1. Merge v1.1.0 first (skip if it is already in main)

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only release-v1.1.0
git push origin main
gh run list --branch main --limit 1
gh run watch                            # wait for green
git tag -a v1.1.0 -m "v1.1.0: site-wide scroll motion system, tuning layer, accessibility fixes"
git push origin v1.1.0
```

## 2. Then v1.2.0

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only v1.2-palette        # refuses to run unless it can fast-forward
git push origin main
gh run list --branch main --limit 1
gh run watch                            # test, security and build must pass; deploy runs on main
```

## 3. If CI is red: put main back without rewriting history

Revert only what v1.2.0 added; v1.1.0 stays:

```powershell
git revert --no-edit origin/release-v1.1.0..main      # one revert commit per palette commit, newest first
git push origin main
```

Fix the cause on `v1.2-palette`, then merge again with `git merge v1.2-palette` (not `--ff-only`, because `main` has moved). To undo v1.1.0 as well, use the revert block in `docs/RELEASE_STEPS.md`.

## 4. Tag v1.2.0 (only when CI on main is green)

```powershell
git tag -a v1.2.0 -m "v1.2.0: warm palette, tokens, contrast checks, 3D background"
git push origin v1.2.0
```

## 5. Rebuild the live stack from main

The live stack at `localhost:8001` runs `release-v1.1.0` today (it was not rebuilt for v1.2: see `docs/DECISIONS.md`, 09:25). Its database is in a Docker volume and the build does not touch it. **Never** run `docker compose down -v`.

```powershell
git checkout main
docker compose up -d --build --no-deps web sweeper
docker compose ps                       # web must show (healthy); wait up to a minute
docker compose exec web flask db current     # must print 0004 (head), unchanged
curl.exe -s http://localhost:8001/healthz     # {"status":"ok"}
```

## What to look at afterwards

Open `http://localhost:8001`: the home page should show the glowing background behind the hero and the pinned showcase; sign in and register the same; a paid order page too. Catalogue, product, cart, checkout and pay have a still gradient, admin is plain dark. Turn on "Reduce motion" in Windows: the background freezes to one frame. To switch the 3D off for good: `{ "off": ["bg3d"] }` in `app/fx.json`, rebuild.

## Commit hashes at the time of writing

| Branch | Commit |
|---|---|
| main (v1.0.0) | `d04a0c4` |
| release-v1.1.0 | `81428c7` |
| motion-3 | `2687ec9` |
| v1.2-palette | `git log --oneline -1 v1.2-palette` (the branch also holds this file, the screenshots and the notes on top of release-v1.1.0) |
