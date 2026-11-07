import os
import json
import urllib.parse
import requests
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


WIKI_DEVICES_URL = "https://wiki.lineageos.org/devices/"
LINEAGE_API_V2_DEVICE = "https://download.lineageos.org/api/v2/devices/{codename}"
LINEAGE_API_V2_BUILDS = "https://download.lineageos.org/api/v2/devices/{codename}/builds"

# Maps LineageOS major branch version -> Android version & NikGapps folder
LINEAGE_TO_ANDROID_MAP = {
    "24.0": ("Android 17", "Android-17"),
    "23.2": ("Android 16 (QPR2)", "Android-16"),
    "23.1": ("Android 16 (QPR1)", "Android-16"),
    "23.0": ("Android 16", "Android-16"),
    "22.2": ("Android 15 (QPR2)", "Android-15"),
    "22.1": ("Android 15 (QPR1)", "Android-15"),
    "22.0": ("Android 15", "Android-15"),
    "21.0": ("Android 14", "Android-14"),
    "21":   ("Android 14", "Android-14"),
    "20.0": ("Android 13", "Android-13"),
    "20":   ("Android 13", "Android-13"),
    "19.1": ("Android 12L", "Android-12.1"),
    "18.1": ("Android 11", "Android-11"),
    "17.1": ("Android 10", "Android-10"),
    "16.0": ("Android 9 Pie", "Android-9"),
    "15.1": ("Android 8.1 Oreo", "Android-8.1"),
    "14.1": ("Android 7.1 Nougat", "Android-7.1"),
}


@dataclass
class SamsungDeviceProfile:
    codename: str = "a21s"
    name: str = "Galaxy A21s"
    models: List[str] = field(default_factory=lambda: ["SM-A217F", "SM-A217F/DS", "SM-A217M"])
    soc: str = "Samsung Exynos 850"
    architecture: str = "arm64"
    supported_versions: List[str] = field(default_factory=lambda: ["22.1", "22.2", "23.0", "23.2", "24.0"])
    latest_lineage_version: str = "24.0"
    latest_android_version: str = "Android 17"
    required_stock_android: str = "12"
    install_method: str = "samloader_rs"
    download_boot_combo: str = "Hold Volume Up + Volume Down, then connect USB cable to PC."
    recovery_boot_combo: str = "Hold Volume Up + Power while connected to a PC via USB cable."
    wiki_url: str = "https://wiki.lineageos.org/devices/a21s/"
    builds_page_url: str = "https://download.lineageos.org/devices/a21s/builds"
    latest_rom_filename: str = ""
    latest_rom_url: str = ""
    latest_recovery_url: str = ""
    has_active_official_builds: bool = True


