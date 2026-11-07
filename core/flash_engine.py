import os
import re
import subprocess
from typing import Callable, Optional, Tuple
from core.archive_builder import ArchiveBuilder

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class FlashEngine:
    """Executes Samsung Download Mode flashing (Odin4 CLI, Heimdall CLI, or Guided Odin3)
    and ADB Sideload streaming for LineageOS 24 & NikGapps."""

    def __init__(self, archive_builder: ArchiveBuilder, log_callback: Optional[Callable[[str], None]] = None):
        self.builder = archive_builder
        self.log = log_callback or (lambda msg: None)

    def flash_recovery_download_mode(
        self,
        recovery_input_path: str,
        vbmeta_input_path: Optional[str] = None,
        method: str = "auto",
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bool, str]:
        """Flashes custom recovery + disabled vbmeta in Samsung Download Mode.
        method can be 'auto', 'odin4', 'heimdall', or 'odin3'."""
        if progress_cb:
            progress_cb(0.1, "Building Odin-compatible recovery + vbmeta .tar package...")

        ok, tar_or_err = self.builder.build_odin_recovery_tar(recovery_input_path, vbmeta_input_path)
        if not ok:
            return False, tar_or_err

        tar_path = tar_or_err
        samloader_exe = self.builder.get_samloader_path()
        odin4_exe = self.builder.get_odin4_path()
        heimdall_exe = self.builder.get_heimdall_path()
        odin3_exe = self.builder.get_odin3_path()
        rec_img = os.path.join(self.builder.work_dir, "recovery.img")

        # 1. If samloader method explicitly requested
        if method == "samloader":
            if not os.path.exists(samloader_exe):
                dl_ok, dl_res = self.builder.download_samloader(progress_cb)
                if dl_ok:
                    samloader_exe = dl_res
            if os.path.exists(samloader_exe):
                return self._run_samloader_flash(samloader_exe, rec_img, progress_cb)

        # 2. Try Odin4 CLI if selected or auto & exists
        if method in ("auto", "odin4") and os.path.exists(odin4_exe):
            self.log(f"[ODIN4] Flashing {os.path.basename(tar_path)} via Odin4 CLI...")
            if progress_cb:
                progress_cb(0.25, "Flashing via Odin4 CLI in Download Mode...")
            return self._run_odin4_flash(odin4_exe, tar_path, progress_cb)

        # 3. Try Heimdall CLI if selected or auto & exists
        if method in ("auto", "heimdall") and os.path.exists(heimdall_exe):
            self.log("[HEIMDALL] Flashing RECOVERY partition via Heimdall CLI...")
            if progress_cb:
                progress_cb(0.25, "Flashing RECOVERY via Heimdall...")
            return self._run_heimdall_flash(heimdall_exe, rec_img, progress_cb)

        # 3. Guided Odin3 GUI Fallback — Auto-download Odin3 if not installed yet!
        if not odin3_exe or not os.path.exists(odin3_exe):
            self.log("[ODIN3] Odin3 not found in tools/ yet — auto-downloading Odin3 v3.14.1 for you...")
            dl_ok, dl_res = self.builder.download_odin3(progress_cb)
            if dl_ok:
                odin3_exe = dl_res

        if odin3_exe and os.path.exists(odin3_exe):
            self.log(f"[ODIN3] Launching Samsung Odin3 ({odin3_exe})...")
            try:
                subprocess.Popen([odin3_exe], cwd=os.path.dirname(odin3_exe))
            except Exception as e:
                self.log(f"[WARN] Could not auto-launch Odin3: {e}")

        # Open Explorer highlighting the generated .tar file so the user can drop it right into [AP]
        self._reveal_in_explorer(tar_path)
        msg = (
            f"Odin3 Launched & TAR Package Copied!\n"
            f"File Path: {tar_path}\n\n"
            f"Do these 3 clicks in the Odin3 window that just opened:\n"
            f"1. Click [AP] button -> Paste path (Ctrl+V) or select '{os.path.basename(tar_path)}'.\n"
            f"2. Click 'Options' tab -> UNCHECK 'Auto Reboot'.\n"
            f"3. Click [Start] -> Wait for green 'PASS!'"
        )
        self.log(f"[INFO] {msg}")
        if progress_cb:
            progress_cb(1.0, "Odin3 launched & .tar path copied to clipboard!")
        return True, tar_path

    def _run_odin4_flash(
        self,
        odin4_exe: str,
        tar_path: str,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bool, str]:
        """Executes `odin4 -a <tar_path>` and streams output."""
        cmd = [odin4_exe, "-a", tar_path]
        self.log(f"[CMD] {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace"
            )
            for line in proc.stdout:
                clean = line.strip()
                if clean:
                    self.log(f"[ODIN4] {clean}")
                    m = re.search(r"(\d+)%", clean)
                    if m and progress_cb:
                        pct = 0.25 + (int(m.group(1)) / 100.0) * 0.70
                        progress_cb(min(0.95, pct), f"Odin4 Flashing: {clean}")

            proc.wait()
            if proc.returncode == 0:
                if progress_cb:
                    progress_cb(1.0, "Recovery & vbmeta flashed successfully via Odin4!")
                self.log("[OK] Odin4 flashing completed successfully!")
                return True, "Flashed successfully via Odin4 CLI."
            else:
                err = f"Odin4 exited with code {proc.returncode}"
                self.log(f"[ERROR] {err}")
                return False, err
        except Exception as e:
            self.log(f"[ERROR] Odin4 execution error: {e}")
            return False, str(e)

    def _run_samloader_flash(
        self,
        samloader_exe: str,
        recovery_img: str,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bool, str]:
        """Executes official LineageOS Wiki command: `samloader flash --partition RECOVERY recovery.img --no-reboot`."""
        cmd = [
            samloader_exe,
            "flash",
            "--partition", "RECOVERY",
            recovery_img,
            "--no-reboot"
        ]
        self.log(f"[CMD] {' '.join(cmd)}")
        if progress_cb:
            progress_cb(0.30, "Flashing RECOVERY via official samloader-rs...")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace"
            )
            for line in proc.stdout:
                clean = line.strip()
                if clean:
                    self.log(f"[SAMLOADER] {clean}")

            proc.wait()
            if proc.returncode == 0:
                if progress_cb:
                    progress_cb(1.0, "Recovery flashed via samloader-rs (No-Reboot)! Do Sub-Step 4C now!")
                self.log("[OK] samloader-rs flashed RECOVERY! Now hold Vol Down + Power for 8s, then Vol Up + Power!")
                return True, "Flashed successfully via samloader-rs."
            else:
                err = f"samloader exited with code {proc.returncode}"
                self.log(f"[ERROR] {err}")
                return False, err
        except Exception as e:
            self.log(f"[ERROR] samloader execution error: {e}")
            return False, str(e)

    def _run_heimdall_flash(
        self,
        heimdall_exe: str,
        recovery_img: str,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bool, str]:
        """Executes `heimdall flash --RECOVERY recovery.img --no-reboot`."""
        cmd = [
            heimdall_exe,
            "flash",
            "--RECOVERY", recovery_img,
            "--no-reboot"
        ]
        self.log(f"[CMD] {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace"
            )
            for line in proc.stdout:
                clean = line.strip()
                if clean:
                    self.log(f"[HEIMDALL] {clean}")
                    m = re.search(r"(\d+)%", clean)
                    if m and progress_cb:
                        pct = 0.25 + (int(m.group(1)) / 100.0) * 0.70
                        progress_cb(min(0.95, pct), f"Heimdall Flashing: {clean}")

            proc.wait()
            if proc.returncode == 0:
                if progress_cb:
                    progress_cb(1.0, "Recovery & vbmeta flashed via Heimdall (No-Reboot)!")
                self.log("[OK] Heimdall flash succeeded! Now hold Vol Up + Power to enter Recovery.")
                return True, "Flashed successfully via Heimdall."
            else:
                err = f"Heimdall exited with code {proc.returncode}"
                self.log(f"[ERROR] {err}")
                return False, err
        except Exception as e:
            self.log(f"[ERROR] Heimdall execution error: {e}")
            return False, str(e)

    def sideload_package(
        self,
        zip_path: str,
        label: str = "Package",
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[bool, str]:
        """Streams `adb sideload <zip_path>` with real-time percentage parsing.
        Note: ADB sideload often finishes at 'Total xfer: 1.00x' (or 47% on host side) with return code 0."""
        adb_exe = self.builder.get_adb_path()
        if not os.path.exists(adb_exe):
            return False, "ADB executable not found. Please install Platform-Tools in Step 1."
        if not zip_path or not os.path.exists(zip_path):
            return False, f"{label} ZIP file not found: {zip_path}"

        cmd = [adb_exe, "sideload", zip_path]
        self.log(f"[SIDELOAD] Starting {label} sideload: {os.path.basename(zip_path)}")
        self.log(f"[CMD] {' '.join(cmd)}")

        if progress_cb:
            progress_cb(0.05, f"Starting ADB Sideload for {label}...")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace"
            )

            saw_xfer = False
            for line in proc.stdout:
                clean = line.strip()
                if not clean:
                    continue
                self.log(f"[ADB] {clean}")
                if "Total xfer" in clean or "serving:" in clean:
                    saw_xfer = True
                m = re.search(r"\(~?(\d+)%\)", clean)
                if m and progress_cb:
                    pct = int(m.group(1)) / 100.0
                    progress_cb(min(0.98, max(0.05, pct)), f"Sideloading {label}: {m.group(1)}%")

            proc.wait()
            if proc.returncode == 0 or saw_xfer:
                if progress_cb:
                    progress_cb(1.0, f"{label} sideloaded successfully!")
                self.log(f"[OK] {label} sideload finished!")
                return True, f"{label} flashed successfully."
            else:
                err = f"ADB Sideload exited with code {proc.returncode}. Make sure phone is in 'Apply Update -> Apply from ADB' mode."
                self.log(f"[ERROR] {err}")
                return False, err
        except Exception as e:
            self.log(f"[ERROR] Sideload exception: {e}")
            return False, str(e)

    def _reveal_in_explorer(self, filepath: str):
        if os.name == "nt" and os.path.exists(filepath):
            try:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(filepath)])
            except Exception:
                pass

