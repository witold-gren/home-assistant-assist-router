#!/usr/bin/env bash
# Copies the integration into the Home Assistant configuration (by default the
# Samba share mounted on the Mac). Restart HA after deploying.
#
#   scripts/deploy.sh                          # to /Volumes/config
#   HA_CONFIG=/other/path scripts/deploy.sh    # override the HA config directory
#
# Environment:
#   HA_CONFIG  Home Assistant config directory (default: /Volumes/config)
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
target="${HA_CONFIG:-/Volumes/config}/custom_components/assist_router"

if [ ! -d "$(dirname "$target")" ]; then
  echo "Directory $(dirname "$target") not found - is the config share mounted?" >&2
  exit 1
fi

# The version from manifest.json with sed, so deploying needs nothing but the tools of macOS.
version="$(sed -n 's/^[[:space:]]*"version":[[:space:]]*"\([^"]*\)".*/\1/p' \
  "$repo/custom_components/assist_router/manifest.json")"

# --inplace: no temporary files. The temporary name of __init__.py starts with
# "._", and the macOS SMB share rejects such names (AppleDouble).
rsync -rt --inplace --delete --exclude '__pycache__' --exclude '*.pyc' \
  "$repo/custom_components/assist_router/" "$target/"

echo "Deployed Assist Router $version to $target"
echo "Restart Home Assistant (Settings -> System -> Restart)."
