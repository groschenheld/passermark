#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Make a GitHub release on your own machine instead of with the workflows (e.g. when the Actions minutes are used
# up): source package, optionally the AppImage, a .sha256 for each, release text from the changelogs – exactly
# the files the update function of the program looks for. The Windows Setup.exe is added from the Windows machine
# with windows/release_upload.ps1.
#
#   tools/release_local.sh v1.19.8                 build the AppImage too (takes a while)
#   tools/release_local.sh v1.19.8 --no-appimage   only the source package (install.sh installations)
#
# Needs: git, python3, sha256sum, gh (GitHub CLI, once: gh auth login); for the AppImage what
# linux/build-appimage.sh needs. The tag must exist and be pushed (git tag v1.19.8 && git push origin v1.19.8).
set -eu
cd "$(dirname "$0")/.."

TAG="${1:-}"
[ -n "$TAG" ] || { sed -n '4,13p' "$0"; exit 2; }
APPIMAGE=1
[ "${2:-}" = "--no-appimage" ] && APPIMAGE=0
VER="${TAG#v}"
APPVER=$(python3 -c "import pdfdruck; print(pdfdruck.__version__)")

git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "Tag $TAG not found (git tag $TAG)"; exit 1; }
[ "$(git rev-parse "$TAG^{commit}")" = "$(git rev-parse HEAD)" ] || {
  echo "HEAD is not the commit of $TAG – check out the tag first (git checkout $TAG)"; exit 1; }
case "$VER" in "$APPVER"|"$APPVER"-*) ;; *) echo "Tag $TAG does not match the program version $APPVER"; exit 1;; esac
command -v gh >/dev/null || { echo "GitHub CLI (gh) missing"; exit 1; }

OUT="dist/release-$VER"
rm -rf "$OUT" && mkdir -p "$OUT"
git archive --format=tar.gz --prefix="passermark-$VER/" -o "$OUT/passermark-src-$VER.tar.gz" "$TAG"
if [ "$APPIMAGE" = 1 ]; then
  ./linux/build-appimage.sh
  cp "dist/Passermark-$APPVER-x86_64.AppImage" "$OUT/"
fi
(cd "$OUT" && for f in *.tar.gz *.AppImage; do [ -f "$f" ] && sha256sum "$f" > "$f.sha256"; done; true)
python3 tools/release_notes.py "$TAG" "$OUT/notes.md"

PRE=""
case "$VER" in *-*) PRE="--prerelease";; esac   # suffix = test version: only the test channel sees it
gh release view "$TAG" >/dev/null 2>&1 \
  || gh release create "$TAG" --verify-tag --title "$TAG" --notes-file "$OUT/notes.md" $PRE
gh release upload "$TAG" --clobber $(ls "$OUT"/* | grep -v '/notes.md$')
echo "Done: $(ls "$OUT" | grep -v notes.md | tr '\n' ' ')"
