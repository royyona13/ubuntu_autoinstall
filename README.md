Ubuntu Auto Install Builder — Setup Instructions
Requirements
=================================================================================================
Before running the scripts, make sure you have:

1. Ubuntu 24.04.2 ISO
  Download: https://old-releases.ubuntu.com/releases/24.04.2/ubuntu-24.04.2-desktop-amd64.iso
  Place it in:
  ~/Downloads/

2. run: git clone https://github.com/royyona13/ubuntu_autoinstall.git
3. Make sure extract and mnt folders are on the same place as the code (ubuntu_autoinstall).

4. Install required packages:

    sudo apt update
    sudo apt install -y \
    xorriso \
    grub-pc-bin \
    grub-efi-amd64-bin \
    mtools \
    python3 \
    python3-pip
    Running the Builder

5. Go into the project folder:
  cd ubuntu-autoinstall-server

    Run the GUI builder:
    python3 build-gc-gui.py