class UniversalSamsungDatabase:
    """Manages all 120+ official & historical Samsung devices supported by LineageOS,
    plus live querying of the LineageOS v2 Download API for latest builds and recovery images."""

    def __init__(self, base_dir: str, log_callback=None):
        self.base_dir = base_dir
        self.cache_path = os.path.join(base_dir, "tools", "samsung_lineage_db.json")
        self.log = log_callback or (lambda msg: None)
        self.devices_by_codename: Dict[str, SamsungDeviceProfile] = {}
        self.model_to_codename: Dict[str, str] = {}

        # Always seed with built-in popular Samsung models immediately so it works offline too
        self._seed_builtin_defaults()
        self._load_cached_db()

    def _seed_builtin_defaults(self):
        defaults = [
            SamsungDeviceProfile(
                codename="a21s",
                name="Galaxy A21s",
                models=["SM-A217F", "SM-A217F/DS", "SM-A217F/DSN", "SM-A217M", "SM-A217M/DS"],
                soc="Samsung Exynos 850",
                architecture="arm64",
                supported_versions=["22.1", "22.2", "23.0", "23.2", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="12",
                wiki_url="https://wiki.lineageos.org/devices/a21s/",
                builds_page_url="https://download.lineageos.org/devices/a21s/builds",
            ),
            SamsungDeviceProfile(
                codename="a52q",
                name="Galaxy A52 4G",
                models=["SM-A525F", "SM-A525F/DS", "SM-A525M", "SM-A525M/DS"],
                soc="Qualcomm SM7125 Snapdragon 720G",
                architecture="arm64",
                supported_versions=["18.1", "19.1", "20", "21", "22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="14",
                wiki_url="https://wiki.lineageos.org/devices/a52q/",
                builds_page_url="https://download.lineageos.org/devices/a52q/builds",
            ),
            SamsungDeviceProfile(
                codename="a52sxq",
                name="Galaxy A52s 5G",
                models=["SM-A528B", "SM-A528B/DS", "SM-A528N"],
                soc="Qualcomm SM7325 Snapdragon 778G 5G",
                architecture="arm64",
                supported_versions=["19.1", "20", "21", "22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="14",
                wiki_url="https://wiki.lineageos.org/devices/a52sxq/",
                builds_page_url="https://download.lineageos.org/devices/a52sxq/builds",
            ),
            SamsungDeviceProfile(
                codename="a53x",
                name="Galaxy A53 5G",
                models=["SM-A536B", "SM-A536B/DS", "SM-A536E", "SM-A536U", "SM-A536N"],
                soc="Samsung Exynos 1280",
                architecture="arm64",
                supported_versions=["23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="14",
                wiki_url="https://wiki.lineageos.org/devices/a53x/",
                builds_page_url="https://download.lineageos.org/devices/a53x/builds",
            ),
            SamsungDeviceProfile(
                codename="a71",
                name="Galaxy A71 4G",
                models=["SM-A715F", "SM-A715F/DS", "SM-A715F/DSN", "SM-A715W"],
                soc="Qualcomm SDM730 Snapdragon 730",
                architecture="arm64",
                supported_versions=["18.1", "19.1", "20", "21", "22.1", "23.2"],
                latest_lineage_version="23.2",
                latest_android_version="Android 16 (QPR2)",
                required_stock_android="13",
                wiki_url="https://wiki.lineageos.org/devices/a71/",
                builds_page_url="https://download.lineageos.org/devices/a71/builds",
            ),
            SamsungDeviceProfile(
                codename="a72q",
                name="Galaxy A72",
                models=["SM-A725F", "SM-A725F/DS", "SM-A725M"],
                soc="Qualcomm SM7125 Snapdragon 720G",
                architecture="arm64",
                supported_versions=["18.1", "19.1", "20", "21", "22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="14",
                wiki_url="https://wiki.lineageos.org/devices/a72q/",
                builds_page_url="https://download.lineageos.org/devices/a72q/builds",
            ),
            SamsungDeviceProfile(
                codename="a73xq",
                name="Galaxy A73 5G",
                models=["SM-A736B", "SM-A736B/DS"],
                soc="Qualcomm SM7325 Snapdragon 778G 5G",
                architecture="arm64",
                supported_versions=["20", "21", "22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="14",
                wiki_url="https://wiki.lineageos.org/devices/a73xq/",
                builds_page_url="https://download.lineageos.org/devices/a73xq/builds",
            ),
            SamsungDeviceProfile(
                codename="r8q",
                name="Galaxy S20 FE (Snapdragon)",
                models=["SM-G780G", "SM-G781B", "SM-G781U", "SM-G781W"],
                soc="Qualcomm SM8250 Snapdragon 865",
                architecture="arm64",
                supported_versions=["18.1", "19.1", "20", "21", "22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="13",
                wiki_url="https://wiki.lineageos.org/devices/r8q/",
                builds_page_url="https://download.lineageos.org/devices/r8q/builds",
            ),
            SamsungDeviceProfile(
                codename="beyond1lte",
                name="Galaxy S10",
                models=["SM-G973F", "SM-G973F/DS", "SM-G973N"],
                soc="Samsung Exynos 9820",
                architecture="arm64",
                supported_versions=["17.1", "18.1", "19.1", "20", "21", "22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="12",
                wiki_url="https://wiki.lineageos.org/devices/beyond1lte/",
                builds_page_url="https://download.lineageos.org/devices/beyond1lte/builds",
            ),
            SamsungDeviceProfile(
                codename="x1s",
                name="Galaxy S20 (4G/5G)",
                models=["SM-G980F", "SM-G981B"],
                soc="Samsung Exynos 990",
                architecture="arm64",
                supported_versions=["20", "21", "22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="13",
                wiki_url="https://wiki.lineageos.org/devices/x1s/",
                builds_page_url="https://download.lineageos.org/devices/x1s/builds",
            ),
            SamsungDeviceProfile(
                codename="r0s",
                name="Galaxy S22",
                models=["SM-S901B", "SM-S901B/DS"],
                soc="Samsung Exynos 2200",
                architecture="arm64",
                supported_versions=["22.1", "23.0", "24.0"],
                latest_lineage_version="24.0",
                latest_android_version="Android 17",
                required_stock_android="14",
                wiki_url="https://wiki.lineageos.org/devices/r0s/",
                builds_page_url="https://download.lineageos.org/devices/r0s/builds",
            ),
        ]
        for p in defaults:
            self._register_profile(p)

    def _register_profile(self, profile: SamsungDeviceProfile):
        self.devices_by_codename[profile.codename.lower()] = profile
        for m in profile.models:
            clean_m = m.upper().strip()
            self.model_to_codename[clean_m] = profile.codename.lower()
            # Also index base model without /DS or /DSN
            if "/" in clean_m:
                base_m = clean_m.split("/")[0]
                if base_m not in self.model_to_codename:
                    self.model_to_codename[base_m] = profile.codename.lower()

    def _load_cached_db(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
                for item in raw_list:
                    self._register_profile(SamsungDeviceProfile(**item))
            except Exception:
                pass

    def sync_all_samsung_devices_from_wiki(self) -> int:
        """Downloads the full 120+ Samsung device catalog from LineageOS Wiki and caches it locally."""
        try:
            self.log("[DATABASE] Syncing all 120+ Samsung devices from official LineageOS Wiki...")
            resp = requests.get(WIKI_DEVICES_URL, timeout=20)
            resp.raise_for_status()
            if "decodeURIComponent(" not in resp.text:
                return len(self.devices_by_codename)

            enc = resp.text.split("decodeURIComponent(")[1].split(")")[0][1:-1]
            decoded_str = urllib.parse.unquote_plus(enc)
            all_devs, _ = json.JSONDecoder().raw_decode(decoded_str)

            saved_profiles = []
            for key, val in all_devs.items():
                if str(val.get("vendor", "")).lower() != "samsung":
                    continue
                codename = str(val.get("codename") or key).strip()
                name = str(val.get("name", codename))
                models = [str(m) for m in (val.get("models") or [])]
                soc = str(val.get("soc", "Samsung Exynos / Snapdragon"))
                arch = val.get("architecture", "arm64")
                if isinstance(arch, dict):
                    arch = str(arch.get("cpu", "arm64"))

                versions = [str(v) for v in (val.get("versions") or [])]
                cur_branch = str(val.get("current_branch") or (versions[-1] if versions else "24.0"))
                android_ver, _ = LINEAGE_TO_ANDROID_MAP.get(cur_branch, (f"LineageOS {cur_branch}", "Android"))

                before_inst = val.get("before_install") or {}
                req_fw = str(before_inst.get("version", "")) if isinstance(before_inst, dict) else ""

                dl_boot = str(val.get("download_boot", "")).replace("<kbd>", "[").replace("</kbd>", "]")
                rec_boot = str(val.get("recovery_boot", "")).replace("<kbd>", "[").replace("</kbd>", "]")

                prof = SamsungDeviceProfile(
                    codename=codename,
                    name=name,
                    models=models,
                    soc=soc,
                    architecture=str(arch),
                    supported_versions=versions,
                    latest_lineage_version=cur_branch,
                    latest_android_version=android_ver,
                    required_stock_android=req_fw,
                    install_method=str(val.get("install_method", "odin")),
                    download_boot_combo=dl_boot,
                    recovery_boot_combo=rec_boot,
                    wiki_url=f"https://wiki.lineageos.org/devices/{codename}/",
                    builds_page_url=f"https://download.lineageos.org/devices/{codename}/builds",
                )
                self._register_profile(prof)
                saved_profiles.append(prof.__dict__)

            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(saved_profiles, f, indent=2)

            self.log(f"[OK] Synced {len(saved_profiles)} Samsung devices from LineageOS Wiki!")
            return len(saved_profiles)
        except Exception as e:
            self.log(f"[WARN] Could not sync live Wiki catalog (using built-in database): {e}")
            return len(self.devices_by_codename)

    def find_device(self, model_or_codename: str, codename_hint: str = "") -> Optional[SamsungDeviceProfile]:
        """Matches any Samsung model number (e.g. 'SM-A217F/DS', 'SM-A528B', 'SM-G973F')
        or codename (e.g. 'a21s', 'a52sxq', 'beyond1lte') to its SamsungDeviceProfile."""
        if codename_hint:
            ch = codename_hint.lower().strip()
            if ch in self.devices_by_codename:
                return self.devices_by_codename[ch]

        query = (model_or_codename or "").strip()
        if not query or query.upper() in ("UNKNOWN", "SAMSUNG", "DEVICE", "ANDROID"):
            return None

        # 1. Direct codename match
        if query.lower() in self.devices_by_codename:
            return self.devices_by_codename[query.lower()]

        # 2. Direct model match (e.g. SM-A217F/DS or SM-A217F)
        upper_q = query.upper()
        if upper_q in self.model_to_codename:
            return self.devices_by_codename[self.model_to_codename[upper_q]]
        if not upper_q.startswith("SM-") and f"SM-{upper_q}" in self.model_to_codename:
            return self.devices_by_codename[self.model_to_codename[f"SM-{upper_q}"]]

        # 3. Prefix/substring match (e.g. 'SM-A217F' inside 'SM-A217F/DS')
        for mod_key, cname in self.model_to_codename.items():
            if mod_key in upper_q or upper_q in mod_key:
                return self.devices_by_codename[cname]

        # 4. Name search (e.g. 'Galaxy A52')
        for cname, prof in self.devices_by_codename.items():
            if query.lower() in prof.name.lower():
                return prof

        return None

    def fetch_live_builds_for_device(self, profile: SamsungDeviceProfile) -> SamsungDeviceProfile:
        """Queries `https://download.lineageos.org/api/v2/devices/<codename>/builds`
        to populate the exact latest nightly ZIP URL and recovery.img URL."""
        try:
            url = LINEAGE_API_V2_BUILDS.format(codename=profile.codename)
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                builds = resp.json()
                if isinstance(builds, list) and len(builds) > 0:
                    latest = builds[0]
                    ver = str(latest.get("version") or profile.latest_lineage_version)
                    profile.latest_lineage_version = ver
                    android_str, _ = LINEAGE_TO_ANDROID_MAP.get(ver, (f"LineageOS {ver}", "Android"))
                    profile.latest_android_version = android_str
                    profile.has_active_official_builds = True

                    for f in latest.get("files", []):
                        fname = str(f.get("filename", ""))
                        furl = str(f.get("url", ""))
                        if fname.endswith(".zip") and "lineage-" in fname:
                            profile.latest_rom_filename = fname
                            profile.latest_rom_url = furl
                        elif fname == "recovery.img":
                            profile.latest_recovery_url = furl
                else:
                    profile.has_active_official_builds = False
        except Exception:
            pass
        return profile

    def get_dropdown_choices(self) -> List[str]:
        """Returns sorted list of 'Galaxy Name (Codename — Models)' for the GUI selector."""
        items = []
        for cname, prof in sorted(self.devices_by_codename.items(), key=lambda x: x[1].name):
            mod_preview = ", ".join(prof.models[:2])
            items.append(f"{prof.name} [{prof.codename}] ({mod_preview}) — Max: LineageOS {prof.latest_lineage_version}")
        return items

