---
name: coc-patch
description: Build the Clash of Critters patch zip and write its release note. Use when the user asks to create, export or release a CoC patch, patch zip or release note. Always asks for the version first.
---

# Clash of Critters patch and release note

## Step 1 - pull, then ask the version

Always pull the latest source and tags first, so the tag hint and the release note range are current:

```bash
git pull --ff-only
git fetch --tags origin
git tag --list "coc-vn-v*" --sort=-v:refname | head -3
```

If the pull is not a fast-forward or the working tree blocks it, stop and tell the user. Then ask the user for the patch version (format `X.Y.Z`, for example `0.4.0`; a leading `v` is accepted and ignored) and show the latest tag as a hint. Also ask which ref to start the release note from if it is not obvious (default: the latest `coc-vn-v*` tag). Do not guess the version.

The tag is `coc-vn-v<X.Y.Z>`: input `0.4.0` or `v0.4.0` both give `coc-vn-v0.4.0`. Stop if that tag already exists.

## Step 2 - build the zip

Run from the repo root. The script packages files from git (`HEAD` by default), so uncommitted changes are not included - warn the user if `git status` shows changes under the game folder.

```bash
python scripts/build_coc_patch.py <version>
```

- Output: `clash_of_critters_patch_v<version>.zip`, two levels above the repo (override with `--out`).
- Layout: `.py` files go to `Lib/site-packages/adb_auto_player/games/clash_of_critters/`; `templates/`, `tatari_db/`, `tatari_formations/` go to `games/clash_of_critters/`.
- `ClashOfCritters.toml` is not packaged. If the settings model changed since the last release, tell the user it must be copied or reset by hand.

## Step 3 - write the release note

- Read `git log --format='%h %s' <since-ref>..HEAD` and the diff of `settings.py` and `ClashOfCritters.toml`.
- Write the note in Vietnamese using `.github/RELEASE_TEMPLATE.md` sections: Patch (cập nhật tự động) and App (cần tải về).
- List new settings with defaults, removed settings, and anything users must do by hand.
- Show the draft to the user for approval. Do not write it to a file or `CHANGELOG.md` until they confirm.
- Once approved, save it next to the zip as `release_note_coc-vn-v<X.Y.Z>.md` (same folder as `clash_of_critters_patch_v<X.Y.Z>.zip`, two levels above the repo). Do not write it into the repo or `CHANGELOG.md`.

## Step 4 - tag and push

- Create the tag on `HEAD` once the zip is built: `git tag coc-vn-v<X.Y.Z>` (the zip packages `HEAD`, so commit everything first).
- Push only after the zip is built and the release note is approved (pushing publishes the tag). Push the branch first, so the commit the tag points to exists on the remote, then the tag:

```bash
git push origin <current-branch>
git push origin coc-vn-v<X.Y.Z>
```

- Check afterwards that `git ls-remote --tags origin coc-vn-v<X.Y.Z>` shows the commit of the branch head.

## Step 5 - create the GitHub release (pre-release)

`gh` lives in `C:\Program Files\GitHub CLI`; if `gh` is not found in the shell, run `export PATH="$PATH:/c/Program Files/GitHub CLI"` first and check `gh auth status`.

- Always create the patch release as a **pre-release**. The self-updater of the setup reads `releases/latest/download/latest.json`, and a patch release marked Latest would shadow the `coc-vn-setup-v*` release and break app updates. Never pass `--latest` here.
- Creating a release is public: show the title, tag, assets and pre-release flag to the user and create it only after they confirm.

```bash
gh release create coc-vn-v<X.Y.Z> \
  <dir>/clash_of_critters_patch_v<X.Y.Z>.zip \
  --repo anhlt3010/AdbAutoPlayer \
  --title "Clash of Critters (VN) - v<X.Y.Z>" \
  --notes-file <dir>/release_note_coc-vn-v<X.Y.Z>.md \
  --prerelease --latest=false
```

- Afterwards check that the release is not the Latest one:

```bash
gh release view coc-vn-v<X.Y.Z> --repo anhlt3010/AdbAutoPlayer --json isPrerelease,isDraft,assets
gh release list --repo anhlt3010/AdbAutoPlayer --limit 3
```
