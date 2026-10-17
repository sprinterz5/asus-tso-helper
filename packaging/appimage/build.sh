#!/bin/bash
# Builds dist/asus-tso-helper-x86_64.AppImage: a relocatable Python 3.12 (python-appimage), PySide6,
# evdev and dbus-python, plus the app. Meant for quay.io/pypa/manylinux_2_34_x86_64 (glibc 2.34,
# what PySide6 6.11 needs), so the AppImage runs on distributions from 2021 on. Run it through
# build-in-podman.sh locally; the release workflow runs it in the same container.
set -euo pipefail

PYTHON_APPIMAGE=https://github.com/niess/python-appimage/releases/download/python3.12/python3.12.15-cp312-cp312-manylinux_2_28_x86_64.AppImage
APPIMAGETOOL=https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
# the versions Fedora 44 ships, which the app is tested with
PACKAGES=("PySide6-Essentials==6.11.2" "evdev==1.9.3" "dbus-python==1.4.0")

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
BUILD=$ROOT/build/appimage
APPDIR=$BUILD/AppDir
OUT=$ROOT/dist/asus-tso-helper-x86_64.AppImage
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ROOT/asus_tso_helper/config.py")

if command -v dnf >/dev/null; then  # headers to build evdev and dbus-python
    dnf install -y -q dbus-devel glib2-devel kernel-headers file >/dev/null
fi

rm -rf "$BUILD" && mkdir -p "$BUILD" "$(dirname "$OUT")"
cd "$BUILD"
curl -fsSL -o python.AppImage "$PYTHON_APPIMAGE"
curl -fsSL -o appimagetool "$APPIMAGETOOL"
chmod +x python.AppImage appimagetool
./python.AppImage --appimage-extract >/dev/null
mv squashfs-root "$APPDIR"
rm -f "$APPDIR"/AppRun "$APPDIR"/*.desktop "$APPDIR"/*.png "$APPDIR"/.DirIcon
rm -rf "$APPDIR"/usr/share/tcltk "$APPDIR"/usr/share/applications "$APPDIR"/usr/share/icons "$APPDIR"/usr/share/metainfo

PY=$APPDIR/opt/python3.12/bin/python3.12
"$PY" -m pip install -q --no-cache-dir --no-compile --no-warn-script-location --disable-pip-version-check "${PACKAGES[@]}"

# Qt parts the app never loads (it uses Core, Gui, Widgets, Svg, Network, DBus)
SITE=$("$PY" -c 'import site; print(site.getsitepackages()[0])')
QT=$SITE/PySide6
rm -rf "$QT"/{Qt/qml,Qt/translations,Qt/libexec,Qt/metatypes,include,typesystems,glue,scripts,examples}
rm -rf "$QT"/{assistant,designer,linguist,lrelease,lupdate,qmllint,qmlformat,qmlls,uic,rcc,balsam,balsamui,svgtoqml}
for mod in Qml Quick QuickControls2 QuickWidgets QuickTest OpenGL OpenGLWidgets Sql Test Designer Help \
           UiTools Xml Concurrent PrintSupport Pdf PdfWidgets StateMachine; do
    rm -f "$QT"/Qt$mod.* "$QT"/Qt$mod.pyi
done
rm -f "$QT"/Qt/lib/libQt6{Qml,Quick,QmlModels,QmlMeta,QmlWorkerScript,QuickControls2,QuickTemplates2,QuickWidgets,QuickTest,Designer,Help,UiTools,Sql,Test,Pdf,PdfWidgets,ShaderTools,Labs,VirtualKeyboard}*.so* 2>/dev/null || true
rm -rf "$QT"/Qt/plugins/{sqldrivers,qmltooling,designer,sceneparsers,assetimporters,virtualkeyboard,position,multimedia} 2>/dev/null || true
"$PY" -m pip uninstall -q -y pip setuptools 2>/dev/null || true
find "$APPDIR" -name __pycache__ -prune -exec rm -rf {} +

# the app
APP=$APPDIR/opt/asus-tso-helper
mkdir -p "$APP"
cp -r "$ROOT/asus_tso_helper" "$ROOT/asus-tso-helper" "$ROOT/LICENSE" "$APP/"
find "$APP" -name __pycache__ -prune -exec rm -rf {} +
"$PY" -m compileall -q "$APP" "$SITE" >/dev/null || true
cp "$ROOT/packaging/appimage/AppRun" "$APPDIR/AppRun"
sed -e "s|@EXEC@|asus-tso-helper|; s|@ICON@|asus-tso-helper|" \
    "$ROOT/asus_tso_helper/assets/asus-tso-helper.desktop" > "$APPDIR/asus-tso-helper.desktop"
echo "X-AppImage-Version=$VERSION" >> "$APPDIR/asus-tso-helper.desktop"
cp "$ROOT/asus_tso_helper/assets/asus-tso-helper.png" "$APPDIR/asus-tso-helper.png"
ln -sf asus-tso-helper.png "$APPDIR/.DirIcon"

rm -f "$OUT"
ARCH=x86_64 VERSION=$VERSION ./appimagetool --appimage-extract-and-run --no-appstream -n "$APPDIR" "$OUT" >/dev/null
sha256sum "$OUT" | sed "s|$ROOT/||"
ls -la "$OUT"
