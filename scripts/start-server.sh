#!/usr/bin/env bash
# Downloads and starts Paper or the official Vanilla server for MC_VERSION.
set -Eeuo pipefail

MC_VERSION="${MC_VERSION:-1.21.4}"
SERVER_TYPE="${SERVER_TYPE:-paper}"
MAX_RAM="${MAX_RAM:-2G}"
SERVER_DIR="${SERVER_DIR:-$PWD/server}"
PAPER_API="https://api.papermc.io/v2/projects/paper/versions/${MC_VERSION}"

require_command() { command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 1; }; }
require_command curl
require_command java
require_command python3
[[ "$SERVER_TYPE" == "paper" || "$SERVER_TYPE" == "vanilla" ]] || { echo "SERVER_TYPE must be paper or vanilla." >&2; exit 1; }
mkdir -p "$SERVER_DIR"

if [[ "$SERVER_TYPE" == "paper" ]]; then
  BUILD="$(curl --fail --silent --show-error "$PAPER_API" | python3 -c 'import json,sys; print(json.load(sys.stdin)["builds"][-1])')"
  JAR_URL="${PAPER_API}/builds/${BUILD}/downloads/paper-${MC_VERSION}-${BUILD}.jar"
  echo "Downloading Paper ${MC_VERSION}, build ${BUILD}..."
else
  # Resolve the official server download from Mojang's version manifest.
  JAR_URL="$(curl --fail --silent --show-error https://piston-meta.mojang.com/mc/game/version_manifest_v2.json | MC_VERSION="$MC_VERSION" python3 -c '
import json, os, sys, urllib.request
manifest=json.load(sys.stdin)
version=next((v for v in manifest["versions"] if v["id"] == os.environ["MC_VERSION"]), None)
if not version: raise SystemExit("Unknown Minecraft version: " + os.environ["MC_VERSION"])
print(json.load(urllib.request.urlopen(version["url"]))["downloads"]["server"]["url"])')"
  echo "Downloading official Vanilla ${MC_VERSION} server..."
fi
curl --fail --location --silent --show-error "$JAR_URL" --output "$SERVER_DIR/server.jar"
printf 'eula=true\n' > "$SERVER_DIR/eula.txt"
[[ -f "${CONFIG_FILE:-server.properties}" ]] && cp "${CONFIG_FILE:-server.properties}" "$SERVER_DIR/server.properties"
if [[ "$SERVER_TYPE" == "paper" && -d "${PLUGINS_DIR:-plugins}" ]]; then
  mkdir -p "$SERVER_DIR/plugins"; cp -a "${PLUGINS_DIR:-plugins}/." "$SERVER_DIR/plugins/"
fi
cd "$SERVER_DIR"
echo "Starting ${SERVER_TYPE} server on TCP port 25565 (maximum heap: ${MAX_RAM})."
exec java -Xms1G -Xmx"$MAX_RAM" -jar server.jar --nogui
