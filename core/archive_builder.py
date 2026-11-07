import os
import struct
import zipfile
import tarfile
import hashlib
import shutil
import requests
from typing import Callable, Optional, Tuple, Dict


PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
SAMSUNG_DRIVER_URL = "https://developer.samsung.com/sdp/file/2663042f-1b42-4888-a761-5c5c7f7c9116"
ODIN3_DOWNLOAD_URL = "https://github.com/PrivacyMap/Odin-Windows/releases/download/v3.14.1/Odin3_v3.14.1.zip"
SAMLOADER_DOWNLOAD_URL = "https://github.com/topjohnwu/samloader-rs/releases/download/2.2.0/samloader-v2.2.0-windows-x86_64.zip"
LINEAGE_A21S_DOWNLOAD_URL = "https://download.lineageos.org/devices/a21s/builds"
NIKGAPPS_DOWNLOAD_URL = "https://sourceforge.net/projects/nikgapps/files/Releases/"

# Exact breakdown of the 7 files shown on the official LineageOS a21s "Download builds" page:
LINEAGE_PAGE_FILES_GUIDE = [
    ("lineage-24.0-YYYYMMDD-nightly-a21s-signed.zip", "✅ DOWNLOAD THIS", "Put in Box #2 (Main LineageOS 24 ROM ZIP)", "#10B981"),
    ("recovery.img",                                  "✅ DOWNLOAD THIS", "Put in Box #1 (Lineage Recovery Image)", "#10B981"),
    ("vbmeta.img",                                    "❌ SKIP / IGNORE", "DO NOT FLASH! Causes SW REV. CHECK FAIL(VBMETA) on Bit 10 (0xa)!", "#EF4444"),
    ("boot.img",                                      "❌ SKIP / IGNORE", "Not needed (Already inside the main lineage-24.0 .zip)", "#6B7280"),
    ("dtbo.img",                                      "❌ SKIP / IGNORE", "Not needed (Already inside the main lineage-24.0 .zip)", "#6B7280"),
    ("super_empty.img",                               "❌ SKIP / IGNORE", "Not needed for Samsung Odin + Recovery Sideload", "#6B7280"),
    ("build-manifest.xml",                            "❌ SKIP / IGNORE", "Not needed (Developer build metadata file)", "#6B7280"),
]

# Curated Download Catalog for Samsung Galaxy A21s (SM-A217F/DS - codename: a21s - arm64)
A217F_DOWNLOAD_CATALOG = [
    {
        "category": "From LineageOS 'Download builds' Page (Only 2 Files Needed!)",
        "exact_filename": "1) lineage-24.0-...-nightly-a21s-signed.zip    2) recovery.img",
        "must_match": "Skip boot.img, dtbo.img, super_empty.img, and build-manifest.xml!",
        "what_to_pick": (
            "On the LineageOS 'Download builds' page you showed:\n"
            "• ✅ Download 'lineage-24.0-XXXXXXXX-nightly-a21s-signed.zip' -> Select in Box #2.\n"
            "• ✅ Download 'recovery.img' -> Select in Box #1.\n"
            "• ⭕ 'vbmeta.img' is optional (Select in Box #4 if you downloaded it, or leave Box #4 empty and this app will create it).\n"
            "• ❌ DO NOT download boot.img, dtbo.img, super_empty.img, or build-manifest.xml!"
        ),
        "links": [
            ("Open Official LineageOS a21s Downloads", LINEAGE_A21S_DOWNLOAD_URL),
        ]
    },
    {
        "category": "From NikGapps (For Box #3 — Google Play Store & Google Apps)",
        "exact_filename": "NikGapps-core-arm64-17-YYYYMMDD-signed.zip",
        "must_match": "Architecture: ARM64  |  Edition: Core (Recommended)",
        "what_to_pick": (
            "1. Click the button below to open NikGapps Releases.\n"
            "2. Open the latest Android folder matching LineageOS 24 (or Android 17 / NikGapps-core).\n"
            "3. Download 'NikGapps-core-arm64-...-signed.zip' and select it in Box #3."
        ),
        "links": [
            ("Open Official NikGapps Releases (SourceForge)", NIKGAPPS_DOWNLOAD_URL),
            ("NikGapps Website", "https://nikgapps.com/downloads"),
        ]
    }
]




