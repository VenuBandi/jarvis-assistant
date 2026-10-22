#!/bin/sh
# J1b: build Jarvis Bar (menu-bar app) into mac/JarvisBar/build/JarvisBar.app.
#   sh scripts/build_jarvis_bar.sh
# Writes only mac/JarvisBar/.build/ and mac/JarvisBar/build/ (both git-ignored). Signed ad hoc (local use only).
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/mac/JarvisBar"
APP="$PKG/build/JarvisBar.app"

swift build --package-path "$PKG" -c release
BIN="$(swift build --package-path "$PKG" -c release --show-bin-path)/JarvisBar"

mkdir -p "$PKG/build"
rm -rf "$APP"   # previous build output of this script only
mkdir -p "$APP/Contents/MacOS"
cp "$BIN" "$APP/Contents/MacOS/JarvisBar"
sed "s|__JARVIS_ROOT__|$ROOT|" "$PKG/Info.plist" > "$APP/Contents/Info.plist"
plutil -lint "$APP/Contents/Info.plist" >/dev/null
codesign --force --sign - "$APP"
echo "built $APP"
