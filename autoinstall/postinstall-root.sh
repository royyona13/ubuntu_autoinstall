#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

USER_NAME="gc"
MARKER="/var/lib/gc-postinstall.done"

# Prevent rerun
if [ -f "$MARKER" ]; then
  echo "Postinstall already completed. Exiting."
  systemctl disable postinstall-root.service || true
  rm -f /etc/systemd/system/postinstall-root.service || true
  systemctl daemon-reload || true
  exit 0
fi

# Disable service immediately
systemctl disable postinstall-root.service || true

# Wait for network
for i in {1..60}; do
  if ping -c1 google.com >/dev/null 2>&1; then
    echo "Network is ready"
    break
  fi

  echo "Waiting for network... attempt $i"
  sleep 3
done

apt update -y

apt install -y openssh-server
systemctl enable ssh || true
systemctl start ssh || true

# Fix possible package issues
apt remove -y libglapi-amber || true
apt --fix-broken install -y || true
dpkg --configure -a || true
apt update -y

# Install full desktop + tools
apt install -y \
  ubuntu-desktop \
  gdm3 \
  docker.io docker-compose-v2 \
  python3-pip ninja-build wget sshpass \
  htop iptraf-ng usbtop git nano mc vim curl net-tools \
  build-essential checkinstall libssl-dev libsqlite3-dev \
  tk-dev libgdbm-dev libc6-dev libbz2-dev linux-generic \
  filezilla ntpdate yq mpv iperf3

systemctl enable gdm3
systemctl set-default graphical.target

# Docker permissions
usermod -aG docker "$USER_NAME" || true


# Create standard user folders
mkdir -p \
  /home/gc/Desktop \
  /home/gc/Documents \
  /home/gc/Downloads \
  /home/gc/Music \
  /home/gc/Pictures \
  /home/gc/Videos \
  /home/gc/src \
  /home/gc/src/irondrone \
  /home/gc/.config \
  /home/gc/.local
# Create irondrone folders
mkdir -p /irondrone

# Ownership
chown -R gc:gc /home/gc
chown -R gc:gc /irondrone

# Permissions
chmod 755 /home/gc
chmod 755 /home/gc/src
chmod 755 /home/gc/src/irondrone
chmod 755 /irondrone
chmod 700 /home/gc/.ssh

# SSH setup
mkdir -p "/home/$USER_NAME/.ssh"
chown -R "$USER_NAME:$USER_NAME" "/home/$USER_NAME/.ssh"
chmod 700 "/home/$USER_NAME/.ssh"

if [ ! -f "/home/$USER_NAME/.ssh/id_ed25519" ]; then
  sudo -u "$USER_NAME" ssh-keygen -t ed25519 \
    -f "/home/$USER_NAME/.ssh/id_ed25519" \
    -N '' \
    -C "$(hostname)"
fi

# VS Code
wget -O /tmp/code.deb \
  "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"

apt install -y /tmp/code.deb || apt-get -f install -y

# TeamViewer
wget -O /tmp/teamviewer.deb \
  "https://download.teamviewer.com/download/linux/teamviewer_amd64.deb"

apt install -y /tmp/teamviewer.deb || apt-get -f install -y

# Chrome
wget -O /tmp/chrome.deb \
  "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"

apt install -y /tmp/chrome.deb || apt-get -f install -y

# Chromium
apt install -y chromium-browser || true

# Firewall
ufw allow ssh
ufw allow 3389/tcp || true
ufw --force enable

# Fix ownership
chown -R "$USER_NAME:$USER_NAME" \
  "/home/$USER_NAME/.config" \
  "/home/$USER_NAME/.local" \
  "/home/$USER_NAME/.ssh" || true

# Mark complete
mkdir -p /var/lib
touch "$MARKER"

# Disable/remove postinstall service
systemctl daemon-reload || true

echo "Post install complete. Please reboot now."
reboot
exit 0
