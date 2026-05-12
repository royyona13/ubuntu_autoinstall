#!/usr/bin/env python3
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

BASE_DIR = Path.home() / "ubuntu-autoinstall-server"
EXTRACT_DIR = BASE_DIR / "extract"
AUTOINSTALL_DIR = EXTRACT_DIR / "autoinstall"

ORIGINAL_ISO = Path.home() / "Downloads" / "ubuntu-24.04.2-live-server-amd64.iso"

TEMPLATE = AUTOINSTALL_DIR / "user-data.template"
USER_DATA = AUTOINSTALL_DIR / "user-data"

GC_LOGIN_TEMPLATE = AUTOINSTALL_DIR / "gc-first-login.sh.template"
GC_LOGIN_SCRIPT = AUTOINSTALL_DIR / "gc-first-login.sh"


def run(cmd, cwd=None):
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)


def get_usb_devices():
    try:
        result = subprocess.check_output(
            "lsblk -dpno NAME,SIZE,MODEL,TYPE | awk '$5==\"disk\" {print $1\"|\"$2\"|\"$3}'",
            shell=True,
            text=True
        )

        devices = []
        for line in result.splitlines():
            if not line.strip():
                continue

            parts = line.split("|")
            if len(parts) < 3:
                continue

            name, size, model = parts[0], parts[1], parts[2]

            if "nvme" in name:
                continue

            devices.append(f"{name} - {size} - {model}")

        return devices

    except Exception as e:
        print("USB detection failed:", e)
        return []


def build_and_flash():
    num = entry_num.get().strip()
    user_pass = entry_user_pass.get()
    luks_pass = entry_luks_pass.get()
    usb_line = usb_combo.get()

    if not num or not user_pass or not luks_pass or not usb_line:
        messagebox.showerror("Missing data", "Fill all fields and select USB.")
        return

    if not ORIGINAL_ISO.exists():
        messagebox.showerror("Missing ISO", f"Original ISO not found:\n{ORIGINAL_ISO}")
        return

    num = num.replace("gc-cb", "")
    hostname = f"gc-cb{num}"

    usb_dev = usb_line.split()[0]
    out_iso = BASE_DIR / f"ubuntu-{hostname}-autoinstall.iso"

    if "nvme" in usb_dev:
        messagebox.showerror("Unsafe device", "Refusing to write to NVMe disk.")
        return

    if not messagebox.askyesno(
        "Confirm USB erase",
        f"This will erase:\n\n{usb_dev}\n\nContinue?"
    ):
        return

    try:
        status.set("Creating password hash...")
        root.update()

        user_hash = subprocess.check_output(
            ["openssl", "passwd", "-6", user_pass],
            text=True
        ).strip()

        status.set("Creating user-data...")
        root.update()

        data = TEMPLATE.read_text()
        data = data.replace("__HOSTNAME__", hostname)
        data = data.replace("__USER_PASSWORD_HASH__", user_hash)
        data = data.replace("__LUKS_PASSWORD__", luks_pass)
        USER_DATA.write_text(data)

        if "__HOSTNAME__" in data or "__USER_PASSWORD_HASH__" in data or "__LUKS_PASSWORD__" in data:
            raise RuntimeError("Template replacement failed.")

        status.set("Creating gc-first-login.sh...")
        root.update()

        login_data = GC_LOGIN_TEMPLATE.read_text()
        login_data = login_data.replace("__RDP_PASSWORD__", user_pass)
        GC_LOGIN_SCRIPT.write_text(login_data)

        status.set("Fixing script formats and permissions...")
        root.update()

        run(f"dos2unix '{AUTOINSTALL_DIR}/postinstall-root.sh' >/dev/null 2>&1 || true")
        run(f"chmod +x '{AUTOINSTALL_DIR}/postinstall-root.sh'")

        if GC_LOGIN_SCRIPT.exists():
            run(f"dos2unix '{GC_LOGIN_SCRIPT}' >/dev/null 2>&1 || true")
            run(f"chmod +x '{GC_LOGIN_SCRIPT}'")

        status.set("Building ISO from official Ubuntu ISO...")
        root.update()

        if out_iso.exists():
            out_iso.unlink()

        run(f"""
        sudo xorriso \
          -indev "{ORIGINAL_ISO}" \
          -outdev "{out_iso}" \
          -boot_image any replay \
          -map "{AUTOINSTALL_DIR}" /autoinstall \
          -map "{BASE_DIR}/grub.cfg" /boot/grub/grub.cfg
        """)

        status.set("Unmounting USB...")
        root.update()

        run(f"sudo umount {usb_dev}?* 2>/dev/null || true")

        status.set("Wiping old USB signatures...")
        root.update()

        run(f"sudo wipefs -a {usb_dev}")

        status.set("Writing ISO to USB...")
        root.update()

        run(f"sudo dd if='{out_iso}' of='{usb_dev}' bs=4M status=progress conv=fsync")

        status.set("Syncing...")
        root.update()

        run("sync")

        status.set("Powering off USB safely...")
        root.update()

        run(f"sudo udisksctl power-off -b {usb_dev} || true")

        status.set("Done.")
        messagebox.showinfo("Done", f"USB is ready for {hostname}\n\nUsername: gc")

    except subprocess.CalledProcessError as e:
        status.set("Failed.")
        messagebox.showerror("Command failed", str(e))

    except Exception as e:
        status.set("Failed.")
        messagebox.showerror("Error", str(e))


def refresh_usb():
    devices = get_usb_devices()
    usb_combo["values"] = devices

    if devices:
        usb_combo.current(0)
        status.set("USB detected.")
    else:
        status.set("No USB detected.")


root = tk.Tk()
root.title("GC Ubuntu Autoinstall USB Builder")
root.geometry("700x360")

frame = ttk.Frame(root, padding=20)
frame.pack(fill="both", expand=True)

ttk.Label(frame, text="Computer number, example 12:").pack(anchor="w")
entry_num = ttk.Entry(frame)
entry_num.pack(fill="x")

ttk.Label(frame, text="Linux user password:").pack(anchor="w", pady=(10, 0))
entry_user_pass = ttk.Entry(frame, show="*")
entry_user_pass.pack(fill="x")

ttk.Label(frame, text="LUKS encryption passphrase:").pack(anchor="w", pady=(10, 0))
entry_luks_pass = ttk.Entry(frame, show="*")
entry_luks_pass.pack(fill="x")

ttk.Label(frame, text="USB device:").pack(anchor="w", pady=(10, 0))
usb_combo = ttk.Combobox(frame, width=90)
usb_combo.pack(fill="x")

ttk.Button(frame, text="Refresh USB List", command=refresh_usb).pack(pady=8)
ttk.Button(frame, text="Build ISO and Flash USB", command=build_and_flash).pack(pady=8)

status = tk.StringVar(value="Ready.")
ttk.Label(frame, textvariable=status).pack(anchor="w", pady=(10, 0))

refresh_usb()
root.mainloop()
