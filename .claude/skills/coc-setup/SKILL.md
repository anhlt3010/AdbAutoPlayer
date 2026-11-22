---
name: coc-setup
description: Build the Windows setup installer (NSIS .exe) of AdbAutoPlayer that contains only Clash of Critters. Use when the user asks to release, build or export a CoC-only setup, installer or full app (not the patch zip). Always asks for the version first.
---

# Clash of Critters only setup

Builds `CocAutoPlayer_<X.Y.Z>_x64-setup.exe` with every other game removed. For the python-only patch zip use the `coc-patch` skill instead.

## Step 1 - pull, then ask the version

```bash
git pull --ff-only
git fetch --tags origin
git tag --list "coc-vn-setup-v*" --sort=-v:refname | head -3
git status --short
```

- If the pull is not a fast-forward, stop and tell the user.
- Warn if `git status` shows uncommitted changes: the build packages `HEAD` only.
- Ask the user for the version (`X.Y.Z`, leading `v` ignored) and show the latest tag as a hint. Do not guess. The tag is `coc-vn-setup-v<X.Y.Z>`; stop if it already exists.

## Step 2 - check prerequisites

- `src-tauri/pyembed/python/python.exe` exists (git-ignored; created as in `.github/workflows/publish.yaml`, "Download python-build-standalone").
- `node_modules/` exists (`pnpm install`).
- `uv`, `node`, `pnpm`, `cargo` are on PATH.

If something is missing, tell the user instead of improvising.

## Step 3 - build

The first build recompiles the app crate and takes about 10 minutes; run it in the background and wait for the notification.

```bash
python scripts/build_coc_setup.py <version>
```

What the script does (all in a staging copy at `../../coc_setup_build/src`, the repo is never touched):

- exports `HEAD` with `git archive`, deletes every game folder except `clash_of_critters` and the seed `AFKJourney.toml`
- gives the app its own identity (`productName`/`mainBinaryName` `CocAutoPlayer`, identifier `com.anhlt3010.CocAutoPlayer`) so it installs beside an existing AdbAutoPlayer: separate install folder, shortcuts, uninstall entry and settings folder (`%APPDATA%\com.anhlt3010.CocAutoPlayer`); never change these between releases or updates and settings break
- swaps the visible name to `CocAutoPlayer` in the tray menu and tooltip, crash log file and dialog title, Discord webhook username and the UI brand name (the `REBRAND` list in the script; if upstream changes one of those lines the script stops and the list needs updating)
- regenerates all app icons with `pnpm tauri icon` from `scripts/coc_icon.png` (or `--icon <png>`); without an image the original icon is kept and a warning is printed. Ask the user for a square PNG, 1024 px recommended
- ships the MIT `LICENSE` inside the install folder (the license requires the notice to stay with copies)
- sets the version, points the updater endpoint to the `anhlt3010` fork (so the app never self-updates to the full upstream app) and turns off updater artifacts (no signing key needed)
- copies `pyembed`, installs the stripped package into it, regenerates `tauri.bundle.templates.json`, runs `pnpm tauri build` with `tauri.bundle.windows.json`
- output: `CocAutoPlayer_<version>_x64-setup.exe`, two levels above the repo (override with `--out`)

`--stage-only` stops after staging, useful to inspect what will be packaged.

### Updatable build (`--updater`)

Ask the user which kind they want. The updatable build is signed with the user's own key and also produces `.sig` and `latest.json`:

```bash
export TAURI_SIGNING_PRIVATE_KEY="<path or content of the .key file>"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="<password>"
python scripts/build_coc_setup.py <version> --updater --pubkey-file <file>.key.pub
```

- Never print, commit or log the private key or password. If the env vars or the `.pub` file are missing, point the user to the one-time setup below and stop.
- The release must be a GitHub release on `anhlt3010/AdbAutoPlayer` with tag `coc-vn-setup-v<X.Y.Z>` holding three assets: the `.exe`, the `.exe.sig` and `latest.json`.
- The updater reads `releases/latest/download/latest.json`, so the setup release must be the repo's latest release. Mark `coc-vn-v*` patch releases as pre-release, otherwise they shadow it.
- Every new version must be higher than the one installed, or the app sees no update.

One-time setup for the user: `pnpm tauri signer generate -w <path>/coc.key` (set a password), then keep the key file safe. Losing it means installed apps can never update again.

## Step 4 - verify

- Confirm the exe exists and show its size (the full app is about 160 MB).
- Confirm the staged games folder holds only `clash_of_critters` and that the build log has no `afk_journey` resource entries.
- Tell the user it was not run on a device; recommend installing it once on a machine that already has AdbAutoPlayer, to check that both coexist and only Clash of Critters appears. `mainBinaryName` is untested with pytauri; if the app fails to start, drop that line from the script first.

## Step 5 - release note, tag, push

- Write a short Vietnamese release note (what is in this setup, version, that it is CoC-only and does not auto-update to upstream). Show it for approval; once approved save it next to the exe as `release_note_coc-setup-v<X.Y.Z>.md`. Do not write it to the repo or `CHANGELOG.md`.
- After approval only: `git tag coc-vn-setup-v<X.Y.Z>`, push the branch first, then the tag, then check `git ls-remote --tags origin coc-vn-setup-v<X.Y.Z>`. Attaching the exe to a GitHub release is manual unless the user asks.
