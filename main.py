import os
import sys
import json
import subprocess
import threading
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    print("[SETUP] Installing required packages from requirements.txt...")
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
    import customtkinter as ctk

from core.archive_builder import (
    ArchiveBuilder,
    SAMSUNG_DRIVER_URL,
    LINEAGE_A21S_DOWNLOAD_URL,
    NIKGAPPS_DOWNLOAD_URL,
    LINEAGE_PAGE_FILES_GUIDE,
    A217F_DOWNLOAD_CATALOG,
)
from core.device_manager import DeviceManager, DeviceStatus
from core.flash_engine import FlashEngine
from core.samsung_db import UniversalSamsungDatabase, SamsungDeviceProfile

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "installer_state.json"
APP_TITLE = "Lineage OS Installer for Samsung GUI"

LEGAL_DISCLAIMER_TEXT = """⚠️ IMPORTANT LEGAL DISCLAIMER, TERMS & CONDITIONS — READ CAREFULLY BEFORE PROCEEDING

#include <std_disclaimer.h>
/*
 * Your warranty is now void (and Samsung Knox e-fuse 0x1 may be permanently tripped).
 *
 * LineageOS and this installer are provided "AS-IS" WITHOUT ANY WARRANTY of any kind,
 * either express or implied, including but not limited to warranties of merchantability
 * or fitness for a particular purpose.
 *
 * I / the developers are NOT responsible for bricked devices, bootloops, loss of operating
 * system (OS), permanent data loss, tripped Knox / lost Samsung Pay / Secure Folder,
 * dead SD cards, hardware damage, or you getting fired because the alarm app failed.
 * YOU are choosing to make these modifications to your device of your own free will!
 */

BY USING "LINEAGE OS INSTALLER FOR SAMSUNG GUI", YOU ACKNOWLEDGE AND AGREE THAT:
1. NO GUARANTEE AGAINST BRICKING OR OS LOSS: Unlocking the bootloader, flashing custom recovery in Odin / Download Mode, or sideloading custom ROMs/GApps carries an inherent risk of soft-bricking or hard-bricking your device or leaving it without a bootable operating system.
2. COMPLETE DATA LOSS: Unlocking the bootloader and formatting data in recovery will permanently erase ALL personal data, photos, apps, and files on your phone. Back up everything beforehand!
3. SAMSUNG KNOX & WARRANTY: Flashing unofficial binaries permanently trips the Samsung Knox hardware fuse (0x1), voiding manufacturer warranty and permanently disabling Knox-dependent features (Samsung Wallet/Pay, Secure Folder, Samsung Pass).
4. PROCEED AT YOUR OWN RISK: You assume 100% sole responsibility for any consequences resulting from the use of this software."""

STEPS = [
    ("1. Setup & Files", "Tools & ROM Selection"),
    ("2. Device Check", "ADB & USB Verification"),
    ("3. Bootloader", "Unlock & Download Mode"),
    ("4. Flash Recovery", "Odin / VBMeta + Recovery"),
    ("5. LineageOS ROM", "Format Data & Sideload ROM"),
    ("6. NikGapps & Boot", "Sideload GApps & Finish"),
]


