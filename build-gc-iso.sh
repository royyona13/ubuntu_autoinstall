#!/bin/bash
set -euo pipefail

# base paths
BASE_DIR="$HOME/ubuntu-autoinstall-server"
EXTRACT_DIR="$BASE_DIR/extract"
AUTOINSTALL_DIR="$EXTRACT_DIR/autoinstall"

TEMPLATE="$AUTOINSTALL_DIR/user-data.template"
USER_DATA="$AUTOINSTALL_DIR/user-data"

# ===== INPUT =====
read -p "Enter computer number (e.g. 01): " NUM
HOSTNAME="gc-cb${NUM}"

read -s -p "Enter Linux user password: " USER_PASS
echo
read -s -p "Enter LUKS encryption passphrase: " LUKS_PASS
echo

# ===== HASH PASSWORD =====
USER_HASH=$(openssl passwd -6 "$USER_PASS")

# ===== CREATE USER-DATA =====
cp "$TEMPLATE" "$USER_DATA"

sed -i "s|__HOSTNAME__|$HOSTNAME|g" "$USER_DATA"
sed -i "s|__USER_PASSWORD_HASH__|$USER_HASH|g" "$USER_DATA"
sed -i "s|__LUKS_PASSWORD__|$LUKS_PASS|g" "$USER_DATA"


# ===== CREATE FIRST LOGIN SCRIPT (RDP PASSWORD) =====
GC_TEMPLATE="$AUTOINSTALL_DIR/gc-first-login.sh.template"
GC_SCRIPT="$AUTOINSTALL_DIR/gc-first-login.sh"

if [ -f "$GC_TEMPLATE" ]; then
  cp "$GC_TEMPLATE" "$GC_SCRIPT"
  sed -i "s|__RDP_PASSWORD__|$USER_PASS|g" "$GC_SCRIPT"
  chmod +x "$GC_SCRIPT"

# ===== BUILD ISO =====
OUT_ISO="$BASE_DIR/ubuntu-${HOSTNAME}-autoinstall.iso"

cd "$EXTRACT_DIR"

sudo xorriso -as mkisofs \
  -r -V "UbuntuServerAuto" \
  -o "$OUT_ISO" \
  -J -l -iso-level 3 \
  -partition_offset 16 \
  -b boot/grub/i386-pc/eltorito.img \
  -c boot.catalog \
  -no-emul-boot -boot-load-size 4 -boot-info-table \
  -eltorito-alt-boot \
  -e EFI/boot/bootx64.efi \
  -no-emul-boot \
  .

# ===== DONE =====
echo
echo "==============================="
echo "ISO created:"
echo "$OUT_ISO"
echo
echo "Hostname: $HOSTNAME"
echo "Username: gc"
echo "==============================="




echo "Detecting USB devices..."

mapfile -t USB_LIST < <(lsblk -dpno NAME,SIZE,MODEL,MOUNTPOINT | grep '/media/')

if [ ${#USB_LIST[@]} -eq 0 ]; then
  echo "No USB devices found under /media"
  lsblk -dpno NAME,SIZE,MODEL,MOUNTPOINT
  exit 1
fi

echo "Available USB devices:"
i=1
for dev in "${USB_LIST[@]}"; do
  echo "[$i] $dev"
  ((i++))
done

read -p "Select USB number: " choice

USB_DEV=$(echo "${USB_LIST[$((choice-1))]}" | awk '{print $1}')

echo "You selected: $USB_DEV"
read -p "WARNING: this will erase $USB_DEV. Type yes: " confirm

if [ "$confirm" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

echo "Unmounting USB partitions..."
sudo umount ${USB_DEV}?* 2>/dev/null || true

echo "Writing ISO to USB..."
sudo dd if="$OUT_ISO" of="$USB_DEV" bs=4M status=progress oflag=sync

sync

echo
echo "Done."
echo "USB is ready for $HOSTNAME"
echo "Username: gc"
