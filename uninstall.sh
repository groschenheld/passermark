#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Remove pdfToolkit (installed by install.sh). Dependencies (Python, ghostscript, cups ...) are kept.
#   sudo ./uninstall.sh --dry-run   show what would be removed
#   sudo ./uninstall.sh             remove the program, keep /etc/pdfdruck (settings, ICC profiles)
#   sudo ./uninstall.sh --purge     also remove /etc/pdfdruck
set -eu
DRY=0; PURGE=0
for a in "$@"; do
    case "$a" in
        --dry-run) DRY=1 ;;
        --purge) PURGE=1 ;;
        *) echo "unknown option: $a"; exit 2 ;;
    esac
done
[ "$DRY" -eq 1 ] || [ "$(id -u)" -eq 0 ] || { echo "Please run with sudo."; exit 1; }
rmp() {
    for p in "$@"; do
        if [ -e "$p" ] || [ -L "$p" ]; then
            if [ "$DRY" -eq 1 ]; then echo "would remove: $p"; else rm -rf -- "$p"; echo "removed: $p"; fi
        fi
    done
}
rmp /usr/local/lib/pdfdruck /usr/local/bin/pdftoolkit /usr/libexec/pdfdruck-admin \
    /usr/share/polkit-1/actions/at.hias.pdfdruck.policy \
    /usr/share/applications/pdftoolkit.desktop /usr/share/icons/hicolor/scalable/apps/pdftoolkit.svg \
    /usr/share/nautilus-python/extensions/pdftoolkit_nautilus.py
# old symlink name (only if it points to us)
if [ -L /usr/local/bin/pdfdruck ] && [ "$(readlink /usr/local/bin/pdfdruck)" = "/usr/local/bin/pdftoolkit" ]; then rmp /usr/local/bin/pdfdruck; fi
[ "$PURGE" -eq 1 ] && rmp /etc/pdfdruck
if [ "$DRY" -eq 0 ]; then
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
    command -v update-desktop-database >/dev/null && update-desktop-database -q || true
    echo "pdfToolkit removed. Restart Nautilus: nautilus -q"
fi
