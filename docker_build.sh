#!/usr/bin/env bash

set -euo pipefail

CONFIG_JSON="${1:-config.driver.json}"
JOBS="${JOBS:-4}"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl xz-utils python2.7 python-serial
if ! command -v python2 >/dev/null 2>&1; then
  ln -sf /usr/bin/python2.7 /usr/bin/python2
fi

# Install Node.js from official binaries (NodeSource no longer supports Ubuntu bionic).
NODE_VERSION="${NODE_VERSION:-v16.20.2}"
NODE_TARBALL="node-${NODE_VERSION}-linux-x64.tar.xz"
NODE_URL_BASE="https://nodejs.org/dist/${NODE_VERSION}"

curl -fsSL -o "/tmp/${NODE_TARBALL}" "${NODE_URL_BASE}/${NODE_TARBALL}"
curl -fsSL -o /tmp/SHASUMS256.txt "${NODE_URL_BASE}/SHASUMS256.txt"
grep " ${NODE_TARBALL}\$" /tmp/SHASUMS256.txt | (cd /tmp && sha256sum -c -)
tar -xJf "/tmp/${NODE_TARBALL}" -C /usr/local --strip-components=1

npm install -g ejs-cli

if [ "${GENERATE_CONFIG:-0}" = "1" ]; then
  CONFIG_PATH="${2:-config_gen/config/SuperGreenOS/Controllers/Driver}"
  ./update_config.sh "$CONFIG_PATH" "$CONFIG_JSON"
fi
./update_templates.sh "$CONFIG_JSON"

if [ -n "${IDF_PATH:-}" ] && [ -f "${IDF_PATH}/export.sh" ]; then
  . "${IDF_PATH}/export.sh"
fi

make defconfig
make -j"$JOBS"
