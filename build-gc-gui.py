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
GRUB_CFG = EXTRACT_DIR / "boot" / "grub" / "grub.cfg"

GC_LOGIN_TEMPLATE = AUTOINSTALL_DIR / "gc-first-login.sh.template"
GC_LOGIN_SCRIPT = AUTOINSTALL_DIR / "gc-first-login.sh"


def run(cmd, cwd=None):
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)


def set_status(text):
    status.set(text)
    root.update_idletasks()


def set_busy(is_busy):
    state = "disabled" if is_busy else "normal"
    refresh_button.config(state=state)
    build_button.config(state=state)
    num_entry.config(state=state)
    user_pass_entry.config(state=state)
    luks_pass_entry.config(state=state)
    usb_combo.config(state="disabled" if is_busy else "readonly")


def update_summary(*_):
    num = num_var.get().strip()
    hostname = f"gc-cb{num.replace('gc-cb', '')}" if num else "gc-cbXX"
    usb_text = usb_var.get().strip() or "No USB selected"
    summary_text.set(f"Target host: {hostname}   |   USB: {usb_text}")


def toggle_password_visibility(entry_widget, visible_var):
    entry_widget.config(show="" if visible_var.get() else "*")


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
    num = num_var.get().strip()
    user_pass = user_pass_var.get()
    luks_pass = luks_pass_var.get()
    usb_line = usb_var.get().strip()

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

    set_busy(True)

    try:
        set_status("Creating password hash...")

        user_hash = subprocess.check_output(
            ["openssl", "passwd", "-6", user_pass],
            text=True
        ).strip()

        set_status("Creating user-data...")

        data = TEMPLATE.read_text()
        data = data.replace("__HOSTNAME__", hostname)
        data = data.replace("__USER_PASSWORD_HASH__", user_hash)
        data = data.replace("__LUKS_PASSWORD__", luks_pass)
        USER_DATA.write_text(data)

        if "__HOSTNAME__" in data or "__USER_PASSWORD_HASH__" in data or "__LUKS_PASSWORD__" in data:
            raise RuntimeError("Template replacement failed.")

        set_status("Creating first-login script...")

        login_data = GC_LOGIN_TEMPLATE.read_text()
        login_data = login_data.replace("__RDP_PASSWORD__", user_pass)
        GC_LOGIN_SCRIPT.write_text(login_data)

        set_status("Normalizing script formats and permissions...")

        run(f"dos2unix '{AUTOINSTALL_DIR}/postinstall-root.sh' >/dev/null 2>&1 || true")
        run(f"chmod +x '{AUTOINSTALL_DIR}/postinstall-root.sh'")

        if GC_LOGIN_SCRIPT.exists():
            run(f"dos2unix '{GC_LOGIN_SCRIPT}' >/dev/null 2>&1 || true")
            run(f"chmod +x '{GC_LOGIN_SCRIPT}'")

        set_status("Building ISO from official Ubuntu ISO...")

        if out_iso.exists():
            out_iso.unlink()

        if not GRUB_CFG.exists():
            raise FileNotFoundError(f"Missing grub config: {GRUB_CFG}")

        run(f"""
        sudo xorriso \
          -indev "{ORIGINAL_ISO}" \
          -outdev "{out_iso}" \
          -boot_image any replay \
          -map "{AUTOINSTALL_DIR}" /autoinstall \
          -map "{GRUB_CFG}" /boot/grub/grub.cfg
        """)

        set_status("Unmounting USB...")

        run(f"sudo umount {usb_dev}?* 2>/dev/null || true")

        set_status("Wiping old USB signatures...")

        run(f"sudo wipefs -a {usb_dev}")

        set_status("Writing ISO to USB...")

        run(f"sudo dd if='{out_iso}' of='{usb_dev}' bs=4M status=progress conv=fsync")

        set_status("Syncing...")

        run("sync")

        set_status("Powering off USB safely...")

        run(f"sudo udisksctl power-off -b {usb_dev} || true")

        set_status("Done.")
        messagebox.showinfo("Done", f"USB is ready for {hostname}\n\nUsername: gc")

    except subprocess.CalledProcessError as e:
        set_status("Failed.")
        messagebox.showerror("Command failed", str(e))

    except Exception as e:
        set_status("Failed.")
        messagebox.showerror("Error", str(e))

    finally:
        set_busy(False)