class ArchiveBuilder:
    """Handles downloading SDK platform-tools, creating disabled vbmeta.img,
    and packaging recovery.img + vbmeta.img into an Odin-ready .tar archive."""

    def __init__(self, base_dir: str, log_callback: Optional[Callable[[str], None]] = None):
        self.base_dir = base_dir
        self.tools_dir = os.path.join(base_dir, "tools")
        self.work_dir = os.path.join(base_dir, "workspace_files")
        os.makedirs(self.tools_dir, exist_ok=True)
        os.makedirs(self.work_dir, exist_ok=True)
        self.log = log_callback or (lambda msg: None)

    def get_adb_path(self) -> str:
        local_adb = os.path.join(self.tools_dir, "platform-tools", "adb.exe")
        if os.path.exists(local_adb):
            return local_adb
        which_adb = shutil.which("adb")
        return which_adb or local_adb

    def get_fastboot_path(self) -> str:
        local_fb = os.path.join(self.tools_dir, "platform-tools", "fastboot.exe")
        if os.path.exists(local_fb):
            return local_fb
        which_fb = shutil.which("fastboot")
        return which_fb or local_fb

    def get_odin4_path(self) -> str:
        for candidate in [
            os.path.join(self.tools_dir, "odin4.exe"),
            os.path.join(self.tools_dir, "odin4", "odin4.exe"),
            shutil.which("odin4") or ""
        ]:
            if candidate and os.path.exists(candidate):
                return candidate
        return os.path.join(self.tools_dir, "odin4.exe")

    def get_odin3_path(self) -> str:
        for root, _, files in os.walk(self.tools_dir):
            for f in files:
                if f.lower().startswith("odin3") and f.lower().endswith(".exe"):
                    return os.path.join(root, f)
        return ""

    def get_heimdall_path(self) -> str:
        for candidate in [
            os.path.join(self.tools_dir, "heimdall.exe"),
            os.path.join(self.tools_dir, "heimdall", "heimdall.exe"),
            shutil.which("heimdall") or ""
        ]:
            if candidate and os.path.exists(candidate):
                return candidate
        return os.path.join(self.tools_dir, "heimdall.exe")

    def get_samloader_path(self) -> str:
        for root, _, files in os.walk(self.tools_dir):
            for f in files:
                if f.lower() == "samloader.exe":
                    return os.path.join(root, f)
        return os.path.join(self.tools_dir, "samloader", "samloader.exe")

    def download_samloader(self, progress_cb: Optional[Callable[[float, str], None]] = None) -> Tuple[bool, str]:
        """Downloads and extracts official samloader-rs (recommended by LineageOS Wiki for a21s)."""
        existing = self.get_samloader_path()
        if existing and os.path.exists(existing):
            return True, existing

        zip_path = os.path.join(self.tools_dir, "samloader.zip")
        extract_dir = os.path.join(self.tools_dir, "samloader")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            self.log(f"[DOWNLOAD] Downloading official samloader-rs flasher from {SAMLOADER_DOWNLOAD_URL}...")
            if progress_cb:
                progress_cb(0.15, "Downloading official samloader-rs CLI flasher...")

            resp = requests.get(SAMLOADER_DOWNLOAD_URL, stream=True, timeout=30)
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            os.remove(zip_path)

            exe = self.get_samloader_path()
            if os.path.exists(exe):
                self.log(f"[OK] samloader-rs ready at: {exe}")
                return True, exe
            return False, "samloader.exe not found after extraction"
        except Exception as e:
            self.log(f"[ERROR] Failed to download samloader-rs: {e}")
            return False, str(e)

    def is_platform_tools_installed(self) -> bool:
        return os.path.exists(self.get_adb_path())

    def is_odin_installed(self) -> bool:
        return (
            os.path.exists(self.get_odin4_path())
            or bool(self.get_odin3_path())
            or os.path.exists(self.get_heimdall_path())
        )

    def download_odin3(self, progress_cb: Optional[Callable[[float, str], None]] = None) -> Tuple[bool, str]:
        """Automatically downloads and extracts Samsung Odin3 v3.14.1 into tools/odin3/."""
        existing = self.get_odin3_path()
        if existing and os.path.exists(existing):
            return True, existing

        zip_path = os.path.join(self.tools_dir, "Odin3_v3.14.1.zip")
        extract_dir = os.path.join(self.tools_dir, "odin3")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            self.log(f"[DOWNLOAD] Auto-downloading Samsung Odin3 v3.14.1 from {ODIN3_DOWNLOAD_URL}...")
            if progress_cb:
                progress_cb(0.15, "Downloading Samsung Odin3 Flasher...")

            resp = requests.get(ODIN3_DOWNLOAD_URL, stream=True, timeout=30)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0 and progress_cb:
                            pct = 0.15 + min(0.70, (downloaded / total) * 0.70)
                            progress_cb(pct, f"Downloading Odin3 ({downloaded // 1024} KB / {total // 1024} KB)...")

            if progress_cb:
                progress_cb(0.90, "Extracting Odin3...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            os.remove(zip_path)

            odin_exe = self.get_odin3_path()
            if odin_exe:
                self.log(f"[OK] Samsung Odin3 installed at: {odin_exe}")
                if progress_cb:
                    progress_cb(1.0, "Samsung Odin3 installed and ready!")
                return True, odin_exe
            return False, "Odin3 .exe not found after extraction."
        except Exception as e:
            self.log(f"[ERROR] Failed to download Odin3: {e}")
            return False, str(e)

    def download_platform_tools(self, progress_cb: Optional[Callable[[float, str], None]] = None) -> bool:
        """Downloads and extracts official Google Android SDK Platform-Tools."""
        zip_path = os.path.join(self.tools_dir, "platform-tools.zip")
        try:
            self.log(f"[DOWNLOAD] Fetching Google Platform-Tools from {PLATFORM_TOOLS_URL}...")
            if progress_cb:
                progress_cb(0.05, "Connecting to Google repository...")

            resp = requests.get(PLATFORM_TOOLS_URL, stream=True, timeout=30)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0 and progress_cb:
                            pct = min(0.85, (downloaded / total) * 0.85)
                            progress_cb(pct, f"Downloading Platform-Tools ({downloaded // 1024} KB / {total // 1024} KB)...")

            if progress_cb:
                progress_cb(0.90, "Extracting Platform-Tools...")
            self.log("[EXTRACT] Extracting platform-tools.zip...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self.tools_dir)

            os.remove(zip_path)
            if progress_cb:
                progress_cb(1.0, "Platform-Tools installed successfully!")
            self.log(f"[OK] ADB & Fastboot ready at: {self.get_adb_path()}")
            return True
        except Exception as e:
            self.log(f"[ERROR] Failed to download Platform-Tools: {e}")
            if progress_cb:
                progress_cb(0.0, f"Download failed: {e}")
            return False

    def generate_disabled_vbmeta(self, output_path: Optional[str] = None) -> str:
        """Generates a standard Android Verified Boot 2.0 (AVB0) disabled vbmeta.img
        with flags=3 (AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED | VERIFICATION_DISABLED)
        required by Samsung Exynos 850 (SM-A217F) to boot custom recovery/ROMs."""
        if not output_path:
            output_path = os.path.join(self.work_dir, "vbmeta.img")

        # AVB0 Header layout:
        # 0..4   : magic "AVB0"
        # 4..8   : required_libavb_version_major (1)
        # 8..12  : required_libavb_version_minor (0)
        # 120..124: flags (uint32 big-endian = 3 -> disable verification + hashtree)
        # 128..160: release_string ("avbtool 1.2.0\x00...")
        buf = bytearray(4096)
        buf[0:4] = b"AVB0"
        struct.pack_into(">I", buf, 4, 1)    # major = 1
        struct.pack_into(">I", buf, 8, 0)    # minor = 0
        struct.pack_into(">I", buf, 120, 3)  # flags = 3 (verification + verity disabled)
        rel = b"avbtool 1.2.0"
        buf[128:128 + len(rel)] = rel

        with open(output_path, "wb") as f:
            f.write(buf)

        self.log(f"[OK] Generated AVB-disabled vbmeta.img ({len(buf)} bytes) at {output_path}")
        return output_path

    def build_odin_recovery_tar(
        self,
        source_recovery_path: str,
        custom_vbmeta_path: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Prepares an Odin-compatible .tar file containing ONLY recovery.img.
        IMPORTANT: Do NOT include vbmeta.img inside the Odin .tar on SM-A217F Binary 10 (0xa),
        because flashing an unsigned vbmeta.img triggers 'SW REV. CHECK FAIL(VBMETA) Device: 0xa, BINARY: 0x0'.
        LineageOS Wiki for a21s specifies flashing ONLY the RECOVERY partition!"""
        if not os.path.exists(source_recovery_path):
            return False, "Selected recovery file does not exist."

        lower = source_recovery_path.lower()
        if lower.endswith(".tar") or lower.endswith(".tar.md5"):
            self.log(f"[INFO] Recovery is already packaged as an Odin archive: {os.path.basename(source_recovery_path)}")
            return True, source_recovery_path

        try:
            # Copy recovery image to exact 'recovery.img' inside workspace_files
            target_rec = os.path.join(self.work_dir, "recovery.img")
            if os.path.abspath(source_recovery_path) != os.path.abspath(target_rec):
                shutil.copy2(source_recovery_path, target_rec)

            tar_out = os.path.join(self.work_dir, "A217F_LineageRecovery_Odin.tar")
            # Odin requires standard USTAR or GNU tar with bare filename 'recovery.img' ONLY
            with tarfile.open(tar_out, "w", format=tarfile.USTAR_FORMAT) as tf:
                tf.add(target_rec, arcname="recovery.img")

            self.log(f"[OK] Built Odin flashable package: {tar_out} (recovery.img ONLY — prevents VBMETA 0xa error!)")
            return True, tar_out
        except Exception as e:
            self.log(f"[ERROR] Failed to build Odin .tar package: {e}")
            return False, str(e)

    def create_bootloader_bypass_rom_zip(
        self,
        source_rom_zip: str,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bool, str]:
        """Creates a copy of the LineageOS ROM ZIP with the strict Binary 'C' bootloader check
        (`assert(exynos850.verify_bootloader_min("") == "1" ...);`) removed from updater-script,
        so SM-A217F phones on Android 12 One UI 4.1 Binary 'A' (Bit 10 / 0xa) can install without
        having to download a 4GB stock firmware first."""
        if not source_rom_zip or not os.path.exists(source_rom_zip):
            return False, "Source LineageOS ZIP does not exist."

        out_name = os.path.basename(source_rom_zip).replace(".zip", "-BitA_Patched.zip")
        out_path = os.path.join(self.work_dir, out_name)
        script_entry = "META-INF/com/google/android/updater-script"

        try:
            self.log(f"[PATCH] Creating Binary-A compatible LineageOS 24 ZIP: {out_name}...")
            if progress_cb:
                progress_cb(0.05, "Patching updater-script to allow Bootloader Binary A (0xa)...")

            with zipfile.ZipFile(source_rom_zip, "r") as zin:
                infos = zin.infolist()
                total = max(1, len(infos))
                with zipfile.ZipFile(out_path, "w") as zout:
                    for idx, item in enumerate(infos):
                        # Skip JAR signature files because modifying updater-script invalidates whole-file APK sig
                        if item.filename.startswith("META-INF/com/android/otacert") or item.filename in (
                            "META-INF/CERT.SF",
                            "META-INF/CERT.RSA",
                            "META-INF/MANIFEST.MF",
                        ):
                            pass
                        data = zin.read(item.filename)
                        if item.filename == script_entry:
                            txt = data.decode("utf-8", errors="ignore")
                            patched_lines = []
                            for line in txt.splitlines():
                                if "verify_bootloader_min" in line:
                                    patched_lines.append(
                                        'ui_print("Bypassed Binary C check (Running on Android 12 Binary A / 0xa)...");'
                                    )
                                else:
                                    patched_lines.append(line)
                            data = ("\n".join(patched_lines) + "\n").encode("utf-8")
                        zout.writestr(item, data)
                        if progress_cb:
                            pct = 0.05 + (idx / total) * 0.90
                            progress_cb(pct, f"Building patched ROM ZIP ({idx + 1}/{total} files)...")

            if progress_cb:
                progress_cb(1.0, f"Patched ROM ready: {out_name} (Tap 'Yes' on Signature prompt on phone!)")
            self.log(f"[OK] Patched ROM ZIP created at: {out_path}")
            return True, out_path
        except Exception as e:
            self.log(f"[ERROR] Failed to patch ROM ZIP: {e}")
            return False, str(e)

    def inspect_rom_zip(self, zip_path: str, target_codename: str = "a21s", target_arch: str = "arm64") -> Dict[str, any]:
        """Inspects a LineageOS or NikGapps ZIP file to verify integrity and target Samsung codename/arch metadata."""
        info = {
            "valid_zip": False,
            "size_mb": 0.0,
            "sha256_short": "",
            "is_lineage": False,
            "is_nikgapps": False,
            "target_device_ok": True,
            "metadata_summary": ""
        }
        if not zip_path or not os.path.exists(zip_path):
            return info

        try:
            size_bytes = os.path.getsize(zip_path)
            info["size_mb"] = round(size_bytes / (1024 * 1024), 1)
            fname = os.path.basename(zip_path).lower()
            tc = (target_codename or "a21s").lower()

            if "lineage" in fname:
                info["is_lineage"] = True
                if tc == "a21s" and "a21" in fname and "a21s" not in fname and "a217" not in fname:
                    info["target_device_ok"] = False
                    info["metadata_summary"] = "❌ WRONG DEVICE: This file is for 'a21', NOT 'a21s' (SM-A217F)!"
                    return info

            if "nikgapps" in fname or "gapps" in fname:
                info["is_nikgapps"] = True
                if target_arch == "arm64" and ("arm-" in fname or "arm_" in fname or "x86" in fname) and "arm64" not in fname:
                    info["target_device_ok"] = False
                    info["metadata_summary"] = f"❌ WRONG ARCHITECTURE: Download the '{target_arch}' NikGapps ZIP!"
                    return info

            with zipfile.ZipFile(zip_path, "r") as zf:
                info["valid_zip"] = True
                names = zf.namelist()

                # Check META-INF/com/android/metadata or updater-script
                meta_text = ""
                if "META-INF/com/android/metadata" in names:
                    meta_text = zf.read("META-INF/com/android/metadata").decode("utf-8", errors="ignore")
                elif "META-INF/com/google/android/updater-script" in names:
                    meta_text = zf.read("META-INF/com/google/android/updater-script").decode("utf-8", errors="ignore")

                if meta_text:
                    if tc in meta_text.lower():
                        info["target_device_ok"] = True
                        info["metadata_summary"] = f"Verified target codename: {tc}"
                    elif "pre-device=" in meta_text.lower():
                        info["target_device_ok"] = False
                        info["metadata_summary"] = f"Warning: Package metadata specifies a different device than '{tc}'!"
                    else:
                        info["metadata_summary"] = "Valid flashable Android ZIP archive"
                else:
                    info["metadata_summary"] = "Valid ZIP archive ready for sideload"
        except Exception as e:
            info["metadata_summary"] = f"Invalid or corrupted ZIP: {e}"

        return info

