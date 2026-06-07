import sys
import os
# ====== 【Core code for fixing OMP conflicts】 ======
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# =======================================
import json
import time
import shutil
import ctypes
import subprocess
import web browser
# ====== 【New】: Enable pre-processing environment detection (anti-crash mechanism) ======
def check_windows_dependencies():
    if sys.platform != "win32":
        return
    missing_dlls = []
    Image recognition libraries such as OpenCV (cv2) heavily rely on Microsoft VC++ 2015-2022 runtime libraries.
    required_dlls = ["vcruntime140.dll", "msvcp140.dll", "vcruntime140_1.dll"]
    
    for dll in required_dlls:
        try:
            # Attempt to silently load the runtime library; if it is not present in the system, an OSError will be triggered.
            ctypes.WinDLL(dll)
        except OSError:
            missing_dlls.append(dll)
            
    if missing_dlls:
        msg = (
            Warning: The following critical runtime libraries are missing from your system, which will likely cause the program to crash or image recognition to fail:\n\n
            f"{', '.join(missing_dlls)}\n\n"
            This is because your computer lacks the Microsoft C++ runtime environment.
            Please search and download either "Microsoft Common Runtime Libraries Collection" or "VC++ 2015-2022" and try again after installation.
            Click "OK" to force continue running (if it crashes, please install the runtime library).
        )
        # 0x30 = MB_ICONWARNING (yellow warning icon), 0x0 = MB_OK (OK button only)
        ctypes.windll.user32.MessageBoxW(0, msg, "Missing runtime library interception message", 0x30 | 0x0)
# Perform interception and detection immediately before importing large, performance-intensive modules.
check_windows_dependencies()
# ===================================================
# [Extremely Critical]: DPI awareness must be set before importing any UI library.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Win 8.1+
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Win Vista+
    except Exception:
        pass

import customtkinter as ctk
ctk.deactivate_automatic_dpi_awareness()
ctk.set_widget_scaling(1.0)
ctk.set_window_scaling(1.0)
import cv2
import numpy as np
import pyautogui
import pydirectinput
import requests
from pynput import keyboard
from PIL import Image, ImageGrab
import win32gui
import pickle
import threading



# ==========================================
# --- Path and Resource Strategy ---
# assets: Read-only internal, local overwrite prohibited
# images: Packaged into the exe file, automatically released if no external images are found upon startup; image recognition prioritizes reading external images.
# ==========================================
def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_internal_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return get_app_dir()


APP_DIR = get_app_dir()
INTERNAL_DIR = get_internal_dir()
# Add config directory path
CONFIG_DIR = os.path.join(APP_DIR, "config")
USER_CONFIG_FILE = os.path.join(APP_DIR, "config.json") # <--- Replace all with config.json
LOG_FILE = os.path.join(APP_DIR, "bot_log.txt")
CACHE_DIR = os.path.join(APP_DIR, "cache")
TEMPLATE_CACHE_FILE = os.path.join(CACHE_DIR, "template_cache.pkl")
TEMPLATE_META_FILE = os.path.join(CACHE_DIR, "template_meta.json")
CURRENT_VERSION = "1.1.6.3"
def auto_extract_configs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # Backward compatibility, automatically rename and migrate old versions of bot_config
    old_configs = [
        os.path.join(APP_DIR, "bot_config.json"),
        os.path.join(APP_DIR, "bot-config.json"),
        os.path.join(CONFIG_DIR, "bot-config.json"),
        os.path.join(CONFIG_DIR, "bot_config.json"),
        os.path.join(CONFIG_DIR, "config.json")
    ]
    for old_path in old_configs:
        if os.path.exists(old_path):
            try:
                if not os.path.exists(USER_CONFIG_FILE):
                    shutil.move(old_path, USER_CONFIG_FILE)
                else:
                    os.remove(old_path)
            except Exception:
                pass
def auto_extract_images(folder_name="images"):
    internal_dir = os.path.join(INTERNAL_DIR, folder_name)
    external_dir = os.path.join(APP_DIR, folder_name)

    if not os.path.isdir(internal_dir):
        print(f"[auto_extract_images] Internal directory does not exist: {internal_dir}")
        return

    try:
        os.makedirs(external_dir, exist_ok=True)

        for root, dirs, files in os.walk(internal_dir):
            rel_path = os.path.relpath(root, internal_dir)
            target_root = external_dir if rel_path == "." else os.path.join(external_dir, rel_path)
            os.makedirs(target_root, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(target_root, file)

                # Only release if it does not exist externally, retaining user-defined replacements.
                if not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)

    except Exception as e:
        print(f"[auto_extract_images] failed to extract images: {e}")


def get_img_path(filename):
    basename = os.path.basename(filename)

    # Prioritize reading images outside the program directory (allows users to replace them).
    ext_path = os.path.join(APP_DIR, "images", basename)
    if os.path.exists(ext_path):
        return ext_path

    # If no external images are found, read the built-in images.
    int_path = os.path.join(INTERNAL_DIR, "images", basename)
    if os.path.exists(int_path):
        return int_path

    return filename


def get_asset_path(*parts):
    """
    assets can only read built-in resources:
    - Packaged as: _MEIPASS/assets
    - Development environment: Project directory/assets
    """
    asset_path = os.path.join(INTERNAL_DIR, "assets", *parts)
    if os.path.exists(asset_path):
        return asset_path

    dev_asset_path = os.path.join(get_app_dir(), "assets", *parts)
    if os.path.exists(dev_asset_path):
        return dev_asset_path

    return None


def parse_version(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return (0, 0, 0)

# ==========================================
# --- Ctypes Hardware-Level Keyboard Simulation Structure Definition ---
# ==========================================
SendInput = ctypes.windll.user32.SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I),
    ]


# --- Hardware Scan Codes (Contains numbers 0-9) ---
THICK_CODES = {
    # control
    "esc": (0x01, False),
    "enter": (0x1C, False),
    "space": (0x39, False),
    "backspace": (0x0E, False),
    "tab": (0x0F, False),
    "lshift": (0x2A, False),
    "rshift": (0x36, False),
    "lctrl": (0x1D, False),
    "rctrl": (0x1D, True),
    "other": (0x38, False),
    "ralt": (0x38, True),
    "capslock": (0x3A, False),

    # letters
    "a": (0x1E, False),
    "b": (0x30, False),
    "c": (0x2E, False),
    "d": (0x20, False),
    "e": (0x12, False),
    "f": (0x21, False),
    "g": (0x22, False),
    "h": (0x23, False),
    "i": (0x17, False),
    "j": (0x24, False),
    "k": (0x25, False),
    "l": (0x26, False),
    "m": (0x32, False),
    "n": (0x31, False),
    "o": (0x18, False),
    "p": (0x19, False),
    "q": (0x10, False),
    "r": (0x13, False),
    "s": (0x1F, False),
    "t": (0x14, False),
    "u": (0x16, False),
    "v": (0x2F, False),
    "in": (0x11, False),
    "x": (0x2D, False),
    "y": (0x15, False),
    "z": (0x2C, False),

    # number row
    "1": (0x02, False),
    "2": (0x03, False),
    "3": (0x04, False),
    "4": (0x05, False),
    "5": (0x06, False),
    "6": (0x07, False),
    "7": (0x08, False),
    "8": (0x09, False),
    "9": (0x0A, False),
    "0": (0x0B, False),

    # arrows / navigation
    "up": (0xC8, True),
    "down": (0xD0, True),
    "left": (0xCB, True),
    "right": (0xCD, True),
    "pageup": (0xC9, True),
    "pagedown": (0xD1, True),
    "home": (0xC7, True),
    "end": (0xCF, True),
    "insert": (0xD2, True),
    "delete": (0xD3, True),

    # function keys
    "f1": (0x3B, False),
    "f2": (0x3C, False),
    "f3": (0x3D, False),
    "f4": (0x3E, False),
    "f5": (0x3F, False),
    "f6": (0x40, False),
    "f7": (0x41, False),
    "f8": (0x42, False),
    "f9": (0x43, False),
    "f10": (0x44, False),
    "f11": (0x57, False),
    "f12": (0x58, False),
}

# --- Global Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
MATCH_THRESHOLD = 0.8
pyautogui.FAILSAFE = False


