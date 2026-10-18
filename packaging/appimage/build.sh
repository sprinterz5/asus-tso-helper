#!/bin/bash
# Builds dist/shiftray-x86_64.AppImage: a relocatable Python 3.12 (python-appimage), PySide6,
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
OUT=$ROOT/dist/shiftray-x86_64.AppImage
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ROOT/shiftray/config.py")

if command -v dnf >/dev/null; then  # headers to build evdev and dbus-python
    dnf install -y -q dbus-devel glib2-devel kernel-headers file gcc >/dev/null
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
if compgen -G "$ROOT/build/wheels/*.whl" >/dev/null; then  # local builds where PyPI is slow
    "$PY" -m pip install -q --no-cache-dir --no-compile --no-deps --disable-pip-version-check "$ROOT"/build/wheels/*.whl
fi
"$PY" -m pip install -q --no-cache-dir --no-compile --no-warn-script-location --disable-pip-version-check "${PACKAGES[@]}"

# Qt parts the app never loads (it uses Core, Gui, Widgets, Svg, Network, DBus)
SITE=$("$PY" -c 'import site; print(site.getsitepackages()[0])')
QT=$SITE/PySide6
rm -rf "$QT"/{Qt/qml,Qt/translations,Qt/libexec,Qt/metatypes,include,typesystems,glue,scripts,examples}
rm -rf "$QT"/{assistant,designer,linguist,lrelease,lupdate,qmllint,qmlformat,qmlls,uic,rcc,balsam,balsamui,svgtoqml}
for mod in Qml Quick QuickControls2 QuickWidgets QuickTest OpenGL OpenGLWidgets Sql Test Designer Help \
           UiTools Xml Concurrent PrintSupport Pdf PdfWidgets StateMachine SvgWidgets; do
    rm -f "$QT"/Qt$mod.* "$QT"/Qt$mod.pyi
done
rm -f "$QT"/Qt/lib/libQt6{Qml,Quick,QmlModels,QmlMeta,QmlWorkerScript,QuickControls2,QuickTemplates2,QuickWidgets,QuickTest,Designer,Help,UiTools,Sql,Test,Pdf,PdfWidgets,ShaderTools,Labs,VirtualKeyboard}*.so* 2>/dev/null || true
rm -f "$QT"/Qt/lib/libQt6{Concurrent,EglFSDeviceIntegration,EglFsKmsSupport,Lottie,LottieVectorImageGenerator,LottieVectorImageHelpers,OpenGLWidgets,PrintSupport,WaylandCompositor,WaylandEglCompositorHwIntegration,WlShellIntegration,Xml,SvgWidgets}.so*
rm -f "$QT"/*.pyi
# plugins: only the X11 and Wayland platforms (plus offscreen and minimal), their GL glue, SVG and
# ICO images, input methods and the desktop themes
P=$QT/Qt/plugins
rm -rf "$P"/{sqldrivers,qmltooling,designer,sceneparsers,assetimporters,virtualkeyboard,position,multimedia} 2>/dev/null || true
rm -rf "$P"/{egldeviceintegrations,generic,networkinformation,printsupport,qmllint,vectorimageformats,tls,wayland-graphics-integration-server}
rm -f "$P"/platforminputcontexts/libqtvirtualkeyboardplugin.so
find "$P"/platforms -type f ! -name libqxcb.so ! -name libqwayland.so ! -name libqoffscreen.so ! -name libqminimal.so -delete
find "$P"/imageformats -type f ! -name libqsvg.so ! -name libqico.so -delete
find "$P"/wayland-graphics-integration-client -type f ! -name libqt-plugin-wayland-egl.so -delete
find "$P"/wayland-shell-integration -type f ! -name libxdg-shell.so -delete
# Qt Core links ICU, but the app uses none of its 30 MB of locale tables (collation, calendars,
# old encodings), so an empty data library takes their place
ICU=$(basename "$(ls "$QT"/Qt/lib/libicudata.so.*)")  # libicudata.so.73
printf 'const unsigned char icudt%s_dat[32] __attribute__((aligned(16))) = {0};\n' "${ICU##*.so.}" > "$BUILD/icudata.c"
gcc -O2 -shared -fPIC -nostdlib -Wl,-soname,"$ICU" -o "$QT/Qt/lib/$ICU" "$BUILD/icudata.c"
"$PY" -m pip uninstall -q -y pip setuptools build packaging pyproject_hooks 2>/dev/null || true
rm -f "$SITE"/sitecustomize.py  # python-appimage's hook for pip installs

# Python: tools, tests and Tk, which the app never imports
PYLIB=$(dirname "$SITE")
rm -rf "$PYLIB"/{idlelib,ensurepip,pydoc_data,lib2to3,tkinter,turtledemo,unittest,sqlite3,venv,dbm,curses,test,config-3.12-x86_64-linux-gnu}
rm -f "$PYLIB"/{turtle.py,_pydecimal.py,pydoc.py,doctest.py}
rm -f "$PYLIB"/lib-dynload/{_test,_ctypes_test,xx,_xx,_tkinter,_sqlite3,_curses,_dbm,_gdbm,audioop,ossaudiodev,spwd,readline}*.so
rm -f "$APPDIR"/usr/lib/{libtcl8.6.so,libtk8.6.so,libsqlite3.so,libXft.so.2,libXrender.so.1,libgdbm.so.6,libgdbm_compat.so.4,libreadline.so.7,libncursesw.so.6,libpanelw.so.6,libtinfo.so.6}
rm -f "$APPDIR"/usr/bin/pip* "$APPDIR"/opt/python3.12/bin/pip*
find "$APPDIR" -name __pycache__ -prune -exec rm -rf {} +
# The AppImage is read-only, so Python can't cache bytecode and would compile the standard library
# on every start (about 350 ms): ship it compiled, without the sources
"$PY" -m compileall -q -b -x '/site-packages/' "$PYLIB" >/dev/null || true
find "$PYLIB" -path "$SITE" -prune -o -name '*.py' -print | while read -r f; do
    if [ -f "${f}c" ]; then rm "$f"; fi
done

# the app
APP=$APPDIR/opt/shiftray
mkdir -p "$APP"
cp -r "$ROOT/shiftray" "$ROOT/bin" "$ROOT/LICENSE" "$APP/"
find "$APP" -name __pycache__ -prune -exec rm -rf {} +
"$PY" -m compileall -q "$APP" "$SITE" >/dev/null || true
cp "$ROOT/packaging/appimage/AppRun" "$APPDIR/AppRun"
sed -e "s|@EXEC@|shiftray|; s|@ICON@|shiftray|" \
    "$ROOT/shiftray/assets/shiftray.desktop" > "$APPDIR/shiftray.desktop"
echo "X-AppImage-Version=$VERSION" >> "$APPDIR/shiftray.desktop"
cp "$ROOT/shiftray/assets/shiftray.png" "$APPDIR/shiftray.png"
ln -sf shiftray.png "$APPDIR/.DirIcon"

rm -f "$OUT"
ARCH=x86_64 VERSION=$VERSION ./appimagetool --appimage-extract-and-run --no-appstream -n "$APPDIR" "$OUT" >/dev/null
sha256sum "$OUT" | sed "s|$ROOT/||"
ls -la "$OUT"
