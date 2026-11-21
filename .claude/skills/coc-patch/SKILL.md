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

## Step 4 - tag and push

- Create the tag on `HEAD` once the zip is built: `git tag coc-vn-v<X.Y.Z>` (the zip packages `HEAD`, so commit everything first).
- Push it only after the zip is built and the release note is approved: `git push origin coc-vn-v<X.Y.Z>`. Pushing the tag publishes it, so never push before the user has approved the note.