class FH_UltimateBot(ctk.CTk):
    def __init__(self):
        super().__init__()
        #Window Related
        self.title(f"FH6Auto by YSTO v{CURRENT_VERSION}")
        self.geometry("1800x800")
        #self.minsize(980, 560)
        self.attributes("-topmost", False)
        self.attributes("-alpha", 0.98)
        self.resizable(False, False)

        try:
            icon_path = get_asset_path("icon.ico")
            if icon_path:
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self.is_running = False
        self.current_thread = None
        self.is_paused = False # <--- [Added] Global pause state

        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.sc_count = 0
        self.global_loop_current = 0

        self.template_cache = {}
        self.scaled_template_cache = {}
        self.file_template_cache = {}
        self.last_positions = {}
        self.support_win = None
        self.edge_template_cache = {}
        self.scaled_edge_template_cache = {}

        self.init_regions()
        
        # [Optimize loading speed]: Move IO extraction and image cache loading/generation to a background thread to avoid blocking the main interface startup.
        # Add model release steps
        def background_init():
            auto_extract_images()
            
            self.prepare_template_cache()
            #self.use_ocr = self.config.get("use_ocr", True)
            #if self.use_ocr:
            #    self.init_ocr_engine()
        threading.Thread(target=background_init, daemon=True).start()
        
        # Load configuration file
        auto_extract_configs()  
        self.load_config()

        self.setup_ui()
        self.start_hotkey_listener()
        self.update_skill_grid()
        self.center_window()
        
        self.log("Disclaimer: This script is for Python automation technology exchange and learning purposes only. Do not use it for commercial profit or to disrupt game balance. Users are solely responsible for any account bans or other losses resulting from the use of this script.")
        self.log("The directory where the tool is running should not contain Chinese characters")
        self.log("Default vehicle for farming: Subaru Impreza 22B-STi Version, tuned S2 900, keeps default paint job, favorite vehicle]")
        self.log("Set the keyboard to English before starting up")
        self.log("Game settings are set to [Auto Steering] [Automatic Transmission], game language is set to [Simplified Chinese]")
        self.log("Most of the data is guided by image recognition to reduce the risk of blind machine operation, but it cannot be completely avoided. Please be prepared before use.")

    # ==========================================
    # --- UI Security Scheduling ---
    # ==========================================
    def ui_call(self, func, *args, **kwargs):
        try:
            self.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        gx, gy, gw, gh = self.regions["All Interfaces"]
        x = gx + (gw - w) // 2
        y = gy + (gh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
    def sync_buy_to_sell(self, event=None):
        try:
            val = "".join(c for c in self.entry_car.get() if c.isdigit())
            if val == "":
                val = "0"
            self.entry_sc.delete(0, "end")
            self.entry_sc.insert(0, val)
        except Exception:
            pass

    def normalize_step_entry(self, entry_widget, default_value):
        try:
            v = "".join(c for c in entry_widget.get() if c.isdigit())
            if v == "":
                v = str(default_value)
            iv = int(v)
            if iv < 1:
                iv = 1
            if iv > 4:
                iv = 4
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(iv))
        except Exception:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(default_value))
    # ==========================================
    # --- Initialize global Region ---
    # ==========================================
    def init_regions(self):
        sw, sh = pyautogui.size()
        self.update_regions_by_window(0, 0, sw, sh)

    def update_regions_by_window(self, x, y, w, h):
        self.regions = {
            "Total interface": (x, y, w, h)
            "Top left": (x, y, w // 2, h // 2),
            "Top right": (x + w // 2, y, w // 2, h // 2),
            "Bottom Left": (x, y + h // 2, w // 2, h // 2),
            "Bottom right": (x + w // 2, y + h // 2, w // 2, h // 2),
            "上": (x, y, w, h // 2),
            "下": (x, y + h // 2, w, h // 2),
            "Left": (x, y, w // 2, h),
            "右": (x + w // 2, y, w // 2, h),
            "中间": (x + w // 4, y + h // 4, w // 2, h // 2),
        }

    # ==========================================
    # --- Configuration Management ---
    # ==========================================
    def load_config(self):
        # 1. Use the built-in dictionary directly as the "absolute base text" (safest, ignores the problem of missing files during packaging)
        self.config = {
            "race_count": 99,
            "buy_count": 30, 
            "cj_count": 30, 
            "sc_count": 30,
            "chk_1": True, 
            "chk_2": True, 
            "chk_3": True, 
            "chk_4": True,
            "next_1": 2, 
            "next_2": 3, 
            "next_3": 1, 
            "next_4": 1,
            "global_loops": 10, 
            "skill_dirs": ["right", "up", "up", "up", "left"],
            "share_code": "890169683", 
            "auto_restart": False,
            "restart_cmd": "start steam://run/2483190", 
            "sell_mode": 1 
        }
        ext_path = USER_CONFIG_FILE
        # 2. Read the user's config.json and merge it with the original file (automatically complete missing items).
        if os.path.exists(ext_path):
            try:
                with open(ext_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                    self.config.update(user_config) 
            except Exception as e:
                self.log(f"User's config.json is corrupted; default configuration has been automatically restored.")
                
        # 3. Rewrite the latest and most complete configuration back to the external file.
        try:
            with open(ext_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass
    

    def save_config(self):
        try:
            self.config["race_count"] = int(self.entry_race.get())
            self.config["buy_count"] = int(self.entry_car.get())
            self.config["cj_count"] = int(self.entry_cj.get())
            self.config["sc_count"] = int(self.entry_sc.get())
            self.config["global_loops"] = int(self.entry_global_loop.get())
            self.config["share_code"] = "".join(c for c in self.entry_share.get() if c.isdigit())
            #self.config["base_width"] = int(self.entry_base_w.get())
            self.config["next_1"] = int(self.entry_next1.get())
            self.config["next_2"] = int(self.entry_next2.get())
            self.config["next_3"] = int(self.entry_next3.get())
            self.config["next_4"] = int(self.entry_next4.get())
            if hasattr(self, "opt_sell_mode"):
                val = self.opt_sell_mode.get()
                if "mode1" in val:
                    self.config["sell_mode"] = 1
                else:
                    self.config["sell_mode"] = 2
        except Exception:
            pass

        self.config["chk_1"] = self.var_chk1.get()
        self.config["chk_2"] = self.var_chk2.get()
        self.config["chk_3"] = self.var_chk3.get()
        self.config["chk_4"] = self.var_chk4.get()
        self.config["auto_restart"] = self.var_auto_restart.get()
        self.config["restart_cmd"] = self.le_restart_cmd.get().strip()
        try:
            if hasattr(self, "entry_calc_a"):
                self.config["calc_a"] = self.entry_calc_a.get().strip()
                self.config["calc_b"] = self.entry_calc_b.get().strip()
                self.config["calc_c"] = self.entry_calc_c.get().strip()
        except Exception:
            pass
        try:
            with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log(f"Failed to save configuration: {e}")

    def auto_calculate_pipeline(self):
        val_a = self.entry_calc_a.get().strip()
        if not val_a:
            self.log("CR was not entered, no calculation required.")
            return
            
        try:
            target_cr = int(val_a)
            val_b = self.entry_calc_b.get().strip()
            cost_per_car = int(val_b) if val_b else 81700
            
            val_c = self.entry_calc_c.get().strip()
            sp_per_car = int(val_c) if val_c else 30
        except Exception:
            self.log("Incorrect input format. Please ensure you only enter numbers!")
            return

        if cost_per_car <= 0 or sp_per_car <= 0:
            self.log("Bicycle cost or skill points cannot be 0!")
            return

        # 1. Basic Conversion (Total Number of Vehicles & Total Number of Map Runs)
        total_cars = target_cr // cost_per_car
        total_races = (total_cars * sp_per_car) // 10

        if total_races <= 0:
            self.log("Insufficient target amount (only enough to buy {total_cars} cars), unable to generate a valid map run!")
            return

        # 2. Core Allocation Logic
        if total_races <= 99:
            final_loops = 1
            final_races_per_loop = total_races
        else:
            import math
            loops = math.ceil(total_races / 99)
            avg_races = total_races // loops

            # If the average number of trials is greater than or equal to 70, then use the equal distribution strategy.
            if avg_races >= 70:
                final_loops = loops
                final_races_per_loop = avg_races
            # If the number of iterations is less than 70, directly maximize each round to 99, discarding any remainders that are not enough to fill a full round.
            else:
                final_races_per_loop = 99
                final_loops = total_races // 99 

        #3. Calculate the specific number of cars purchased, drawn, and sold in each round.
        cars_per_loop = (final_races_per_loop * 10) // sp_per_car

        if final_loops <= 0:
            self.log("After calculation, the number of available loop iterations is 0.")
            return

        # 4. Automatically fill in the information on the interface
        self.entry_race.delete(0, "end")
        self.entry_race.insert(0, str(final_races_per_loop))
        
        self.entry_car.delete(0, "end")
        self.entry_car.insert(0, str(cars_per_loop))
        
        self.entry_cj.delete(0, "end")
        self.entry_cj.insert(0, str(cars_per_loop))
        
        self.entry_sc.delete(0, "end")
        self.entry_sc.insert(0, str(cars_per_loop))
        
        self.entry_global_loop.delete(0, "end")
        self.entry_global_loop.insert(0, str(final_loops))

        self.log(f"✅Calculation complete: A total of {total_cars} cars are needed, and the map is run {total_races} times. The allocation is: {final_loops} large loops, with each loop running {final_races_per_loop} times, and {cars_per_loop} actions.")
        self.save_config()

    # ==========================================
    # --- UI Layout Design ---
    # ==========================================
    def setup_ui(self):
        self.top_container = ctk.CTkFrame(self, fg_color="transparent")
        self.top_container.pack(fill="x", padx=18, pady=(18, 10))

        self.config_frame = ctk.CTkFrame(self.top_container, fg_color="transparent")
        self.config_frame.pack(fill="x")

        def create_box(parent, title, btn_text, btn_cmd, btn_color, def_val):
            frame = ctk.CTkFrame(
                parent,
                width=210,
                height=300,
                corner_radius=12,
                border_width=1,
                border_color="#2B2B2B",
            )
            frame.pack_propagate(False)
            frame.pack(side="left", padx=8)

            ctk.CTkLabel(
                frame,
                text=title,
                font=ctk.CTkFont(weight="bold", size=20),
            ).pack(pady=(14, 10))

            btn = ctk.CTkButton(
                frame,
                text=btn_text,
                fg_color=btn_color,
                hover_color=btn_color,
                command=btn_cmd,
                width=140,
                height=38,
                corner_radius=10,
            )
            btn.pack(pady=8, padx=10)

            entry = ctk.CTkEntry(frame, width=95, height=34, justify="center", corner_radius=8)
            entry.insert(0, str(def_val))
            entry.pack(pady=8)

            lbl = ctk.CTkLabel(
                frame,
                text=f"Execution: 0 / {def_val}",
                text_color="#A0A0A0",
                font=ctk.CTkFont(size=16),
            )
            lbl.pack(pady=8)
            return frame, btn, entry, lbl

        def create_next_step(parent, var_checked, def_step, box_h=300):
            frame = ctk.CTkFrame(parent, width=120, height=box_h, corner_radius=12, border_width=1, border_color="#2B2B2B")
            frame.pack(side="left", padx=4)
            frame.pack_propagate(False)

            ctk.CTkLabel(
                frame,
                text="Next Step",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color="#5DADE2",
            ).pack(pady=(55, 10))

            entry = ctk.CTkEntry(frame, width=60, height=34, justify="center", corner_radius=8)
            entry.insert(0, str(def_step))
            entry.pack(pady=6)

            chk = ctk.CTkCheckBox(frame, text="继续", variable=var_checked, width=60)
            chk.pack(pady=8)

            return frame, entry, chk

        self.var_chk1 = ctk.BooleanVar(value=self.config["chk_1"])
        self.var_chk2 = ctk.BooleanVar(value=self.config["chk_2"])
        self.var_chk3 = ctk.BooleanVar(value=self.config["chk_3"])
        self.var_chk4 = ctk.BooleanVar(value=self.config.get("chk_4", True))

        box_race, self.btn_race, self.entry_race, self.lbl_race = create_box(
            self.config_frame,
            1. Loop through the map,
            "start",
            lambda: self.start_pipeline("race"),
            "#1F6AA5",
            self.config.get("race_count", 99),
        )
        self.entry_share = ctk.CTkEntry(box_race, width=130, justify="center", placeholder_text="Blueprint Numeric Code")
        self.entry_share.insert(0, self.config.get("share_code", "890169683"))
        self.entry_share.pack(pady=4)

        self.next_frame1, self.entry_next1, self.chk1 = create_next_step(
            self.config_frame, self.var_chk1, self.config.get("next_1", 2)
        )

        box_car, self.btn_car, self.entry_car, self.lbl_car = create_box(
            self.config_frame,
            2. Bulk car purchases
            "start",
            lambda: self.start_pipeline("buy"),
            "#2EA043",
            self.config.get("buy_count", 30),
        )
        self.entry_car.bind("<KeyRelease>", self.sync_buy_to_sell)

        self.next_frame2, self.entry_next2, self.chk2 = create_next_step(
            self.config_frame, self.var_chk2, self.config.get("next_2", 3)
        )

        self.box_cj = ctk.CTkFrame(
            self.config_frame,
            width=360,
            height=300,
            corner_radius=12,
            border_width=1,
            border_color="#2B2B2B",
        )
        self.box_cj.pack_propagate(False)
        self.box_cj.pack(side="left", padx=8)

        top_cj = ctk.CTkFrame(self.box_cj, fg_color="transparent")
        top_cj.pack(fill="x", pady=10)

        left_cj = ctk.CTkFrame(top_cj, fg_color="transparent")
        left_cj.pack(side="left", padx=10)

        ctk.CTkLabel(left_cj, text="3. Super Lottery", font=ctk.CTkFont(weight="bold", size=20)).pack(pady=(0, 8))

        self.btn_cj = ctk.CTkButton(
            left_cj,
            text="Start",
            width=120,
            height=38,
            corner_radius=10,
            fg_color="#8E44AD",
            hover_color="#8E44AD",
            command=lambda: self.start_pipeline("cj"),
        )
        self.btn_cj.pack(pady=5)

        self.entry_cj = ctk.CTkEntry(left_cj, width=95, height=34, justify="center", corner_radius=8)
        self.entry_cj.insert(0, str(self.config.get("cj_count", 30)))
        self.entry_cj.pack(pady=5)

        self.lbl_cj = ctk.CTkLabel(
            left_cj,
            text=f"执行: 0 / {self.config.get('cj_count', 30)}",
            text_color="#A0A0A0",
            font=ctk.CTkFont(size=14),
        )
        self.lbl_cj.pack(pady=(2, 8))

        dir_frame = ctk.CTkFrame(left_cj, fg_color="transparent")
        dir_frame.pack(pady=4)

        for text, val in [("↑", "up"), ("↓", "down"), ("←", "left"), ("→", "right")]:
            ctk.CTkButton(
                dir_frame,
                text=text,
                width=30,
                height=28,
                corner_radius=8,
                command=lambda x=val: self.add_skill_dir(x),
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            left_cj,
            text="Clear Matrix",
            width=90,
            height=28,
            corner_radius=8,
            fg_color="#C0392B",
            hover_color="#A93226",
            command=self.clear_skill_dir,
        ).pack(pady=8)

        self.grid_frame = ctk.CTkFrame(top_cj, fg_color="transparent")
        self.grid_frame.pack(side="right", padx=12)

        self.grid_labels = [[None] * 4 for _ in range(4)]
        for r in range(4):
            for c in range(4):
                lbl = ctk.CTkLabel(
                    self.grid_frame,
                    text="",
                    width=28,
                    height=28,
                    corner_radius=5,
                    fg_color="#444444",
                )
                lbl.grid(row=r, column=c, padx=4, pady=4)
                self.grid_labels[r][c] = lbl
        ctk.CTkLabel(
            self.grid_frame,
            text="Skill Tree",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#A0A0A0",
        ).grid(row=4, column=0, columnspan=4, pady=(8, 0))

        self.next_frame3, self.entry_next3, self.chk3 = create_next_step(
            self.config_frame, self.var_chk3, self.config.get("next_3", 4)
        )

        box_sc, self.btn_sc, self.entry_sc, self.lbl_sc = create_box(
            self.config_frame,
            4. Remove the vehicle.
            "!!start!!",
            lambda: self.start_pipeline("sell"),
            "#D97706",
            self.config.get("sc_count", 30),
        )
        # ====== 【New Feature】: Removed Vehicle Mode Drop-down Selection ======
        self.opt_sell_mode = ctk.CTkOptionMenu(
            box_sc,
            values=["Mode 1: Image Removal Mode", "Mode 2: Remove Recently Added"],
            width=180,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color="#D97706",
            button_color="#B96705",
            button_hover_color="#995704"
        )
        # Read configuration, default selection is mode 1
        saved_mode = self.config.get("sell_mode", 1)
        if str(saved_mode) == "1" or "模式1" in str(saved_mode):
            self.opt_sell_mode.set("Mode 1: Image Removal Mode")
        else:
            self.opt_sell_mode.set("Mode 2: Remove Recently Added")
            
        self.opt_sell_mode.pack(pady=4)
        # ==========================================
        self.next_frame4, self.entry_next4, self.chk4 = create_next_step(
        self.config_frame, self.var_chk4, self.config.get("next_4", 1)
        )
        # ====== Move the global settings bar from the bottom (to the top) ======
        # [Modification 1] Changed self.top_container to self
        self.global_settings_frame = ctk.CTkFrame(self, fg_color="#2B2B2B", height=45, corner_radius=10)
        # [Modification 2] Added padx=18 to align it with the top and bottom edges.
        self.global_settings_frame.pack(fill="x", padx=18, pady=(15, 0))
        self.global_settings_frame.pack_propagate(False)
        ctk.CTkLabel(
            self.global_settings_frame, 
            text="⚙️ Loop and Guardian Settings",
            font=ctk.CTkFont(weight="bold", size=15), 
            text_color="#F1C40F"
        ).pack(side="left", padx=(15, 20))
        ctk.CTkLabel(self.global_settings_frame, text="Number of large loops:").pack(side="left", padx=(10, 5))
        self.entry_global_loop = ctk.CTkEntry(self.global_settings_frame, width=70, height=28, justify="center")
        self.entry_global_loop.insert(0, str(self.config.get("global_loops", 10)))
        self.entry_global_loop.pack(side="left", padx=(0, 20))
        self.var_auto_restart = ctk.BooleanVar(value=self.config.get("auto_restart", True))
        self.cb_auto_restart = ctk.CTkCheckBox(self.global_settings_frame, text="Game crashes (VRAM overflow) and automatically restarts", variable=self.var_auto_restart)
        self.cb_auto_restart.pack(side="left", padx=(10, 20))
        ctk.CTkLabel(self.global_settings_frame, text="Startup Command (CMD):").pack(side="left", padx=(10, 5))
        self.le_restart_cmd = ctk.CTkEntry(self.global_settings_frame, width=250, height=28)
        self.le_restart_cmd.insert(0, self.config.get("restart_cmd", "start steam://run/2483190"))
        self.le_restart_cmd.pack(side="left", padx=(0, 20))
        # ====== 【New Feature】: Test Automatic Power-On Process Button ======
        self.btn_test_boot = ctk.CTkButton(
            self.global_settings_frame, 
            text="Test Startup Process",
            fg_color="#8E44AD", 
            hover_color="#7D3C98", 
            width=110, 
            height=28, 
            command=self.start_test_boot
        )
        #self.btn_test_boot.pack(side="left", padx=(0, 20))
        
        # =================================


        # ====== New Addition: Smart Calculation Allocation Toolbar (located at the bottom) ======
        # [Modification 1] Changed self.top_container to self
        self.calc_frame = ctk.CTkFrame(self, fg_color="#2B2B2B", height=45, corner_radius=10)
        # [Modification 2] Added padx=18 to align it with the top and bottom edges.
        self.calc_frame.pack(fill="x", padx=18, pady=(10, 0))
        self.calc_frame.pack_propagate(False)
        ctk.CTkLabel(
            self.calc_frame, 
            text="count calculator",
            font=ctk.CTkFont(weight="bold", size=15), 
            text_color="#2EA043"
        ).pack(side="left", padx=(15, 20))
        ctk.CTkLabel(self.calc_frame, text="CR:").pack(side="left", padx=(0, 5))
        self.entry_calc_a = ctk.CTkEntry(self.calc_frame, width=110, height=28, placeholder_text="Leave blank and do not calculate")
        self.entry_calc_a.insert(0, self.config.get("calc_a", ""))
        self.entry_calc_a.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(self.calc_frame, text="Cost per vehicle (CR):").pack(side="left", padx=(0, 5))
        self.entry_calc_b = ctk.CTkEntry(self.calc_frame, width=70, height=28)
        self.entry_calc_b.insert(0, self.config.get("calc_b", "81700"))
        self.entry_calc_b.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(self.calc_frame, text="Bicycle Skill Points:").pack(side="left", padx=(0, 5))
        self.entry_calc_c = ctk.CTkEntry(self.calc_frame, width=50, height=28)
        self.entry_calc_c.insert(0, self.config.get("calc_c", "30"))
        self.entry_calc_c.pack(side="left", padx=(0, 15))
        ctk.CTkButton(
            self.calc_frame,
            text="Calculate and apply",
            width=90,
            height=28,
            fg_color="#D35400",
            hover_color="#A04000",
            command=self.auto_calculate_pipeline
        ).pack(side="left", padx=(0, 15))
        
        # Dynamically limit the length of the input field (allow only numbers and truncate them)
        def limit_len(evt, widget, max_l):
            val = "".join(c for c in widget.get() if c.isdigit())
            if len(val) > max_l:
                val = val[:max_l]
            if widget.get() != val:
                widget.delete(0, "end")
                widget.insert(0, val)
        self.entry_calc_a.bind("<KeyRelease>", lambda e: limit_len(e, self.entry_calc_a, 10))
        self.entry_calc_b.bind("<KeyRelease>", lambda e: limit_len(e, self.entry_calc_b, 7))
        self.entry_calc_c.bind("<KeyRelease>", lambda e: limit_len(e, self.entry_calc_c, 2))
        # ==========================================
        #ctk.CTkLabel(self.global_settings_frame, text="Original image width (do not modify):").pack(side="left", padx=(10, 5))
        #self.entry_base_w = ctk.CTkEntry(self.global_settings_frame, width=70, height=28, justify="center")
        #self.entry_base_w.insert(0, str(self.config.get("base_width", 2560)))
        #self.entry_base_w.pack(side="left", padx=(0, 20))

        self.entry_next1.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next1, 2))
        self.entry_next2.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next2, 3))
        self.entry_next3.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next3, 4))
        self.entry_next4.bind("<FocusOut>", lambda e: self.normalize_step_entry(self.entry_next4, 1))

        if not self.entry_sc.get().strip():
            self.entry_sc.insert(0, "30")

        # === A Brand New Horizontal Mini UI Design ===
        self.mini_frame = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=10)

        # 1. Log section (far left, occupies the main resizing space)
        self.mini_log_box = ctk.CTkTextbox(self.mini_frame, state="disabled", wrap="word", font=ctk.CTkFont(size=13), fg_color="#2B2B2B")
        self.mini_log_box.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)

        # 2. Information Area (task status and time consumption arranged vertically)
        self.mini_info_frame = ctk.CTkFrame(self.mini_frame, fg_color="transparent")
        self.mini_info_frame.pack(side="left", fill="y", padx=5, pady=10)

        self.lbl_mini_task = ctk.CTkLabel(self.mini_info_frame, text="Current task: Waiting", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498DB")
        self.lbl_mini_task.pack(pady=(5, 2), anchor="w")

        self.lbl_mini_prog = ctk.CTkLabel(self.mini_info_frame, text="Task progress: 0 / 0", font=ctk.CTkFont(size=13))
        self.lbl_mini_prog.pack(pady=2, anchor="w")

        self.lbl_mini_loop = ctk.CTkLabel(self.mini_info_frame, text="大循环: 0 / 0", font=ctk.CTkFont(size=13))
        self.lbl_mini_loop.pack(pady=2, anchor="w")

        self.lbl_mini_time = ctk.CTkLabel(self.mini_info_frame, text="总耗时: 00:00:00", font=ctk.CTkFont(size=13))
        self.lbl_mini_time.pack(pady=2, anchor="w")
        # 3. Button area (arranged on the right)
        self.btn_mini_stop = ctk.CTkButton(self.mini_frame, text="⏸ 停止 (F8)", fg_color="#DA3633", hover_color="#B02A37", width=90, font=ctk.CTkFont(weight="bold"), command=self.stop_all)
        self.btn_mini_stop.pack(side="left", fill="y", padx=5, pady=10)

        # ====== 【New Feature】Pause button on the mini panel======
        self.btn_mini_pause = ctk.CTkButton(self.mini_frame, text="⏸ 暂停 (F9)", fg_color="#F1C40F", hover_color="#D4AC0D", width=90, font=ctk.CTkFont(weight="bold"), command=self.toggle_pause)
        self.btn_mini_pause.pack(side="left", fill="y", padx=5, pady=10)

        self.btn_mini_support = ctk.CTkButton(self.mini_frame, text="❤ 支持", fg_color="#F97316", hover_color="#EA580C", width=60, font=ctk.CTkFont(weight="bold"), command=self.open_support_window)
        self.btn_mini_support.pack(side="left", fill="y", padx=(5, 10), pady=10)


        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent", height=200)
        self.bottom_frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))

        self.btn_stop = ctk.CTkButton(
            self.bottom_frame,
            text="⏸ Waiting for command (F8)",
            fg_color="#3A3A3A",
            hover_color="#4A4A4A",
            width=180,
            height=60,
            corner_radius=12,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.stop_all,
        )
        self.btn_stop.pack(side="left", padx=6)

        self.log_box = ctk.CTkTextbox(
            self.bottom_frame,
            state="disabled",
            wrap="word",
            corner_radius=12,
            height=120,
            font=ctk.CTkFont(size=18),
        )
        self.log_box.pack(side="left", fill="both", expand=True, padx=8)

        self.btn_support = ctk.CTkButton(
            self,
            text="❤ Support the author / Check for updates",
            fg_color="#F97316",
            hover_color="#EA580C",
            height=42,
            corner_radius=12,
            font=ctk.CTkFont(weight="bold", size=15),
            command=self.open_support_window,
        )
        self.btn_support.pack(fill="x", padx=18, pady=(6, 12))
        self.sync_buy_to_sell()

        #ocr loading
    
    def open_support_window(self):
        if self.support_win is not None and self.support_win.winfo_exists():
            self.support_win.focus()
            return

        self.support_win = ctk.CTkToplevel(self)
        self.support_win.title("Thank you for your support & updates")
        self.support_win.geometry("340x520")
        self.support_win.attributes("-topmost", True)
        self.support_win.resizable(False, False)

        try:
            icon_path = get_asset_path("icon.ico")
            if icon_path:
                self.support_win.iconbitmap(icon_path)
        except Exception:
            pass

        self.support_win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 520) // 2
        self.support_win.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            self.support_win,
            text="Thank you for your support and encouragement",
            font=ctk.CTkFont(weight="bold", size=18),
            text_color="#F97316",
        ).pack(pady=(20, 6))

        ctk.CTkLabel(
            self.support_win,
            Your support is my motivation to continuously optimize!
            font=ctk.CTkFont(size=12),
        ).pack(pady=4)

        qr_path = get_asset_path("qrcode.png")
        try:
            if qr_path and os.path.exists(qr_path):
                img = Image.open(qr_path)
                qr_img = ctk.CTkImage(light_image=img, size=(210, 210))
                qr_label = ctk.CTkLabel(self.support_win, text="", image=qr_img)
                qr_label.image = qr_img
                qr_label.pack(pady=10)
            else:
                ctk.CTkLabel(self.support_win, text="（Built-in qrcode.png not found）", text_color="gray").pack(pady=40)
        except Exception:
            ctk.CTkLabel(self.support_win, text="（QR code loading failed）", text_color="gray").pack(pady=40)

        ctk.CTkButton(
            self.support_win,
            text="Go to the Aifa Power Sponsorship Homepage",
            fg_color="#8E44AD",
            hover_color="#7D3C98",
            command=lambda: webbrowser.open("https://ifdian.net/a/yousto"),
        ).pack(pady=5)

        ctk.CTkFrame(self.support_win, height=2, fg_color="#333333").pack(fill="x", padx=20, pady=10)

        self.lbl_version = ctk.CTkLabel(
            self.support_win,
            text=f"Current version: v{CURRENT_VERSION}",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_version.pack()

        def check_update_logic():
            self.ui_call(self.lbl_version.configure, text="Connecting to Github...", text_color="#3498DB")
            try:
                url = "https://raw.githubusercontent.com/YOUSTHEONE/FH6Auto/refs/heads/main/version.json"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    remote_ver = data.get("version", "0.0.0")
                    remote_url = data.get("url", "")

                    if parse_version(remote_ver) > parse_version(CURRENT_VERSION):
                        if remote_url.startswith("https://github.com/YOUSTHEONE/") or remote_url.startswith("https://ifdian.net/"):
                            self.ui_call(
                                self.lbl_version.configure,
                                text=f"New version v{remote_ver} found, browser is now open!"
                                text_color="#2EA043",
                            )
                            webbrowser.open(remote_url)
                        else:
                            self.ui_call(
                                self.lbl_version.configure,
                                text="Update found, but the link is untrusted and has been blocked",
                                text_color="#DA3633",
                            )
                    else:
                        self.ui_call(
                            self.lbl_version.configure,
                            text=f"This is the latest version (v{CURRENT_VERSION})",
                            text_color="gray",
                        )
                else:
                    self.ui_call(
                        self.lbl_version.configure,
                        text="Update check failed (server error)",
                        text_color="#DA3633",
                    )
            except Exception:
                self.ui_call(
                    self.lbl_version.configure,
                    text="Update check failed (network timeout or inaccessible)",
                    text_color="#DA3633",
                )

        btn_frame = ctk.CTkFrame(self.support_win, fg_color="transparent")
        btn_frame.pack(pady=6)

        ctk.CTkButton(
            btn_frame,
            text="Check for updates",
            width=100,
            height=30,
            fg_color="#444444",
            hover_color="#555555",
            command=lambda: threading.Thread(target=check_update_logic, daemon=True).start(),
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="GitHub",
            width=100,
            height=30,
            fg_color="#2EA043",
            hover_color="#238636",
            command=lambda: webbrowser.open("https://github.com/YOUSTHEONE/FH6Auto"),
        ).pack(side="left", padx=5)
    def update_timer(self):
        if not self.is_running:
            return
        elapsed = int(time.time() - self.start_time)
        hrs = elapsed // 3600
        mins = (elapsed % 3600) // 60
        secs = elapsed % 60
        time_str = f"Total time elapsed: {hrs:02d}:{mins:02d}:{secs:02d}"
        try:
            self.lbl_mini_time.configure(text=time_str)
        except Exception: pass
        
        if self.is_running:
            self.after(1000, self.update_timer)

    def update_running_ui(self, task_name="", current_val=0, max_val=0):
        try:
            if task_name:
                self.ui_call(self.lbl_mini_task.configure, text=f"Current task: {task_name}")
            if max_val > 0:
                self.ui_call(self.lbl_mini_prog.configure, text=f"Execution progress: {current_val} / {max_val}")
        except Exception:
            pass

    # ==========================================
    # --- Core Operations and Process Control ---
    # ==========================================
    def hw_key_down(self, key):
        if key not in DIK_CODES:
            return
        scan_code, extended = DIK_CODES[key]
        flags = 0x0008 | (0x0001 if extended else 0)
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(1), ii_)
        SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def hw_key_up(self, key):
        if key not in DIK_CODES:
            return
        scan_code, extended = DIK_CODES[key]
        flags = 0x000A | (0x0001 if extended else 0)
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(1), ii_)
        SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def hw_press(self, key, delay=0.08):
        self.check_pause() # <--- 【Added】If the script is paused, it will wait indefinitely here until it resumes.
        if not self.is_running:
            return
        self.hw_key_down(key)
        time.sleep(delay)
        self.hw_key_up(key)
    #Secondary screen support
    def hw_mouse_move(self, x, y):
        # Obtain the coordinates and dimensions of the entire "virtual desktop" composed of multiple monitors
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79
        left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if width == 0 or height == 0:
            return
        # Absolute virtual coordinate system mapped to 0~65535
        calc_x = int((x - left) * 65535 / width)
        calc_y = int((y - top) * 65535 / height)
        # MOUSEEVENTF_MOVE = 0x0001, MOUSEEVENTF_ABSOLUTE = 0x8000, MOUSEEVENTF_VIRTUALDESK = 0x4000
        flags = 0x0001 | 0x8000 | 0x4000 
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.mi = MouseInput(calc_x, calc_y, 0, flags, 0, ctypes.pointer(extra))
        cmd = Input(ctypes.c_ulong(0), ii_)
        SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))
    def game_click(self, pos, double=False):
        self.check_pause() # <--- [Added] Intercept mouse clicks
        if not self.is_running or not pos:
            return
        x, y = int(pos[0]), int(pos[1])
        
        # Use hardware-level mobility for multi-screen compatibility
        self.hw_mouse_move(x, y)
        time.sleep(0.2)
        for _ in range(2 if double else 1):
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.1)
        time.sleep(0.1)
        # Move the mouse 10 pixels away to prevent the in-game tooltip from obscuring the next screenshot.
        try:
            gx, gy, gw, gh = self.regions["All Interfaces"]
            # Move it to the top left corner of the game and offset it inwards by 5 pixels, ensuring it's in-game but absolutely doesn't block any central UI elements.
            self.hw_mouse_move(gx + 5, gy + 5)
        except Exception:
            # Backup: If the window coordinates cannot be obtained, move it to the absolute top-left corner of the screen.
            self.hw_mouse_move(5, 5)
        time.sleep(0.2)

    def move_to_game_coord(self, x, y):
        """
        Move the mouse to the (x, y) coordinates starting from the top left corner of the game window.
        For example, passing in (5, 5) will move you to a safe position 5 pixels in the top left corner of the game.
        """
        try:
            gx, gy, gw, gh = self.regions["All Interfaces"]
            abs_x = gx + x
            abs_y = gy + y
            self.hw_mouse_move(abs_x, abs_y)
        except Exception:
            # Backup: If the window coordinates cannot be obtained, move the object using absolute coordinates.
            self.hw_mouse_move(x, y)
    
    def add_skill_dir(self, direction):
        self.config["skill_dirs"].append(direction)
        self.update_skill_grid()
        self.save_config()

    def clear_skill_dir(self):
        self.config["skill_dirs"].clear()
        self.update_skill_grid()
        self.save_config()

    def update_skill_grid(self):
        for r in range(4):
            for c in range(4):
                self.grid_labels[r][c].configure(fg_color="#333333")

        curr_r, curr_c = 3, 0
        self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
        valid_dirs = []

        for d in self.config["skill_dirs"]:
            if d == "up":
                curr_r -= 1
            elif d == "down":
                curr_r += 1
            elif d == "left":
                curr_c -= 1
            elif d == "right":
                curr_c += 1

            if 0 <= curr_r < 4 and 0 <= curr_c < 4:
                self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
                valid_dirs.append(d)
            else:
                break

        self.config["skill_dirs"] = valid_dirs

    def log(self, message):
        curr_time = time.strftime("%H:%M:%S")
        full_msg = f"[{curr_time}] {message}"

        def write_ui():
            try:
                # Write logs to the main interface below
                self.log_box.configure(state="normal")
                self.log_box.insert("end", full_msg + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
                # Simultaneously write to the horizontal log of the mini interface
                if hasattr(self, "mini_log_box"):
                    self.mini_log_box.configure(state="normal")
                    self.mini_log_box.insert("end", full_msg + "\n")
                    self.mini_log_box.see("end")
                    self.mini_log_box.configure(state="disabled")
            except Exception:
                pass
        self.ui_call(write_ui)
    def start_pipeline(self, start_step):
        if self.is_running:
            return

        self.is_running = True
        self.save_config()

        # Hide all elements in the large window
        self.config_frame.pack_forget()
        self.global_settings_frame.pack_forget()
        self.calc_frame.pack_forget()
        self.top_container.pack_forget()
        if hasattr(self, "bottom_frame"):
            self.bottom_frame.pack_forget()
        self.btn_support.pack_forget()

        # Show the new mini horizontal UI
        self.mini_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ====== Calculate 15% Height 40% Width ======
        last_x, last_y, last_w, last_h = self.regions["全界面"]
        if last_w <= 0: last_w = self.winfo_screenwidth()
        if last_h <= 0: last_h = self.winfo_screenheight()

        calc_w = int(last_w * 0.40)
        calc_h = int(last_h * 0.15)
        # Set a minimum safety margin to prevent text compression and crashes when the resolution is too low.
        calc_w = max(calc_w, 650)
        calc_h = max(calc_h, 150)

        pos_x = last_x + last_w - calc_w - 20
        pos_y = last_y + 20

        self.attributes("-topmost", True)
        self.geometry(f"{calc_w}x{calc_h}+{pos_x}+{pos_y}")
        
        # Start timer
        self.start_time = time.time()
        self.update_timer()

        
        self.update_running_ui("Initializing...")
        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.sc_count = 0
        self.global_loop_current = 0

        def runner():
            if not self.check_and_focus_game():
                self.stop_all()
                return

            steps = ["race", "buy", "cj", "sell"]
            curr_idx = steps.index(start_step)

            try:
                total_loops = int(self.entry_global_loop.get())
            except Exception:
                total_loops = self.config.get("global_loops", 10)
            self.global_loop_current = 1
            if hasattr(self, "lbl_mini_loop"):
                self.ui_call(self.lbl_mini_loop.configure, text=f"大循环: {self.global_loop_current} / {total_loops}")

            # [New Feature]: Global Consecutive Failure Counter
            continuous_failures = 0 
            # [You can modify this]: Set the maximum number of consecutive restores allowed globally (e.g., 3 times).
            MAX_RECOVERIES = 10 

            while self.is_running:
                step_name = steps[curr_idx]
                success = False

                try:
                    if step_name == "race":
                        success = self.logic_race(int(self.entry_race.get()))
                    elif step_name == "buy":
                        success = self.logic_buy_car(int(self.entry_car.get()))
                    elif step_name == "cj":
                        success = self.logic_super_wheelspin(int(self.entry_cj.get()))
                    elif step_name == "sell":
                        # ====== 【New Feature】: Determine the dropdown list's mode ======
                        sell_mode = self.opt_sell_mode.get()
                        if "mode1" is in sell_mode:
                            success = self.find_and_remove_consumable_car(int(self.entry_sc.get()))
                        else:
                            success = self.sell_consumable_car(int(self.entry_sc.get()))
                        # =========================================
                except Exception as e:
                    self.log(f"Exception occurred while executing module {step_name}: {e}")
                    success = False

                if not self.is_running:
                    break

                if not success:
                    continuous_failures += 1
                    
                    # Check if the maximum tolerance number has been exceeded
                    if continuous_failures > MAX_RECOVERIES:
                        self.log(f"!!! Warning: The problem persists despite triggering breakpoints and resuming operations for {continuous_failures} consecutive times!")
                        self.log("To prevent the game from getting stuck in an infinite loop, all current tasks will be forcibly terminated. Please manually check the game status.")
                        break # Exits the while loop and stops the script.
                        
                    self.log(f"Global recovery in progress ({continuous_failures}/{MAX_RECOVERIES} allowed retries)...")
                    
                    if self.attempt_recovery():
                        continue # Resuming successfully, return to the top of the while loop and try this task again.
                    else:
                        self.log("Fatal error: Even returning to the back menu/restarting failed, completely stopped.")
                        break
                else:
                    # Once this major step is successfully completed, the consecutive failure count is reset to zero, rewarding it to continue running!
                    continuous_failures = 0
                #v1.0.1
                # ====== Core Flow and Infinite Loop Logic ======
                next_idx = curr_idx + 1 # Proceed to the next step by default
                if curr_idx == 0:
                    if self.var_chk1.get():
                        try: next_idx = max(0, min(3, int(self.entry_next1.get()) - 1))
                        except Exception: next_idx = 1
                    else: break
                elif curr_idx == 1:
                    if self.var_chk2.get():
                        try: next_idx = max(0, min(3, int(self.entry_next2.get()) - 1))
                        except Exception: next_idx = 2
                    else: break
                elif curr_idx == 2:
                    if self.var_chk3.get():
                        try: next_idx = max(0, min(3, int(self.entry_next3.get()) - 1))
                        except Exception: next_idx = 3
                    else: break
                elif curr_idx == 3:
                    if self.var_chk4.get():
                        try: next_idx = max(0, min(3, int(self.entry_next4.get()) - 1))
                        except Exception: next_idx = 0
                    else: break

                if next_idx <= curr_idx:
                    self.global_loop_current += 1
                    
                    if self.global_loop_current > total_loops:
                        self.log("The set total number of loops has been reached, and the task has been successfully completed.")
                        break
                        
                    self.log(f"Starting a new round of the global loop ({self.global_loop_current}/{total_loops})")
                    
                    if hasattr(self, "lbl_mini_loop"):
                        self.ui_call(self.lbl_mini_loop.configure, text=f"大循环: {self.global_loop_current} / {total_loops}")

                    self.race_counter = 0
                    self.car_counter = 0
                    self.cj_counter = 0
                    self.sc_count = 0
                
                curr_idx = next_idx

            self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()

    def stop_all(self):
        if not self.is_running:
            return

        self.is_running = False
        self.is_paused = False # <--- [Added] The pause lock must be released when the device is completely stopped.

        for key in DIK_CODES.keys():
            self.hw_key_up(key)

        for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
            self.hw_key_up(key)

        try:
            pydirectinput.mouseUp()
        except Exception:
            pass

        def restore_ui():
            if hashttr(self, "mini_frame"):
                self.mini_frame.pack_forget()
                
            # [Core Fix]: First, unbind everything in the large container and start over.
            self.config_frame.pack_forget()
            self.global_settings_frame.pack_forget()
            self.calc_frame.pack_forget()
            
            # 1. Lay out the outermost large container
            self.top_container.pack(fill="x", padx=18, pady=(18, 10))
            
            # 2. Insert the three modules in sequence to perfectly ensure the top-to-bottom order!
            self.config_frame.pack(fill="x")
            self.global_settings_frame.pack(fill="x", pady=(15, 0))
            self.calc_frame.pack(fill="x", pady=(10, 0))
            
            # 3. Install the log and buttons at the bottom.
            if hasattr(self, "bottom_frame"):
                self.bottom_frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))
            self.btn_support.pack(fill="x", padx=18, pady=(6, 12))
            
            # Restore the window to its original state
            self.btn_stop.configure(text="Wait for command (F8)", fg_color="#3A3A3A", hover_color="#4A4A4A")
            self.attributes("-topmost", False)
            self.geometry("1800x800")
            self.center_window()

        self.ui_call(restore_ui)
        self.log("!!! Task has stopped, all physical button states have been forcibly reset")
    def start_test_boot(self):
        "Standalone test boot process"
        if self.is_running:
            self.log("A task is already running. Please click 'Stop' before testing the startup process!")
            return
            
        self.is_running = True
        self.save_config()
        
        # ==========================================
        # [New/Fixed]: Hides all elements in the large window and enters mini mode.
        # ==========================================
        self.config_frame.pack_forget()
        self.global_settings_frame.pack_forget()
        self.calc_frame.pack_forget()
        self.top_container.pack_forget()
        if hasattr(self, "bottom_frame"):
            self.bottom_frame.pack_forget()
        self.btn_support.pack_forget()

        # Show the new mini horizontal UI
        self.mini_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Start timer and status text update
        self.update_running_ui("Test startup process...")
        self.start_time = time.time()
        self.update_timer()
        # ==========================================

        self.log("====== Start independent testing of automatic power-on and recognition process======")
        
        def test_runner():
            success = self.restart_game_and_boot(force_test=True)
            if success:
                self.log("Test complete: Automatic power-on, A/B/C state machine recognition, and menu navigation all worked perfectly!")
            else:
                self.log("Test complete: Automatic boot process failed. Please check screenshots or logs.")
            self.stop_all() # Automatically stop the script after testing and automatically restore the large window state.
            
        self.current_thread = threading.Thread(target=test_runner, daemon=True)
        self.current_thread.start()
    # ==========================================
    # --- [New Feature] Pause and Resume Logic ---
    # ==========================================
    def toggle_pause(self):
        if not self.is_running:
            return
            
        self.is_paused = not self.is_paused
        
        if self.is_paused:
            self.log("⏸ Task paused (Press F9 or click the button to resume)")
            # Force release all potentially held buttons to prevent the car from driving away on its own or the UI from malfunctioning.
            for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
                self.hw_key_up(key)
            try:
                pydirectinput.mouseUp()
            except Exception:
                pass
            # Change button UI
            if hastatr(self, "btn_mini_pause"):
                self.ui_call(self.btn_mini_pause.configure, text="▶ 继续 (F9)", fg_color="#2EA043", hover_color="#238636")
        else:
            self.log("▶ Task has been resumed")
            if hastatr(self, "btn_mini_pause"):
                self.ui_call(self.btn_mini_pause.configure, text="⏸ 暂停 (F9)", fg_color="#F1C40F", hover_color="#D4AC0D")

    def check_pause(self):
        "Core Blocker: This method is called before any action is taken; if the system is paused, it will wait indefinitely here."
        while self.is_paused and self.is_running:
            time.sleep(0.1)

    
    def start_hotkey_listener(self):
        def hotkey_thread():
            def on_press(k):
                if k == keyboard.Key.f8:
                    self.stop_all()
                elif k == keyboard.Key.f9: # <--- 【New】F9 shortcut key
                    self.toggle_pause()
                elif k == keyboard.Key.f3: # <--- 【New】F3 test image search
                    self.start_test_find_image()

            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()

        threading.Thread(target=hotkey_thread, daemon=True).start()

   
    # ==========================================
    # --- Logical Guarantee ---
    # ==========================================
    # [New Feature]: Force switch to English keyboard and disable Chinese keyboard mode
    def set_english_input(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return
            # Strategy 1: Try switching to the US keyboard
            hkl = ctypes.windll.user32.LoadKeyboardLayoutW("00000409", 1)
            ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, hkl) 
            # Strategy 2: Forcefully disable the Chinese input mode of the current Chinese input method at the underlying level (the ultimate solution)
            WM_IME_CONTROL = 0x0283
            IMC_SETOPENSTATUS = 0x0006
            ctypes.windll.user32.SendMessageW(hwnd, WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)
            
            self.log("Automatically switched to English keyboard/disabled Chinese input method.")
        except Exception as e:
            self.log(f"Automatic Chinese input prevention settings failed: {e}")
    def check_and_focus_game(self):
        self.log("Checking game process (forzahorizon6.exe)...")
        try:
            CREATE_NO_WINDOW = 0x08000000
            cmd = 'tasklist /FI "IMAGENAME eq forzahorizon6.exe" /NH /FO CSV'
            output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW)

            if "forzahorizon6.exe" not in output.lower():
                self.log("No forzahorizon6.exe process found! (Please ensure the game is running)")
                return False

            target_pid = None
            for line in output.strip().split("\n"):
                parts = line.split('","')
                if len(parts) >= 2 and "forzahorizon6.exe" in parts[0].lower():
                    target_pid = int(parts[1].replace('"', ""))
                    break

            if not target_pid:
                self.log("Process found but PID could not be resolved!")
                return False

            hwnds = []

            def foreach_window(hwnd, lParam):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        window_pid = ctypes.c_ulong()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                        if window_pid.value == target_pid:
                            hwnds.append(hwnd)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(foreach_window), 0)

            if hwnds:
                hwnd = hwnds[0]
                if ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)
                else:
                    ctypes.windll.user32.ShowWindow(hwnd, 5)
                    
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                # ====== 【New Feature】: Force disable Chinese input method ======
                self.set_english_input()
                # ==========================================
                try:
                    # 1. Update the image recognition area to the actual game window area (image recognition must be within the game window).
                    client_rect = win32gui.GetClientRect(hwnd)
                    pt = win32gui.ClientToScreen(hwnd, (0, 0))
                    gx, gy = pt[0], pt[1]
                    gw, gh = client_rect[2], client_rect[3]
                    # ====== 【Core Fix】: Intercepting Startup Window/Anti-Cheat Screen Flicker ======
                    # If the window width and height are too small, it definitely is not a normal game main screen.
                    if gw < 1000 or gh < 600:
                        self.log(f"A small window ({gw}x{gh}) has been intercepted, which is determined to be a startup splash screen. Waiting for the main window to load...")
                        return False 
                    # ====================================================
                    self.update_regions_by_window(gx, gy, gw, gh)

                    # 2. Obtain the physical display boundaries of the window.
                    MONITOR_DEFAULTTONEAREST = 2
                    hMonitor = ctypes.windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
                    class RECT(ctypes.Structure):
                        _fields_ = [
                            ("left", ctypes.c_long), 
                            ("top", ctypes.c_long), 
                            ("right", ctypes.c_long), 
                            ("bottom", ctypes.c_long)
                        ]
                    class MONITORINFO(ctypes.Structure):
                        _fields_ = [
                            ("cbSize", ctypes.c_ulong),
                            ("rcMonitor", RECT),
                            ("rcWork", RECT), 
                            ("dwFlags", ctypes.c_ulong)
                        ]
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    
                    if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                        mx = mi.rcMonitor.left
                        my = mi.rcMonitor.top
                        mw = mi.rcMonitor.right - mi.rcMonitor.left
                        mh = mi.rcMonitor.bottom - mi.rcMonitor.top
                    else:
                        # Backup: If the screen boundaries cannot be obtained, use the game window boundaries.
                        mx, my, mw, mh = gx, gy, gw, gh

                    # ====== 【Modification】: The small window now precisely snaps to the top right corner of the monitor. ======
                    def snap_to_game():
                        if self.is_running:
                            calc_w = int(mw * 0.40)
                            calc_h = int(mh * 0.15)
                            calc_w = max(calc_w, 650)
                            calc_h = max(calc_h, 150)
                            
                            # Place it in the top right corner of the current screen (with a 20-pixel margin).
                            pos_x = mx + mw - calc_w - 20
                            pos_y = my + 20
                            self.geometry(f"{calc_w}x{calc_h}+{pos_x}+{pos_y}")
                    self.ui_call(snap_to_game)
                    # ==========================================
                except Exception as e:
                    self.log(f"Failed to get window coordinates: {e}")

                time.sleep(1.0)
                return True

        except Exception as e:
            self.log(f"Checking for process errors: {e}")
            return False

        return False

    def restart_game_and_boot(self, force_test=False):
        # Unless the test button (force_test) is clicked, check if automatic restart is enabled in the settings.
        if not force_test:
            auto_restart = getattr(self, "var_auto_restart", None)
            if auto_restart is None or not auto_restart.get():
                self.log("Automatic restart not enabled, task completed.")
                return False

        self.log("Triggered the launch mechanism! Launching the game...")
        try:
            cmd_widget = getattr(self, "le_restart_cmd", None)
            cmd_str = cmd_widget.get() if cmd_widget else self.config.get("restart_cmd", "start steam://run/2483190")
            os.system(cmd_str)
        except Exception as e:
            self.log(f"Failed to execute startup command: {e}")
            return False

        self.log("Waiting for game progress to appear (maximum 60 seconds)...")
        process_found = False
        for _ in range(120):
            if hasattr(self, "check_pause"): self.check_pause()
            if not self.is_running: return False
            if self.check_and_focus_game():
                process_found = True
                break
            time.sleep(1)
            
        if not process_found:
            self.log("No game process detected, startup failed.")
            return False

        self.log("Game process has started, entering dynamic recognition phase (limited to 5 minutes)...")
        start_time = time.time()
        
        passed_screen_1 = False # Record whether the Enter key on screen 1 has been pressed.
        last_continue_time = 0 # Record the timestamp of the last time the "Continue" button was seen/clicked

        while self.is_running and time.time() - start_time < 300:
            if hasattr(self, "check_pause"): self.check_pause()

            # ==============================
            # Screen 1: Locate the bottom left corner horizon6.png -> Press Enter
            # ==============================
            if not passed_screen_1:
                pos_h6 = None
                
                # Strategy A: Transparent Image Recognition
                pos_h6 = self.find_image_transparent("horizon6.png", region=self.regions["全界面"], threshold=0.60, fast_mode=False)
                
                # Strategy B: Edge contour recognition as a fallback!
                if not pos_h6:
                    try:
                        screen_bgr = self.capture_region(self.regions["All Interfaces"])
                        tpl_bgr, _ = self.load_template("horizon6.png")
                        if tpl_bgr is not None:
                            screen_edge = self.to_edge_image(screen_bgr)
                            tpl_edge = self.to_edge_image(tpl_bgr)
                            
                            for scale in self.get_scales_to_try(fast_mode=False):
                                t_e = tpl_edge if scale == 1.0 else cv2.resize(tpl_edge, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                                h, w = t_e.shape[:2]
                                if h > screen_edge.shape[0] or w > screen_edge.shape[1] or h < 5 or w < 5: continue
                                
                                res = cv2.matchTemplate(screen_edge, t_e, cv2.TM_CCOEFF_NORMED)
                                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                                
                                if max_val >= 0.40: 
                                    self.log(f"[Outline Black Technology] Ignore Background and Hit! Score: {max_val:.2f} Scaling: {scale:.2f}")
                                    pos_h6 = (max_loc[0] + w//2 + self.regions["full interface"][0], max_loc[1] + h//2 + self.regions["full interface"][1])
                                    break
                    except Exception:
                        pass
                
                if pos_h6:
                    self.log("✅ Successfully detected screen 1 (horizon6.png), pressed [Enter]...")
                    time.sleep(1)
                    for _ in range(2):
                        self.hw_press("enter")
                        time.sleep(1)
                    passed_screen_1 = True
                    # Activate the countdown mechanism for screen 2. If screen 2 is not found during the subsequent search, it will attempt to enter the menu after 30 seconds.
                    last_continue_time = time.time() 
                    self.log("Screen 1 confirmed, forcing a 10-second wait for screen 2 to load...")
                    time.sleep(10) # Wait 10 seconds
                    continue
                else:
                    self.log("Frame 1 not found. Full-scale depth scan is in progress...")

            # ==============================
            # Screen 2: Find the "continue-b" or "continue-w" button in the bottom right corner -> keep clicking it.
            # ==============================
            # Only after passing screen 1 should you search for screen 2.
            if passed_screen_1:
                pos_continue = self.find_any_image_gray(["continue-b.png", "continue-w.png"], threshold=0.75)
                if pos_continue:
                    self.log("Screen 2 (Continue button) detected, clicked...")
                    self.game_click(pos_continue)
                    
                    # [Core Logic]: Refresh the timestamp whenever a click is made!
                    last_continue_time = time.time() 
                    
                    time.sleep(3.0) # Try again after 3 seconds of clicking; keep clicking as long as it works.
                    continue

                # ==============================
                # State transition: Entering the roaming mode and calling up the menu
                # ==============================
                # If more than 30 seconds have passed since the last click on screen 2, and no further clicks have been made during that time...
                time_since_last_seen = time.time() - last_continue_time
                if time_since_last_seen >= 30.0:
                    self.log("✅ No continue button has been found for 30 consecutive seconds, indicating that roaming loading is complete! Attempting to enter the menu...")
                    
                    if getattr(self, "enter_menu")(): 
                        self.log("🎉 Verification successful: Successfully entered the game's main menu! The startup process is complete.")
                        return True
                    else:
                        self.log("Failed to enter the menu normally (may still be on a black screen or a new pop-up may appear), resetting the 30-second countdown, continuing to observe...")
                        # If the attempt to enter the menu fails, reset the timestamp. The script will continue searching for screen 2, or wait another 30 seconds to try entering the menu again.
                        last_continue_time = time.time()
            
            time.sleep(1.0) # Rest for 1 second during each loop to prevent excessive CPU usage.

        self.log("Automatic startup timed out (5 minutes), resuscitation abandoned.")
        return False

    def handle_vramne_restart(self):
        self.log("!!! VRAMNE.png detected. Game will be terminated in 2 seconds. Restart will be waited 10 minutes...")
        time.sleep(2.0)

        if not self.is_running:
            return False

        try:
            os.system('taskkill /F /IM forzahorizon6.exe /T')
            self.log("forzahorizon6.exe has been forcibly deleted")
        except Exception as e:
            self.log(f"Failed to force kill the game: {e}")
            return False

        self.log("Starting to wait 10 minutes to release video memory...")
        for _ in range(600):
            if hasattr(self, "check_pause"):
                self.check_pause()
            if not self.is_running:
                return False
            time.sleep(1)

        self.log("10-minute wait time is complete, preparing to automatically restart the game...")
        return self.restart_game_and_boot()


    def check_vramne_during_race(self):
        try:
            pos_vram = self.find_image_gray(
                "VRAMNE.png",
                region = self.regions["full interface"],
                threshold=0.70,
                fast_mode=True
            )
            if pos_vram:
                return self.handle_vramne_restart()
            return None
        except Exception as e:
            self.log(f"Insufficient video memory detected: {e}")
            return None
    def attempt_recovery(self):
        self.log("Task execution was interrupted abnormally, preparing to execute the breakpoint recovery process...")
        if not self.check_and_focus_game():
            # If the game is not running or the process has stopped, simply restart the game.
            if not self.restart_game_and_boot():
                return False
        else:
            # The process is still running; try to dynamically roll back using an advanced state machine.
            if not self.advanced_enter_menu():
                self.log("Advanced dynamic rollback failed (the game may be frozen or have a fatal error), preparing to force-kill the process and restart...")
                try:
                    os.system('taskkill /F /IM forzahorizon6.exe /T')
                    time.sleep(4)
                except Exception: pass
                
                # Restart after killing the process
                if not self.restart_game_and_boot():
                    return False
        self.log("Environment reset successful! Resuming the remaining tasks from where they were interrupted.")
        return True

    def wait_for_freeroam(self):
        self.log("Verifying roaming status...")
        for i in range(100):
            if not self.is_running:
                return False

            if self.find_image("anna.png", region=self.regions["左下"], threshold=0.5):
                self.log("Verification successful: Confirmed to be in the game roaming interface.")
                return True

            self.log(f"Retry returning to the roaming interface ({i + 1}/100)")
            self.hw_press("esc")

            for _ in range(20):
                if not self.is_running:
                    return False
                time.sleep(0.1)

        self.log("Failed to verify the roaming interface multiple times. Attempting to access the menu.")
        return True

    def recover_to_menu(self):
        self.log("Attempting to return to the main menu...")
        return self.enter_menu()

    def is_in_menu(self):    
        return self.find_image_gray(
            "collectionjournal.png",
            region=self.regions["Left"],
            threshold=0.70,
            fast_mode=True
        )
    def enter_menu(self):
        self.log("Attempting to access the main menu...")
        # It takes about 40-60 seconds to try 60 times consecutively.
        for i in range(60):
            if not self.is_running:
                return False
                

            pos_menu = self.find_image_gray("collectionjournal.png", region=self.regions["左"], threshold=0.70, fast_mode=True)
            
            if pos_menu:
                self.log(f"Successfully located the menu anchor!({i + 1}/60)")
                time.sleep(0.5)
                return True
                
            self.log(f"Not in main menu... ({i + 1}/60)")
            self.hw_press("esc")
            # Give the game some animation loading time
            time.sleep(1.0)
            
        self.log("60 attempts failed to enter the menu. Please check the game status.")
        return False
    def advanced_enter_menu(self):
        """
        Advanced state machine rollback: specifically designed for fault recovery.
        It can identify specific pop-ups and intermediate transition screens and execute clicks; it only presses ESC if the target is not found.
        """
        self.log("Attempting to return to the main menu using Advanced Recovery Mode...")
        
        # ==========================================
        # Dynamically read all images in images/obstacles/
        # ==========================================
        obstacles_dir = os.path.join("images", "obstacles")
        dynamic_obstacles = []
        
        # Check if the folder exists
        if os.path.exists(obstacles_dir):
            for file in os.listdir(obstacles_dir):
                # Include all images that are in PNG or JPG format.
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    # Spell it as "obstacles/filename.png" so that find_any_image_gray can correctly locate the path.
                    dynamic_obstacles.append(f"obstacles/{file}")
        
        if not dynamic_obstacles:
            self.log("Note: The images/obstacles/ folder is empty or does not exist. You will only return with ESC.")
        # Try 80 times consecutively to handle a long random process.
        for i in range(80):
            if hasattr(self, "check_pause"): self.check_pause() # Compatible with pause functionality
            if not self.is_running:
                return False
                
            #1. Final judgment: Is it already on the menu?
            if self.is_in_menu():
                self.log(f"Successfully located the menu anchor! (Number of attempts: {i + 1})")
                time.sleep(0.5)
                return True

            # 2. Fatal Error Troubleshooting (Insufficient video memory detected, forced rest for 10 minutes)
            if self.find_image_gray("VRAMNE.png", region=self.regions["全界面"], threshold=0.75, fast_mode=True):
                self.log("!!! Critical Warning: Insufficient video memory detected (VRAMNE.png) Error!")
                self.log("Game will be terminated in 2 seconds, followed by a 10-minute cooldown...")
                time.sleep(2.0)
                try:
                    os.system('taskkill /F /IM forzahorizon6.exe /T')
                    self.log("forzahorizon6.exe has been forcibly deleted")
                except Exception as e:
                    self.log(f"Failed to force kill the game: {e}")
                    return False
                for _ in range(600):
                    if hasattr(self, "check_pause"):
                        self.check_pause()
                    if not self.is_running:
                        return False
                    time.sleep(1)
                self.log("10-minute cooldown complete, now handing over the restart process to the outer layer.")
                return False

            # 3. Dynamically scan all possible pop-ups/clickable images in the middle.
            pos_obs = self.find_any_image_gray(dynamic_obstacles, region=self.regions["全界面"], threshold=0.75, fast_mode=True)
            if pos_obs:
                self.log(f"Known image/popup detected during rollback, click to proceed... ({i+1}/80)")
                self.game_click(pos_obs)
                time.sleep(1.5) # Allow animation time for screen transitions
                Continue # Click to skip this round; do not press ESC.
                
            # 4. If you neither enter a menu nor see a specific image, it means you are in the normal interface. Press ESC to return.
            self.log(f"Not in the main menu and no specific image is known, press ESC... ({i + 1}/80)")
            self.hw_press("esc")
            time.sleep(1.2) # Give the game some animation loading time.
            
        self.log("80 dynamic attempts failed to enter the menu, advanced return failed.")
        return False
    # ==========================================
    # --- Image Search ---
    # ==========================================
    def load_template(self, template_path):
        actual_path = get_img_path(template_path)
        cache_key = actual_path

        if cache_key in self.template_cache:
            return self.template_cache[cache_key], actual_path

        tpl = cv2.imread(actual_path, cv2.IMREAD_COLOR)
        if tpl is not None:
            self.template_cache[cache_key] = tpl
        return tpl, actual_path
    def load_template_gray(self, template_path):
        actual_path = get_img_path(template_path)
        cache_key = ("gray", actual_path)
        if not hasattr(self, "template_gray_cache"):
            self.template_gray_cache = {}
        if cache_key in self.template_gray_cache:
            return self.template_gray_cache[cache_key]
        tpl = cv2.imread(actual_path, cv2.IMREAD_GRAYSCALE)
        if tpl is not None:
            self.template_gray_cache[cache_key] = tpl
        return tpl
    def get_images_root_dir(self):
        ext_dir = os.path.join(APP_DIR, "images")
        if os.path.isdir(ext_dir):
            return ext_dir

        int_dir = os.path.join(INTERNAL_DIR, "images")
        if os.path.isdir(int_dir):
            return int_dir

        return None

    def get_template_meta(self):
        images_dir = self.get_images_root_dir()
        meta_data = {}
        if not images_dir:
            return meta_data

        for root, _, files in os.walk(images_dir):
            for file in files:
                if not file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    continue

                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, images_dir).replace("\\", "/")

                try:
                    stat = os.stat(path)
                    meta_data[rel_path] = {
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                    }
                except Exception:
                    pass

        return meta_data

    def is_template_cache_valid(self):
        if not os.path.exists(TEMPLATE_CACHE_FILE) or not os.path.exists(TEMPLATE_META_FILE):
            return False

        try:
            with open(TEMPLATE_META_FILE, "r", encoding="utf-8") as f:
                old_meta = json.load(f)
        except Exception:
            return False

        new_meta = self.get_template_meta()
        return old_meta == new_meta

    def build_template_file_cache(self):
        self.log("Starting to build template cache files...")
        os.makedirs(CACHE_DIR, exist_ok=True)

        images_dir = self.get_images_root_dir()
        if not images_dir:
            self.log("Images directory not found; unable to build template cache.")
            return False

        cache_data = {}
        meta_data = self.get_template_meta()

        scales = self.get_scales_to_try(fast_mode=False)

        for rel_path in meta_data.keys():
            img_path = os.path.join(images_dir, rel_path)
            tpl = cv2.imread(img_path, cv2.IMREAD_COLOR)
            if tpl is None:
                continue

            cache_data[rel_path] = {}
            for scale in scales:
                try:
                    if scale == 1.0:
                        scaled = tpl.copy()
                    else:
                        scaled = cv2.resize(tpl, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                    cache_data[rel_path][str(round(scale, 3))] = scaled
                except Exception:
                    continue

        try:
            with open(TEMPLATE_CACHE_FILE, "wb") as f:
                pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)

            with open(TEMPLATE_META_FILE, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)

            self.log("Template cache file built successfully.")
            return True
        except Exception as e:
            self.log(f"Failed to write to template cache: {e}")
            return False

    def load_template_file_cache(self):
        try:
            with open(TEMPLATE_CACHE_FILE, "rb") as f:
                self.file_template_cache = pickle.load(f)
            self.log("Template cache file loaded successfully.")
            return True
        except Exception as e:
            self.log(f"Failed to load template cache: {e}")
            self.file_template_cache = {}
            return False

    def prepare_template_cache(self):
        os.makedirs(CACHE_DIR, exist_ok=True)

        if self.is_template_cache_valid():
            if self.load_template_file_cache():
                return

        self.log("Template cache does not exist or has expired. Starting background rebuild (this may take a few seconds)...")
        if self.build_template_file_cache():
            self.template_cache.clear()
            self.scaled_template_cache.clear()
            self.load_template_file_cache()

    def capture_region(self, region=None, mask_areas=None):
        try:
            if region:
                x, y, w, h = region
                bbox = (int(x), int(y), int(x + w), int(y + h))
                screen = ImageGrab.grab(bbox=bbox, all_screens=True)
            else:
                screen = ImageGrab.grab(all_screens=True)
        except Exception:
            screen = pyautogui.screenshot(region=region)

        screen_bgr = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)

        # Mark a specified area with a black block to avoid repeatedly identifying the same target.
        if mask_areas:
            for rect in mask_areas:
                try:
                    mx1, my1, mx2, my2 = rect
                    mx1 = max(0, int(mx1))
                    my1 = max(0, int(my1))
                    mx2 = min(screen_bgr.shape[1], int(mx2))
                    my2 = min(screen_bgr.shape[0], int(my2))
                    if mx2 > mx1 and my2 > my1:
                        screen_bgr[my1:my2, mx1:mx2] = 0
                except Exception:
                    pass

        return screen_bgr

    def get_scales_to_try(self, fast_mode=True):
        full_region = self.regions.get("Full Interface")
        curr_w = full_region[2] if full_region else pyautogui.size()[0]
        # Your graph is mainly cropped at 2560, so prioritize calculations around 2560.
        primary_base = 2560
        primary_scale = curr_w / primary_base
        scales = []
        def add_scale(s):
            s = round(float(s), 3)
            if 0.45 <= s <= 1.8 and s not in scales:
                scales.append(s)
        # First add the proportion of the "most likely correct" and make minor adjustments.
        add_scale(primary_scale)
        add_scale(primary_scale * 0.98)
        add_scale(primary_scale * 1.02)
        add_scale(primary_scale * 0.95)
        add_scale(primary_scale * 1.05)
        add_scale(primary_scale * 0.92)
        add_scale(primary_scale * 1.08)
        # Re-compatible with other sources
        for bw in [1920, 1600]:
            s = curr_w / bw
            add_scale(s)
            add_scale(s * 0.98)
            add_scale(s * 1.02)
        # Last resort commonly used ratios
        for s in [1.0, 0.95, 1.05, 0.9, 1.1, 0.85, 1.15, 0.8, 0.75, 0.7]:
            add_scale(s)
        if fast_mode:
            return scales[:8]
        return scales

    def get_scaled_template(self, template_path, scale):
        actual_path = get_img_path(template_path)
        images_dir = self.get_images_root_dir()

        if images_dir and os.path.exists(actual_path):
            try:
                rel_key = os.path.relpath(actual_path, images_dir).replace("\\", "/")
            except Exception:
                rel_key = os.path.basename(actual_path)
        else:
            rel_key = os.path.basename(actual_path)

        mem_key = (actual_path, round(scale, 3))
        if mem_key in self.scaled_template_cache:
            return self.scaled_template_cache[mem_key], actual_path

        scale_key = str(round(scale, 3))
        if rel_key in self.file_template_cache:
            tpl = self.file_template_cache[rel_key].get(scale_key)
            if tpl is not None:
                self.scaled_template_cache[mem_key] = tpl
                return tpl, actual_path

        template_orig, actual_path = self.load_template(template_path)
        if template_orig is None:
            return None, actual_path

        try:
            if scale == 1.0:
                tpl = template_orig.copy()
            else:
                tpl = cv2.resize(template_orig, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

            self.scaled_template_cache[mem_key] = tpl
            return tpl, actual_path
        except Exception:
            return None, actual_path

    def find_image_in_screen(self, screen_bgr, template_path, region=None, threshold=0.75, fast_mode=True):
        try:
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            for scale in scales_to_try:
                tpl_c, actual_path = self.get_scaled_template(template_path, scale)
                if tpl_c is None:
                    continue

                h, w = tpl_c.shape[:2]
                if h < 5 or w < 5:
                    continue
                if h > screen_bgr.shape[0] or w > screen_bgr.shape[1]:
                    continue

                res = cv2.matchTemplate(screen_bgr, tpl_c, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val >= threshold:
                    pos = (
                        max_loc[0] + w // 2 + (region[0] if region else 0),
                        max_loc[1] + h // 2 + (region[1] if region else 0),
                    )
                    self.last_positions[template_path] = pos
                    # [New Feature]: Added detailed log return for basic image search.
                    self.log(f"[ImageMatch] Hit: {template_path} | Score: {max_val:.3f} (threshold {threshold}) | Scaling: {scale:.3f}")
                    return pos

            return None

        except Exception as e:
            self.log(f"find_image_in_screen 异常: {e}")
            return None

    def find_image(self, template_path, region=None, threshold=0.75, fast_mode=True):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region)
            return self.find_image_in_screen(
                screen_bgr,
                template_path,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode
            )
        except Exception as e:
            self.log(f"An exception occurred while searching for an image: {e}")
            return None

    def find_any_image(self, image_list, region=None, threshold=MATCH_THRESHOLD, fast_mode=True):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region)
            for img_path in image_list:
                pos = self.find_image_in_screen(
                    screen_bgr,
                    img_path,
                    region=region,
                    threshold=threshold,
                    fast_mode=fast_mode
                )
                if pos:
                    return pos
            return None
        except Exception as e:
            self.log(f"find_any_image exception: {e}")
            return None

    def find_image_with_element(self, main_path, sub_path, region=None, threshold=0.85, fast_mode=True):
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)
            for scale in scales_to_try:
                # 1. Directly read scaled images using the new architecture's caching mechanism.
                main_tpl_c, _ = self.get_scaled_template(main_path, scale)
                sub_tpl_c, _ = self.get_scaled_template(sub_path, scale)
                if main_tpl_c is None or sub_tpl_c is None:
                    continue
                h_m, w_m = main_tpl_c.shape[:2]
                if h_m < 5 or w_m < 5 or h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
                    continue
                # 2. First-order matching: Finding the main target that matches across the entire screen.
                res_main = cv2.matchTemplate(screen_bgr, main_tpl_c, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res_main >= threshold)
                checked = set() # [Key Optimization]: Coordinate deduplication, resolving the lag caused by hundreds of thousands of invalid loops.
                for pt in zip(*loc[::-1]):
                    x, y = pt
                    # Filter out duplicate recognition points within 10 adjacent pixels
                    key = (x // 10, y // 10)
                    if key in checked:
                        continue
                    checked.add(key)
                    # 3. The core essence of the old code: Find elements within a range that slightly expands by 5 pixels around the main image area.
                    sub_roi = screen_bgr[
                        max(0, y - 5):min(screen_bgr.shape[0], y + h_m + 5),
                        max(0, x - 5):min(screen_bgr.shape[1], x + w_m + 5),
                    ]
                    if sub_tpl_c.shape[0] > sub_roi.shape[0] or sub_tpl_c.shape[1] > sub_roi.shape[1]:
                        continue
                                        # 4. Second-order matching: Verify whether the extraction range contains child elements.
                    res_sub = cv2.matchTemplate(sub_roi, sub_tpl_c, cv2.TM_CCOEFF_NORMED)
                    sub_score = cv2.minMaxLoc(res_sub)[1]
                    if sub_score >= threshold:
                        # [New Feature]: Added detailed log return for combined image search.
                        main_score = res_main[y, x]
                        self.log(f"[ComboMatch] Hit: {main_path}+{sub_path} | Main image score: {main_score:.3f} | Element score: {sub_score:.3f} (threshold {threshold}) | Scaling ratio: {scale:.3f}")
                        return (
                            x + w_m // 2 + (region[0] if region else 0),
                            y + h_m // 2 + (region[1] if region else 0),
                        )
            return None
        except Exception as e:
            self.log(f"find_image_with_element 异常: {e}")
            return None
    def find_image_with_element_stable(
        self,
        main_path,
        sub_path,
        region=None,
        main_threshold=0.60,
        verify_threshold=0.72,
        sub_threshold=0.70,
        max_candidates=15
    ):
        if not self.is_running:
            return None

        try:
            screen = pyautogui.screenshot(region=region)
            screen_gray = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2GRAY)

            main_tpl = self.load_template_gray(main_path)
            sub_tpl = self.load_template_gray(sub_path)

            if main_tpl is None or sub_tpl is None:
                return None

            h_m, w_m = main_tpl.shape[:2]
            h_s, w_s = sub_tpl.shape[:2]

            if h_m > screen_gray.shape[0] or w_m > screen_gray.shape[1]:
                return None

            res_main = cv2.matchTemplate(screen_gray, main_tpl, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(res_main >= main_threshold)

            if len(xs) == 0:
                return None

            candidates = [(float(res_main[y, x]), x, y) for x, y in zip(xs, ys)]
            candidates.sort(key=lambda t: t[0], reverse=True)

            checked = set()
            checked_count = 0

            for main_score, x, y in candidates:
                key = (x // 8, y // 8)
                if key in checked:
                    continue
                checked.add(key)

                checked_count += 1
                if checked_count > max_candidates:
                    break

                pad = 8
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(screen_gray.shape[1], x + w_m + pad)
                y2 = min(screen_gray.shape[0], y + h_m + pad)

                sub_roi = screen_gray[y1:y2, x1:x2]
                if sub_roi.shape[0] < h_s or sub_roi.shape[1] < w_s:
                    continue

                res_sub = cv2.matchTemplate(sub_roi, sub_tpl, cv2.TM_CCOEFF_NORMED)
                sub_score = cv2.minMaxLoc(res_sub)[1]

                if main_score >= verify_threshold and sub_score >= sub_threshold:
                    cx = x + w_m // 2
                    cy = y + h_m // 2
                    if region:
                        cx += region[0]
                        cy += region[1]
                    # [New Feature]: Detailed scores for printing stable version combination matching
                    `self.log(f"[StableMatch] Hit: {main_path}+{sub_path} | Main graph: {main_score:.3f} (must be >{verify_threshold}) | Element: {sub_score:.3f} (must be >{sub_threshold})")`
                    return (cx, cy)

            return None

        except Exception as e:
            self.log(f"find_image_with_element_stable recognition error: {e}")
            return None
    def find_image_with_element_multi(self, main_path, sub_path, region=None, fast_mode=True,
        main_threshold=0.60, like_threshold=0.75, final_threshold=0.72, mask_areas=None):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region, mask_areas=mask_areas)
            screen_gray = self.to_gray_image(screen_bgr)
            screen_edge = self.to_edge_image(screen_bgr)

            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            for scale in scales_to_try:
                main_tpl_c, _ = self.get_scaled_template(main_path, scale)
                sub_tpl_c, _ = self.get_scaled_template(sub_path, scale)

                if main_tpl_c is None or sub_tpl_c is None:
                    continue

                main_tpl_gray = self.to_gray_image(main_tpl_c)
                main_tpl_edge = self.to_edge_image(main_tpl_c)

                h_m, w_m = main_tpl_c.shape[:2]
                if h_m < 5 or w_m < 5:
                    continue
                if h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
                    continue

                # Use a colored main template to find candidates first, lowering the threshold.
                res_main = cv2.matchTemplate(screen_bgr, main_tpl_c, cv2.TM_CCOEFF_NORMED)
                # Instead of relying solely on >= main_threshold for hard slicing, we now select the top N high-scoring candidates.
                flat = res_main.ravel()
                if flat.size == 0:
                    continue
                top_k = min(80, flat.size) # Adjustable, start with 80
                idxs = np.argpartition(flat, -top_k)[-top_k:]
                points = []
                for idx in idxs:
                    y, x = np.unravel_index(idx, res_main.shape)
                    score = res_main[y, x]
                    # Set a very low baseline to prevent too many garbage collection points.
                    if score < max(0.55, main_threshold - 0.12):
                        continue
                    points.append((x, y, score))
                # Sort by y and x first to ensure visual order.
                points.sort(key=lambda p: (p[1], p[0]))

                checked_points = set()

                for pt in points:
                    x, y, base_score = pt

                    # Deduplication to avoid counting the same vehicle multiple times.
                    key = (x // 10, y // 10)
                    if key in checked_points:
                        continue
                    checked_points.add(key)

                    roi_bgr = screen_bgr[y:y + h_m, x:x + w_m]
                    roi_gray = screen_gray[y:y + h_m, x:x + w_m]
                    roi_edge = screen_edge[y:y + h_m, x:x + w_m]

                    if roi_bgr.shape[:2] != main_tpl_c.shape[:2]:
                        continue

                    # 4D Scoring System (Anti-HDR Core)
                    color_score = self.match_template_score(roi_bgr, main_tpl_c)
                    gray_score = self.match_template_score(roi_gray, main_tpl_gray)
                    edge_score = self.match_template_score(roi_edge, main_tpl_edge)

                    roi_center = self.crop_center_ratio(roi_bgr, ratio=0.6)
                    tpl_center = self.crop_center_ratio(main_tpl_c, ratio=0.6)
                    center_score = self.match_template_score(roi_center, tpl_center)

                    # Tag matching (NEW tag or author-liked tag)
                    pad = 5
                    sub_roi = screen_bgr[
                        max(0, y - pad):min(screen_bgr.shape[0], y + h_m + pad),
                        max(0, x - pad):min(screen_bgr.shape[1], x + w_m + pad),
                    ]
                    like_score = self.match_template_score(sub_roi, sub_tpl_c)

                    if like_score < like_threshold:
                        continue

                    # Calculate the total score
                    final_score = (
                        color_score * 0.30 +
                        gray_score * 0.20 +
                        edge_score * 0.20 +
                        center_score * 0.15 +
                        like_score * 0.15
                    )

                    curr_pos = (
                        x + w_m // 2 + (region[0] if region else 0),
                        y + h_m // 2 + (region[1] if region else 0),
                    )

                    # If it passes, return immediately (because it has already been sorted, the first one to pass must be the first target in the top left corner).
                    if final_score >= final_threshold:
                        self.log(
                            f"[MultiMatch] Lock target: {main_path}+{sub_path} | "
                            f"Comprehensive: {final_score:.3f} | Color: {color_score:.3f} | "
                            f"grayscale: {gray_score:.3f} | edge: {edge_score:.3f} | "
                            f"center: {center_score:.3f} | tag: {like_score:.3f}"
                        )
                        return curr_pos

            return None

        except Exception as e:
            self.log(f"find_image_with_element_multi 异常: {e}")
            return None
    
    def find_image_with_element_fast(self, main_path, sub_path, region=None, threshold=0.70, sub_threshold=0.70):
        if not self.is_running:
            return None

        try:
            screen = pyautogui.screenshot(region=region)
            screen_gray = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2GRAY)

            main_tpl = self.load_template_gray(main_path)
            sub_tpl = self.load_template_gray(sub_path)

            if main_tpl is None or sub_tpl is None:
                return None

            h_m, w_m = main_tpl.shape[:2]
            h_s, w_s = sub_tpl.shape[:2]

            if h_m > screen_gray.shape[0] or w_m > screen_gray.shape[1]:
                return None

            res_main = cv2.matchTemplate(screen_gray, main_tpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res_main >= threshold)

            checked = set()

            for pt in zip(*loc[::-1]):
                x, y = pt

                # Remove duplicates to avoid too many adjacent duplicates
                key = (x // 10, y // 10)
                if key in checked:
                    continue
                checked.add(key)

                x1 = max(0, x - 5)
                y1 = max(0, y - 5)
                x2 = min(screen_gray.shape[1], x + w_m + 5)
                y2 = min(screen_gray.shape[0], y + h_m + 5)

                sub_roi = screen_gray[y1:y2, x1:x2]

                if sub_roi.shape[0] < h_s or sub_roi.shape[1] < w_s:
                    continue

                res_sub = cv2.matchTemplate(sub_roi, sub_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val_sub, _, _ = cv2.minMaxLoc(res_sub)

                if max_val_sub >= sub_threshold:
                    cx = x + w_m // 2
                    cy = y + h_m // 2
                    if region:
                        cx += region[0]
                        cy += region[1]
                    # [New Feature]: Print Quick Match mode score
                    main_score = res_main[y, x]
                    `self.log(f"[FastMatch] Hit: {main_path}+{sub_path} | Main graph: {main_score:.3f} (must be >{threshold}) | Element: {max_val_sub:.3f} (must be >{sub_threshold})")`
                    return (cx, cy)

            return None

        except Exception as e:
            self.log(f"find_image_with_element_fast 异常: {e}")
            return None

    def wait_for_image_with_element_multi(self, main_path, sub_path, region=None, fast_mode=True,
        main_threshold=0.60, like_threshold=0.75,
        final_threshold=0.72, timeout=30, interval=0.4):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element_multi(
                main_path=main_path,
                sub_path=sub_path,
                region=region,
                fast_mode=fast_mode,
                main_threshold=main_threshold,
                like_threshold=like_threshold,
                final_threshold=final_threshold
            )
            if pos:
                return pos

            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)

        return None

    def load_template_transparent(self, template_path):
        "Specifically loads images with an alpha transparency channel."
        actual_path = get_img_path(template_path)
        cache_key = ("transparent", actual_path)
        if not hasattr(self, "template_transparent_cache"):
            self.template_transparent_cache = {}
        if cache_key in self.template_transparent_cache:
            return self.template_transparent_cache[cache_key]
            
        # Note the cv2.IMREAD_UNCHANGED here; it preserves the alpha channel (BGRA).
        tpl = cv2.imread(actual_path, cv2.IMREAD_UNCHANGED)
        if tpl is not None:
            self.template_transparent_cache[cache_key] = tpl
        return tpl
    def find_image_transparent(self, template_path, region=None, threshold=0.70, fast_mode=True):
        "Matching with alpha channel: Completely ignores transparent backgrounds and only matches the main image content."
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            tpl_bgra = self.load_template_transparent(template_path)
            
            if tpl_bgra is None:
                return None
            # If the image does not have an alpha channel (not 4 channels), downgrade to normal matching.
            if tpl_bgra.shape[2] != 4:
                return self.find_image_in_screen(screen_bgr, template_path, region, threshold, fast_mode)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)
            for scale in scales_to_try:
                # Scaling up the original image with an alpha channel
                if scale == 1.0:
                    tpl_scaled = tpl_bgra.copy()
                else:
                    tpl_scaled = cv2.resize(tpl_bgra, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                h, w = tpl_scaled.shape[:2]
                if h < 5 or w < 5 or h > screen_bgr.shape[0] or w > screen_bgr.shape[1]:
                    continue
                # Separate the BGR color layer and the Alpha transparent mask layer
                tpl_bgr = tpl_scaled[:, :, :3]
                alpha_mask = tpl_scaled[:, :, 3]
                                # Core Magic: Matches with masks! Transparent areas do not participate in scoring!
                res = cv2.matchTemplate(screen_bgr, tpl_bgr, cv2.TM_CCOEFF_NORMED, mask=alpha_mask)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= threshold:
                    # [New Feature]: Match logs with transparent channel
                    self.log(f"[AlphaMatch] Hit (ignoring background): {template_path} | Score: {max_val:.3f} (threshold {threshold}) | Scaling: {scale:.3f}")
                    return (
                        max_loc[0] + w // 2 + (region[0] if region else 0),
                        max_loc[1] + h // 2 + (region[1] if region else 0),
                    )
            return None
        except Exception as e:
            self.log(f"find_image_transparent exception: {e}")
            return None
    def wait_for_image_transparent(self, template_path, region=None, threshold=0.70, timeout=30, interval=0.4, fast_mode=True):
        "Waiting for an image with a transparent background"
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_transparent(template_path, region, threshold, fast_mode)
            if pos:
                return pos
            time.sleep(interval)
        return None
    def wait_for_image_with_element_stable(
        self,
        main_path,
        sub_path,
        region=None,
        main_threshold=0.60,
        verify_threshold=0.72,
        sub_threshold=0.70,
        max_candidates=15,
        timeout=3,
        interval=0.2
    ):
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element_stable(
                main_path=main_path,
                sub_path=sub_path,
                region=region,
                main_threshold=main_threshold,
                verify_threshold=verify_threshold,
                sub_threshold=sub_threshold,
                max_candidates=max_candidates
            )
            if pos:
                return pos
            time.sleep(interval)
        return None
    def wait_for_image_with_element_fast(
        self,
        main_path,
        sub_path,
        region=None,
        threshold=0.70,
        sub_threshold=0.70,
        timeout=4,
        interval=0.25
    ):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element_fast(
                main_path=main_path,
                sub_path=sub_path,
                region=region,
                threshold=threshold,
                sub_threshold=sub_threshold
            )
            if pos:
                return pos

            time.sleep(interval)

        return None

    # ==========================================
    # --- 【Ultimate Security Lock V5.1】: Exclusivity + Precision Sniping Adjustment in the Bottom Right Corner + Forced Left-to-Right Targeting ---
    # ==========================================
    def find_image_ultimate_safe(self, main_path, anti_path, region=None, main_threshold=0.80, anti_threshold=0.65, mask_areas=None):
        if not self.is_running: return None
        try:
            screen_bgr = self.capture_region(region, mask_areas=mask_areas)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)

            scales_to_try = self.get_scales_to_try(fast_mode=True)

            for scale in scales_to_try:
                main_tpl_bgr, _ = self.get_scaled_template(main_path, scale)
                anti_tpl_bgr = None
                if anti_path:
                    anti_tpl_bgr, _ = self.get_scaled_template(anti_path, scale)
                if main_tpl_bgr is None:
                    continue
                if anti_path and anti_tpl_bgr is None:
                    continue
                
                main_tpl_gray = cv2.cvtColor(main_tpl_bgr, cv2.COLOR_BGR2GRAY)
                h_m, w_m = main_tpl_bgr.shape[:2]
                h_a, w_a = anti_tpl_bgr.shape[:2]

                if h_m < 10 or w_m < 10 or h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
                    continue

                # 1. Basic Color Screening
                res_main = cv2.matchTemplate(screen_bgr, main_tpl_bgr, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res_main >= main_threshold)

                
                points = list(zip(*loc[::-1]))
                # Force sorting based on X coordinate (from left to right), ignoring top and bottom rows.
                points.sort(key=lambda p: (p[1] // 50, p[0]))
                
                checked = set()
                for pt in points:
                    x, y = pt
                    if (x // 10, y // 10) in checked: continue
                    checked.add((x // 10, y // 10))

                    base_score = res_main[y, x]
                    
                    roi_bgr = screen_bgr[y:y+h_m, x:x+w_m]
                    roi_gray = screen_gray[y:y+h_m, x:x+w_m]
                    if roi_bgr.shape[:2] != main_tpl_bgr.shape[:2]: continue

                    # ==================================
                    # Defense Line 1: Exclusivity Check
                    # ==================================
                    if anti_path and anti_tpl_bgr is not None:
                        h_a, w_a = anti_tpl_bgr.shape[:2]
                        pad_anti = 10
                        roi_y1, roi_y2 = max(0, y - pad_anti), min(screen_bgr.shape[0], y + h_m + pad_anti)
                        roi_x1, roi_x2 = max(0, x - pad_anti), min(screen_bgr.shape[1], x + w_m + pad_anti)
                        anti_roi = screen_bgr[roi_y1:roi_y2, roi_x1:roi_x2]
                        if anti_roi.shape[0] >= h_a and anti_roi.shape[1] >= w_a:
                            res_anti = cv2.matchTemplate(anti_roi, anti_tpl_bgr, cv2.TM_CCOEFF_NORMED)
                            _, anti_score, _, _ = cv2.minMaxLoc(res_anti)
                            if anti_score >= anti_threshold:
                                self.log(f"[Exclusive Interception]: Exclusion graph ({anti_score:.2f}) found, abandon target.")
                                continue

                    # ==================================
                    # Defense Line 2: Top Text
                    # ==================================
                    top_h = int(h_m * 0.25)
                    tpl_top = main_tpl_gray[:top_h, :]
                    
                    score_top = 0.0
                    pad_slide = 5 
                    if top_h > pad_slide*2 and w_m > pad_slide*2:
                        tpl_top_core = tpl_top[pad_slide:-pad_slide, pad_slide:-pad_slide]
                        search_top = roi_gray[:int(h_m * 0.35), :]
                        if search_top.shape[0] >= tpl_top_core.shape[0] and search_top.shape[1] >= tpl_top_core.shape[1]:
                            res_top = cv2.matchTemplate(search_top, tpl_top_core, cv2.TM_CCOEFF_NORMED)
                            _, score_top, _, _ = cv2.minMaxLoc(res_top)

                    # ==================================
                    # Defense Line 3: [Bottom Right Corner]
                    # ==================================
                    bottom_h = int(h_m * 0.25)
                    right_w = int(w_m * 0.35)
                    tpl_pi_box = main_tpl_bgr[h_m - bottom_h:, w_m - right_w:]

                    score_bot = 0.0
                    if bottom_h > pad_slide*2 and right_w > pad_slide*2:
                        tpl_pi_core = tpl_pi_box[pad_slide:-pad_slide, pad_slide:-pad_slide]
                        search_y1 = h_m - int(h_m * 0.35)
                        search_x1 = w_m - int(w_m * 0.45)
                        search_bot = roi_bgr[search_y1:, search_x1:]
                        
                        if search_bot.shape[0] >= tpl_pi_core.shape[0] and search_bot.shape[1] >= tpl_pi_core.shape[1]:
                            res_bot = cv2.matchTemplate(search_bot, tpl_pi_core, cv2.TM_CCOEFF_NORMED)
                            _, score_bot, _, _ = cv2.minMaxLoc(res_bot)

                    if base_score >= 0.76 and score_top >= 0.75 and score_bot >= 0.85:
                        self.log(f"[Ultimate Safety - Pass]: Target locked! Total score:{base_score:.3f} | Top car name:{score_top:.2f} | Bottom right tuning:{score_bot:.2f}")
                        return (x + w_m // 2 + (region[0] if region else 0), y + h_m // 2 + (region[1] if region else 0))
                    else:
                        pass # Silent interception, continue searching for the next coordinate.

            return None
        except Exception as e:
            self.log(f"ultimate_safe exception: {e}")
            return None
    def wait_for_image_ultimate_safe(self, main_path, anti_path, region=None, main_threshold=0.80, anti_threshold=0.65, timeout=3, interval=0.2, mask_areas=None):
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_ultimate_safe(main_path, anti_path, region, main_threshold, anti_threshold, mask_areas=mask_areas)
            if pos: return pos
            time.sleep(interval)
        return None
    def find_image_smart(self, template_path, primary_region=None, fallback_region=None, threshold=0.75, fast_mode=True):
        if primary_region:
            pos = self.find_image(template_path, region=primary_region, threshold=threshold, fast_mode=fast_mode)
            if pos:
                return pos

        if fallback_region:
            return self.find_image(template_path, region=fallback_region, threshold=threshold, fast_mode=fast_mode)

        return None
    def to_gray_image(self, img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    def to_edge_image(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        edge = cv2.Canny(blur, 50, 150)
        return edge
    def crop_center_ratio(self, img, ratio=0.6):
        h, w = img.shape[:2]
        ch = int(h * ratio)
        cw = int(w * ratio)
        y1 = max(0, (h - ch) // 2)
        x1 = max(0, (w - cw) // 2)
        return img[y1:y1 + ch, x1:x1 + cw]
    def find_image_gray(self, template_path, region=None, threshold=0.75, fast_mode=True, invert_mode=False):
        """
        Pure grayscale UI search, supports multi-resolution scaling + optional flip mode
        parameter:
            template_path (str): Template image path
            region (tuple|list|None): The search area, usually in the format (x, y, w, h). None indicates full screen/default area.
            threshold (float): Matching threshold, typically ranging from 0 to 1, with higher values ​​indicating stricter matching.
            fast_mode (bool): Whether to use fast zoom search mode, True = less zoom ratio, False = more zoom ratio
            invert_mode (bool): Whether to enable invert mode. When True, it will match both the original image and the inverted image (it can recognize both white text on a black background and black text on a white background).
        return:
            tuple|None:
                - Returns the coordinates (x, y) of the center point of the match when found.
                - Return None if not found
        """
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            # [New Feature] Templates are read only once to avoid repeated loading for each scale.
            tpl_gray_raw = self.load_template_gray(template_path)
            if tpl_gray_raw is None:
                return None

            for scale in scales_to_try:
                # [Change] Copy from the original template to avoid repeated resizing and pollution.
                tpl_gray = tpl_gray_raw
                if scale != 1.0:
                    tpl_gray = cv2.resize(tpl_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                h, w = tpl_gray.shape[:2]
                if h < 5 or w < 5 or h > screen_gray.shape[0] or w > screen_gray.shape[1]:
                    continue

                # ==============================
                # Original Image Matching
                # ==============================
                res = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= threshold:
                    self.log(f"[GrayMatch] Hit: {template_path} | Mode: Original | Grayscale Score: {max_val:.3f} (threshold {threshold}) | Scale: {scale:.3f}")
                    return (
                        max_loc[0] + w // 2 + (region[0] if region else 0),
                        max_loc[1] + h // 2 + (region[1] if region else 0),
                    )

                # ==============================
                # [New Feature] Flip Mode: Inverted Template Matching
                # ==============================
                if invert_mode:
                    tpl_inv = 255 - tpl_gray
                    res_inv = cv2.matchTemplate(screen_gray, tpl_inv, cv2.TM_CCOEFF_NORMED)
                    _, max_val_inv, _, max_loc_inv = cv2.minMaxLoc(res_inv)
                    if max_val_inv >= threshold:
                        self.log(f"[GrayMatch] Hit: {template_path} | Mode: Invert | Grayscale Score: {max_val_inv:.3f} (threshold {threshold}) | Scale: {scale:.3f}")
                        return (
                            max_loc_inv[0] + w // 2 + (region[0] if region else 0),
                            max_loc_inv[1] + h // 2 + (region[1] if region else 0),
                        )

            return None
        except Exception as e:
            self.log(f"find_image_gray exception: {e}")
            return None
    def find_any_image_gray(self, image_list, region=None, threshold=0.75, fast_mode=True, invert_mode=False):
        """
        Pure grayscale multi-image search, supports multi-resolution scaling + optional flip mode
        parameter:
            image_list (list): A list of template image paths, such as ["a.png", "b.png", "c.png"].
            region (tuple|list|None): The search area, usually in the format (x, y, w, h). None indicates full screen/default area.
            threshold (float): Matching threshold, typically ranging from 0 to 1, with higher values ​​indicating stricter matching.
            fast_mode (bool): Whether to use fast zoom search mode, True = less zoom ratio, False = more zoom ratio
            invert_mode (bool): Whether to enable invert mode. When True, it will match both the original image and the inverted image (it can recognize both white text on a black background and black text on a white background).
        return:
            tuple|None:
                - Returns the coordinates (x, y) of the center point of the match when any image is found.
                - If none can be found, return None.
        """
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            for img_path in image_list:
                # [New Feature] Templates are read only once
                tpl_gray_raw = self.load_template_gray(img_path)
                if tpl_gray_raw is None:
                    continue

                for scale in scales_to_try:
                    # [Modification] Copy from the original template
                    tpl_gray = tpl_gray_raw
                    if scale != 1.0:
                        tpl_gray = cv2.resize(tpl_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                    h, w = tpl_gray.shape[:2]
                    if h < 5 or w < 5 or h > screen_gray.shape[0] or w > screen_gray.shape[1]:
                        continue

                    # ==============================
                    # Original Image Matching
                    # ==============================
                    res = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= threshold:
                        self.log(f"[GrayMatchAny] Hit: {img_path} | Mode: Original | Grayscale Score: {max_val:.3f} (threshold {threshold}) | Scale: {scale:.3f}")
                        return (
                            max_loc[0] + w // 2 + (region[0] if region else 0),
                            max_loc[1] + h // 2 + (region[1] if region else 0),
                        )

                    # ==============================
                    # [New Feature] Flip Mode: Inverted Template Matching
                    # ==============================
                    if invert_mode:
                        tpl_inv = 255 - tpl_gray
                        res_inv = cv2.matchTemplate(screen_gray, tpl_inv, cv2.TM_CCOEFF_NORMED)
                        _, max_val_inv, _, max_loc_inv = cv2.minMaxLoc(res_inv)
                        if max_val_inv >= threshold:
                            self.log(f"[GrayMatchAny] Hit: {img_path} | Mode: Invert | Grayscale Score: {max_val_inv:.3f} (threshold {threshold}) | Scale: {scale:.3f}")
                            return (
                                max_loc_inv[0] + w // 2 + (region[0] if region else 0),
                                max_loc_inv[1] + h // 2 + (region[1] if region else 0),
                            )

            return None
        except Exception as e:
            self.log(f"find_any_image_gray exception: {e}")
            return None

    def wait_for_any_image_gray(self, image_list, region=None, threshold=0.75, timeout=30, interval=0.3, fast_mode=True, invert_mode=False):
        """
        Waiting for any one of the multiple grayscale images to appear
        parameter:
            image_list (list): A list of template image paths, such as ["a.png", "b.png", "c.png"].
            region (tuple|list|None): The search area, usually in the format (x, y, w, h). None indicates full screen/default area.
            threshold (float): Matching threshold, typically ranging from 0 to 1, with higher values ​​indicating stricter matching.
            timeout (int|float): Maximum wait time, in seconds.
            interval (int|float): The waiting interval after each failed detection, in seconds.
            fast_mode (bool): Whether to use fast zoom search mode, True = less zoom ratio, False = more zoom ratio
            invert_mode (bool): Whether to enable invert mode. When True, both the original and inverted images will be matched.
        return:
            tuple|None:
                - If a match is found before the timeout, return the coordinates (x, y) of the center point.
                - Timeout, no results found, returns None
        """
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_any_image_gray(
                image_list,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode,
                invert_mode=invert_mode # [Added]
            )
            if pos:
                return pos
            
            # Safety waiting mechanism to prevent freezing
            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)
        return None
    def wait_for_image_gray(self, template_path, region=None, threshold=0.75, timeout=30, interval=0.3, fast_mode=True, invert_mode=False):
        """
        Waiting for a single grayscale image to appear
        parameter:
            template_path (str): Template image path
            region (tuple|list|None): The search area, usually in the format (x, y, w, h). None indicates full screen/default area.
            threshold (float): Matching threshold, typically ranging from 0 to 1, with higher values ​​indicating stricter matching.
            timeout (int|float): Maximum wait time, in seconds.
            interval (int|float): The waiting interval after each failed detection, in seconds.
            fast_mode (bool): Whether to use fast zoom search mode, True = less zoom ratio, False = more zoom ratio
            invert_mode (bool): Whether to enable invert mode. When True, both the original and inverted images will be matched.
        return:
            tuple|None:
                - If a match is found before the timeout, return the coordinates (x, y) of the center point.
                - Timeout, no results found, returns None
        """
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_gray(
                template_path,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode,
                invert_mode=invert_mode # [Added]
            )
            if pos:
                return pos
            
            # Safety Waiting Mechanism
            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)
        return None

    def find_any_image_transparent(self, image_list, region=None, threshold=0.70, fast_mode=True):
        "Find any one of multiple images with an alpha channel"
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            for template_path in image_list:
                tpl_bgra = self.load_template_transparent(template_path)
                if tpl_bgra is None:
                    continue
                
                # If the image does not have an alpha channel, it will be downgraded to a normal match.
                if tpl_bgra.shape[2] != 4:
                    pos = self.find_image_in_screen(screen_bgr, template_path, region, threshold, fast_mode)
                    if pos: return pos
                    continue

                for scale in scales_to_try:
                    if scale == 1.0:
                        tpl_scaled = tpl_bgra.copy()
                    else:
                        tpl_scaled = cv2.resize(tpl_bgra, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                    h, w = tpl_scaled.shape[:2]
                    if h < 5 or w < 5 or h > screen_bgr.shape[0] or w > screen_bgr.shape[1]:
                        continue

                    tpl_bgr = tpl_scaled[:, :, :3]
                    alpha_mask = tpl_scaled[:, :, 3]

                    res = cv2.matchTemplate(screen_bgr, tpl_bgr, cv2.TM_CCOEFF_NORMED, mask=alpha_mask)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)

                    if max_val >= threshold:
                        # [New Feature]: Multiple matching logs with transparent channels
                        self.log(f"[AlphaMatchAny] Hit (ignoring background): {template_path} | Score: {max_val:.3f} (threshold {threshold}) | Scaling: {scale:.3f}")
                        return (
                            max_loc[0] + w // 2 + (region[0] if region else 0),
                            max_loc[1] + h // 2 + (region[1] if region else 0),
                        )
            return None
        except Exception as e:
            self.log(f"find_any_image_transparent exception: {e}")
            return None

    def wait_for_any_image_transparent(self, image_list, region=None, threshold=0.70, timeout=30, interval=0.4, fast_mode=True):
        "Waiting for any one of the multiple images with a transparent background to appear."
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_any_image_transparent(image_list, region, threshold, fast_mode)
            if pos:
                return pos
            
            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)
        return None
    def wait_for_any_image(self, image_list, region=None, threshold=0.75, timeout=30, interval=0.4, fast_mode=True, log_text=None):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            try:
                screen_bgr = self.capture_region(region)
                for img_path in image_list:
                    pos = self.find_image_in_screen(
                        screen_bgr,
                        img_path,
                        region=region,
                        threshold=threshold,
                        fast_mode=fast_mode
                    )
                    if pos:
                        return pos
            except Exception as e:
                self.log(f"wait_for_any_image 异常: {e}")

            if log_text:
                self.log(log_text)

            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)

        return None

    def wait_for_image(self, template_path, region=None, threshold=0.75, timeout=30, interval=0.4, fast_mode=True, log_text=None):
        return self.wait_for_any_image(
            [template_path],
            region=region,
            threshold=threshold,
            timeout=timeout,
            interval=interval,
            fast_mode=fast_mode,
            log_text=log_text
        )

    def wait_for_image_with_element(self, main_path, sub_path, region=None, threshold=0.85, timeout=30, interval=0.4, fast_mode=True):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element(
                main_path,
                sub_path,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode
            )
            if pos:
                return pos

            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)

        return None

    def match_template_score(self, src, tpl):
        try:
            if tpl is None or src is None:
                return 0.0
            th, tw = tpl.shape[:2]
            sh, sw = src.shape[:2]
            if th < 5 or tw < 5 or th > sh or tw > sw:
                return 0.0
            res = cv2.matchTemplate(src, tpl, cv2.TM_CCOEFF_NORMED)
            return cv2.minMaxLoc(res)[1]
        except Exception:
            return 0.0
    #===============================
    #---Test function-----
    #===============================
    def start_test_find_image(self):
        "F3 Test: Repeatedly calling the original find_image_with_element_multi() function finds a maximum of 12 targets, only moving the mouse without clicking."
        if self.is_running:
            self.log("A task is already running; unable to execute F3 test to find the image.")
            return

        self.is_running = True
        self.is_paused = False
        self.save_config()

        # ====== Switch to Mini Mode to maintain consistency with other testing procedures ======
        self.config_frame.pack_forget()
        self.global_settings_frame.pack_forget()
        self.calc_frame.pack_forget()
        self.top_container.pack_forget()
        if hasattr(self, "bottom_frame"):
            self.bottom_frame.pack_forget()
        self.btn_support.pack_forget()

        self.mini_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.update_running_ui("F3 test image search", 0, 12)
        if hasattr(self, "lbl_mini_loop"):
            self.ui_call(self.lbl_mini_loop.configure, text="Large loop: Test mode")

        self.start_time = time.time()
        self.update_timer()

        self.log("====== Start F3 to test the original second-order image search======")

        def test_runner():
            try:
                if not self.check_and_focus_game():
                    self.log("Failed to focus on the game window, test ended.")
                    return

                found_positions = []
                mask_areas = []

                for i in range(15):
                    if not self.is_running:
                        return
                    self.check_pause()

                    pos = self.find_image_with_element_multi(
                        "newCC.png",
                        "newcartag.png",
                        region = self.regions["full interface"],
                        main_threshold=0.70,
                        like_threshold=0.70,
                        final_threshold=0.70,
                        fast_mode=True,
                        mask_areas=mask_areas
                    )

                    if not pos:
                        self.log(f"{i + 1}th search: No new target found, test ends.")
                        break

                    x, y = int(pos[0]), int(pos[1])

                    duplicated = False
                    for old_x, old_y in found_positions:
                        if abs(x - old_x) <= 80 and abs(y - old_y) <= 80:
                            duplicated = True
                            break

                    region_x, region_y, _, _ = self.regions["All Interfaces"]
                    local_x = x - region_x
                    local_y = y - region_y

                    block_w = 210
                    block_h = 120
                    mask_areas.append((
                        local_x - block_w // 2,
                        local_y - block_h // 2,
                        local_x + block_w // 2,
                        local_y + block_h // 2
                    ))

                    if duplicated:
                        self.log(f"F3 test: Duplicate target ({x}, {y}) detected. Mask has been expanded. Continue searching.")
                        continue

                    found_positions.append((x, y))
                    self.update_running_ui("F3 test image search", len(found_positions), 12)
                    self.log(f"F3 test: found the {len(found_positions)}th target -> ({x}, {y})")
                    self.hw_mouse_move(x, y)
                    time.sleep(0.5)

                self.log(f"F3 test complete, a total of {len(found_positions)} targets found.")

            except Exception as e:
                self.log(f"F3 test exception: {e}")
            finally:
                self.stop_all()

        self.current_thread = threading.Thread(target=test_runner, daemon=True)
        self.current_thread.start()
    # ==========================================
    # --- Module: Pre-running and Loop Run---
    # ==========================================
    def logic_race(self, target_count):
        if self.race_counter >= target_count:
            return True

        self.update_running_ui("Looping through the map", self.race_counter, target_count)

        self.log("Preparing for verification/entering the menu...")
        if not self.enter_menu():
            return False

        self.log("Switching to the Creative Hub...")
        for _ in range(4):
            self.hw_press("pagedown", delay=0.15)
            time.sleep(0.3)

        time.sleep(0.8)


        pos_el = self.wait_for_image_gray(
            "eventlab.png",
            region = self.regions["full interface"],
            threshold=0.7,
            timeout=5,
            interval=0.25,
            fast_mode=True
        )
    
        if not pos_el:
            self.log("eventlab not found")
            return False

        self.game_click(pos_el)
        time.sleep(1.2)

        pos_yg = self.wait_for_image_gray(
            "playenent.png",
            region = self.regions["middle"],
            threshold=0.75,
            timeout=40,
            interval=0.3,
            fast_mode=True
        )
        if not pos_yg:
            self.log("No events found")
            return False

        self.game_click(pos_yg)
        time.sleep(1.5)

        self.hw_press("backspace")
        time.sleep(0.8)
        self.hw_press("up")
        time.sleep(0.4)
        self.hw_press("enter")
        time.sleep(0.8)

        code_text = "".join(c for c in self.entry_share.get() if c.isdigit())
        for char in code_text:
            if not self.is_running:
                return False
            if char in DIK_CODES:
                self.hw_press(char, delay=0.05)
                time.sleep(0.05)

        time.sleep(0.4)
        self.hw_press("enter")
        time.sleep(0.8)
        self.hw_press("down")
        time.sleep(0.3)
        self.hw_press("enter")
        time.sleep(1.5)

        pos_ck = self.wait_for_image_gray(
            "VEI.png",
            region=self.regions["下"],
            threshold=0.75,
            timeout=20,
            interval=1.0,
            fast_mode=True
        )
        if not pos_ck:
            self.log("Connection timed out")
            return False

        self.hw_press("enter")
        time.sleep(2.0)
        self.hw_press("enter")
        time.sleep(2.0)

        pos_target = self.wait_for_image_with_element_multi(
            "skillcar.png",
            "liketag.png",
            region = self.regions["full interface"],
            fast_mode=True,
            main_threshold=0.75,
            like_threshold=0.7,
            final_threshold=0.7,
            timeout=2,
            interval=0.25
        )

        if not pos_target:
            self.log("No target vehicle with liketag found, please select brand again...")
            self.hw_press("backspace")
            time.sleep(1.2)

            found_brand = False
            for _ in range(3):
                if not self.is_running:
                    return False

                pos_brand = self.wait_for_image_gray("skillcarbrand.png", region=self.regions["全界面"], threshold=0.8, timeout=1.2, interval=0.2, fast_mode=True)
                if pos_brand:
                    self.game_click(pos_brand)
                    time.sleep(1.2)
                    found_brand = True
                    break

                self.hw_press("up")
                time.sleep(0.4)

            if not found_brand:
                self.log("Failed to find the vehicle brand for farming after three attempts.")
                return False

            for _ in range(20):
                if not self.is_running:
                    return False

                pos_target = self.wait_for_image_with_element_multi(
                    "skillcar.png",
                    "liketag.png",
                    region = self.regions["full interface"],
                    main_threshold=0.75,
                    like_threshold=0.7,
                    final_threshold=0.7,
                    timeout=2,
                    interval=0.25,
                    fast_mode=True
                )
                if pos_target:
                    break

                for _ in range(4):
                    self.hw_press("right", delay=0.08)
                    time.sleep(0.08)
                time.sleep(0.4)

        if not pos_target:
            self.log("Unable to find any vehicles with the liketag for map clearing on page flipping!")
            return False

        self.game_click(pos_target)
        time.sleep(0.5)
        self.hw_press("enter")
        time.sleep(4.0)

        self.log("Preparation complete, starting the loop to run the graph!")

        while self.race_counter < target_count:
            if not self.is_running:
                return False

            self.log(f"Running the race {self.race_counter + 1}/{target_count}: Finding the starting point of the race...")

            pos = None
            for _ in range(120):
                if not self.is_running:
                    return False

                pos = self.wait_for_any_image_gray(
                    ["start.png", "startw.png"],
                    region=self.regions["bottom left"],
                    threshold=0.75,
                    timeout=0.7,
                    interval=0.2,
                    fast_mode=True
                )
                if pos:
                    break

                self.hw_press("down")
                time.sleep(0.25)

            if not pos:
                self.log("Race start not found, exiting the race.")
                return False

            self.game_click(pos)
            time.sleep(4.0)
            self.hw_key_down("w")
            self.hw_key_down("up") 
            
            # Initialize various timers
            race_start_time = time.time() # Added: Records the start time of the race.
            last_like_chk = time.time()
            last_chk = 0
            finished = False
            timeout_triggered = False # Added: Marks whether the 120-second timeout has been triggered

            driving_keys_held = True # <--- [Added] Mark throttle status

            while self.is_running:
                # ====== 【New】Pause handling logic specifically for map exploration======
                if self.is_paused:
                    if driving_keys_held: # Just entered pause mode, release the accelerator
                        self.hw_key_up("w")
                        self.hw_key_up("up")
                        driving_keys_held = False
                    self.check_pause() # Blocks here
                    # Resume from pause; if the race isn't over yet, press the accelerator again.
                    if self.is_running:
                        self.hw_key_down("w")
                        self.hw_key_down("up")
                        driving_keys_held = True
                        
                    # To prevent the recovery from triggering a timeout, reset the timer.
                    race_start_time = time.time() 
                    last_like_chk = time.time()
                    last_chk = time.time()
                    continue 
                # =========================================
                now = time.time()
                
                # [New Logic]: 120-second timeout anti-freeze detection
                if now - race_start_time > 120.0:
                    self.log("Map timeout (exceeded 120 seconds)! ​​Triggered forced restart of the event logic...")
                    timeout_triggered = True
                    break
                
                # Handle special interfaces/errors in the running map every 3 seconds
                if now - last_like_chk >= 3.0:
                    vram_result = self.check_vramne_during_race()
                    if vram_result is True:
                        self.log("VRAM restoration complete. End the current map running process and hand it over to the outer layer for restoration.")
                        return False
                    elif vram_result is False:
                        self.log("VRAM recovery failed.")
                        return False
                    pos_like = self.find_any_image_gray(
                        ["likeauthor.png", "dislikeauthor.png"],
                        region = self.regions["middle"],
                        threshold=0.70
                    )
                    if pos_like:
                        self.log("Likes detected, Enter key pressed to confirm!")
                        self.hw_press("enter")
                    last_like_chk = now
                
                # Restart after checking every 1 second (if the race is completed normally)
                if now - last_chk >= 1.0:
                    found_restart = self.find_image_gray("restart.png", region=self.regions["下"], threshold=0.75, fast_mode=True)
                    if found_restart:
                        finished = True
                        break
                    last_chk = now
                    
                time.sleep(0.3)
                
            # Whether the game ends normally or exceeds the time limit, you must first release the accelerator and steering wheel.
            self.hw_key_up("w")
            self.hw_key_up("up")

            if not self.is_running:
                return False

            # ====== 【Added】: Perform timeout reset operation ======
            if timeout_triggered:
                time.sleep(0.5)
                self.hw_press("esc")
                time.sleep(1.5) # Wait for the menu animation to load
                
                # Find and click restarta.png
                pos_restarta = self.wait_for_image_gray("restarta.png", region=self.regions["全界面"], threshold=0.70, timeout=4.0, interval=0.3, fast_mode=True)
                if pos_restart:
                    self.log("Found restarta.png, clicked to restart the event...")
                    self.game_click(pos_restarta)
                    time.sleep(1.0)
                    self.hw_press("enter") # Horizon Zero Dawn usually has a confirmation pop-up when restarting events; press Enter to confirm.
                    time.sleep(4.0) # Wait for the black screen reload animation.
                else:
                    self.log("restarta.png not found, trying to continue...")
                    
                # [Key]: Skip the settlement process below and return to the outermost while loop to find start.png again (and do not include race_counter this time).
                continue
            # ========================================

            if not finished:
                return False

            if self.race_counter == target_count - 1:
                self.hw_press("enter")
                time.sleep(2.0)
            else:
                self.hw_press("x")
                time.sleep(0.8)
                self.hw_press("enter")
                time.sleep(2.0)

            self.race_counter += 1
            self.update_running_ui("Looping through the map", self.race_counter, target_count)

        return True

    # ==========================================
    # --- Module: Buying a Car ---
    # ==========================================
    def logic_buy_car(self, target_count):
        if self.car_counter >= target_count:
            return True

        self.update_running_ui("Bulk Car Purchase", self.car_counter, target_count)

        self.log("Preparing for verification/entering the menu...")
        if not self.enter_menu():
            return False

        pos_collectionjournal = self.wait_for_image_transparent(
            "collectionjournal.png",
            region=self.regions["Left"],
            threshold=0.7,
            timeout=30,
            interval=0.4,
            fast_mode=True
        )
        if not pos_collectionjournal:
            self.log("Collection book not found")
            return False

        self.game_click(pos_collectionjournal, double=True)
        time.sleep(1.0)


        pos_masterexplorer = self.wait_for_image(
            "masterexplorer.png",
            region = self.regions["full interface"],
            threshold=0.75,
            timeout=30,
            interval=0.4,
            fast_mode=True
        )
        if not pos_masterexplorer:
            self.log("No exploration found")
            return False

        self.game_click(pos_masterexplorer, double=True)
        time.sleep(0.6)

        pos_carcollection = self.wait_for_image_transparent(
            "carcollection.png",
            region = self.regions["full interface"],
            threshold=0.75,
            timeout=30,
            interval=0.3,
            fast_mode=True
        )
        if not pos_carcollection:
            self.log("No vehicle collection found")
            return False

        self.game_click(pos_carcollection, double=True)
        time.sleep(1.0)

        self.hw_press("backspace")
        time.sleep(0.5)

        brand_pos = None
        for _ in range(5):
            if not self.is_running:
                return False
                

            brand_pos = self.wait_for_any_image_gray(
                ["CCbrand.png"],
                region = self.regions["full interface"],
                threshold=0.75,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if brand_pos:
                break

            self.hw_press("up")
            time.sleep(0.25)

        if not brand_pos:
            self.log("Brand not found")
            return False

        self.game_click(brand_pos)
        time.sleep(0.8)
        self.hw_press("down")
        time.sleep(0.4)

        pos_22b = self.wait_for_image(
            "consumablecar.png",
            region = self.regions["full interface"],
            threshold=0.90,
            timeout=8,
            interval=0.3,
            fast_mode=False
        )
        if not pos_22b:
            self.log("No consumable vehicle found")
            return False

        self.game_click(pos_22b, double=True)
        time.sleep(1.0)

        while self.car_counter < target_count:
            if not self.is_running:
                return False
            
            self.hw_press("space")
            time.sleep(0.6)
            self.move_to_game_coord(5, 5)
            self.hw_press("down")
            time.sleep(0.2)
            self.move_to_game_coord(5, 5)
            self.hw_press("enter")
            time.sleep(0.6)
            self.move_to_game_coord(5, 5)
            self.hw_press("enter")
            time.sleep(0.6)
            self.move_to_game_coord(5, 5)
            self.hw_press("enter")
            time.sleep(0.7)

            self.car_counter += 1
            self.update_running_ui("Bulk Car Purchase", self.car_counter, target_count)

        for _ in range(5):
            if not self.is_running:
                return False
            self.hw_press("esc")
            time.sleep(0.8)

        return True
    # ==========================================
    # --- Module: Lottery ---
    # ==========================================
    def logic_super_wheelspin(self, target_count):
        if self.cj_counter >= target_count:
            return True

        self.update_running_ui("Super Lottery", self.cj_counter, target_count)
        # [New Feature]: Initialize memory page numbers
        if not hasattr(self, 'memory_car_page'):
            self.memory_car_page = 0
        self.log("Preparing for verification/entering the menu...")
        if not self.enter_menu():
            return False

        self.log("Entering Vehicles and Favorites...")
        self.hw_press("pagedown", delay=0.15)
        time.sleep(1.0)

        pos_buycar = self.wait_for_image(
            "BNandUC.png",
            region=self.regions["Left"],
            threshold=0.70,
            timeout=15,
            interval=0.3,
            fast_mode=True
        )
        if not pos_buycar:
            self.log("No new or used car purchases detected")
            return False

        self.game_click(pos_buycar)
        time.sleep(0.8)
        self.hw_press("enter")
        time.sleep(5)


        pos_bs = self.wait_for_any_image_gray(
            ["buyandsell-w.png", "buyandsell-b.png"],
            region=self.regions["Left"],
            threshold=0.75,
            timeout=60,
            interval=0.5,
            fast_mode=True
        )
        if not pos_bs:
            self.log("No buy or sell items found")
            return False

        self.game_click(pos_bs)
        time.sleep(1.0)
        self.hw_press("pagedown", delay=0.15)
        self.log("Entering vehicle interface...")
        time.sleep(0.5)

        while self.cj_counter < target_count:
            if not self.is_running:
                return False
            self.log("Entering my vehicle.")
            self.hw_press("enter")
            time.sleep(2.0)
            self.hw_press("backspace")
            time.sleep(1.0)

            brand_pos = None
            for _ in range(30):
                if not self.is_running:
                    return False

                brand_pos = self.wait_for_any_image_gray(
                    ["CCbrand.png"],
                    region = self.regions["full interface"],
                    threshold=0.75,
                    timeout=0.8,
                    interval=0.2,
                    fast_mode=True
                )
                if brand_pos:
                    break

                self.hw_press("up")
                time.sleep(0.25)

            if not brand_pos:
                self.log("Brand selection failed")
                return False

            self.game_click(brand_pos)
            time.sleep(1.0)
            jump_pages = max(0, self.memory_car_page - 1)
            
            if jump_pages > 0:
                self.log(f"Smart memory triggered: Quickly skip the previous {jump_pages} pages...")
                for _ in range(jump_pages):
                    if not self.is_running: return False
                    for _ in range(4):
                        self.hw_press("right", delay=0.06)
                        time.sleep(0.1)
                    time.sleep(0.15) # Give a little bit of animation buffer time
            pos_target = None
            found_car = False
            current_page = jump_pages # Record the current page number
            
            # Maximum number of page turns minus the number of pages already skipped
            for _ in range(85 - jump_pages):
                if not self.is_running:
                    return False
                pos_target = self.wait_for_image_with_element_multi(
                    "newCC.png",
                    "newcartag.png",
                    region = self.regions["full interface"],
                    main_threshold=0.70, # Anti-HDR core: Lowering the first threshold
                    like_threshold=0.70,
                    final_threshold=0.70,
                    timeout=1.5,
                    interval=0.2,
                    fast_mode=True
                )
                
                if pos_target:
                    self.game_click(pos_target)
                    found_car = True
                    # Remember which page you found the car on this time.
                    self.memory_car_page = current_page 
                    self.log(f"Target vehicle locked! Current page number logged: {current_page}")
                    break
                    
                # Turn to the next page
                for _ in range(4):
                    self.hw_press("right", delay=0.06)
                    time.sleep(0.1)
                time.sleep(0.4)
                current_page += 1
            if not found_car:
                self.log("No target vehicle found in the list, resetting memory page number.")
                self.memory_car_page = 0 # If not found, it means the car has been wiped clean, so clear the memory.
                return False
            time.sleep(1.2)
            self.log("Attempting to find the 'Get on board' button...")

            pos_rc = None
            pos_rc = self.wait_for_image_gray("rc.png", region=self.regions["全界面"], threshold=0.70, timeout=0.5, interval=0.1, fast_mode=True)
            
            if pos_rc:
                self.log("Click to get on the bus")
                self.game_click(pos_rc)
                time.sleep(2.0) # Wait for the bus to load after clicking.
            else:
                self.log("Enter to board")
                self.hw_press("enter")
                time.sleep(1.0)
                self.hw_press("enter")
                time.sleep(1.0)


            pos_sjy = None
            for _ in range(20):
                if not self.is_running:
                    return False

                pos_sjy = self.find_any_image_gray(["UandT-w.png", "UandT-b.png"], region=self.regions["左下"], threshold=0.70)
                if pos_sjy:
                    break

                self.hw_press("esc")
                time.sleep(0.5)

            if not pos_sjy:
                self.log("Upgrade page not found")
                return False

            self.game_click(pos_sjy)
            time.sleep(0.5)

            pos_cls = self.wait_for_any_image_gray(
                ["clsldcnw.png", "clsldcnb.png"],
                region=self.regions["bottom left"],
                threshold=0.70,
                timeout=20
            )
            if not pos_cls:
                self.log("No vehicle proficiency found")
                return False
            self.game_click(pos_cls)
            time.sleep(1.5)

            pos_exp = self.wait_for_any_image(
                ["EXPwU.png"],
                region=self.regions["Left"],
                threshold=0.75,
                timeout=1.5,
                interval=0.3,
                fast_mode=True
            )

            if pos_exp:
                self.log("This vehicle skill has already been activated, skipping the count")
            else:
                time.sleep(1.0)
                self.hw_press("enter")
                time.sleep(1.5)

                for dk in self.config["skill_dirs"]:
                    if not self.is_running:
                        return False
                    self.hw_press(dk)
                    time.sleep(0.2)
                    self.hw_press("enter")
                    time.sleep(1.2)

                spne_found = self.find_image_gray("SPNE.png", region=self.regions["全界面"], threshold=0.70)
                
                if spne_found:
                    self.log("No skill points available or all skills have been used up, lottery ends early!")
                    time.sleep(1.0)
                    self.hw_press("enter")
                    time.sleep(0.8)
                    self.hw_press("esc")
                    time.sleep(1.0)
                    self.hw_press("esc")
                    time.sleep(1.0)
                    self.hw_press("esc")
                    time.sleep(1.0)
                    return True
                self.cj_counter += 1
                self.update_running_ui("Super Lottery", self.cj_counter, target_count)

            self.hw_press("esc")
            time.sleep(1.2)
            self.hw_press("esc")
            time.sleep(0.8)
            self.hw_press("up", delay=0.15)
            time.sleep(0.8)
        self.hw_press("esc")
        time.sleep(1.2)
        self.hw_press("esc")
        time.sleep(1.2)
        return True
    # ==========================================
    # --- Module: Remove Vehicle ---
    # ==========================================
    def sell_consumable_car(self, target_count):
        if self.sc_count >= target_count:
            return True

        self.update_running_ui("Removed vehicle", self.sc_count, target_count)

        self.log("Preparing for verification/entering the menu!!! Please manually verify the vehicle before proceeding with automated removal.")
        if not self.enter_menu():
            return False

        self.log("Entering Vehicles and Favorites!!! Please manually verify that a vehicle has been successfully removed before proceeding with automated removal.")
        self.hw_press("pagedown", delay=0.15)
        time.sleep(1.0)

        pos_buycar = self.wait_for_image("BNandUC.png", region=self.regions["左"], threshold=0.70, timeout=12, interval=0.3, fast_mode=True)
        if not pos_buycar:
            self.log("No new or used car purchases detected")
            return False

        self.game_click(pos_buycar)
        time.sleep(0.8)
        self.hw_press("enter")
        time.sleep(5)

        pos_bs = self.wait_for_any_image(["buyandsell-w.png", "buyandsell-b.png"], region=self.regions["上"], threshold=0.75, timeout=40, interval=0.5, fast_mode=True)
        if not pos_bs:
            self.log("No buy or sell items found")
            return False

        self.game_click(pos_bs)
        time.sleep(1.0)

        self.hw_press("pagedown", delay=0.15)
        time.sleep(1.0)

        self.hw_press("enter") # Enter my vehicle
        time.sleep(2.0)
        #Choose one to collect
        self.hw_press("y") 
        time.sleep(1.0)
        self.hw_press("enter")
        time.sleep(0.8)
        self.hw_press("esc") 
        time.sleep(1.5)
        #Driving my collection car
        self.hw_press("enter")
        time.sleep(0.8)
        self.move_to_game_coord(5, 5)
        time.sleep(0.2)

        pos = self.wait_for_image("rc.png", region=self.regions["全界面"], threshold=0.65, timeout=5, interval=0.2, fast_mode=True)
        if pos:
            self.log("Found the boarding route, clicked")
            self.game_click(pos)
            time.sleep(2.0)
        else:
            self.log("The vehicle has been driven, or no image was found. Execute ESC twice")
            self.hw_press("esc")
            time.sleep(1.5)
            self.hw_press("esc")
        time.sleep(2.0)

        found = False
        for i in range(60):
            if not self.is_running:
                return False

            pos = self.wait_for_any_image(["buyandsell-b.png", "buyandsell-w.png"], region=self.regions["上"], threshold=0.70, timeout=0.8, interval=0.2, fast_mode=True)
            if pos:
                self.log(f"The {i + 1}th purchase and sale were detected, and the vehicle interface was entered")
                self.hw_press("enter")
                found = True
                break
            self.log(f"No purchase or sale detected for {i + 1}th time, will try again later")
            time.sleep(1.0)
        if not found:
            self.log("No buy or sell orders found within the last 60 attempts")
            return False
        
        time.sleep(1.5)
        # Switch sort: Most recently obtained
        self.hw_press("x")
        time.sleep(0.5)
        #Mouse Reset
        self.move_to_game_coord(5, 5)
        #Select the most recently received
        self.log("Switch to the most recently retrieved sort...")
        for _ in range(6):
            if not self.is_running:
                return False
            self.hw_press("down")
            time.sleep(0.25)
        time.sleep(0.2)
        self.hw_press("enter")
        time.sleep(1.2)
        self.log("Go back to the most recently accessed point")
        # Return to the top of the list
        self.hw_press("backspace")
        time.sleep(0.8)
        self.hw_press("enter")
        time.sleep(1.5)

        self.log("Starting to delete recently acquired vehicles!!! Please manually confirm removal")

        while self.sc_count < target_count:
            self.log(f"is_running = {self.is_running}")
            if not self.is_running:
                return False
            # Enter the current vehicle
            self.hw_press("enter")
            time.sleep(1.2)
            #Jump to Remove from Garage
            for _ in range(6):
                if not self.is_running:
                    return False
                self.hw_press("down")
                time.sleep(0.2)
            self.hw_press("enter")
            time.sleep(0.5)
            #Select "Hmm" from the list below.
            self.hw_press("down")
            time.sleep(0.3)
            #Confirm "Mmm"
            self.hw_press("enter")
            time.sleep(0.8)
            self.sc_count += 1
            self.log(f"Attempted to delete vehicle {self.sc_count}/{target_count}")

        for _ in range(3):
            if not self.is_running:
                return False
            self.hw_press("esc")
            time.sleep(1.0)

        return True
    
    def find_and_remove_consumable_car(self, target_count):
        if self.sc_count >= target_count:
            return True
        
        self.update_running_ui("Removed vehicle", self.sc_count, target_count)

        self.log("Preparing for verification/entering the menu!!! Please manually verify the vehicle before proceeding with automated removal.")
        if not self.enter_menu():
            return False

        self.log("Entering Vehicles and Favorites!!! Please manually verify that a vehicle has been successfully removed before proceeding with automated removal.")
        self.hw_press("pagedown", delay=0.15)
        time.sleep(1.0)

        pos_buycar = self.wait_for_image("BNandUC.png", region=self.regions["左"], threshold=0.70, timeout=12, interval=0.3, fast_mode=True)
        if not pos_buycar:
            self.log("No new or used car purchases detected")
            return False

        self.game_click(pos_buycar)
        time.sleep(0.8)
        self.hw_press("enter")
        time.sleep(5)

        pos_bs = self.wait_for_any_image(["buyandsell-w.png", "buyandsell-b.png"], region=self.regions["上"], threshold=0.75, timeout=40, interval=0.5, fast_mode=True)
        if not pos_bs:
            self.log("No buy or sell items found")
            return False

        self.game_click(pos_bs)
        time.sleep(1.0)

        self.hw_press("pagedown", delay=0.15)
        time.sleep(1.0)

        self.hw_press("enter") # Enter my vehicle
        time.sleep(2.0)
        #Choose one to collect
        self.hw_press("y") 
        time.sleep(1.0)
        self.hw_press("enter")
        time.sleep(0.8)
        self.hw_press("esc") 
        time.sleep(1.5)
        #Driving my collection car
        self.hw_press("enter")
        time.sleep(0.8)
        self.move_to_game_coord(5, 5)
        time.sleep(0.2)

        pos = self.wait_for_image("rc.png", region=self.regions["全界面"], threshold=0.65, timeout=5, interval=0.2, fast_mode=True)
        if pos:
            self.log("Found the boarding route, clicked")
            self.game_click(pos) 
            time.sleep(2.0)
        else:
            self.log("The vehicle has been driven, or no image was found. Execute ESC twice")
            self.hw_press("esc")
            time.sleep(1.5)
            self.hw_press("esc")
        time.sleep(2.0)

        found = False
        for i in range(30):
            if not self.is_running:
                return False

            pos = self.wait_for_any_image(["buyandsell-b.png", "buyandsell-w.png"], region=self.regions["上"], threshold=0.70, timeout=0.8, interval=0.2, fast_mode=True)
            if pos:
                self.log(f"The {i + 1}th purchase and sale were detected, and the vehicle interface was entered")
                self.hw_press("enter") # Enter my vehicle
                time.sleep(1.5)
                found = True
                break
            self.log(f"No purchase or sale detected for {i + 1}th time, will try again later")
            time.sleep(1.0)
        if not found:
            self.log("No buy or sell orders found within 30 attempts")
            return False
        #filter
        self.hw_press("y")
        time.sleep(1.0)
        '''
        for _ in range(2):
            self.hw_press("down", delay=0.06)
            time.sleep(0.2)
        time.sleep(0.5)
        self.hw_press("enter")
        time.sleep(1.0)
        '''
        pos_repitem = self.wait_for_image_gray("repitem.png", region=self.regions["中间"], threshold=0.70, timeout=1, interval=0.3, fast_mode=True)
        if not pos_repeat:
            self.log("No new or used car purchases detected")
            return False

        self.game_click(pos_repitem)
        time.sleep(0.8)

        self.hw_press("esc")
        time.sleep(1.0)


        #Switch to consumable brand
        self.log("Switched to consumable brand...")
        self.hw_press("backspace")
        brand_pos = None
        for _ in range(5):
            if not self.is_running:
                return False
                

            brand_pos = self.wait_for_any_image_gray(
                ["CCbrand.png"],
                region = self.regions["full interface"],
                threshold=0.75,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if brand_pos:
                break

            self.hw_press("up")
            time.sleep(0.25)

        if not brand_pos:
            self.log("Brand not found")
            return False

        self.game_click(brand_pos)
        time.sleep(0.8)
        
        self.log("Starting to delete recently acquired vehicles!!! Please manually confirm removal")
        
        not_found_pages = 0  
        while self.sc_count < target_count:
            if not self.is_running:
                return False
            self.log(f"Using mode 3 to strictly scan the current page... (continuously not found: {not_found_pages}/5)")
            
            # [Using the Ultimate Security Lock]: 2 images, 4 lines of defense, absolutely no unauthorized deletion.
            pos_target = self.wait_for_image_ultimate_safe(
                main_path="removecarobject.png", # Screenshot of the car you want to delete
                anti_path="newcartag.png", # Screenshot of the NEW tag
                region = self.regions["full interface"],
                main_threshold=0.77, # Extremely high basic similarity requirement
                anti_threshold=0.65, # Extremely sensitive NEW tag rejection
                timeout=3.0,
                interval=0.2
            )
            
            if not pos_target:
                not_found_pages += 1
                if not_found_pages >= 5:
                    self.log("=After searching 5 pages, the target vehicle was not found! The vehicle has been completely cleared.")
                    self.log("Actively ending the cleanup task, preparing to proceed to the next step...")
                    break # Exits the loop and ends the current task.
                    
                self.log(f"The current page was not found. Scroll to the right to find it... (page {not_found_pages})")
                for _ in range(4):
                    self.hw_press("right", delay=0.06)
                    time.sleep(0.1)
                time.sleep(0.4)
                continue
            # ====== Target vehicle found, reset page turn counter ======
            not_found_pages = 0
            
            self.log("Target vehicle precisely located, click executed...")
            self.game_click(pos_target)
            time.sleep(1.2) # Wait for the response after clicking.
            
            # ==========================================
            # Core logic: Find removecar.png (to remove from the garage)
            # ==========================================
            self.log("Looking for the 'Remove from Garage' button...")
            pos_remove = self.find_image_gray("removecar.png", region=self.regions["全界面"], threshold=0.75, fast_mode=True)
            
            if pos_remove:
                self.log("I found the remove button and clicked it...")
                self.game_click(pos_remove)
            else:
                self.log("No remove button found. Press Enter to bring up the menu...")
                self.hw_press("enter")
                time.sleep(0.8) # Wait for the menu to pop up with an animation
                
                # Searching again
                pos_remove = self.find_image_gray("removecar.png", region=self.regions["全界面"], threshold=0.75, fast_mode=True)
                if pos_remove:
                    self.log("After bringing up the menu, I found the Remove button and clicked it...")
                    self.game_click(pos_remove)
                else:
                    self.log("Remove button still not found, may have clicked the wrong button/the car cannot be removed, press ESC to abandon the car...")
                    self.hw_press("esc")
                    time.sleep(1.0)
                    self.hw_press("right") # Move one space to the right to prevent an infinite loop of clicking on the fake car
                    time.sleep(1.2)
                    continue
                    
            time.sleep(0.8) # Wait for the "Are you sure you want to remove?" confirmation pop-up.
            
            # Confirm removal (press down to select "Yes", then press Enter)
            self.log("Confirm removal...")
            self.hw_press("down")
            time.sleep(0.3)
            self.hw_press("enter")
            time.sleep(1.2)

            
            self.sc_count += 1
            self.update_running_ui("Removed vehicle", self.sc_count, target_count)
            self.log(f"Successfully removed vehicle! Current progress: {self.sc_count}/{target_count}")

        # Loop ends, go back to the previous level
        for _ in range(3):
            if not self.is_running:
                return False
            self.hw_press("esc")
            time.sleep(1.0)

        return True
 
    #===============================
    #---Automatic Super Lottery-----
    #===============================

    
if __name__ == "__main__":
    app = FH_UltimateBot()
    app.mainloop()
