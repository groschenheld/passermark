#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# pdfToolkit – Copyright (C) 2026 Hias
# Installation (als root): sudo ./install.sh
# Legt ein eigenes venv an (PEP 668), python3-cups kommt aus apt (--system-site-packages).
set -eu
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }
cd "$(dirname "$0")"
LIB=/usr/local/lib/pdfdruck
VENV="$LIB/venv"

if command -v apt-get >/dev/null; then
    apt-get update
    apt-get install -y python3-venv python3-cups ghostscript polkitd pkexec libxcb-cursor0 \
        python3-nautilus libnotify-bin fonts-ibm-plex p7zip-full
fi

install -d -m 755 "$LIB" /etc/pdfdruck /etc/pdfdruck/icc
rm -rf "$LIB/pdfdruck"
cp -r pdfdruck "$LIB/"

[ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade --quiet pip
"$VENV/bin/pip" install --upgrade --quiet "PySide6>=6.5" "pypdfium2>=4.25" img2pdf Pillow pikepdf
"$VENV/bin/pip" install --upgrade --quiet pillow-heif || echo "Hinweis: pillow-heif nicht installierbar – HEIC wird nicht unterstützt."
"$VENV/bin/python" -c "import cups, PySide6, pypdfium2, img2pdf, pikepdf; print('Abhängigkeiten OK')"

chown -R root:root "$LIB"; chmod -R go-w "$LIB"

# Root-Helper braucht keine Fremdpakete -> System-Python
install -D -m 755 -o root -g root admin/pdfdruck-admin /usr/libexec/pdfdruck-admin
install -D -m 644 data/at.hias.pdfdruck.policy /usr/share/polkit-1/actions/at.hias.pdfdruck.policy
install -D -m 644 data/pdftoolkit.desktop /usr/share/applications/pdftoolkit.desktop
install -D -m 644 data/pdftoolkit.svg /usr/share/icons/hicolor/scalable/apps/pdftoolkit.svg
# Nautilus-Kontextmenü (Bilder: „Als PDF öffnen“, PDFs: „Drucken“)
install -D -m 644 data/pdftoolkit_nautilus.py /usr/share/nautilus-python/extensions/pdftoolkit_nautilus.py

# Altlasten aus der Zeit als „PDF-Druck“ entfernen
rm -f /usr/share/applications/pdfdruck.desktop /usr/share/nautilus-python/extensions/pdfdruck_nautilus.py

[ -f /etc/pdfdruck/defaults.json ] || echo '{}' > /etc/pdfdruck/defaults.json
chown root:root /etc/pdfdruck/defaults.json; chmod 644 /etc/pdfdruck/defaults.json

cat > /usr/local/bin/pdftoolkit <<SH
#!/bin/sh
PYTHONPATH="$LIB" exec "$VENV/bin/python" -m pdfdruck "\$@"
SH
chmod 755 /usr/local/bin/pdftoolkit
ln -sf /usr/local/bin/pdftoolkit /usr/local/bin/pdfdruck     # alter Befehl funktioniert weiter
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
if ! command -v soffice >/dev/null && ! ls /opt/*/desktopeditors/converter/x2t >/dev/null 2>&1; then
    echo "Hinweis: Für Office-Dateien (doc/docx/xlsx/pptx/odt …) LibreOffice, OnlyOffice oder Euro-Office installieren,"
    echo "         z. B.: sudo apt install libreoffice-writer libreoffice-calc libreoffice-impress"
fi
echo "Fertig. Start: pdftoolkit datei.pdf  (oder über das App-Menü: pdfToolkit)"
echo "Nautilus neu starten, damit das Kontextmenü erscheint:  nautilus -q"