class LineageA21sInstallerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(1040, 720)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.base_dir, CONFIG_FILE)
        self.app_state = self._load_state()

        # Initialize backend managers & Universal 120+ Samsung Device Database
        self.builder = ArchiveBuilder(self.base_dir, log_callback=self.log_message)
        self.device_mgr = DeviceManager(self.builder.get_adb_path, log_callback=self.log_message)
        self.flash_engine = FlashEngine(self.builder, log_callback=self.log_message)
        self.samsung_db = UniversalSamsungDatabase(self.base_dir, log_callback=self.log_message)

        saved_codename = self.app_state.get("selected_codename", "a21s")
        self.active_profile: SamsungDeviceProfile = (
            self.samsung_db.find_device(saved_codename) or self.samsung_db.find_device("a21s")
        )
        self._last_auto_matched_codename = ""

        self.current_step_idx = 0
        self.step_buttons = []
        self.step_frames = []
        self.polling_active = True
        self.auto_advance_var = ctk.BooleanVar(value=True)

        self._build_layout()
        self._refresh_dropdown_values()
        self._refresh_active_profile_ui()
        self.select_step(0)

        self.log_message(f"[SYSTEM] Initialized {APP_TITLE}.")
        if self.builder.is_platform_tools_installed():
            self.log_message(f"[OK] Android Platform-Tools detected: {self.builder.get_adb_path()}")
        else:
            self.log_message("[INFO] Android Platform-Tools not installed yet. Click 'Auto-Download Platform-Tools' in Step 1.")

        # Fetch live builds for active profile & sync full 120+ Samsung Wiki DB in background
        self._run_async(self._initial_background_sync)

        # Show mandatory Legal Disclaimer / Risk Warning modal on startup
        self.after(150, self._show_startup_disclaimer_modal)

        # Start background USB/ADB device polling
        self.after(600, self._poll_device_loop)

    def _load_state(self) -> dict:
        default_state = {
            "recovery_path": "",
            "vbmeta_path": "",
            "lineage_zip_path": "",
            "nikgapps_zip_path": "",
            "selected_codename": "a21s",
            "accepted_disclaimer": False,
            "completed_steps": []
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Only keep file paths that actually exist on THIS user's computer
                for path_key in ("recovery_path", "vbmeta_path", "lineage_zip_path", "nikgapps_zip_path"):
                    val = loaded.get(path_key, "")
                    if val and not os.path.exists(val):
                        loaded[path_key] = ""
                default_state.update(loaded)
            except Exception:
                pass
        else:
            # First launch on this machine: dynamically create a clean installer_state.json
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(default_state, f, indent=2)
            except Exception:
                pass
        return default_state

    def _save_state(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.app_state, f, indent=2)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # UI LAYOUT CONSTRUCTION
    # -------------------------------------------------------------------------
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 1. Top Live Device Telemetry Banner
        self.top_bar = ctk.CTkFrame(self, height=74, corner_radius=0, fg_color="#111827")
        self.top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.top_bar.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        self.top_title_lbl = ctk.CTkLabel(
            title_box,
            text=f"LINEAGE OS INSTALLER FOR SAMSUNG GUI — {self.active_profile.name.upper()} ({self.active_profile.codename})",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#38BDF8"
        )
        self.top_title_lbl.pack(anchor="w")

        self.top_subtitle_lbl = ctk.CTkLabel(
            title_box,
            text=f"Latest Supported: LineageOS {self.active_profile.latest_lineage_version} ({self.active_profile.latest_android_version}) + NikGapps  |  Required Base: Android {self.active_profile.required_stock_android or 'Stock'}",
            font=ctk.CTkFont(size=12),
            text_color="#9CA3AF"
        )
        self.top_subtitle_lbl.pack(anchor="w")

        # Live connection badge in top bar
        status_box = ctk.CTkFrame(self.top_bar, fg_color="#1F2937", corner_radius=8)
        status_box.grid(row=0, column=1, padx=16, pady=10, sticky="e")

        self.conn_dot = ctk.CTkLabel(
            status_box,
            text="● DISCONNECTED",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#EF4444"
        )
        self.conn_dot.grid(row=0, column=0, padx=(14, 10), pady=8)

        self.conn_details_lbl = ctk.CTkLabel(
            status_box,
            text=f"Plug in your Samsung {self.active_profile.name} ({self.active_profile.codename}) via USB cable",
            font=ctk.CTkFont(size=12),
            text_color="#D1D5DB"
        )
        self.conn_details_lbl.grid(row=0, column=1, padx=(0, 14), pady=8)

        self.auto_adv_switch = ctk.CTkSwitch(
            self.top_bar,
            text="Auto-Verify & Advance",
            variable=self.auto_advance_var,
            font=ctk.CTkFont(size=12)
        )
        self.auto_adv_switch.grid(row=0, column=2, padx=(0, 20), pady=10, sticky="e")

        # 2. Left Sidebar (6 Wizard Steps + Quick Reboot Bar)
        self.sidebar = ctk.CTkFrame(self, width=255, corner_radius=0, fg_color="#18202F")
        self.sidebar.grid(row=1, column=0, rowspan=2, sticky="nsw")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="INSTALLATION WIZARD",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94A3B8"
        ).pack(padx=18, pady=(18, 8), anchor="w")

        for idx, (title, subtitle) in enumerate(STEPS):
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"{title}\n{subtitle}",
                anchor="w",
                height=52,
                corner_radius=8,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#1E293B",
                hover_color="#334155",
                command=lambda i=idx: self.select_step(i)
            )
            btn.pack(fill="x", padx=14, pady=5)
            self.step_buttons.append(btn)

        # Quick Hardware Controls in Sidebar
        ctk.CTkLabel(
            self.sidebar,
            text="QUICK PHONE ACTIONS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94A3B8"
        ).pack(padx=18, pady=(20, 6), anchor="w")

        ctk.CTkButton(
            self.sidebar,
            text="⚡ Reboot to Download Mode",
            height=34,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=lambda: self._run_async(lambda: self.device_mgr.reboot_to("download"))
        ).pack(fill="x", padx=14, pady=4)

        ctk.CTkButton(
            self.sidebar,
            text="🛠 Reboot to Recovery Mode",
            height=34,
            fg_color="#4F46E5",
            hover_color="#4338CA",
            command=lambda: self._run_async(lambda: self.device_mgr.reboot_to("recovery"))
        ).pack(fill="x", padx=14, pady=4)

        ctk.CTkButton(
            self.sidebar,
            text="🔄 Reboot to System",
            height=34,
            fg_color="#374151",
            hover_color="#4B5563",
            command=lambda: self._run_async(lambda: self.device_mgr.reboot_to(""))
        ).pack(fill="x", padx=14, pady=4)

        # 3. Main Step Content Container
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=1, column=1, padx=18, pady=(14, 8), sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # Build all 6 step panels
        self.step_frames = [
            self._build_step1_setup(),
            self._build_step2_device_check(),
            self._build_step3_bootloader(),
            self._build_step4_flash_recovery(),
            self._build_step5_sideload_rom(),
            self._build_step6_sideload_gapps(),
        ]

        # 4. Bottom Live Progress & Console Log Drawer
        self.bottom_frame = ctk.CTkFrame(self, height=185, corner_radius=10, fg_color="#0F172A")
        self.bottom_frame.grid(row=2, column=1, padx=18, pady=(4, 14), sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        prog_row = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        prog_row.grid(row=0, column=0, padx=14, pady=(8, 4), sticky="ew")
        prog_row.grid_columnconfigure(1, weight=1)

        self.progress_lbl = ctk.CTkLabel(
            prog_row,
            text="Ready.",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38BDF8"
        )
        self.progress_lbl.grid(row=0, column=0, padx=(0, 12), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(prog_row, height=10)
        self.progress_bar.grid(row=0, column=1, sticky="ew")
        self.progress_bar.set(0.0)

        self.console_box = ctk.CTkTextbox(
            self.bottom_frame,
            height=125,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#090D16",
            text_color="#E2E8F0"
        )
        self.console_box.grid(row=1, column=0, padx=14, pady=(4, 10), sticky="ew")

    # -------------------------------------------------------------------------
    # STEP 1: TOOLS & ROM FILES SELECTION
    # -------------------------------------------------------------------------
    def _build_step1_setup(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Step 1: Universal Samsung Device Advisor, Tools & Files",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            frame,
            text="Plug in ANY Samsung Galaxy phone/tablet to auto-detect its model & latest supported LineageOS version, or choose from 120+ Samsung models below!",
            font=ctk.CTkFont(size=13),
            text_color="#9CA3AF"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # Section 0: Universal Samsung Device Compatibility & Latest LineageOS Advisor
        univ_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#0F2942")
        univ_card.pack(fill="x", padx=16, pady=6)
        univ_card.grid_columnconfigure(1, weight=1)

        u_hdr = ctk.CTkFrame(univ_card, fg_color="transparent")
        u_hdr.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            u_hdr,
            text="📱 Universal Samsung Device Detector & LineageOS Version Advisor",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="left")

        ctk.CTkButton(
            u_hdr,
            text="🔄 Sync All 120+ Samsung Models from LineageOS Wiki",
            height=28,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._on_sync_wiki_db_clicked
        ).pack(side="right")

        sel_row = ctk.CTkFrame(univ_card, fg_color="transparent")
        sel_row.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(
            sel_row,
            text="Select or Search Model (SM-XXXX):",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=(0, 8))

        self.model_search_entry = ctk.CTkEntry(
            sel_row,
            placeholder_text="Type e.g. SM-A528B, SM-S901B, a21s...",
            width=210,
            height=32
        )
        self.model_search_entry.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            sel_row,
            text="Lookup Model",
            width=110,
            height=32,
            fg_color="#10B981",
            hover_color="#059669",
            command=self._on_lookup_model_clicked
        ).pack(side="left", padx=(0, 14))

        self.device_dropdown = ctk.CTkOptionMenu(
            sel_row,
            values=self.samsung_db.get_dropdown_choices(),
            width=390,
            height=32,
            fg_color="#1E293B",
            button_color="#0284C7",
            command=self._on_dropdown_device_selected
        )
        self.device_dropdown.pack(side="left", fill="x", expand=True)

        # Compatibility Summary Box inside univ_card
        self.advisor_info_lbl = ctk.CTkLabel(
            univ_card,
            text="",
            justify="left",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color="#A7F3D0"
        )
        self.advisor_info_lbl.pack(anchor="w", padx=14, pady=(2, 8))

        adv_btns = ctk.CTkFrame(univ_card, fg_color="transparent")
        adv_btns.pack(fill="x", padx=14, pady=(0, 10))

        self.open_dev_builds_btn = ctk.CTkButton(
            adv_btns,
            text="🌐 Open Official LineageOS Builds for This Phone",
            height=30,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=lambda: webbrowser.open(self.active_profile.builds_page_url)
        )
        self.open_dev_builds_btn.pack(side="left", padx=(0, 8))

        self.open_dev_wiki_btn = ctk.CTkButton(
            adv_btns,
            text="📖 Open Official Install Wiki for This Phone",
            height=30,
            fg_color="#334155",
            hover_color="#475569",
            command=lambda: webbrowser.open(self.active_profile.wiki_url)
        )
        self.open_dev_wiki_btn.pack(side="left", padx=(0, 8))

        self.open_samfw_btn = ctk.CTkButton(
            adv_btns,
            text="🌐 Open SamFw Stock Firmware for This Phone",
            height=30,
            fg_color="#334155",
            hover_color="#475569",
            command=self._open_samfw_for_active_device
        )
        self.open_samfw_btn.pack(side="left")

        # Section A: Automated SDK & Drivers
        tools_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        tools_card.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            tools_card,
            text="A. Required Flashing & USB Tools",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38BDF8"
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(12, 6), sticky="w")

        self.adb_status_lbl = ctk.CTkLabel(
            tools_card,
            text="Checking Android SDK Platform-Tools...",
            font=ctk.CTkFont(size=13)
        )
        self.adb_status_lbl.grid(row=1, column=0, padx=16, pady=8, sticky="w")

        ctk.CTkButton(
            tools_card,
            text="⬇ Auto-Download ADB & Platform-Tools",
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._on_download_platform_tools
        ).grid(row=1, column=1, padx=10, pady=8)

        ctk.CTkButton(
            tools_card,
            text="🔌 Get Official Samsung USB Driver",
            fg_color="#334155",
            hover_color="#475569",
            command=lambda: webbrowser.open(SAMSUNG_DRIVER_URL)
        ).grid(row=1, column=2, padx=10, pady=8)

        ctk.CTkButton(
            tools_card,
            text="📂 Open Local 'tools/' Folder (Drop odin4.exe / Odin3 here)",
            fg_color="#334155",
            hover_color="#475569",
            command=lambda: os.startfile(self.builder.tools_dir) if os.name == "nt" else None
        ).grid(row=2, column=0, columnspan=3, padx=16, pady=(4, 12), sticky="w")

        # Section B: Exact Mapping of LineageOS Website "Download builds" Page (Visible Right Away!)
        web_map_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#172554")
        web_map_card.pack(fill="x", padx=16, pady=6)
        web_map_card.grid_columnconfigure(1, weight=1)

        header_row = ctk.CTkFrame(web_map_card, fg_color="transparent")
        header_row.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            header_row,
            text="B. Which Files to Download from the LineageOS 'Download builds' Page?",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#60A5FA"
        ).pack(side="left")

        ctk.CTkButton(
            header_row,
            text="🌐 Open NikGapps Download Page",
            height=28,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=lambda: webbrowser.open(NIKGAPPS_DOWNLOAD_URL)
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            header_row,
            text="🌐 Open LineageOS Downloads for Selected Phone",
            height=28,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=lambda: webbrowser.open(self.active_profile.builds_page_url)
        ).pack(side="right")

        ctk.CTkLabel(
            web_map_card,
            text="The LineageOS website lists 7 files. You ONLY need 2 of them (plus 1 NikGapps ZIP):",
            font=ctk.CTkFont(size=12),
            text_color="#E2E8F0"
        ).pack(anchor="w", padx=14, pady=(0, 6))

        table_box = ctk.CTkFrame(web_map_card, corner_radius=8, fg_color="#0F172A")
        table_box.pack(fill="x", padx=14, pady=(0, 10))
        table_box.grid_columnconfigure(2, weight=1)

        self.web_guide_rom_fname_lbl = None
        self.web_guide_rom_desc_lbl = None
        for r_idx, (fname, badge, desc, color) in enumerate(LINEAGE_PAGE_FILES_GUIDE):
            fn_lbl = ctk.CTkLabel(
                table_box,
                text=fname,
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                text_color="#F8FAFC" if "SKIP" not in badge else "#64748B"
            )
            fn_lbl.grid(row=r_idx, column=0, padx=(12, 10), pady=3, sticky="w")

            ctk.CTkLabel(
                table_box,
                text=badge,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=color
            ).grid(row=r_idx, column=1, padx=10, pady=3, sticky="w")

            ds_lbl = ctk.CTkLabel(
                table_box,
                text=desc,
                font=ctk.CTkFont(size=12),
                text_color="#CBD5E1" if "SKIP" not in badge else "#64748B"
            )
            ds_lbl.grid(row=r_idx, column=2, padx=10, pady=3, sticky="w")
            if r_idx == 0:
                self.web_guide_rom_fname_lbl = fn_lbl
                self.web_guide_rom_desc_lbl = ds_lbl

        # Section C: File Pickers + 1-Click Auto-Detect from Downloads Folder
        files_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        files_card.pack(fill="x", padx=16, pady=8)
        files_card.grid_columnconfigure(1, weight=1)

        picker_hdr = ctk.CTkFrame(files_card, fg_color="transparent")
        picker_hdr.grid(row=0, column=0, columnspan=3, padx=16, pady=(12, 6), sticky="ew")

        ctk.CTkLabel(
            picker_hdr,
            text="C. Select Your Downloaded Files (Or Auto-Detect from Downloads Folder)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="left")

        ctk.CTkButton(
            picker_hdr,
            text="🔍 Auto-Find Files in My 'Downloads' Folder",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=self._auto_detect_from_downloads
        ).pack(side="right")

        # 1. Recovery file row
        self.rec_row_lbl, self.rec_entry = self._create_file_row(
            files_card,
            row=2,
            label="1. recovery.img (Lineage Recovery):",
            placeholder="Select 'recovery.img' from the LineageOS download page...",
            initial_val=self.app_state.get("recovery_path", ""),
            browse_cmd=self._browse_recovery
        )

        # 2. LineageOS ROM ZIP row
        self.rom_row_lbl, self.rom_entry = self._create_file_row(
            files_card,
            row=3,
            label=f"2. lineage-{self.active_profile.latest_lineage_version}-...-{self.active_profile.codename}-signed.zip:",
            placeholder=f"Select 'lineage-{self.active_profile.latest_lineage_version}-YYYYMMDD-nightly-{self.active_profile.codename}-signed.zip'...",
            initial_val=self.app_state.get("lineage_zip_path", ""),
            browse_cmd=self._browse_rom
        )
        self.rom_meta_lbl = ctk.CTkLabel(files_card, text="", font=ctk.CTkFont(size=12), text_color="#9CA3AF")
        self.rom_meta_lbl.grid(row=4, column=1, columnspan=2, padx=12, pady=(0, 4), sticky="w")

        # 3. NikGapps ZIP row
        self.gapps_row_lbl, self.gapps_entry = self._create_file_row(
            files_card,
            row=5,
            label=f"3. NikGapps-core-{self.active_profile.architecture}-...-signed.zip:",
            placeholder=f"Select 'NikGapps-core-{self.active_profile.architecture}-...-signed.zip'...",
            initial_val=self.app_state.get("nikgapps_zip_path", ""),
            browse_cmd=self._browse_gapps
        )
        self.gapps_meta_lbl = ctk.CTkLabel(files_card, text="", font=ctk.CTkFont(size=12), text_color="#9CA3AF")
        self.gapps_meta_lbl.grid(row=6, column=1, columnspan=2, padx=12, pady=(0, 4), sticky="w")

        # 4. Optional vbmeta.img row
        self.vbmeta_row_lbl, self.vbmeta_entry = self._create_file_row(
            files_card,
            row=7,
            label="4. vbmeta.img (Optional):",
            placeholder="Optional: Select 'vbmeta.img' (or leave empty to auto-generate disabled vbmeta.img)",
            initial_val=self.app_state.get("vbmeta_path", ""),
            browse_cmd=self._browse_vbmeta
        )

        # Navigation button
        nav_frame = ctk.CTkFrame(frame, fg_color="transparent")
        nav_frame.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(
            nav_frame,
            text="Verify Setup & Continue to Step 2 →",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=lambda: self.select_step(1)
        ).pack(side="right")

        self._refresh_step1_badges()
        return frame

    def _create_file_row(self, parent, row: int, label: str, placeholder: str, initial_val: str, browse_cmd):
        lbl_widget = ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=13, weight="bold"))
        lbl_widget.grid(row=row, column=0, padx=16, pady=6, sticky="w")
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder, height=34)
        entry.grid(row=row, column=1, padx=8, pady=6, sticky="ew")
        if initial_val:
            entry.insert(0, initial_val)
        ctk.CTkButton(parent, text="Browse...", width=100, command=browse_cmd).grid(
            row=row, column=2, padx=16, pady=6
        )
        return lbl_widget, entry

    # -------------------------------------------------------------------------
    # STEP 2: DEVICE CONNECTION & PRE-FLIGHT CHECK
    # -------------------------------------------------------------------------
    def _build_step2_device_check(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)

        self.step2_title_lbl = ctk.CTkLabel(
            frame,
            text=f"Step 2: Connect Samsung {self.active_profile.name} ({self.active_profile.codename}) & Pre-Flight Check",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.step2_title_lbl.pack(anchor="w", padx=16, pady=(12, 4))

        self.step2_subtitle_lbl = ctk.CTkLabel(
            frame,
            text=f"Plug your Samsung {self.active_profile.name} into your PC via USB. If parts are already configured, they will turn green automatically!",
            font=ctk.CTkFont(size=13),
            text_color="#9CA3AF"
        )
        self.step2_subtitle_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        # Live Checklist Card
        check_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        check_card.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            check_card,
            text="Live Hardware & Firmware Verification",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=16, pady=(12, 8))

        self.chk_usb_lbl = ctk.CTkLabel(check_card, text="⏳ 1. USB Connection & Drivers: Waiting for device...", font=ctk.CTkFont(size=13))
        self.chk_usb_lbl.pack(anchor="w", padx=20, pady=4)

        self.chk_model_lbl = ctk.CTkLabel(
            check_card,
            text=f"⏳ 2. Device Model Verification (Target: Samsung {self.active_profile.name} / {self.active_profile.codename}): Waiting...",
            font=ctk.CTkFont(size=13)
        )
        self.chk_model_lbl.pack(anchor="w", padx=20, pady=4)

        self.chk_fw_lbl = ctk.CTkLabel(
            check_card,
            text=f"⏳ 3. Firmware Base (Required: Android {self.active_profile.required_stock_android or 'Stock One UI'}): Waiting...",
            font=ctk.CTkFont(size=13)
        )
        self.chk_fw_lbl.pack(anchor="w", padx=20, pady=4)

        self.chk_bl_lbl = ctk.CTkLabel(check_card, text="⏳ 4. Bootloader & OEM Unlock Status: Waiting...", font=ctk.CTkFont(size=13))
        self.chk_bl_lbl.pack(anchor="w", padx=20, pady=(4, 14))

        # Visual Guide on Enabling USB Debugging & OEM Unlocking
        guide_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        guide_card.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            guide_card,
            text="How to Enable USB Debugging & OEM Unlocking on Samsung One UI:",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#FBBF24"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        steps_text = (
            "1. Connect your phone to Wi-Fi (required by Samsung Knox so the 'OEM unlocking' toggle appears).\n"
            "2. Open Settings -> About phone -> Software information.\n"
            "3. Tap 'Build number' 7 times rapidly until it says 'Developer mode has been turned on'.\n"
            "4. Go back to the main Settings page and scroll to the very bottom -> open 'Developer options'.\n"
            "5. Turn ON 'OEM unlocking' (If it is already greyed out and says 'Bootloader is already unlocked', Step 3 is already done!).\n"
            "6. Scroll down and turn ON 'USB debugging'.\n"
            "7. Look at your phone screen and tap 'Allow' on the 'Allow USB debugging?' popup (check 'Always allow from this computer')."
        )
        ctk.CTkLabel(
            guide_card,
            text=steps_text,
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color="#E5E7EB"
        ).pack(anchor="w", padx=16, pady=(0, 14))

        nav_frame = ctk.CTkFrame(frame, fg_color="transparent")
        nav_frame.pack(fill="x", padx=16, pady=8)

        ctk.CTkButton(
            nav_frame,
            text="⚡ Auto-Reboot Phone to Download Mode Now",
            height=40,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._reboot_and_go_step3
        ).pack(side="left")

        ctk.CTkButton(
            nav_frame,
            text="Continue to Step 3 (Bootloader / Download Mode) →",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=lambda: self.select_step(2)
        ).pack(side="right")

        return frame

    # -------------------------------------------------------------------------
    # STEP 3: BOOTLOADER UNLOCK & SAMSUNG DOWNLOAD MODE
    # -------------------------------------------------------------------------
    def _build_step3_bootloader(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Step 3: Samsung Download Mode & Bootloader Unlock",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.step3_banner_lbl = ctk.CTkLabel(
            frame,
            text="Checking current Bootloader & Download Mode state...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FBBF24"
        )
        self.step3_banner_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        # Card 1: How to enter Download Mode
        dl_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        dl_card.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            dl_card,
            text="Method A (Automatic): Click the button below if phone is on in ADB mode",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkButton(
            dl_card,
            text="⚡ Reboot Phone into Samsung Download Mode Automatically",
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=lambda: self._run_async(lambda: self.device_mgr.reboot_to("download"))
        ).pack(anchor="w", padx=16, pady=(0, 12))

        self.step3_combo_hdr_lbl = ctk.CTkLabel(
            dl_card,
            text=f"Method B (Manual Button Combo on Samsung {self.active_profile.name}):",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FBBF24"
        )
        self.step3_combo_hdr_lbl.pack(anchor="w", padx=16, pady=(4, 6))

        self.step3_combo_body_lbl = ctk.CTkLabel(
            dl_card,
            text="",
            justify="left",
            wraplength=820,
            font=ctk.CTkFont(size=13),
            text_color="#E5E7EB"
        )
        self.step3_combo_body_lbl.pack(anchor="w", padx=16, pady=(0, 14))

        nav_frame = ctk.CTkFrame(frame, fg_color="transparent")
        nav_frame.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(
            nav_frame,
            text="Phone is in Download Mode -> Proceed to Step 4 (Flash Recovery) →",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=lambda: self.select_step(3)
        ).pack(side="right")

        return frame

    # -------------------------------------------------------------------------
    # STEP 4: FLASH LINEAGE RECOVERY & DISABLED VBMETA IN DOWNLOAD MODE
    # -------------------------------------------------------------------------
    def _build_step4_flash_recovery(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Step 4: Flash Lineage Recovery in Download Mode (Odin)",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            frame,
            text="Your phone is in Download Mode! Follow Sub-Steps 4A -> 4B -> 4C below.",
            font=ctk.CTkFont(size=13),
            text_color="#9CA3AF"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # KNOX / PRENORMAL / BOOTLOADER UNLOCK TROUBLESHOOTER CARD
        knox_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#3B1818")
        knox_card.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            knox_card,
            text="🛑 Getting 'Only official released binaries are allowed to be flashed (RECOVERY)' & Odin FAIL!?",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FCA5A5"
        ).pack(anchor="w", padx=16, pady=(10, 4))

        knox_fix_text = (
            "That message on your phone's Download Mode screen means Samsung VaultKeeper / Bootloader Lock is still active!\n"
            "Look at the small text in the top-left corner of your phone's blue Download Mode screen:\n"
            "• Case 1 — It says 'OEM LOCK: ON (L)': Your bootloader was NOT unlocked yet (you entered Download Mode with a short press instead of holding Volume Up for 7 seconds on the teal screen, OR 'OEM unlocking' wasn't turned on in Developer Options).\n"
            "• Case 2 — It says 'KG STATUS: PRENORMAL' (even with OEM LOCK: OFF (U)): After unlocking or wiping a Samsung phone, Samsung VaultKeeper locks custom flashing until you connect to Wi-Fi once!\n\n"
            "HOW TO FIX IT IN 60 SECONDS:\n"
            "1. Exit Download Mode right now: Hold [Volume Down] + [Power] for 7 seconds until the phone restarts normally into Samsung One UI.\n"
            "2. Connect the phone to Wi-Fi (Mandatory! Wait 1 minute with internet active so Samsung servers clear VaultKeeper).\n"
            "3. Open Settings -> About phone -> Software information -> Tap 'Build number' 7 times.\n"
            "4. Go back to Settings -> Developer options -> Verify 'OEM unlocking' is visible and turned ON (or greyed out saying 'Bootloader is already unlocked').\n"
            "5. If OEM Unlocking was NOT unlocked yet: Power off -> Enter Download Mode -> On the teal screen, HOLD [Volume Up] for 7 seconds to unlock -> Then repeat Step 2 (connect to Wi-Fi & open Developer Options)!\n"
            "6. Once 'OEM unlocking' is visible/greyed-out with Wi-Fi connected, re-enter Download Mode -> The screen will now say 'KG STATUS: CHECKING' (or COMPLETED) and Odin will flash PASS!"
        )
        ctk.CTkLabel(
            knox_card,
            text=knox_fix_text,
            justify="left",
            wraplength=820,
            font=ctk.CTkFont(size=12),
            text_color="#FEE2E2"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # SUB-STEP 4A: Build .tar & Auto-Open Odin3
        card_4a = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        card_4a.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            card_4a,
            text="Sub-Step 4A: Click Below to Build Odin Package & Auto-Open Samsung Odin3",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            card_4a,
            text=(
                "Clicking the blue button below will:\n"
                "1. Package ONLY 'recovery.img' into 'A217F_LineageRecovery_Odin.tar' (no vbmeta.img — prevents VBMETA 0xa error!).\n"
                "2. Copy that exact file path to your clipboard (so you can just press Ctrl+V in Odin!).\n"
                "3. Automatically launch Samsung Odin3 on your screen!"
            ),
            justify="left",
            font=ctk.CTkFont(size=12),
            text_color="#E5E7EB"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        btn_row = ctk.CTkFrame(card_4a, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(
            btn_row,
            text="🚀 Option A: Build Recovery-Only .TAR & Launch Odin3",
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._on_flash_recovery_clicked
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="⚡ Option B: Direct Flash via samloader-rs (No Odin Needed!)",
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=self._on_flash_samloader_clicked
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="📋 Copy .TAR Path",
            height=42,
            fg_color="#334155",
            hover_color="#475569",
            command=self._copy_tar_path_to_clipboard
        ).pack(side="left")

        # SUB-STEP 4B: Exact 3 Clicks Inside Odin3 Window
        card_4b = ctk.CTkFrame(frame, corner_radius=10, fg_color="#172554")
        card_4b.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            card_4b,
            text="Sub-Step 4B: Do These Exact 3 Clicks Inside the Odin3 Window That Opens:",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#60A5FA"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        odin_steps = (
            "• CLICK 1 (Select File): In Odin3, click the [AP] button -> Press Ctrl+V in the File name box -> Click 'Open'.\n"
            "  (This loads 'A217F_LineageRecovery_Odin.tar' into the AP slot).\n"
            "• CLICK 2 (Turn Off Auto-Reboot): Click the 'Options' tab on the left side of Odin3 -> UNCHECK 'Auto Reboot'.\n"
            "• CLICK 3 (Flash!): Click the big [Start] button at the bottom of Odin3. Wait ~5 seconds until Odin says green 'PASS!'."
        )
        ctk.CTkLabel(
            card_4b,
            text=odin_steps,
            justify="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#F8FAFC"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # SUB-STEP 4C: Button Combo on Phone After Odin Says PASS!
        warn_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#311B1B")
        warn_card.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            warn_card,
            text="Sub-Step 4C: Once Odin3 Says Green 'PASS!', Do This on Your Phone:",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#F87171"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        self.step4_transition_lbl = ctk.CTkLabel(
            warn_card,
            text="",
            justify="left",
            wraplength=820,
            font=ctk.CTkFont(size=13),
            text_color="#FEE2E2"
        )
        self.step4_transition_lbl.pack(anchor="w", padx=16, pady=(0, 14))

        nav_frame = ctk.CTkFrame(frame, fg_color="transparent")
        nav_frame.pack(fill="x", padx=16, pady=8)
        self.step4_next_btn = ctk.CTkButton(
            nav_frame,
            text=f"Phone is in Lineage Recovery -> Proceed to Step 5 (Install LineageOS {self.active_profile.latest_lineage_version}) →",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=lambda: self.select_step(4)
        )
        self.step4_next_btn.pack(side="right")

        return frame

    # -------------------------------------------------------------------------
    # STEP 5: FORMAT DATA & SIDELOAD LINEAGEOS ROM
    # -------------------------------------------------------------------------
    def _build_step5_sideload_rom(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)

        self.step5_title_lbl = ctk.CTkLabel(
            frame,
            text=f"Step 5: Format Data & Automated LineageOS {self.active_profile.latest_lineage_version} Sideload",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.step5_title_lbl.pack(anchor="w", padx=16, pady=(12, 4))

        self.step5_subtitle_lbl = ctk.CTkLabel(
            frame,
            text=f"In Lineage Recovery (or TWRP) on your Samsung {self.active_profile.name} ({self.active_profile.codename}), follow the two quick actions below.",
            font=ctk.CTkFont(size=13),
            text_color="#9CA3AF"
        )
        self.step5_subtitle_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        wipe_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        wipe_card.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            wipe_card,
            text="Part 1: Remove Samsung File-Based Encryption (Format Data)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#FBBF24"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            wipe_card,
            text=(
                "1. On the phone recovery screen, tap 'Factory reset' -> 'Format data / factory reset' -> Confirm 'Format data'.\n"
                "   (In TWRP: Tap 'Wipe' -> 'Format Data' -> type 'yes').\n"
                "2. Go back to the Recovery main menu and tap 'Apply update' -> 'Apply from ADB'\n"
                "   (In TWRP: Tap 'Advanced' -> 'ADB Sideload' -> Swipe to Start Sideload)."
            ),
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color="#E5E7EB"
        ).pack(anchor="w", padx=16, pady=(0, 14))

        sideload_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        sideload_card.pack(fill="x", padx=16, pady=8)

        self.step5_part2_hdr_lbl = ctk.CTkLabel(
            sideload_card,
            text=f"Part 2: One-Click LineageOS {self.active_profile.latest_lineage_version} Automated Sideload",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38BDF8"
        )
        self.step5_part2_hdr_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        self.step5_sideload_state_lbl = ctk.CTkLabel(
            sideload_card,
            text="Waiting for phone to enter 'ADB Sideload' mode...",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FBBF24"
        )
        self.step5_sideload_state_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        btn_5_row = ctk.CTkFrame(sideload_card, fg_color="transparent")
        btn_5_row.pack(fill="x", padx=16, pady=(0, 14))

        self.step5_sideload_btn = ctk.CTkButton(
            btn_5_row,
            text=f"🚀 Start LineageOS {self.active_profile.latest_lineage_version} Automated ADB Sideload",
            height=46,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._on_sideload_lineage_clicked
        )
        self.step5_sideload_btn.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_5_row,
            text="⚡ Patch & Sideload (Bypass Bootloader Binary Check!)",
            height=46,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=self._on_patch_and_sideload_lineage_clicked
        ).pack(side="left")

        # Binary Check Error Explanation & Official Firmware Option Card
        binc_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#3B1818")
        binc_card.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            binc_card,
            text="🛑 Getting 'Error: This build requires a bootloader with binary version ...'?",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FCA5A5"
        ).pack(anchor="w", padx=16, pady=(10, 4))

        binc_text = (
            "Why this happens on some Samsung devices: Official LineageOS nightlies check that your Samsung bootloader binary revision "
            "matches the newest stock security patch.\n\n"
            "You have 2 ways to fix this right now:\n"
            "• FAST WAY (2 Minutes — No 5GB Download): Put your phone in 'Apply update -> Apply from ADB' mode and click the green button above: "
            "'⚡ Patch & Sideload (Bypass Bootloader Binary Check!)'. It removes the bootloader binary check from the ROM ZIP and sideloads it immediately! "
            "(When your phone screen asks 'Signature verification failed — Install anyway?', tap 'Yes'!).\n"
            "• OFFICIAL WAY (Update Stock Bootloader): Download the latest stock firmware for your model from SamFw "
            "and flash BL + CP in Odin3."
        )
        ctk.CTkLabel(
            binc_card,
            text=binc_text,
            justify="left",
            wraplength=820,
            font=ctk.CTkFont(size=12),
            text_color="#FEE2E2"
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self.step5_samfw_btn = ctk.CTkButton(
            binc_card,
            text=f"🌐 Open SamFw ({self.active_profile.models[0] if self.active_profile.models else self.active_profile.codename} Stock Firmware)",
            height=30,
            fg_color="#334155",
            hover_color="#475569",
            command=self._open_samfw_for_active_device
        )
        self.step5_samfw_btn.pack(anchor="w", padx=16, pady=(0, 12))

        nav_frame = ctk.CTkFrame(frame, fg_color="transparent")
        nav_frame.pack(fill="x", padx=16, pady=8)
        self.step5_next_btn = ctk.CTkButton(
            nav_frame,
            text=f"LineageOS {self.active_profile.latest_lineage_version} Installed -> Proceed to Step 6 (Install NikGapps) →",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=lambda: self.select_step(5)
        )
        self.step5_next_btn.pack(side="right")

        return frame

    # -------------------------------------------------------------------------
    # STEP 6: SIDELOAD NIKGAPPS & FIRST BOOT
    # -------------------------------------------------------------------------
    def _build_step6_sideload_gapps(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)

        self.step6_title_lbl = ctk.CTkLabel(
            frame,
            text=f"Step 6: Flash NikGapps ({self.active_profile.architecture}) & Boot into LineageOS {self.active_profile.latest_lineage_version}!",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.step6_title_lbl.pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            frame,
            text="IMPORTANT: Flash NikGapps BEFORE booting into LineageOS for the first time so Google Play Services gets system permissions.",
            font=ctk.CTkFont(size=13),
            text_color="#FBBF24"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        prep_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        prep_card.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            prep_card,
            text="1. Prepare Recovery for NikGapps",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        self.step6_prep_lbl = ctk.CTkLabel(
            prep_card,
            text=(
                f"• On your Samsung {self.active_profile.name} in Recovery: Tap 'Advanced' -> 'Reboot to recovery' (this reloads the updated partition layout).\n"
                "• Once Recovery reloads, tap 'Apply update' -> 'Apply from ADB'.\n"
                "• Note: If Recovery asks 'Signature verification failed — Install anyway?', tap 'Yes' (NikGapps uses its own key)."
            ),
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color="#E5E7EB"
        )
        self.step6_prep_lbl.pack(anchor="w", padx=16, pady=(0, 14))

        gapps_card = ctk.CTkFrame(frame, corner_radius=10, fg_color="#1E293B")
        gapps_card.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            gapps_card,
            text="2. Sideload NikGapps Package & Reboot to System",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#10B981"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        btn_row = ctk.CTkFrame(gapps_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 14))

        ctk.CTkButton(
            btn_row,
            text="🚀 Start NikGapps Automated ADB Sideload",
            height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._on_sideload_gapps_clicked
        ).pack(side="left", padx=(0, 12))

        self.step6_reboot_btn = ctk.CTkButton(
            btn_row,
            text=f"🎉 Reboot Phone into LineageOS {self.active_profile.latest_lineage_version} System",
            height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=lambda: self._run_async(lambda: self.device_mgr.reboot_to(""))
        )
        self.step6_reboot_btn.pack(side="left")

        return frame

    # -------------------------------------------------------------------------
    # ACTIONS & EVENT HANDLERS
    # -------------------------------------------------------------------------
    def select_step(self, idx: int):
        self.current_step_idx = idx
        for i, frame in enumerate(self.step_frames):
            if i == idx:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()

        for i, btn in enumerate(self.step_buttons):
            if i == idx:
                btn.configure(fg_color="#0284C7", text_color="#FFFFFF")
            elif i in self.app_state.get("completed_steps", []):
                btn.configure(fg_color="#065F46", text_color="#D1FAE5")
            else:
                btn.configure(fg_color="#1E293B", text_color="#CBD5E1")

    def mark_step_completed(self, idx: int):
        completed = self.app_state.get("completed_steps", [])
        if idx not in completed:
            completed.append(idx)
            self.app_state["completed_steps"] = completed
            self._save_state()
            self.select_step(self.current_step_idx)

    def log_message(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}\n"
        self.after(0, lambda: self._append_console(line))

    def _append_console(self, line: str):
        self.console_box.insert("end", line)
        self.console_box.see("end")

    def set_progress(self, value: float, text: str):
        def _update():
            self.progress_bar.set(max(0.0, min(1.0, value)))
            self.progress_lbl.configure(text=text)
        self.after(0, _update)

    def _run_async(self, func):
        threading.Thread(target=func, daemon=True).start()

    def _initial_background_sync(self):
        # 1. Fetch live builds for current active profile
        self.samsung_db.fetch_live_builds_for_device(self.active_profile)
        self.after(0, self._refresh_active_profile_ui)
        # 2. If full Wiki cache isn't built yet, sync all 120+ Samsung models in background
        if len(self.samsung_db.devices_by_codename) < 30:
            self.samsung_db.sync_all_samsung_devices_from_wiki()
            self.after(0, self._refresh_dropdown_values)

    def _refresh_dropdown_values(self):
        choices = self.samsung_db.get_dropdown_choices()
        self.device_dropdown.configure(values=choices)
        for ch in choices:
            if f"[{self.active_profile.codename}]" in ch:
                self.device_dropdown.set(ch)
                break

    def _on_sync_wiki_db_clicked(self):
        def task():
            self.set_progress(0.2, "Syncing all 120+ Samsung models from official LineageOS Wiki...")
            count = self.samsung_db.sync_all_samsung_devices_from_wiki()
            self.samsung_db.fetch_live_builds_for_device(self.active_profile)
            self.set_progress(1.0, f"Synced {count} Samsung models from LineageOS Wiki!")
            self.after(0, self._refresh_dropdown_values)
            self.after(0, self._refresh_active_profile_ui)
        self._run_async(task)

    def _on_lookup_model_clicked(self):
        q = self.model_search_entry.get().strip()
        if not q:
            return
        prof = self.samsung_db.find_device(q)
        if prof:
            self._set_active_profile(prof)
            self.log_message(f"[ADVISOR] Matched '{q}' -> Samsung {prof.name} ({prof.codename}) | Latest: LineageOS {prof.latest_lineage_version} ({prof.latest_android_version})")
        else:
            messagebox.showwarning(
                "Model Not in Official LineageOS Catalog",
                f"Could not find '{q}' in the official LineageOS Samsung catalog.\n\n"
                "Tip: Click '🔄 Sync All 120+ Samsung Models' first, or check XDA Forums for unofficial GSI / ROM builds for your model."
            )

    def _on_dropdown_device_selected(self, choice: str):
        if "[" in choice and "]" in choice:
            cname = choice.split("[")[1].split("]")[0].strip()
            prof = self.samsung_db.find_device(cname)
            if prof:
                self._set_active_profile(prof)

    def _set_active_profile(self, prof: SamsungDeviceProfile):
        self.active_profile = prof
        self.app_state["selected_codename"] = prof.codename
        self._save_state()
        self._refresh_dropdown_values()
        self._refresh_active_profile_ui()

        def bg_fetch():
            self.samsung_db.fetch_live_builds_for_device(prof)
            self.after(0, self._refresh_active_profile_ui)
        self._run_async(bg_fetch)

    def _open_samfw_for_active_device(self):
        first_model = self.active_profile.models[0].split("/")[0] if self.active_profile.models else "SM-A217F"
        webbrowser.open(f"https://samfw.com/firmware/{first_model}")

    def _show_startup_disclaimer_modal(self):
        """Displays a mandatory Terms & Conditions / Legal Risk Warning dialog when opening the app."""
        modal = ctk.CTkToplevel(self)
        modal.title(f"⚠️ Terms & Conditions / Risk Warning — {APP_TITLE}")
        modal.geometry("760x530")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()
        modal.configure(fg_color="#0F172A")

        # If user closes the modal window via the X button without accepting, exit app
        modal.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(
            modal,
            text="⚠️ CAUTION: CUSTOM ROM & RECOVERY FLASHING DISCLAIMER",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#F87171"
        ).pack(padx=20, pady=(16, 4), anchor="w")

        ctk.CTkLabel(
            modal,
            text="Please read and accept the following Terms & Conditions before using Lineage OS Installer for Samsung GUI:",
            font=ctk.CTkFont(size=13),
            text_color="#CBD5E1"
        ).pack(padx=20, pady=(0, 8), anchor="w")

        txt_box = ctk.CTkTextbox(
            modal,
            height=305,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#1E293B",
            text_color="#F8FAFC",
            wrap="word"
        )
        txt_box.pack(fill="x", padx=20, pady=6)
        txt_box.insert("1.0", LEGAL_DISCLAIMER_TEXT)
        txt_box.configure(state="disabled")

        agree_var = ctk.BooleanVar(value=False)

        def on_toggle():
            if agree_var.get():
                accept_btn.configure(state="normal", fg_color="#10B981")
            else:
                accept_btn.configure(state="disabled", fg_color="#334155")

        chk = ctk.CTkCheckBox(
            modal,
            text="I understand that flashing may brick my phone, erase all data, or lose the OS, and I proceed at my own risk.",
            variable=agree_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FBBF24",
            command=on_toggle
        )
        chk.pack(padx=20, pady=(10, 12), anchor="w")

        btn_row = ctk.CTkFrame(modal, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(
            btn_row,
            text="❌ Decline & Exit",
            width=150,
            height=38,
            fg_color="#EF4444",
            hover_color="#DC2626",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy
        ).pack(side="left")

        def on_accept():
            self.app_state["accepted_disclaimer"] = True
            self._save_state()
            self.log_message("[LEGAL] User accepted Terms & Conditions / Custom ROM Risk Disclaimer.")
            modal.grab_release()
            modal.destroy()

        accept_btn = ctk.CTkButton(
            btn_row,
            text="✅ I Understand & Proceed at My Own Risk",
            width=310,
            height=38,
            state="disabled",
            fg_color="#334155",
            hover_color="#059669",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=on_accept
        )
        accept_btn.pack(side="right")

    def _refresh_active_profile_ui(self):
        p = self.active_profile
        models_str = ", ".join(p.models[:4]) if p.models else p.codename
        first_model = p.models[0].split("/")[0] if p.models else p.codename

        # 1. Top Bar Title, Subtitle & Disconnected Prompt
        self.top_title_lbl.configure(
            text=f"LINEAGE OS INSTALLER FOR SAMSUNG GUI — {p.name.upper()} ({p.codename})"
        )
        req_base = f"Android {p.required_stock_android}" if p.required_stock_android else "Latest Stock One UI"
        self.top_subtitle_lbl.configure(
            text=f"Max Official Support: LineageOS {p.latest_lineage_version} ({p.latest_android_version}) + NikGapps ({p.architecture})  |  Required Base: {req_base}"
        )
        cur_st = self.device_mgr.current_status
        if cur_st.mode == "disconnected":
            detail = cur_st.raw_details or f"Plug in your Samsung {p.name} ({p.codename}) via USB cable"
            self.conn_details_lbl.configure(text=detail)

        # 2. Left Sidebar Step 5 Button
        if len(self.step_buttons) >= 5:
            self.step_buttons[4].configure(text=f"5. LineageOS {p.latest_lineage_version}\nFormat Data & Sideload ROM")

        # 3. Step 1 Advisor Card, Table Row & File Picker Labels
        rom_hint = p.latest_rom_filename or f"lineage-{p.latest_lineage_version}-YYYYMMDD-nightly-{p.codename}-signed.zip"
        all_vers = ", ".join(p.supported_versions) if p.supported_versions else p.latest_lineage_version
        advisor_txt = (
            f"✅ Device: Samsung {p.name}  |  Codename: {p.codename}  |  Models: {models_str}\n"
            f"🚀 Latest Supported LineageOS:  LineageOS {p.latest_lineage_version} ({p.latest_android_version})   [All Supported Branches: {all_vers}]\n"
            f"🔧 SoC / Arch: {p.soc} ({p.architecture})  |  Required Stock Firmware Before Flashing: {req_base}\n"
            f"📦 Exact ROM File to Download:  {rom_hint}   +   recovery.img   +   NikGapps-core-{p.architecture}-...zip"
        )
        self.advisor_info_lbl.configure(text=advisor_txt)

        if self.web_guide_rom_fname_lbl:
            self.web_guide_rom_fname_lbl.configure(text=rom_hint)
        if self.web_guide_rom_desc_lbl:
            self.web_guide_rom_desc_lbl.configure(text=f"Put in Box #2 (Main LineageOS {p.latest_lineage_version} ROM ZIP for {p.codename})")

        self.rom_row_lbl.configure(text=f"2. lineage-{p.latest_lineage_version}-...-{p.codename}-signed.zip:")
        self.rom_entry.configure(placeholder_text=f"Select '{rom_hint}'...")
        self.gapps_row_lbl.configure(text=f"3. NikGapps-core-{p.architecture}-...-signed.zip:")
        self.gapps_entry.configure(placeholder_text=f"Select 'NikGapps-core-{p.architecture}-...-signed.zip'...")

        # 4. Step 2 Titles & Waiting Labels
        self.step2_title_lbl.configure(text=f"Step 2: Connect Samsung {p.name} ({p.codename}) & Pre-Flight Check")
        self.step2_subtitle_lbl.configure(
            text=f"Plug your Samsung {p.name} ({models_str}) into your PC via USB. If parts are already configured, they will turn green automatically!"
        )
        if cur_st.mode == "disconnected":
            self.chk_model_lbl.configure(
                text=f"⏳ 2. Device Model Verification (Target: Samsung {p.name} / {p.codename}): Waiting...",
                text_color="#E5E7EB"
            )
            self.chk_fw_lbl.configure(
                text=f"⏳ 3. Firmware Base (Required: {req_base}): Waiting...",
                text_color="#E5E7EB"
            )

        # 5. Step 3 Manual Download Mode Button Combo
        self.step3_combo_hdr_lbl.configure(text=f"Method B (Manual Button Combo on Samsung {p.name} — {first_model}):")
        dl_combo_line = (
            f"• Official Wiki Combo for {p.name}: {p.download_boot_combo}\n"
            if p.download_boot_combo
            else "• Press and HOLD BOTH [Volume Up] + [Volume Down] buttons together while plugging in the USB cable.\n"
        )
        combo_text = (
            f"1. Power OFF your Samsung {p.name} completely.\n"
            f"2. Enter Download Mode:\n   {dl_combo_line.strip()}\n"
            "3. A teal/blue Warning screen will appear on the phone:\n"
            "   • If your Bootloader is NOT unlocked yet: Long-press [Volume Up] for 7 seconds -> Press [Volume Up] to confirm Bootloader Unlock.\n"
            "     (The phone will factory reset, boot back into One UI—reconnect to Wi-Fi, re-enable USB Debugging, and come right back here!)\n"
            "   • If your Bootloader IS ALREADY unlocked: Short-press [Volume Up] once to enter Download Mode ('Downloading... Do not turn off target')."
        )
        self.step3_combo_body_lbl.configure(text=combo_text)

        # 6. Step 4 Recovery Transition Combo & Next Button
        rec_combo_line = (
            f"Official Wiki Recovery Combo for {p.name}: {p.recovery_boot_combo}"
            if p.recovery_boot_combo
            else "Hold [Volume Up] + [Power] until the Lineage Recovery menu appears!"
        )
        transition_text = (
            "Your phone is still on the blue 'Downloading...' screen because we unchecked Auto-Reboot.\n"
            f"Now boot your Samsung {p.name} directly into Lineage Recovery:\n"
            "1. Hold [Volume Down] + [Power] on your phone for ~7 seconds until the screen turns black.\n"
            f"2. The INSTANT the screen goes black, release Volume Down and use your device's Recovery combo:\n   -> {rec_combo_line}\n"
            f"3. Keep holding through the Samsung {p.name} boot logo until the Lineage Recovery menu appears!\n"
            "4. As soon as Lineage Recovery appears on your phone, this app will automatically move to Step 5!"
        )
        self.step4_transition_lbl.configure(text=transition_text)
        self.step4_next_btn.configure(
            text=f"Phone is in Lineage Recovery -> Proceed to Step 5 (Install LineageOS {p.latest_lineage_version}) →"
        )

        # 7. Step 5 & Step 6 Titles and Buttons
        self.step5_title_lbl.configure(text=f"Step 5: Format Data & Automated LineageOS {p.latest_lineage_version} Sideload")
        self.step5_subtitle_lbl.configure(
            text=f"In Lineage Recovery (or TWRP) on your Samsung {p.name} ({p.codename}), follow the two quick actions below."
        )
        self.step5_part2_hdr_lbl.configure(text=f"Part 2: One-Click LineageOS {p.latest_lineage_version} Automated Sideload")
        self.step5_sideload_btn.configure(text=f"🚀 Start LineageOS {p.latest_lineage_version} Automated ADB Sideload")
        self.step5_samfw_btn.configure(text=f"🌐 Open SamFw ({first_model} Stock Firmware)")
        self.step5_next_btn.configure(
            text=f"LineageOS {p.latest_lineage_version} Installed -> Proceed to Step 6 (Install NikGapps) →"
        )
        self.step6_title_lbl.configure(
            text=f"Step 6: Flash NikGapps ({p.architecture}) & Boot into LineageOS {p.latest_lineage_version}!"
        )
        self.step6_prep_lbl.configure(
            text=(
                f"• On your Samsung {p.name} in Recovery: Tap 'Advanced' -> 'Reboot to recovery' (this reloads the updated partition layout).\n"
                "• Once Recovery reloads, tap 'Apply update' -> 'Apply from ADB'.\n"
                "• Note: If Recovery asks 'Signature verification failed — Install anyway?', tap 'Yes' (NikGapps uses its own key)."
            )
        )
        self.step6_reboot_btn.configure(text=f"🎉 Reboot Phone into LineageOS {p.latest_lineage_version} System")

        self._refresh_step1_badges()

    def _refresh_step1_badges(self):
        if self.builder.is_platform_tools_installed():
            self.adb_status_lbl.configure(
                text=f"✅ Android Platform-Tools Installed ({self.builder.get_adb_path()})",
                text_color="#34D399"
            )
        else:
            self.adb_status_lbl.configure(
                text="❌ Android Platform-Tools Not Found — Click 'Auto-Download' ->",
                text_color="#F87171"
            )

        # Validate selected ROM & NikGapps ZIPs against active_profile
        rom_path = self.rom_entry.get().strip()
        if rom_path and os.path.exists(rom_path):
            info = self.builder.inspect_rom_zip(
                rom_path,
                target_codename=self.active_profile.codename,
                target_arch=self.active_profile.architecture
            )
            color = "#34D399" if info["valid_zip"] and info["target_device_ok"] else "#F87171"
            self.rom_meta_lbl.configure(
                text=f"Size: {info['size_mb']} MB  |  {info['metadata_summary']}",
                text_color=color
            )

        gapps_path = self.gapps_entry.get().strip()
        if gapps_path and os.path.exists(gapps_path):
            info = self.builder.inspect_rom_zip(
                gapps_path,
                target_codename=self.active_profile.codename,
                target_arch=self.active_profile.architecture
            )
            color = "#34D399" if info["valid_zip"] else "#F87171"
            self.gapps_meta_lbl.configure(
                text=f"Size: {info['size_mb']} MB  |  {info['metadata_summary']}",
                text_color=color
            )

    def _on_download_platform_tools(self):
        def task():
            ok = self.builder.download_platform_tools(progress_cb=self.set_progress)
            self.after(0, self._refresh_step1_badges)
            if ok:
                self.after(0, lambda: self.mark_step_completed(0))
        self._run_async(task)

    def _browse_recovery(self):
        path = filedialog.askopenfilename(
            title="Select Custom Recovery (.img or .tar)",
            filetypes=[("Recovery Image or Tar", "*.img *.tar *.md5"), ("All Files", "*.*")]
        )
        if path:
            self.rec_entry.delete(0, "end")
            self.rec_entry.insert(0, path)
            self.app_state["recovery_path"] = path
            self._save_state()
            self.log_message(f"[FILE] Selected Recovery: {path}")

    def _browse_rom(self):
        path = filedialog.askopenfilename(
            title="Select LineageOS 24 ROM ZIP",
            filetypes=[("ZIP Archives", "*.zip"), ("All Files", "*.*")]
        )
        if path:
            self.rom_entry.delete(0, "end")
            self.rom_entry.insert(0, path)
            self.app_state["lineage_zip_path"] = path
            self._save_state()
            self.log_message(f"[FILE] Selected LineageOS 24 ZIP: {path}")
            self._refresh_step1_badges()

    def _browse_gapps(self):
        path = filedialog.askopenfilename(
            title="Select NikGapps ZIP",
            filetypes=[("ZIP Archives", "*.zip"), ("All Files", "*.*")]
        )
        if path:
            self.gapps_entry.delete(0, "end")
            self.gapps_entry.insert(0, path)
            self.app_state["nikgapps_zip_path"] = path
            self._save_state()
            self.log_message(f"[FILE] Selected NikGapps ZIP: {path}")
            self._refresh_step1_badges()

    def _browse_vbmeta(self):
        path = filedialog.askopenfilename(
            title="Select Optional vbmeta.img",
            filetypes=[("VBMeta Image", "*.img"), ("All Files", "*.*")]
        )
        if path:
            self.vbmeta_entry.delete(0, "end")
            self.vbmeta_entry.insert(0, path)
            self.app_state["vbmeta_path"] = path
            self._save_state()
            self.log_message(f"[FILE] Selected Optional vbmeta.img: {path}")

    def _auto_detect_from_downloads(self):
        """Scans the user's Windows Downloads folder (and current workspace) for
        LineageOS a21s ZIP, recovery.img, NikGapps ZIP, and vbmeta.img."""
        search_dirs = [
            os.path.join(os.path.expanduser("~"), "Downloads"),
            self.base_dir,
        ]
        found_any = []

        for d in search_dirs:
            if not os.path.exists(d):
                continue
            try:
                files = sorted(
                    [os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))],
                    key=lambda x: os.path.getmtime(x),
                    reverse=True
                )
            except Exception:
                continue

            for fpath in files:
                fname = os.path.basename(fpath).lower()
                # 1. Recovery
                if not self.rec_entry.get().strip() and (
                    fname == "recovery.img" or ("recovery" in fname and fname.endswith((".img", ".tar"))) or ("twrp" in fname and "a21s" in fname)
                ):
                    self.rec_entry.delete(0, "end")
                    self.rec_entry.insert(0, fpath)
                    self.app_state["recovery_path"] = fpath
                    found_any.append(f"Recovery: {os.path.basename(fpath)}")

                # 2. LineageOS ZIP
                elif not self.rom_entry.get().strip() and fname.startswith("lineage-") and fname.endswith(".zip"):
                    self.rom_entry.delete(0, "end")
                    self.rom_entry.insert(0, fpath)
                    self.app_state["lineage_zip_path"] = fpath
                    found_any.append(f"LineageOS ROM: {os.path.basename(fpath)}")

                # 3. NikGapps ZIP
                elif not self.gapps_entry.get().strip() and ("nikgapps" in fname or "gapps" in fname) and fname.endswith(".zip"):
                    self.gapps_entry.delete(0, "end")
                    self.gapps_entry.insert(0, fpath)
                    self.app_state["nikgapps_zip_path"] = fpath
                    found_any.append(f"NikGapps: {os.path.basename(fpath)}")

                # 4. Optional vbmeta.img
                elif not self.vbmeta_entry.get().strip() and fname == "vbmeta.img":
                    self.vbmeta_entry.delete(0, "end")
                    self.vbmeta_entry.insert(0, fpath)
                    self.app_state["vbmeta_path"] = fpath
                    found_any.append(f"VBMeta: {os.path.basename(fpath)}")

        self._save_state()
        self._refresh_step1_badges()

        if found_any:
            summary = "\n• ".join(found_any)
            self.log_message(f"[AUTO-FIND] Found in Downloads: {', '.join(found_any)}")
            messagebox.showinfo("Files Auto-Detected!", f"Automatically found and filled:\n\n• {summary}")
        else:
            self.log_message("[AUTO-FIND] No matching files found in your Downloads folder yet.")
            messagebox.showinfo(
                "No Files Found Yet",
                "Could not find 'recovery.img', 'lineage-24.0-...-a21s-signed.zip', or 'NikGapps-...zip' in your Downloads folder yet.\n\n"
                "Use the blue buttons in Section B above to download them first!"
            )

    def _reboot_and_go_step3(self):
        def task():
            ok = self.device_mgr.reboot_to("download")
            if ok:
                self.after(0, lambda: self.select_step(2))
        self._run_async(task)

    def _on_only_build_tar_clicked(self):
        rec_path = self.rec_entry.get().strip()
        vb_path = self.vbmeta_entry.get().strip() or None
        if not rec_path or not os.path.exists(rec_path):
            messagebox.showwarning("Missing Recovery File", "Please select 'recovery.img' in Step 1 (Box #1) first.")
            self.select_step(0)
            return

        def task():
            ok, res = self.builder.build_odin_recovery_tar(rec_path, vb_path)
            if ok:
                self.set_progress(1.0, f"Built Odin package: {os.path.basename(res)}")
                self.flash_engine._reveal_in_explorer(res)
            else:
                self.set_progress(0.0, f"Failed to build .tar: {res}")
        self._run_async(task)

    def _copy_tar_path_to_clipboard(self):
        tar_path = os.path.join(self.builder.work_dir, "A217F_LineageRecovery_Odin.tar")
        self.clipboard_clear()
        self.clipboard_append(tar_path)
        self.update()
        self.log_message(f"[CLIPBOARD] Copied path: {tar_path}")
        messagebox.showinfo("Path Copied!", f"Copied to clipboard:\n{tar_path}\n\nNow click [AP] in Odin3 and press Ctrl+V!")

    def _on_flash_samloader_clicked(self):
        rec_path = self.rec_entry.get().strip()
        if not rec_path or not os.path.exists(rec_path):
            messagebox.showwarning("Missing Recovery File", "Please select 'recovery.img' in Step 1 (Box #1) first.")
            self.select_step(0)
            return

        def task():
            ok, msg = self.flash_engine.flash_recovery_download_mode(
                recovery_input_path=rec_path,
                method="samloader",
                progress_cb=self.set_progress
            )
            if ok:
                self.after(0, lambda: self.mark_step_completed(3))
        self._run_async(task)

    def _on_flash_recovery_clicked(self):
        rec_path = self.rec_entry.get().strip()
        vb_path = self.vbmeta_entry.get().strip() or None
        if not rec_path or not os.path.exists(rec_path):
            messagebox.showwarning("Missing Recovery File", "Please select 'recovery.img' in Step 1 (Box #1) first.")
            self.select_step(0)
            return

        def task():
            ok, msg = self.flash_engine.flash_recovery_download_mode(
                recovery_input_path=rec_path,
                vbmeta_input_path=vb_path,
                progress_cb=self.set_progress
            )
            if ok and os.path.exists(msg):
                def _copy_and_notify():
                    self.clipboard_clear()
                    self.clipboard_append(msg)
                    self.update()
                    self.mark_step_completed(3)
                self.after(0, _copy_and_notify)
            elif ok:
                self.after(0, lambda: self.mark_step_completed(3))
        self._run_async(task)

    def _on_patch_and_sideload_lineage_clicked(self):
        rom_path = self.rom_entry.get().strip()
        if not rom_path or not os.path.exists(rom_path):
            messagebox.showwarning("Missing LineageOS ZIP", "Please select your LineageOS 24 .zip file in Step 1 first.")
            self.select_step(0)
            return

        def task():
            patched_name = os.path.basename(rom_path).replace(".zip", "-BitA_Patched.zip")
            patched_path = os.path.join(self.builder.work_dir, patched_name)
            if not os.path.exists(patched_path):
                ok_p, res_p = self.builder.create_bootloader_bypass_rom_zip(rom_path, progress_cb=self.set_progress)
                if not ok_p:
                    return
                patched_path = res_p
            else:
                self.log_message(f"[INFO] Using existing Binary-A Patched ROM: {patched_path}")

            self.log_message("[IMPORTANT] Look at your phone screen when verification reaches ~47% — Tap 'Yes' on 'Signature verification failed — Install anyway?'!")
            ok, msg = self.flash_engine.sideload_package(
                zip_path=patched_path,
                label="LineageOS 24 (Binary-A Patched)",
                progress_cb=self.set_progress
            )
            if ok:
                self.after(0, lambda: self.mark_step_completed(4))
                if self.auto_advance_var.get():
                    self.after(1200, lambda: self.select_step(5))
        self._run_async(task)

    def _on_sideload_lineage_clicked(self):
        rom_path = self.rom_entry.get().strip()
        if not rom_path or not os.path.exists(rom_path):
            messagebox.showwarning("Missing LineageOS ZIP", "Please select your LineageOS 24 .zip file in Step 1 first.")
            self.select_step(0)
            return

        def task():
            ok, msg = self.flash_engine.sideload_package(
                zip_path=rom_path,
                label="LineageOS 24",
                progress_cb=self.set_progress
            )
            if ok:
                self.after(0, lambda: self.mark_step_completed(4))
                if self.auto_advance_var.get():
                    self.after(1200, lambda: self.select_step(5))
        self._run_async(task)

    def _on_sideload_gapps_clicked(self):
        gapps_path = self.gapps_entry.get().strip()
        if not gapps_path or not os.path.exists(gapps_path):
            messagebox.showwarning("Missing NikGapps ZIP", "Please select your NikGapps .zip file in Step 1 first.")
            self.select_step(0)
            return

        def task():
            ok, msg = self.flash_engine.sideload_package(
                zip_path=gapps_path,
                label="NikGapps",
                progress_cb=self.set_progress
            )
            if ok:
                self.after(0, lambda: self.mark_step_completed(5))
                self.after(0, lambda: messagebox.showinfo(
                    "Installation Complete!",
                    "LineageOS 24 + NikGapps have been sideloaded!\n\nTap 'Reboot system now' on your phone (or click the green Reboot button) to enjoy LineageOS 24!"
                ))
        self._run_async(task)

    # -------------------------------------------------------------------------
    # REAL-TIME BACKGROUND DEVICE POLLING & AUTO-STEP DETECTION
    # -------------------------------------------------------------------------
    def _poll_device_loop(self):
        if not self.polling_active:
            return

        def worker():
            status = self.device_mgr.check_device()
            self.after(0, lambda: self._update_ui_from_device_status(status))

        threading.Thread(target=worker, daemon=True).start()
        self.after(2500, self._poll_device_loop)

    def _update_ui_from_device_status(self, st: DeviceStatus):
        # 1. First, if a phone is connected in system or recovery mode, auto-match its Samsung profile
        matched_prof = None
        if st.mode in ("system", "recovery") and (st.model or st.device_codename):
            matched_prof = self.samsung_db.find_device(st.model, codename_hint=st.device_codename)
            if matched_prof and matched_prof.codename != self._last_auto_matched_codename:
                self._last_auto_matched_codename = matched_prof.codename
                self._set_active_profile(matched_prof)
                self.log_message(
                    f"[AUTO-DETECT] Connected Samsung {matched_prof.name} ({st.model} / {matched_prof.codename}) -> "
                    f"Max Supported: LineageOS {matched_prof.latest_lineage_version} ({matched_prof.latest_android_version})"
                )

        p = matched_prof or self.active_profile

        # 2. Update Top Telemetry Bar (dynamically showing detected or selected device name)
        if st.mode == "disconnected":
            self.conn_dot.configure(text="● DISCONNECTED", text_color="#EF4444")
            detail = st.raw_details or f"Plug in your Samsung {p.name} ({p.codename}) via USB cable"
            self.conn_details_lbl.configure(text=detail)
        elif st.mode == "unauthorized":
            self.conn_dot.configure(text="● UNAUTHORIZED (TAP ALLOW ON PHONE)", text_color="#F59E0B")
            self.conn_details_lbl.configure(text=f"Serial: {st.serial} — Check phone screen to allow USB debugging")
        elif st.mode == "system":
            bat = f" | 🔋 {st.battery_level}%" if st.battery_level >= 0 else ""
            self.conn_dot.configure(text="● ADB ONLINE (SYSTEM)", text_color="#10B981")
            dev_display = f"Samsung {p.name} ({st.model or p.codename})" if matched_prof else f"{st.model} ({st.device_codename})"
            self.conn_details_lbl.configure(
                text=f"{dev_display} | {st.oneui_version} | Bootloader: {st.bootloader_state.upper()}{bat}"
            )
        elif st.mode == "download":
            port_str = f" ({st.com_port})" if st.com_port else ""
            self.conn_dot.configure(text=f"● DOWNLOAD MODE{port_str}", text_color="#38BDF8")
            self.conn_details_lbl.configure(text=f"Samsung {p.name} ({p.codename}) — {st.raw_details} — Ready for Odin Flash!")
        elif st.mode == "recovery":
            self.conn_dot.configure(text="● RECOVERY MODE (ADB)", text_color="#A855F7")
            dev_label = st.model if (st.model and st.model != "Unknown") else f"Samsung {p.name} ({p.codename})"
            self.conn_details_lbl.configure(text=f"{dev_label} in Custom Recovery — Ready for Wipe / Sideload")
        elif st.mode == "sideload":
            self.conn_dot.configure(text="● ADB SIDELOAD READY", text_color="#10B981")
            self.conn_details_lbl.configure(
                text=f"Samsung {p.name} ({p.codename}) [{st.serial}] — Ready to stream LineageOS {p.latest_lineage_version} & NikGapps!"
            )

        # 3. Update Step 2 Pre-Flight Checklist Labels
        if st.mode in ("system", "recovery", "sideload", "download"):
            self.chk_usb_lbl.configure(
                text=f"✅ 1. USB Connection & Drivers: Connected in {st.mode.upper()} mode",
                text_color="#34D399"
            )

            if matched_prof or st.mode in ("download", "sideload"):
                self.chk_model_lbl.configure(
                    text=(
                        f"✅ 2. Device Target: Samsung {p.name} ({st.model or p.codename}) — "
                        f"Max Official Support: LineageOS {p.latest_lineage_version} ({p.latest_android_version})!"
                    ),
                    text_color="#34D399"
                )
            else:
                self.chk_model_lbl.configure(
                    text=f"ℹ️ 2. Device Model: Detected '{st.model}' ({st.device_codename}) — Using profile 'Samsung {p.name} ({p.codename})'",
                    text_color="#38BDF8"
                )

            bl_info = f" | Bootloader: {st.bootloader_version} (Bit {st.bootloader_binary_char})" if st.bootloader_version else ""
            req_ver = p.required_stock_android
            if req_ver and st.android_version == req_ver:
                self.chk_fw_lbl.configure(
                    text=f"✅ 3. Firmware Base: {st.oneui_version}{bl_info} — Matches required Android {req_ver} base for LineageOS {p.latest_lineage_version}!",
                    text_color="#34D399"
                )
            elif st.android_version:
                req_note = f" (LineageOS {p.latest_lineage_version} recommends Android {req_ver} base)" if req_ver else ""
                self.chk_fw_lbl.configure(
                    text=f"ℹ️ 3. Firmware Base: Android {st.android_version} ({st.oneui_version}){bl_info}{req_note}",
                    text_color="#38BDF8"
                )

            if st.bootloader_state == "unlocked":
                self.chk_bl_lbl.configure(
                    text="✅ 4. Bootloader Status: ALREADY UNLOCKED! (You can skip unlocking and go straight to Download Mode)",
                    text_color="#34D399"
                )
                self.step3_banner_lbl.configure(
                    text="✅ Bootloader is ALREADY UNLOCKED! Just enter Download Mode to flash Recovery.",
                    text_color="#34D399"
                )
                self.mark_step_completed(1)
            elif st.bootloader_state == "locked":
                self.chk_bl_lbl.configure(
                    text="🔒 4. Bootloader Status: LOCKED — Follow Step 3 to unlock in Download Mode",
                    text_color="#FBBF24"
                )
                self.step3_banner_lbl.configure(
                    text="🔒 Bootloader is currently LOCKED. Enter Download Mode below and hold Volume Up for 7s.",
                    text_color="#FBBF24"
                )
        elif st.mode == "unauthorized":
            self.chk_usb_lbl.configure(
                text="⚠️ 1. USB Connected, but waiting for 'Allow USB Debugging' prompt on your phone screen!",
                text_color="#FBBF24"
            )

        # 3. Update Step 5 Sideload Indicator & Smart Auto-Advance
        if st.mode == "sideload":
            self.step5_sideload_state_lbl.configure(
                text="✅ Phone is in ADB Sideload Mode! Click the blue button below to flash.",
                text_color="#34D399"
            )
        elif st.mode == "recovery":
            self.step5_sideload_state_lbl.configure(
                text="ℹ️ Phone detected in Recovery Mode. On phone, tap 'Apply update' -> 'Apply from ADB'.",
                text_color="#38BDF8"
            )
        else:
            self.step5_sideload_state_lbl.configure(
                text="⏳ Waiting for phone to enter Recovery / ADB Sideload mode...",
                text_color="#FBBF24"
            )

        # Smart Auto-Advance when user plugs phone in a specific mode
        if self.auto_advance_var.get():
            if st.mode == "download" and self.current_step_idx in (1, 2):
                self.mark_step_completed(2)
                self.select_step(3)  # Jump directly to Step 4: Flash Recovery
            elif st.mode in ("recovery", "sideload") and self.current_step_idx in (1, 2, 3):
                self.mark_step_completed(2)
                self.mark_step_completed(3)
                self.select_step(4)  # Jump directly to Step 5: Sideload LineageOS 24


if __name__ == "__main__":
    app = LineageA21sInstallerApp()
    app.mainloop()

