# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark als AppImage bauen (x86_64) - alle Abhaengigkeiten eingebettet:
# Python, PySide6, pikepdf, pypdfium2, pillow-heif UND Ghostscript.
# Ergebnis: dist/Passermark-<Version>-x86_64.AppImage
#
# Voraussetzungen (Debian/Ubuntu, einmalig):
#   sudo apt install python3-venv python3-cups python3-dev ghostscript patchelf wget
# (pycups kommt als python3-cups vom System - kein Kompilieren, keine libcups2-dev noetig)
# Aufruf:  ./linux/build-appimage.sh
set -eu
cd "$(dirname "$0")/.."
VERSION="1.4.4"

# --- 0) System-Voraussetzungen pruefen ---------------------------------------
for cmd in python3 gs wget; do
    command -v "$cmd" >/dev/null || { echo "Fehler: '$cmd' fehlt. Voraussetzungen siehe Kopf dieses Skripts."; exit 1; }
done

# --- 1) Python-Umgebung + PyInstaller ---------------------------------------
# --system-site-packages: pycups (python3-cups) kommt vom System,
# genau wie bei install.sh (PEP 668), und wird von PyInstaller mitgebuendelt.
rm -rf .venv
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
# pycups bewusst NICHT per pip installieren (wuerde libcups2-dev brauchen):
grep -v '^ *pycups' requirements.txt > /tmp/requirements-nocups.txt
.venv/bin/pip install -r /tmp/requirements-nocups.txt pyinstaller
.venv/bin/python -c "import cups; print('pycups: OK (aus python3-cups)')"

# --- 2) PyInstaller-Ordner bauen ---------------------------------------------
.venv/bin/pyinstaller --noconfirm linux/passermark-linux.spec --distpath dist --workpath build

# --- 3) AppDir zusammenstellen ------------------------------------------------
APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/program" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -r dist/passermark/. "$APPDIR/usr/program/"
install -D -m 644 data/passermark.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/passermark.svg"
install -D -m 644 data/passermark.desktop "$APPDIR/usr/share/applications/passermark.desktop"

# Wrapper: startet das gebuendelte PyInstaller-Binary
cat > "$APPDIR/usr/bin/passermark" <<'WRAP'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
APPDIR="${APPDIR:-$(dirname "$(dirname "$HERE")")}"
exec "$APPDIR/usr/program/passermark" "$@"
WRAP
chmod 755 "$APPDIR/usr/bin/passermark"

# --- 4) Ghostscript mit einpacken (Reparieren/Optimieren/PDF-A/CMYK) ---------
cp "$(command -v gs)" "$APPDIR/usr/bin/gs"

# --- 5) linuxdeploy + appimagetool ---------------------------------------------
[ -f linuxdeploy-x86_64.AppImage ] || wget -q "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
chmod +x linuxdeploy-x86_64.AppImage

ARCH=x86_64 OUTPUT="dist/Passermark-$VERSION-x86_64.AppImage" \
  ./linuxdeploy-x86_64.AppImage \
    --appdir "$APPDIR" \
    --executable="$APPDIR/usr/bin/gs" \
    --desktop-file "$APPDIR/usr/share/applications/passermark.desktop" \
    --icon-file "$APPDIR/usr/share/icons/hicolor/scalable/apps/passermark.svg" \
    --output appimage

echo "Fertig: dist/Passermark-$VERSION-x86_64.AppImage"
