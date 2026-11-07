import os
import json
import subprocess
import threading
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class DeviceStatus:
    mode: str = "disconnected"  # disconnected, unauthorized, system, recovery, sideload, download
    serial: str = ""
    model: str = ""
    device_codename: str = ""
    android_version: str = ""
    oneui_version: str = ""
    security_patch: str = ""
    bootloader_state: str = "unknown"  # locked, unlocked, unknown
    bootloader_version: str = ""       # e.g. A217FXXUAA... or G973FXXU...
    bootloader_binary_char: str = ""   # e.g. 'A', 'B', 'C', '8'
    kg_status: str = "unknown"         # Prenormal, Checking, Completed, Locked, etc.
    oem_unlock_toggle: str = "unknown" # 1 (ON), 0 (OFF)
    battery_level: int = -1
    com_port: str = ""
    usb_driver_ok: bool = False
    is_a217f: bool = False
    raw_details: str = ""


class DeviceManager:
    """Handles real-time detection and interaction with Samsung Galaxy A21s (SM-A217F/DS)
    across ADB (System, Recovery, Sideload) and Samsung Download Mode (Odin/Modem COM port)."""

    def __init__(self, adb_path_getter: Callable[[], str], log_callback: Optional[Callable[[str], None]] = None):
        self.get_adb_path = adb_path_getter
        self.log = log_callback or (lambda msg: None)
        self.current_status = DeviceStatus()
        self._lock = threading.Lock()

    def _run_cmd(self, args: List[str], timeout: int = 8) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="replace"
        )

    def check_device(self) -> DeviceStatus:
        """Polls both ADB and Windows USB/PnP devices to determine the exact phone state."""
        status = DeviceStatus()
        adb_exe = self.get_adb_path()

        # 1. Check ADB if available
        if adb_exe and os.path.exists(adb_exe):
            try:
                res = self._run_cmd([adb_exe, "devices", "-l"], timeout=5)
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                for line in lines[1:]:  # skip "List of devices attached"
                    parts = line.split()
                    if len(parts) >= 2:
                        serial = parts[0]
                        state = parts[1]
                        status.serial = serial
                        status.usb_driver_ok = True

                        if state == "unauthorized":
                            status.mode = "unauthorized"
                            status.raw_details = "USB Debugging authorization pending on phone screen."
                            with self._lock:
                                self.current_status = status
                            return status
                        elif state == "sideload":
                            status.mode = "sideload"
                            status.model = ""
                            status.device_codename = ""
                            status.raw_details = f"Ready for ADB Sideload ({serial})"
                            with self._lock:
                                self.current_status = status
                            return status
                        elif state == "recovery":
                            status.mode = "recovery"
                            self._populate_adb_props(adb_exe, serial, status)
                            with self._lock:
                                self.current_status = status
                            return status
                        elif state == "device":
                            status.mode = "system"
                            self._populate_adb_props(adb_exe, serial, status)
                            with self._lock:
                                self.current_status = status
                            return status
            except Exception:
                pass

        # 2. Check Windows WMI / PnP for Samsung Download Mode or Unrecognized USB
        if os.name == "nt":
            dl_info = self._check_windows_samsung_usb()
            if dl_info.get("download_mode"):
                status.mode = "download"
                status.com_port = dl_info.get("com_port", "USB")
                status.model = ""
                status.device_codename = ""
                status.usb_driver_ok = True
                status.raw_details = dl_info.get("name", "Samsung Mobile USB Modem (Download Mode)")
                with self._lock:
                    self.current_status = status
                return status
            elif dl_info.get("mtp_only"):
                status.mode = "disconnected"
                status.usb_driver_ok = True
                status.raw_details = "Phone connected via USB (MTP), but USB Debugging is OFF."

        with self._lock:
            self.current_status = status
        return status

    def _populate_adb_props(self, adb_exe: str, serial: str, status: DeviceStatus):
        """Reads system properties via ADB to verify SM-A217F, Android 12, One UI 4.1, and Bootloader state."""
        def getprop(prop: str) -> str:
            try:
                r = self._run_cmd([adb_exe, "-s", serial, "shell", "getprop", prop], timeout=4)
                return r.stdout.strip()
            except Exception:
                return ""

        model = getprop("ro.product.model") or getprop("ro.product.system.model") or "Unknown"
        device = getprop("ro.product.device") or getprop("ro.build.product") or ""
        release = getprop("ro.build.version.release") or ""
        sec_patch = getprop("ro.build.version.security_patch") or ""
        oneui_raw = getprop("ro.build.version.oneui") or getprop("ro.build.version.sep") or ""
        boot_locked = getprop("ro.boot.flash.locked")
        vbmeta_state = getprop("ro.boot.vbmeta.device_state")
        verified_state = getprop("ro.boot.verifiedbootstate")
        bootloader_ver = getprop("ro.boot.bootloader") or getprop("ro.bootloader") or ""
        kg_state = (
            getprop("ro.boot.kg.status")
            or getprop("ro.boot.prenormal")
            or getprop("sys.oem_unlock_allowed")
            or ""
        )
        oem_allowed = getprop("sys.oem_unlock_allowed") or getprop(" persist.sys.oem_unlock_allowed") or ""

        status.model = model
        status.device_codename = device
        status.android_version = release
        status.security_patch = sec_patch
        status.bootloader_version = bootloader_ver
        if len(bootloader_ver) >= 9:
            status.bootloader_binary_char = bootloader_ver[8]
        elif len(bootloader_ver) >= 4:
            status.bootloader_binary_char = bootloader_ver[-4]
        status.kg_status = kg_state
        status.oem_unlock_toggle = oem_allowed

        # Parse One UI version if available (e.g. 40100 -> 4.1)
        if oneui_raw.isdigit() and len(oneui_raw) >= 5:
            major = int(oneui_raw[:-4])
            minor = int(oneui_raw[-4:-2])
            status.oneui_version = f"One UI {major}.{minor}"
        elif release == "12":
            status.oneui_version = "One UI 4.1 / Android 12"
        else:
            status.oneui_version = f"Android {release}" if release else "Custom / Recovery"

        # Check if A217F / a21s
        upper_model = model.upper()
        lower_dev = device.lower()
        status.is_a217f = ("A217" in upper_model) or ("a21s" in lower_dev)

        # Bootloader unlock detection
        if boot_locked == "0" or vbmeta_state == "unlocked" or verified_state == "orange":
            status.bootloader_state = "unlocked"
        elif boot_locked == "1" or vbmeta_state == "locked" or verified_state == "green":
            status.bootloader_state = "locked"
        else:
            status.bootloader_state = "unknown"

        # Battery level
        try:
            bat_res = self._run_cmd([adb_exe, "-s", serial, "shell", "dumpsys", "battery"], timeout=4)
            m = re.search(r"level:\s*(\d+)", bat_res.stdout)
            if m:
                status.battery_level = int(m.group(1))
        except Exception:
            pass

    def _check_windows_samsung_usb(self) -> Dict[str, any]:
        """Uses PowerShell Get-PnpDevice / WMI to detect Samsung Download Mode (Odin/Modem) or MTP."""
        ps_script = (
            "Get-CimInstance Win32_PnPEntity | "
            "Where-Object { $_.DeviceID -match 'VID_04E8' -or $_.Name -match 'Samsung|SAMSUNG|Odin|Gadget Serial' } | "
            "Select-Object Name, DeviceID, PNPClass, Status | ConvertTo-Json -Compress"
        )
        try:
            res = self._run_cmd(["powershell", "-NoProfile", "-Command", ps_script], timeout=6)
            out = res.stdout.strip()
            if not out:
                return {}
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]

            download_mode = False
            mtp_only = False
            com_port = ""
            matched_name = ""

            for item in data:
                name = str(item.get("Name") or "")
                pnp_class = str(item.get("PNPClass") or "")
                dev_id = str(item.get("DeviceID") or "")

                # In Download Mode, Samsung exposes a CDC ACM Modem ("SAMSUNG Mobile USB Modem")
                # and/or a COM port ("SAMSUNG Mobile USB Serial Port (COMx)") or PID 685D
                if (
                    "Modem" in name
                    or "Modem" in pnp_class
                    or "PID_685D" in dev_id.upper()
                    or "Gadget Serial" in name
                    or "Odin" in name
                ):
                    download_mode = True
                    matched_name = name
                    m = re.search(r"\((COM\d+)\)", name)
                    if m:
                        com_port = m.group(1)
                elif "COM" in name and "SAMSUNG" in name.upper():
                    m = re.search(r"\((COM\d+)\)", name)
                    if m:
                        com_port = m.group(1)
                elif "Galaxy" in name or "A21" in name or "MTP" in name or "PID_6860" in dev_id.upper():
                    mtp_only = True

            return {
                "download_mode": download_mode,
                "com_port": com_port,
                "name": matched_name,
                "mtp_only": mtp_only
            }
        except Exception:
            return {}

    def reboot_to(self, target: str) -> bool:
        """Reboots connected ADB device to 'download' (Odin), 'recovery', or 'system'."""
        adb_exe = self.get_adb_path()
        if not adb_exe or not os.path.exists(adb_exe):
            self.log("[ERROR] ADB binary not found. Please download Platform Tools in Step 1.")
            return False

        cmd = [adb_exe, "reboot"]
        if target in ("download", " recovery", "recovery", "bootloader"):
            cmd.append(target.strip())

        self.log(f"[ADB] Executing: {' '.join(cmd)}")
        try:
            res = self._run_cmd(cmd, timeout=10)
            if res.returncode == 0:
                self.log(f"[OK] Reboot command ({target}) sent to device.")
                return True
            else:
                self.log(f"[WARN] Reboot returned non-zero: {res.stderr.strip()}")
                return False
        except Exception as e:
            self.log(f"[ERROR] Failed to reboot device: {e}")
            return False

