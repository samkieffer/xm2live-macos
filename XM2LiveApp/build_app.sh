#!/bin/bash
# Compile l'app SwiftUI et assemble XM2Live.app (avec les scripts Python embarqués).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$HERE/.." && pwd)"   # racine du projet (contient xm2live.py)
APP_NAME="XM2Live"
BUILD_DIR="$HERE/.build/release"
APP="$HERE/dist/$APP_NAME.app"
# Version unique, lue dans xm2live.py (__version__)
VERSION="$(sed -n "s/^__version__ = '\(.*\)'/\1/p" "$PROJECT_DIR/xm2live.py")"

echo "==> Compilation (swift build -c release)"
cd "$HERE"
swift build -c release

echo "==> Assemblage de $APP_NAME.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/xm2live"

cp "$BUILD_DIR/$APP_NAME" "$APP/Contents/MacOS/$APP_NAME"

# Embarque les scripts Python et ressources nécessaires à la conversion.
echo "==> Copie des scripts Python"
for f in xm2live.py xm_parser.py mod_parser.py als_validator.py envelope_reader.py batch_convert.py \
         minimal_template.py create_template_200.py simpler_template.xml \
         requirements.txt; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        cp "$PROJECT_DIR/$f" "$APP/Contents/Resources/xm2live/"
    fi
done
# Templates .als optionnels (la conversion les auto-génère si absents).
for als in "$PROJECT_DIR"/*.als; do
    [ -e "$als" ] && cp "$als" "$APP/Contents/Resources/xm2live/" || true
done

# Icône (générée par make_icon.py).
if [ -f "$HERE/icon/AppIcon.icns" ]; then
    cp "$HERE/icon/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
else
    echo "    (icône absente — lancez d'abord: python3 make_icon.py)"
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>XM2Live</string>
    <key>CFBundleDisplayName</key>     <string>XM2Live</string>
    <key>CFBundleIdentifier</key>      <string>com.sam.xm2live</string>
    <key>CFBundleVersion</key>         <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key><string>${VERSION}</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleExecutable</key>      <string>XM2Live</string>
    <key>CFBundleIconFile</key>        <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>  <string>14.0</string>
    <key>NSHighResolutionCapable</key> <true/>
    <key>NSPrincipalClass</key>        <string>NSApplication</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key>       <string>Tracker Module</string>
            <key>CFBundleTypeRole</key>       <string>Viewer</string>
            <key>LSHandlerRank</key>          <string>Alternate</string>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>xm</string>
                <string>mod</string>
                <string>XM</string>
                <string>MOD</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
PLIST

# Signature ad-hoc pour éviter les blocages Gatekeeper au lancement local.
# Les attributs étendus (ex. FinderInfo sur les templates .als) font échouer codesign.
xattr -cr "$APP"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

echo "==> Terminé : $APP"
echo "    Lancer avec : open \"$APP\""