def refresh_usb():
    devices = get_usb_devices()
    usb_combo["values"] = devices

    if devices:
        usb_combo.current(0)
        set_status("USB detected.")
    else:
        usb_var.set("")
        set_status("No USB detected.")

    update_summary()


root = tk.Tk()
root.title("GC Ubuntu Autoinstall Builder")
root.geometry("960x620")
root.minsize(880, 560)
root.configure(bg="#eef2f6")

style = ttk.Style(root)
try:
    style.theme_use("clam")
except tk.TclError:
    pass

style.configure("App.TFrame", background="#eef2f6")
style.configure("Header.TFrame", background="#0f2747")
style.configure("Card.TFrame", background="#ffffff")
style.configure("Title.TLabel", background="#0f2747", foreground="#ffffff", font=("TkDefaultFont", 20, "bold"))
style.configure("SubTitle.TLabel", background="#0f2747", foreground="#c6d2e3", font=("TkDefaultFont", 10))
style.configure("CardTitle.TLabel", background="#ffffff", foreground="#0f2747", font=("TkDefaultFont", 13, "bold"))
style.configure("Body.TLabel", background="#ffffff", foreground="#3f4d63", font=("TkDefaultFont", 10))
style.configure("Field.TLabel", background="#ffffff", foreground="#1f2d40", font=("TkDefaultFont", 10, "bold"))
style.configure("Summary.TLabel", background="#edf3f9", foreground="#17324f", padding=(12, 8), font=("TkDefaultFont", 10, "bold"))
style.configure("Status.TLabel", background="#eef2f6", foreground="#3f4d63", font=("TkDefaultFont", 10))
style.configure("Accent.TButton", padding=(14, 9), font=("TkDefaultFont", 10, "bold"))

status = tk.StringVar(value="Ready.")
summary_text = tk.StringVar(value="Target host: gc-cbXX   |   USB: No USB selected")
num_var = tk.StringVar()
user_pass_var = tk.StringVar()
luks_pass_var = tk.StringVar()
usb_var = tk.StringVar()
show_user_pass_var = tk.BooleanVar(value=False)
show_luks_pass_var = tk.BooleanVar(value=False)

num_var.trace_add("write", update_summary)
usb_var.trace_add("write", update_summary)

root.columnconfigure(0, weight=1)
root.rowconfigure(1, weight=1)

header = ttk.Frame(root, style="Header.TFrame", padding=(24, 20))
header.grid(row=0, column=0, sticky="ew")
header.columnconfigure(0, weight=1)

ttk.Label(header, text="GC Ubuntu Autoinstall Builder", style="Title.TLabel").grid(row=0, column=0, sticky="w")
ttk.Label(
    header,
    text="Prepare a custom Ubuntu autoinstall ISO and flash it to a removable USB device.",
    style="SubTitle.TLabel"
).grid(row=1, column=0, sticky="w", pady=(6, 0))

content = ttk.Frame(root, style="App.TFrame", padding=24)
content.grid(row=1, column=0, sticky="nsew")
content.columnconfigure(0, weight=3)
content.columnconfigure(1, weight=2)
content.rowconfigure(0, weight=1)

form_card = ttk.Frame(content, style="Card.TFrame", padding=20)
form_card.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
form_card.columnconfigure(0, weight=1)

