#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# Installation (als root): sudo ./install.sh
# Legt ein eigenes venv an (PEP 668), python3-cups kommt aus apt (--system-site-packages).
set -eu
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }
cd "$(dirname "$0")"
LIB=/usr/local/lib/passermark
VENV="$LIB/venv"

if command -v apt-get >/dev/null; then
    apt-get install -y python3-venv python3-cups ghostscript librsvg2-bin fontconfig fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea fonts-urw-base35 fonts-dejavu-core polkitd pkexec libxcb-cursor0 \
        python3-nautilus libnotify-bin fonts-ibm-plex p7zip-full
fi

install -d -m 755 "$LIB" /etc/passermark /etc/passermark/icc
rm -rf "$LIB/pdfdruck"
cp -r pdfdruck "$LIB/"

[ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade --quiet pip
"$VENV/bin/pip" install --upgrade --quiet "PySide6>=6.5" "pypdfium2>=4.25" img2pdf Pillow pikepdf numpy scipy contourpy
"$VENV/bin/pip" install --upgrade --quiet pillow-heif || echo "Hinweis: pillow-heif nicht installierbar – HEIC wird nicht unterstützt."
"$VENV/bin/python" -c "import cups, PySide6, pypdfium2, img2pdf, pikepdf, numpy, scipy, contourpy; print('Abhängigkeiten OK')"

chown -R root:root "$LIB"; chmod -R go-w "$LIB"

# Root-Helper braucht keine Fremdpakete -> System-Python
install -D -m 755 -o root -g root admin/passermark-admin /usr/libexec/passermark-admin
install -D -m 644 data/at.hias.passermark.policy /usr/share/polkit-1/actions/at.hias.passermark.policy
install -D -m 644 data/passermark.desktop /usr/share/applications/passermark.desktop
install -D -m 644 data/passermark.svg /usr/share/icons/hicolor/scalable/apps/passermark.svg
# Nautilus-Kontextmenü (Bilder: „Als PDF öffnen“, PDFs: „Drucken“)
install -D -m 644 data/passermark_nautilus.py /usr/share/nautilus-python/extensions/passermark_nautilus.py


[ -f /etc/passermark/defaults.json ] || echo '{}' > /etc/passermark/defaults.json
chown root:root /etc/passermark/defaults.json; chmod 644 /etc/passermark/defaults.json

cat > /usr/local/bin/passermark <<SH
#!/bin/sh
PYTHONPATH="$LIB" exec "$VENV/bin/python" -m pdfdruck "\$@"
SH
chmod 755 /usr/local/bin/passermark
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
if ! command -v soffice >/dev/null && ! ls /opt/*/desktopeditors/converter/x2t >/dev/null 2>&1; then
    echo "Hinweis: Für Office-Dateien (doc/docx/xlsx/pptx/odt …) LibreOffice, OnlyOffice oder Euro-Office installieren,"
    echo "         z. B.: sudo apt install libreoffice-writer libreoffice-calc libreoffice-impress"
fi
echo "Fertig. Start: passermark datei.pdf  (oder über das App-Menü: Passermark)"
echo "Nautilus neu starten, damit das Kontextmenü erscheint:  nautilus -q"
