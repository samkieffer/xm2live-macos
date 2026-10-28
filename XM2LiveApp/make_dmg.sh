#!/usr/bin/env bash
# Compile XM2Live (via build_app.sh) puis empaquette dist/XM2Live.app dans un
# .dmg distribuable. N'utilise que des outils intégrés (swift + hdiutil).
#
# Usage:
#   ./make_dmg.sh            # produit dist/XM2Live-<version>.dmg (version de xm2live.py)
#   ./make_dmg.sh 2.5.0      # force la version

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

VERSION="${1:-$(sed -n "s/^__version__ = '\(.*\)'/\1/p" ../xm2live.py)}"
APP_NAME="XM2Live.app"
DIST_DIR="dist"
DMG_NAME="XM2Live-${VERSION}.dmg"
STAGE_DIR="${DIST_DIR}/stage"

echo "==> Compilation et assemblage de l'app"
./build_app.sh

APP_SOURCE="${DIST_DIR}/${APP_NAME}"
if [ ! -d "$APP_SOURCE" ]; then
    echo "build_app.sh n'a pas produit ${APP_SOURCE}" >&2
    exit 1
fi

echo "==> Préparation du dossier de staging"
rm -rf "$STAGE_DIR" "${DIST_DIR}/${DMG_NAME}"
mkdir -p "$STAGE_DIR"
cp -R "$APP_SOURCE" "$STAGE_DIR/"

# Lien vers /Applications pour l'installation par glisser-déposer.
ln -s /Applications "$STAGE_DIR/Applications"

echo "==> Construction du DMG"
hdiutil create \
    -volname "XM2Live ${VERSION}" \
    -srcfolder "$STAGE_DIR" \
    -ov \
    -format UDZO \
    "${DIST_DIR}/${DMG_NAME}"

rm -rf "$STAGE_DIR"

echo "==> Terminé"
echo "    ${HERE}/${DIST_DIR}/${DMG_NAME}"
echo
echo "Note: l'app est signée en ad-hoc (Sign to Run Locally). Au premier"
echo "lancement, l'utilisateur verra un avertissement Gatekeeper —"
echo "contournable via clic droit → Ouvrir."
