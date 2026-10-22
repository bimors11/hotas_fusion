#!/usr/bin/env bash
# Install HOTAS Fusion and enable its system-wide boot service.
set -euo pipefail

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo "Usage: sudo bash install.sh"
    echo "Installs to /opt/hotas-fusion and starts the systemd service."
    exit 0
fi
if (( $# != 0 )); then
    echo "Unexpected arguments. Usage: sudo bash install.sh" >&2
    exit 1
fi
if (( EUID != 0 )); then
    echo "Run this installer as root: sudo bash install.sh" >&2
    exit 1
fi
if [[ $(uname -s) != Linux || ! -d /run/systemd/system ]]; then
    echo "HOTAS Fusion requires Linux running systemd." >&2
    exit 1
fi

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install_dir=/opt/hotas-fusion
for file in hotas_fusion.py requirements.txt systemd/hotas-fusion.service udev/99-hotas-fusion.rules; do
    if [[ ! -f "$source_dir/$file" ]]; then
        echo "Missing project file: $source_dir/$file" >&2
        exit 1
    fi
done

echo "Installing system dependencies..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y python3 python3-venv python3-dev build-essential linux-libc-dev kmod
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 python3-pip python3-devel gcc kernel-headers kmod
elif command -v pacman >/dev/null 2>&1; then
    pacman -S --needed --noconfirm python python-pip gcc linux-api-headers kmod
else
    echo "Unsupported package manager. Supported: apt-get, dnf, pacman." >&2
    exit 1
fi

echo "Preparing Python environment..."
install -d -m 0755 "$install_dir"
python3 -m venv "$install_dir/.venv"
"$install_dir/.venv/bin/python" -m pip install -r "$source_dir/requirements.txt"
"$install_dir/.venv/bin/python" -c 'import evdev'

# Stop an existing instance before replacing its application file.
if systemctl cat hotas-fusion.service >/dev/null 2>&1; then
    systemctl stop hotas-fusion.service
fi
install -m 0644 "$source_dir/hotas_fusion.py" "$install_dir/hotas_fusion.py"
install -m 0644 "$source_dir/requirements.txt" "$install_dir/requirements.txt"
install -d -m 0755 /etc/modules-load.d /etc/udev/rules.d /etc/systemd/system
printf 'uinput\njoydev\n' > /etc/modules-load.d/hotas-fusion.conf
modprobe uinput
modprobe joydev
install -m 0644 "$source_dir/systemd/hotas-fusion.service" /etc/systemd/system/hotas-fusion.service
install -m 0644 "$source_dir/udev/99-hotas-fusion.rules" /etc/udev/rules.d/99-hotas-fusion.rules
systemctl daemon-reload
udevadm control --reload-rules
systemctl enable --now hotas-fusion.service
systemctl --no-pager --full status hotas-fusion.service
echo "Installed. HOTAS Fusion will start at boot and wait for both devices."
echo "Logs: journalctl -u hotas-fusion.service -f"
