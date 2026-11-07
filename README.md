# 📱 Lineage OS Installer for Samsung GUI

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![GUI: CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-0284C7?style=for-the-badge)](https://github.com/TomSchimansky/CustomTkinter)
[![Supported Devices](https://img.shields.io/badge/Samsung_Devices-120%2B_Models-10B981?style=for-the-badge&logo=samsung&logoColor=white)](https://wiki.lineageos.org/devices/#samsung)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows_10%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge)](./LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-8B5CF6?style=for-the-badge)](#-open-source--contributing)

**Lineage OS Installer for Samsung GUI** is an open-source, step-by-step desktop wizard built with Python and CustomTkinter that automates and demystifies installing **LineageOS** and **NikGapps (Google Apps)** across **120+ supported Samsung Galaxy smartphones and tablets**.

Unlike generic ADB wrappers, this tool is purpose-built for **Samsung's unique flashing ecosystem**—handling **Samsung Odin Download Mode**, **VaultKeeper (`KG STATUS: PRENORMAL`)**, **VBMeta `0xa` verification quirks**, **Bootloader Binary revision checks**, and **real-time USB/ADB/WMI hardware state transitions**.

---

## ⚠️ Legal Disclaimer & Risk Warning

```c
#include <std_disclaimer.h>
/*
 * Your warranty is now void (and Samsung Knox e-fuse 0x1 will be permanently tripped).
 *
 * LineageOS and this installer are provided "AS-IS" WITHOUT ANY WARRANTY of any kind.
 * We are NOT responsible for bricked devices, bootloops, loss of operating system (OS),
 * permanent data loss, tripped Knox (loss of Samsung Wallet/Pay, Secure Folder, Pass),
 * dead SD cards, thermonuclear war, or you getting fired because the alarm app failed.
 *
 * YOU are choosing to make these modifications to your device AT YOUR OWN RISK.
 */
```

- **Startup Acknowledgment**: On launch, the application presents a mandatory **Terms & Conditions / Risk Warning** modal that must be explicitly accepted before any flashing controls unlock.
- **Backup First**: Unlocking the bootloader and formatting `/data` in recovery **permanently erases all personal files, photos, and apps**.

---

## ✨ Key Features

- 🔎 **Universal Samsung Device Detector & LineageOS Version Advisor (120+ Models)**
  - Automatically detects any connected Samsung device over ADB (`ro.product.model`, `ro.product.device`, `ro.boot.bootloader`), matches it against **120+ official Samsung devices** from the LineageOS catalog, and queries the live **LineageOS API v2** (`download.lineageos.org/api/v2`) to recommend the **latest supported LineageOS branch, Android version, and exact nightly ZIP filename**.
  - Includes a searchable model lookup (`SM-XXXX`) and dropdown selector that dynamically adapts the entire 6-step wizard (including device-specific Download & Recovery hardware button combos).
- ⬇️ **Zero-Setup Tool Auto-Downloader**
  - One-click automatic downloading and extraction of official **Google Android SDK Platform-Tools (`adb.exe` & `fastboot.exe`)**, **Samsung Odin3 v3.14.1**, and **official `samloader-rs` CLI** directly into the local `tools/` directory.
- 📡 **Real-Time Multi-Mode USB & Hardware Telemetry**
  - Background polling thread continuously detects **ADB System Mode**, **ADB Unauthorized**, **Samsung Download Mode (Odin USB Modem / COM Port via Windows WMI/PnP)**, **Custom Recovery Mode**, and **ADB Sideload Mode**—with optional **Auto-Verify & Advance** to jump straight to the active step.
- 📦 **Smart Odin `.tar` Recovery Packager (Prevents `SW REV. CHECK FAIL(VBMETA)`)**
  - Automatically packages raw `recovery.img` into an Odin-ready USTAR `.tar` archive (`recovery.img` only) so modern Samsung bootloaders (such as Binary 10 / `0xa`) do not fail with `SW REV. CHECK FAIL(VBMETA) Device: 0xa, BINARY: 0x0`.
- ⚡ **One-Click Bootloader Binary Revision Bypass Patcher**
  - If an official LineageOS build aborts at 47% with `Error: This build requires a bootloader with binary version ...`, Step 5 includes a **⚡ Patch & Sideload** button that strips the strict bootloader revision assert from `updater-script` and streams the patched ROM immediately—saving users from a 5 GB stock firmware re-flash.
- 🚀 **Automated ADB Sideload Streaming Engine**
  - Streams both the **LineageOS ROM `.zip`** and **NikGapps `.zip`** via `adb sideload` with live percentage tracking and real-time console output.

---

## 🛠️ Tech Stack & Architecture

| Layer | Technology / Library | Purpose |
| :--- | :--- | :--- |
| **Language** | **Python 3.10+** | Core application logic, multithreaded subprocess orchestration, archive manipulation |
| **Desktop GUI** | **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)** + **Pillow** | Modern dark-mode 6-step wizard UI, live telemetry banner, modal dialogs, progress bars |
| **Networking & APIs** | **Requests** + **LineageOS API v2 & Wiki** | Live nightly build discovery (`download.lineageos.org/api/v2`), 120+ Samsung Wiki catalog sync, and tool auto-downloads |
| **Hardware Detection** | **Android ADB** + **Windows CIM / WMI (`Win32_PnPEntity`)** | Real-time detection of ADB states (`system`, `recovery`, `sideload`) and Samsung Odin Download Mode (`VID_04E8` USB Modem / COM ports) |
| **Flashing Engines** | **Samsung Odin3 / Odin4 CLI / `samloader-rs` / Heimdall / `adb sideload`** | Multi-backend Download Mode partition flashing and Recovery OTA/ZIP streaming |
| **Binary & Archive Processing** | Python `tarfile` (USTAR), `zipfile`, `struct`, `hashlib` | Building Odin-compatible `.tar` archives, AVB0 `vbmeta.img` generation, and on-the-fly ROM `updater-script` patching |

### 📂 Project Structure

```text
lineage-os-installer-samsung-gui/
├── main.py                         # Main CustomTkinter GUI Wizard (6 steps, startup T&C modal, UI state sync)
├── core/                           # Modular backend package
│   ├── __init__.py
│   ├── archive_builder.py          # Auto-downloads ADB/Odin3/samloader, builds Odin .tar, patches ROM ZIPs
│   ├── device_manager.py           # Real-time ADB property reader & Windows WMI/PnP Odin COM port scanner
│   ├── flash_engine.py             # Subprocess runner for Odin3, Odin4, samloader-rs, Heimdall & ADB Sideload
│   └── samsung_db.py               # Universal 120+ Samsung device database & Live LineageOS API v2 client
├── tools/
│   └── samsung_lineage_db.json     # Pre-synced catalog of 120+ Samsung devices (models, SoCs, button combos)
├── requirements.txt                # Python dependencies (customtkinter, requests, pillow, packaging)
├── run_installer.bat               # One-click Windows launcher with automatic dependency installation
├── LICENSE                         # MIT License + Custom ROM risk disclaimer
└── README.md                       # Project documentation
```

---

## 🚀 Quick Start & Installation

### Prerequisites
1. **Windows 10 or Windows 11** (64-bit).
2. **[Python 3.10 or newer](https://www.python.org/downloads/)** installed (check *"Add Python to PATH"* during installation).
3. **Samsung USB Cable** connected to your PC and Samsung Galaxy phone/tablet.

### 1. Clone the Repository
```powershell
git clone https://github.com/B3RZERK20/lineage-os-installer-samsung-gui.git
cd lineage-os-installer-samsung-gui
```

### 2. Launch the Application
- **Option A (One-Click Windows Launcher):**
  Double-click **[`run_installer.bat`](./run_installer.bat)**.
- **Option B (Terminal):**
  ```powershell
  pip install -r requirements.txt
  python main.py
  ```
  *(Note: `main.py` also includes a built-in bootstrapper that automatically installs `requirements.txt` if any package is missing on first launch!)*

---

## 🧭 How the 6-Step Installation Wizard Works

1. **Step 1 — Universal Samsung Device Advisor, Tools & Files**
   - Plug in your Samsung phone (or pick from the **120+ Samsung models dropdown**) to see the exact **latest supported LineageOS version** and required stock Android base.
   - Click **⬇ Auto-Download ADB & Platform-Tools** and install the **Samsung USB Driver**.
   - Click **🌐 Open LineageOS Downloads for Selected Phone** and download **only 2 files**:
     1. `lineage-<version>-YYYYMMDD-nightly-<codename>-signed.zip`
     2. `recovery.img`
   - Download your matching `NikGapps-core-<arch>-...zip` (optional, for Google Play Store) and click **🔍 Auto-Find Files in My 'Downloads' Folder**.
2. **Step 2 — Connect Phone & Automatic Pre-Flight Check**
   - Enable **OEM unlocking** (with Wi-Fi connected!) and **USB debugging** in Developer Options.
   - The app automatically verifies your USB connection, Samsung model, stock Android base, and Bootloader lock state.
3. **Step 3 — Bootloader Unlock & Samsung Download Mode**
   - Reboot into Download Mode with 1 click (or follow the device-specific hardware button combo shown on screen) and unlock the bootloader if not already unlocked.
4. **Step 4 — Flash Lineage Recovery in Download Mode**
   - **Option A (Odin3 GUI):** Builds a clean `recovery.img`-only `.tar` archive, copies the path to your clipboard (`Ctrl+V` into Odin's `[AP]` slot), and launches **Odin3 v3.14.1** automatically.
   - **Option B (`samloader-rs` CLI):** Flashes `RECOVERY` directly from Download Mode without opening Odin.
   - Follow the on-screen button combo to boot straight into **Lineage Recovery**.
5. **Step 5 — Format Data & Automated LineageOS Sideload**
   - In Lineage Recovery, select **Factory reset -> Format data / factory reset**, then **Apply update -> Apply from ADB**.
   - Click **🚀 Start LineageOS Automated ADB Sideload** (or **⚡ Patch & Sideload** if your bootloader binary revision is older than the nightly's assert).
6. **Step 6 — Flash NikGapps & First Boot**
   - Reboot to recovery to reload the slot/partition layout, start **Apply from ADB**, and click **🚀 Start NikGapps Automated ADB Sideload**, then **🎉 Reboot Phone into LineageOS System**!

---

## 🛟 Built-In Solutions to Common Samsung Flashing Errors

| Error Message on Phone / Recovery | Root Cause | How This Installer Solves It |
| :--- | :--- | :--- |
| **`Only official released binaries are allowed to be flashed (RECOVERY)`** | `KG STATE : PRENORMAL` (Samsung VaultKeeper is active after a wipe/unlock) or `OEM LOCK : ON (L)`. | **Step 4 Troubleshooter** walks you through booting into One UI, connecting to Wi-Fi for 60 seconds, and verifying `OEM unlocking` in Developer Options so `KG STATE` switches to `CHECKING` / `COMPLETED`. |
| **`SW REV. CHECK FAIL(VBMETA) Device: 0xa, BINARY: 0x0`** | Flashing an unsigned `vbmeta.img` on newer Samsung bootloaders (Bit 10 / `0xa`). | [`ArchiveBuilder.build_odin_recovery_tar()`](./core/archive_builder.py) packages **only** `recovery.img` into the Odin `.tar` archive (skipping unsigned `vbmeta.img`). |
| **`Error: This build requires a bootloader with binary version C`** | Official LineageOS nightly checks for a newer stock bootloader security revision than installed. | **Step 5** includes **⚡ Patch & Sideload**, calling [`ArchiveBuilder.create_bootloader_bypass_rom_zip()`](./core/archive_builder.py) to strip the bootloader assert and sideload immediately. |

---

## 🤝 Open Source & Contributing

**Lineage OS Installer for Samsung GUI** is **100% open-source** under the [MIT License](./LICENSE) and is architected to welcome community contributions, new device quirks, and cross-platform extensions!

### 🌟 Roadmap & Ideas for Future Contributions
We welcome Pull Requests (PRs) and Issues for:
- [ ] **Cross-Platform Linux & macOS Support**: Expand [`DeviceManager`](./core/device_manager.py) to use `lsusb` / `system_profiler` alongside Heimdall & `samloader-rs` on Linux and macOS.
- [ ] **Direct In-App ROM & Recovery Downloader**: Stream the latest `lineage-*.zip` and `recovery.img` directly from `download.lineageos.org/api/v2` with automatic `SHA-256` verification.
- [ ] **Unofficial / XDA / TWRP Catalog Support**: Allow community maintainers to register unofficial LineageOS builds and TWRP `.img`/`.tar` links for Samsung devices not in the official LineageOS roster.
- [ ] **Optional Post-Install Add-ons**: One-click sideload support for Magisk / Lygisk, MindTheGapps, or F-Droid privileged extension in Step 6.
- [ ] **Automated Stock Firmware Downloader**: Integrate `samloader` firmware download & decryption for users who want to upgrade their stock `BL` / `CP` modem partitions.

### How to Contribute
1. **Fork** this repository on GitHub.
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes in [`main.py`](./main.py) or [`core/`](./core/) and test with `python main.py`.
4. Commit and push your branch:
   ```bash
   git commit -m "feat: add description of your improvement"
   git push origin feature/your-feature-name
   ```
5. Open a **Pull Request**!

---

## 📜 License & Acknowledgments

- Licensed under the **[MIT License](./LICENSE)**.
- Built for the **[LineageOS](https://lineageos.org/)** & **[NikGapps](https://nikgapps.com/)** communities.
- Uses official tools from Google ([Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)) and [`samloader-rs`](https://github.com/topjohnwu/samloader-rs).
- *Not affiliated with or endorsed by Samsung Electronics Co., Ltd. or LineageOS LLC.*
