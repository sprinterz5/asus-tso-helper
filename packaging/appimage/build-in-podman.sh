#!/bin/sh
# Local build in the same container as the release workflow: dist/shiftray-x86_64.AppImage
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
exec podman run --rm -v "$ROOT:/src:Z" -w /src quay.io/pypa/manylinux_2_34_x86_64 \
    /src/packaging/appimage/build.sh
