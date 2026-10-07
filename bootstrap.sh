#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ${1:-} == --plan ]]; then
  echo 'Ubuntu 24.04 x86_64: install Docker/Compose, SteamCMD prerequisites and Python; create a dedicated download account; install server app 1863440; build runtime and prepare isolated instances. No instance starts until you add a token and config.'
  exit 0
fi
[[ $EUID == 0 ]] || { echo 'Run: sudo bash bootstrap.sh [settings.json]' >&2; exit 1; }
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $(uname -m) == x86_64 ]] || { echo 'Requires Ubuntu 24.04 x86_64.' >&2; exit 1; }
settings=${1:-settings.json}
# Validate before changing the host.
python3 bl.py --settings "$settings" validate
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl tar python3 lib32gcc-s1 lib32stdc++6 rsync
if ! command -v docker >/dev/null; then
  install -d -m 755 /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<'APT'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
APT
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version >/dev/null
systemctl enable --now docker
id bl-download >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/bl-download --shell /usr/sbin/nologin bl-download
[[ $(getent passwd bl-download | cut -d: -f6) == /var/lib/bl-download ]] || { echo 'Existing bl-download account has a different home; refusing to reuse it.' >&2; exit 1; }
python3 bl.py --settings "$settings" provision
echo 'Prepared. Add each instance token/config, then start it. See README.md.'