ttk.Label(form_card, text="Build settings", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
ttk.Label(
    form_card,
    text="Use the fields below to define the hostname, local account password, disk unlock passphrase, and target USB device.",
    style="Body.TLabel",
    wraplength=540,
    justify="left"
).grid(row=1, column=0, sticky="w", pady=(6, 18))

fields = ttk.Frame(form_card, style="Card.TFrame")
fields.grid(row=2, column=0, sticky="nsew")
fields.columnconfigure(0, weight=1)

ttk.Label(fields, text="Computer number", style="Field.TLabel").grid(row=0, column=0, sticky="w")
num_entry = ttk.Entry(fields, textvariable=num_var)
num_entry.grid(row=1, column=0, sticky="ew", pady=(6, 12))

ttk.Label(fields, text="Linux user password", style="Field.TLabel").grid(row=2, column=0, sticky="w")
user_pass_row = ttk.Frame(fields, style="Card.TFrame")
user_pass_row.grid(row=3, column=0, sticky="ew", pady=(6, 12))
user_pass_row.columnconfigure(0, weight=1)
user_pass_entry = ttk.Entry(user_pass_row, textvariable=user_pass_var, show="*")
user_pass_entry.grid(row=0, column=0, sticky="ew")
ttk.Checkbutton(
    user_pass_row,
    text="Show",
    variable=show_user_pass_var,
    command=lambda: toggle_password_visibility(user_pass_entry, show_user_pass_var)
).grid(row=0, column=1, padx=(10, 0))

ttk.Label(fields, text="LUKS encryption passphrase", style="Field.TLabel").grid(row=4, column=0, sticky="w")
luks_pass_row = ttk.Frame(fields, style="Card.TFrame")
luks_pass_row.grid(row=5, column=0, sticky="ew", pady=(6, 12))
luks_pass_row.columnconfigure(0, weight=1)
luks_pass_entry = ttk.Entry(luks_pass_row, textvariable=luks_pass_var, show="*")
luks_pass_entry.grid(row=0, column=0, sticky="ew")
ttk.Checkbutton(
    luks_pass_row,
    text="Show",
    variable=show_luks_pass_var,
    command=lambda: toggle_password_visibility(luks_pass_entry, show_luks_pass_var)
).grid(row=0, column=1, padx=(10, 0))

ttk.Label(fields, text="USB device", style="Field.TLabel").grid(row=6, column=0, sticky="w")
usb_combo = ttk.Combobox(fields, textvariable=usb_var, state="readonly")
usb_combo.grid(row=7, column=0, sticky="ew", pady=(6, 6))

button_row = ttk.Frame(form_card, style="Card.TFrame")
button_row.grid(row=3, column=0, sticky="ew", pady=(18, 0))
button_row.columnconfigure(0, weight=1)
button_row.columnconfigure(1, weight=1)

refresh_button = ttk.Button(button_row, text="Refresh Devices", command=refresh_usb)
refresh_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

build_button = ttk.Button(button_row, text="Build and Flash", command=build_and_flash, style="Accent.TButton")
build_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

side_card = ttk.Frame(content, style="Card.TFrame", padding=20)
side_card.grid(row=0, column=1, sticky="nsew")
side_card.columnconfigure(0, weight=1)

ttk.Label(side_card, text="Operational summary", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
ttk.Label(side_card, textvariable=summary_text, style="Summary.TLabel", wraplength=280, justify="left").grid(
    row=1,
    column=0,
    sticky="ew",
    pady=(10, 18)
)

ttk.Label(side_card, text="What this tool does", style="Field.TLabel").grid(row=2, column=0, sticky="w")
ttk.Label(
    side_card,
    text="1. Creates autoinstall files\n2. Builds a customized ISO\n3. Writes the ISO to the selected USB\n4. Powers the USB off safely",
    style="Body.TLabel",
    justify="left",
    wraplength=280
).grid(row=3, column=0, sticky="w", pady=(6, 16))

ttk.Label(side_card, text="Checks before flashing", style="Field.TLabel").grid(row=4, column=0, sticky="w")
ttk.Label(
    side_card,
    text=f"• Official ISO: {ORIGINAL_ISO}\n• Output ISO: {BASE_DIR / 'ubuntu-gc-cbXX-autoinstall.iso'}\n• Only removable drives are listed",
    style="Body.TLabel",
    justify="left",
    wraplength=280
).grid(row=5, column=0, sticky="w", pady=(6, 0))

footer = ttk.Frame(root, style="App.TFrame", padding=(24, 0, 24, 20))
footer.grid(row=2, column=0, sticky="ew")
footer.columnconfigure(0, weight=1)

ttk.Separator(footer).grid(row=0, column=0, sticky="ew", pady=(0, 12))
ttk.Label(footer, textvariable=status, style="Status.TLabel").grid(row=1, column=0, sticky="w")

root.bind("<Return>", lambda _event: build_and_flash())

refresh_usb()
update_summary()
root.after_idle(lambda: num_entry.focus_set())
root.mainloop()
