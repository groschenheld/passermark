#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build Passermark-<version>-x86_64.AppImage (Python, Qt, all Python packages and Ghostscript included).
# Ubuntu/Debian build host:
#   sudo apt install python3-venv python3-cups python3-dev ghostscript libcups2-dev patchelf wget file \
#        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
#        libxcb-shape0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1
#   ./linux/build-appimage.sh
# Built on an old distro (GitHub: ubuntu-22.04) the AppImage runs on all newer ones.
set -euo pipefail
cd "$(dirname "$0")/.."
for c in python3 gs wget patchelf file; do command -v "$c" >/dev/null || { echo "missing: $c"; exit 1; }; done
python3 -c "import cups" 2>/dev/null || { echo "missing: python3-cups (apt)"; exit 1; }
VERSION=$(python3 -c "import pdfdruck; print(pdfdruck.__version__)")
# all program files must compile with THIS Python (build host = oldest supported, e.g. 3.10 on ubuntu-22.04)
{ python3 -m compileall -q -f pdfdruck >/dev/null && python3 -m py_compile admin/*-admin; } || { python3 -m compileall -q -f pdfdruck; echo "syntax not supported by $(python3 --version)"; exit 1; }
find pdfdruck admin -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# 1) Python environment (pycups from apt -> --system-site-packages, nothing to compile)
[ -x .venv/bin/python ] || python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --upgrade pip
grep -v -i '^pycups' requirements.txt | sed 's/#.*//' | grep -v '^ *$' > build-req.txt
.venv/bin/pip install -r build-req.txt pyinstaller
rm -f build-req.txt

# 2) program folder
.venv/bin/pyinstaller --noconfirm linux/passermark.spec --distpath dist --workpath build/pyi

# 3) AppDir
rm -rf AppDir && mkdir -p AppDir/usr/lib AppDir/usr/bin AppDir/usr/share
cp -a "dist/passermark" "AppDir/usr/lib/passermark"
install -m 755 linux/AppRun AppDir/AppRun
sed 's/^Exec=passermark/Exec=AppRun/; s/^TryExec=.*//' data/passermark.desktop > AppDir/passermark.desktop
cp data/passermark.svg AppDir/passermark.svg
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp data/passermark.svg AppDir/usr/share/icons/hicolor/scalable/apps/

# 4) Ghostscript: binary + its libraries (not glibc) + resources; started via a small wrapper
GSBIN=$(readlink -f "$(command -v gs)")
GSVER=$(gs --version)
mkdir -p AppDir/usr/lib/gs
cp "$GSBIN" AppDir/usr/lib/gs/gs.bin
ldd "$GSBIN" | awk '/=> \// {print $3}' | while read -r lib; do
    case "$(basename "$lib")" in
        libc.so*|libm.so*|libdl.so*|libpthread.so*|librt.so*|ld-linux*|libgcc_s.so*|libstdc++.so*) ;;
        *) cp -L "$lib" AppDir/usr/lib/gs/ ;;
    esac
done
patchelf --set-rpath '$ORIGIN' AppDir/usr/lib/gs/gs.bin
cp -a /usr/share/ghostscript AppDir/usr/share/
[ -d /usr/share/fonts/type1/urw-base35 ] && mkdir -p AppDir/usr/share/fonts && cp -a /usr/share/fonts/type1/urw-base35 AppDir/usr/share/fonts/
[ -d "/usr/share/ghostscript/$GSVER" ] || { echo "Ghostscript resources not found: /usr/share/ghostscript/$GSVER"; ls /usr/share/ghostscript; exit 1; }
# wrapper: resource paths as separate, quoted arguments (safe with spaces in paths)
cat > AppDir/usr/bin/gs <<EOF
#!/bin/sh
D="\$(dirname "\$(readlink -f "\$0")")/.."
R="\$D/share/ghostscript/$GSVER"
export GS_LIB="\$R/Resource/Init:\$R/lib:\$R/Resource/Font:\$D/share/ghostscript/fonts:\$D/share/fonts/urw-base35"
export LD_LIBRARY_PATH="\$D/lib/gs\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
exec "\$D/lib/gs/gs.bin" "-sGenericResourceDir=\$R/Resource/" "-sICCProfilesDir=\$R/iccprofiles/" "\$@"
EOF
chmod 755 AppDir/usr/bin/gs
# test the bundled Ghostscript (no pipe -> no SIGPIPE/pipefail race; show the real error if it fails)
echo "== testing bundled Ghostscript $GSVER"
set +e
GSOUT=$(AppDir/usr/bin/gs -q -dNODISPLAY -dNOSAFER -dBATCH -dNOPAUSE -c "(gs ok) = quit" 2>&1)
GSRC=$?
set -e
case "$GSOUT" in
    *"gs ok"*) echo "bundled gs ok" ;;
    *)
        echo "::warning::Bundled Ghostscript does not run - removed from the AppImage (system Ghostscript is used)."
        echo "$GSOUT"
        echo "exit code: $GSRC"
        echo "--- libraries not found:"
        LD_LIBRARY_PATH=AppDir/usr/lib/gs ldd AppDir/usr/lib/gs/gs.bin | grep -i "not found" || echo "(none)"
        rm -rf AppDir/usr/bin/gs AppDir/usr/lib/gs AppDir/usr/share/ghostscript AppDir/usr/share/fonts/urw-base35 ;;
esac

# 5) appimagetool
mkdir -p linux/tools
TOOL=linux/tools/appimagetool-x86_64.AppImage
[ -x "$TOOL" ] || { wget -q -O "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage && chmod +x "$TOOL"; }
mkdir -p dist
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream AppDir "dist/Passermark-$VERSION-x86_64.AppImage"
echo "Done: dist/Passermark-$VERSION-x86_64.AppImage"
