"""
HackSolve — Stealth Screen AI
Invisible overlay that reads HackerRank problems from your screen and gives Python solutions.
Invisible to Teams, Google Meet, Zoom, OBS — all screen share tools via Windows Display Affinity.
"""

import os
import sys
import json
import base64
import io
import time
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox

# Optional dependencies with graceful fallbacks
try:
    from PIL import Image, ImageTk, ImageGrab, ImageEnhance, ImageFilter
except ImportError:
    Image = None
    ImageGrab = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import mss
except ImportError:
    mss = None

try:
    import requests
except ImportError:
    requests = None


# =====================================================================
# USER CONFIGURATION (Edit these as needed)
# =====================================================================
GEMINI_API_KEY = "YOUR_API_KEY_HERE"  # Set your key here or in .env file
GROQ_API_KEY = "YOUR_GROQ_KEY_HERE"
OPENROUTER_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
HOTKEY = "f9"
OVERLAY_X = 50
OVERLAY_Y = 50
OVERLAY_WIDTH = 540
OVERLAY_HEIGHT = 680
OPACITY = 0.95
DEFAULT_MODEL = "gemini-3.6-flash"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.8-flash"]
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_FALLBACK_MODEL = "groq/compound-mini"
TIMEOUT = 30
# =====================================================================


# Win32 Constants for Stealth Screen Share Invisibility
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 build 2004+ (Stealth from OBS, Zoom, Teams, Meet)

def apply_stealth_affinity(hwnd: int) -> bool:
    """Applies Windows Display Affinity to make the window invisible to capture."""
    if not hwnd or sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        # Try WDA_EXCLUDEFROMCAPTURE first (completely hides from all capture)
        res = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        if res != 0:
            return True
        # Fallback to WDA_MONITOR for older Windows 10 builds
        res2 = user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
        return res2 != 0
    except Exception as e:
        print(f"[Stealth Error] Could not set window display affinity: {e}")
        return False


def get_active_gemini_key() -> str:
    """Resolves Gemini API Key from constant, environment, or .env file."""
    if GEMINI_API_KEY and GEMINI_API_KEY.strip() and GEMINI_API_KEY != "YOUR_API_KEY_HERE":
        return GEMINI_API_KEY.strip()
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    # Check .env file in the same directory
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        k = line.strip().split("=", 1)[1].strip(" '\"")
                        if k:
                            return k
        except Exception:
            pass
    return ""


def get_active_groq_key() -> str:
    """Resolves Groq API Key from constant, environment, or .env file."""
    if GROQ_API_KEY and GROQ_API_KEY.strip() and GROQ_API_KEY != "YOUR_GROQ_KEY_HERE":
        return GROQ_API_KEY.strip()
    env_key = os.environ.get("GROQ_API_KEY", "").strip()
    if env_key:
        return env_key
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GROQ_API_KEY="):
                        k = line.strip().split("=", 1)[1].strip(" '\"")
                        if k:
                            return k
        except Exception:
            pass
    return ""


def get_active_openrouter_key() -> str:
    """Resolves OpenRouter API Key from constant, environment, or .env file."""
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY.strip() and OPENROUTER_API_KEY != "YOUR_OPENROUTER_KEY_HERE":
        return OPENROUTER_API_KEY.strip()
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        k = line.strip().split("=", 1)[1].strip(" '\"")
                        if k:
                            return k
        except Exception:
            pass
    return ""


def preprocess_image_for_ocr(img: "Image.Image") -> "Image.Image":
    """Enhance screenshot contrast and grayscale for superior OCR text detection."""
    try:
        # Convert to grayscale
        gray = img.convert("L")
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.8)
        # Apply slight sharpening
        sharpened = enhanced.filter(ImageFilter.SHARPEN)
        return sharpened
    except Exception:
        return img


from datetime import datetime, timezone


class QuotaTracker:
    """Tracks daily question requests and tokens against Google AI Studio free tier."""
    DAILY_LIMIT = 1500
    CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".quota_tracker.json")

    def __init__(self):
        self.used_today = 32  # Initialized to estimated session usage
        self.last_tokens = 0
        self.current_date = self._get_today_date()
        self.load()

    def _get_today_date(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def load(self):
        today = self._get_today_date()
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("date") == today:
                        self.used_today = data.get("used", self.used_today)
                        self.last_tokens = data.get("last_tokens", 0)
                    else:
                        # New day: automatically reset quota
                        self.used_today = 0
                        self.last_tokens = 0
                        self.save()
            except Exception:
                pass

    def save(self):
        today = self._get_today_date()
        try:
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "date": today,
                    "used": self.used_today,
                    "total_limit": self.DAILY_LIMIT,
                    "last_tokens": self.last_tokens
                }, f, indent=2)
        except Exception:
            pass

    def record_request(self, tokens: int = 0):
        today = self._get_today_date()
        if today != self.current_date:
            self.current_date = today
            self.used_today = 0
        self.used_today += 1
        self.last_tokens = tokens
        self.save()

    def get_remaining(self) -> int:
        return max(0, self.DAILY_LIMIT - self.used_today)

    def get_display_text(self) -> str:
        rem = self.get_remaining()
        return f"Left: {rem:,} / {self.DAILY_LIMIT:,}"


class StealthOverlayApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.is_collapsed = False
        self.last_solution_code = ""
        self.last_extracted_text = ""
        self.last_explanation = ""
        self.is_processing = False
        self.opacity_level = OPACITY
        self.auto_scroll_enabled = True
        self.quota_tracker = QuotaTracker()

        # Window styling
        self.root.title("HackSolve — Stealth AI")
        self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+{OVERLAY_X}+{OVERLAY_Y}")
        self.root.minsize(360, 200)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.opacity_level)
        self.root.overrideredirect(True)  # Frameless for modern custom stealth HUD

        # Configure Tesseract
        self.setup_tesseract()

        # Build UI
        self.build_ui()

        # Dragging mechanics
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Enable Stealth Affinity once window is realized
        self.root.update_idletasks()
        self.init_stealth()

        # Register global hotkey
        self.setup_hotkey()

    def init_stealth(self):
        """Finds top-level Win32 HWND and sets stealth affinity."""
        try:
            # On Windows Tkinter, the top-level container HWND is wm_frame or GetParent(winfo_id)
            hwnd = None
            try:
                frame_id = self.root.wm_frame()
                if frame_id:
                    hwnd = int(frame_id, 16)
            except Exception:
                pass

            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()

            success = apply_stealth_affinity(hwnd)
            if success:
                self.update_status("Stealth Active (Invisible to Screen Share)", "#a6e3a1")
            else:
                self.update_status("Stealth Ready (Default Monitor)", "#f9e2af")
        except Exception as e:
            self.update_status(f"Affinity Warning: {e}", "#f38ba8")

    def setup_tesseract(self):
        """Verifies or auto-locates Tesseract executable."""
        if not pytesseract:
            return
        if os.path.exists(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        else:
            # Fallback checks in common locations
            common_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
            ]
            for path in common_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    break

    def setup_hotkey(self):
        """Binds global hotkey if keyboard library is available."""
        if keyboard:
            try:
                keyboard.add_hotkey(HOTKEY, self.trigger_scan_thread, suppress=False)
            except Exception as e:
                print(f"[Hotkey Warning] Could not hook '{HOTKEY}': {e}. (Run as Administrator)")
        # Also bind escape to minimize / restore
        self.root.bind("<Escape>", lambda e: self.toggle_collapse())

    # ================= UI CREATION =================
    def build_ui(self):
        # Palette: Sleek Catppuccin Mocha / Dark IDE theme
        self.bg_color = "#181825"
        self.header_bg = "#11111b"
        self.card_bg = "#1e1e2e"
        self.accent_color = "#89b4fa"
        self.accent_hover = "#b4befe"
        self.success_color = "#a6e3a1"
        self.warning_color = "#f9e2af"
        self.error_color = "#f38ba8"
        self.text_primary = "#cdd6f4"
        self.text_dim = "#a6adc8"

        self.root.configure(bg=self.bg_color)

        # Outer border frame
        self.border_frame = tk.Frame(self.root, bg="#313244", bd=1)
        self.border_frame.pack(fill="both", expand=True)

        self.main_container = tk.Frame(self.border_frame, bg=self.bg_color)
        self.main_container.pack(fill="both", expand=True, padx=1, pady=1)

        # 1. Custom Title Bar (Draggable)
        self.title_bar = tk.Frame(self.main_container, bg=self.header_bg, height=38)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        self.title_bar.bind("<Button-1>", self.start_drag)
        self.title_bar.bind("<B1-Motion>", self.do_drag)

        # Title / Brand Icon with Active Model Name
        self.lbl_title = tk.Label(
            self.title_bar,
            text=f"⚡ HackSolve — {DEFAULT_MODEL}",
            font=("Segoe UI", 9, "bold"),
            bg=self.header_bg,
            fg=self.accent_color,
            padx=8
        )
        self.lbl_title.pack(side="left", fill="y")
        self.lbl_title.bind("<Button-1>", self.start_drag)
        self.lbl_title.bind("<B1-Motion>", self.do_drag)

        # Header Control Buttons (Right aligned)
        self.btn_close = tk.Button(
            self.title_bar,
            text="✕",
            font=("Segoe UI", 9, "bold"),
            bg=self.header_bg,
            fg="#f38ba8",
            activebackground="#f38ba8",
            activeforeground="#11111b",
            bd=0,
            padx=10,
            cursor="hand2",
            command=self.root.destroy
        )
        self.btn_close.pack(side="right", fill="y")

        self.btn_collapse = tk.Button(
            self.title_bar,
            text="▲",
            font=("Segoe UI", 9),
            bg=self.header_bg,
            fg=self.text_dim,
            activebackground="#313244",
            activeforeground=self.text_primary,
            bd=0,
            padx=8,
            cursor="hand2",
            command=self.toggle_collapse
        )
        self.btn_collapse.pack(side="right", fill="y")

        self.btn_opacity = tk.Button(
            self.title_bar,
            text=f"👁 {int(self.opacity_level*100)}%",
            font=("Segoe UI", 8),
            bg=self.header_bg,
            fg=self.text_dim,
            activebackground="#313244",
            activeforeground=self.text_primary,
            bd=0,
            padx=6,
            cursor="hand2",
            command=self.cycle_opacity
        )
        self.btn_opacity.pack(side="right", fill="y")

        # 2. Status Strip
        self.status_bar = tk.Frame(self.main_container, bg="#11111b", height=24)
        self.status_bar.pack(fill="x", side="top")
        self.status_bar.pack_propagate(False)

        self.lbl_status_dot = tk.Label(
            self.status_bar,
            text="●",
            font=("Segoe UI", 8),
            bg="#11111b",
            fg=self.success_color,
            padx=6
        )
        self.lbl_status_dot.pack(side="left")

        self.lbl_status_text = tk.Label(
            self.status_bar,
            text="Ready — Press F9 to Scan Screen",
            font=("Segoe UI", 8),
            bg="#11111b",
            fg=self.text_dim
        )
        self.lbl_status_text.pack(side="left", fill="x")

        # Quota remaining badge on right of status bar
        self.lbl_quota = tk.Label(
            self.status_bar,
            text=self.quota_tracker.get_display_text(),
            font=("Segoe UI", 8, "bold"),
            bg="#11111b",
            fg=self.success_color,
            padx=8
        )
        self.lbl_quota.pack(side="right")

        # 3. Action Toolbar
        self.toolbar = tk.Frame(self.main_container, bg=self.card_bg, padx=8, pady=6)
        self.toolbar.pack(fill="x", side="top", pady=2)

        self.btn_scan = tk.Button(
            self.toolbar,
            text=f"⚡ Scan ({HOTKEY.upper()})",
            font=("Segoe UI", 9, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            activeforeground="#11111b",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.trigger_scan_thread
        )
        self.btn_scan.pack(side="left", padx=(0, 6))

        # Auto-Scroll toggle button
        self.btn_scroll = tk.Button(
            self.toolbar,
            text="📜 Scroll: ON",
            font=("Segoe UI", 9, "bold"),
            bg="#313244",
            fg=self.success_color,
            activebackground="#45475a",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.toggle_autoscroll
        )
        self.btn_scroll.pack(side="left", padx=4)

        self.btn_copy = tk.Button(
            self.toolbar,
            text="📋 Copy Code",
            font=("Segoe UI", 9),
            bg="#313244",
            fg=self.text_primary,
            activebackground="#45475a",
            activeforeground="#ffffff",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.copy_solution_code
        )
        self.btn_copy.pack(side="left", padx=4)

        self.btn_clear = tk.Button(
            self.toolbar,
            text="🗑 Clear",
            font=("Segoe UI", 9),
            bg="#313244",
            fg=self.text_dim,
            activebackground="#45475a",
            activeforeground=self.text_primary,
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.clear_all
        )
        self.btn_clear.pack(side="left", padx=4)

        # API Key Change button on right of toolbar
        self.btn_api_key = tk.Button(
            self.toolbar,
            text="🔑 API Key",
            font=("Segoe UI", 9),
            bg="#313244",
            fg=self.accent_color,
            activebackground="#45475a",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.show_api_key_prompt
        )
        self.btn_api_key.pack(side="right", padx=4)

        # 4. Tabbed Content (Notebook)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#1e1e2e",
            foreground=self.text_dim,
            padding=[10, 4],
            font=("Segoe UI", 9)
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#313244")],
            foreground=[("selected", self.accent_color)]
        )

        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=4)

        # TAB 1: Python Solution
        self.tab_code = tk.Frame(self.notebook, bg=self.card_bg)
        self.notebook.add(self.tab_code, text=" Python Solution ")

        self.txt_code = tk.Text(
            self.tab_code,
            wrap="none",
            font=("Consolas", 10),
            bg="#181825",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            selectbackground="#45475a",
            selectforeground="#ffffff",
            bd=0,
            padx=8,
            pady=8
        )
        scroll_code_y = tk.Scrollbar(self.tab_code, orient="vertical", command=self.txt_code.yview)
        scroll_code_x = tk.Scrollbar(self.tab_code, orient="horizontal", command=self.txt_code.xview)
        self.txt_code.configure(yscrollcommand=scroll_code_y.set, xscrollcommand=scroll_code_x.set)

        scroll_code_y.pack(side="right", fill="y")
        scroll_code_x.pack(side="bottom", fill="x")
        self.txt_code.pack(side="left", fill="both", expand=True)

        # TAB 2: Explanation & Complexity
        self.tab_exp = tk.Frame(self.notebook, bg=self.card_bg)
        self.notebook.add(self.tab_exp, text=" Notes & Complexity ")

        self.txt_exp = tk.Text(
            self.tab_exp,
            wrap="word",
            font=("Segoe UI", 9),
            bg="#181825",
            fg="#bac2de",
            insertbackground="#cdd6f4",
            selectbackground="#45475a",
            selectforeground="#ffffff",
            bd=0,
            padx=10,
            pady=8
        )
        scroll_exp_y = tk.Scrollbar(self.tab_exp, orient="vertical", command=self.txt_exp.yview)
        self.txt_exp.configure(yscrollcommand=scroll_exp_y.set)
        scroll_exp_y.pack(side="right", fill="y")
        self.txt_exp.pack(side="left", fill="both", expand=True)

        # TAB 3: Detected Problem Text
        self.tab_ocr = tk.Frame(self.notebook, bg=self.card_bg)
        self.notebook.add(self.tab_ocr, text=" Scanned OCR Text ")

        self.txt_ocr = tk.Text(
            self.tab_ocr,
            wrap="word",
            font=("Consolas", 9),
            bg="#181825",
            fg="#a6adc8",
            insertbackground="#cdd6f4",
            selectbackground="#45475a",
            selectforeground="#ffffff",
            bd=0,
            padx=10,
            pady=8
        )
        scroll_ocr_y = tk.Scrollbar(self.tab_ocr, orient="vertical", command=self.txt_ocr.yview)
        self.txt_ocr.configure(yscrollcommand=scroll_ocr_y.set)
        scroll_ocr_y.pack(side="right", fill="y")
        self.txt_ocr.pack(side="left", fill="both", expand=True)

        # Initial Welcome Message in Code Box
        welcome_msg = (
            "# HackSolve — Stealth Screen AI\n"
            "# 1. Ensure HackerRank problem is visible on your screen.\n"
            f"# 2. Press [{HOTKEY.upper()}] or click 'Scan' above.\n"
            "# 3. Invisible to Zoom, Teams, Meet, Discord & OBS screen share.\n"
            "# 4. Click 'Copy Code' to copy optimal solution directly.\n\n"
            "def solve():\n"
            "    # Your optimal HackerRank solution will appear here\n"
            "    pass\n"
        )
        self.txt_code.insert("1.0", welcome_msg)

    # ================= WINDOW CONTROLS =================
    def start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def do_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_start_x)
        y = self.root.winfo_y() + (event.y - self._drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def toggle_collapse(self):
        """Folds/unfolds the window into a minimal title strip."""
        if self.is_collapsed:
            self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}")
            self.status_bar.pack(fill="x", side="top")
            self.toolbar.pack(fill="x", side="top", pady=2)
            self.notebook.pack(fill="both", expand=True, padx=6, pady=4)
            self.btn_collapse.config(text="▲")
            self.is_collapsed = False
        else:
            self.notebook.pack_forget()
            self.toolbar.pack_forget()
            self.status_bar.pack_forget()
            self.root.geometry(f"{OVERLAY_WIDTH}x38")
            self.btn_collapse.config(text="▼")
            self.is_collapsed = True

    def cycle_opacity(self):
        levels = [0.95, 0.85, 0.70, 0.50]
        try:
            curr_idx = levels.index(self.opacity_level)
            next_idx = (curr_idx + 1) % len(levels)
        except ValueError:
            next_idx = 0
        self.opacity_level = levels[next_idx]
        self.root.attributes("-alpha", self.opacity_level)
        self.btn_opacity.config(text=f"👁 {int(self.opacity_level*100)}%")

    def update_status(self, text: str, color: str = None):
        if not color:
            color = self.text_dim
        self.lbl_status_text.config(text=text)
        self.lbl_status_dot.config(fg=color)
        self.root.update_idletasks()

    def clear_all(self):
        self.txt_code.delete("1.0", tk.END)
        self.txt_exp.delete("1.0", tk.END)
        self.txt_ocr.delete("1.0", tk.END)
        self.last_solution_code = ""
        self.last_extracted_text = ""
        self.last_explanation = ""
        self.update_status("Cleared — Ready", self.success_color)

    def copy_solution_code(self):
        code = self.last_solution_code.strip()
        if not code:
            code = self.txt_code.get("1.0", tk.END).strip()
        if code:
            self.root.clipboard_clear()
            self.root.clipboard_append(code)
            self.btn_copy.config(text="✓ Copied!", bg="#a6e3a1", fg="#11111b")
            self.root.after(2000, lambda: self.btn_copy.config(text="📋 Copy Code", bg="#313244", fg=self.text_primary))

    def toggle_autoscroll(self):
        """Toggles between full auto-scrolling capture and single screen capture."""
        self.auto_scroll_enabled = not self.auto_scroll_enabled
        if self.auto_scroll_enabled:
            self.btn_scroll.config(text="📜 Scroll: ON", fg=self.success_color)
            self.update_status("Auto-Scroll: ON (Captures & stitches full question)", self.success_color)
        else:
            self.btn_scroll.config(text="📜 Scroll: OFF", fg=self.text_dim)
            self.update_status("Auto-Scroll: OFF (Single screen capture)", self.text_dim)

    # ================= CORE LOGIC =================
    def trigger_scan_thread(self):
        if self.is_processing:
            return
        # 6-second cooldown to respect Google's 5-RPM burst limit
        now = time.time()
        elapsed = now - getattr(self, "_last_scan_time", 0)
        if elapsed < 5.0:
            wait_sec = int(5.0 - elapsed) + 1
            self.update_status(f"Please wait {wait_sec}s before next scan...", self.warning_color)
            return
        self._last_scan_time = now

        thread = threading.Thread(target=self.run_screen_solve_pipeline, daemon=True)
        thread.start()

    def run_screen_solve_pipeline(self):
        self.is_processing = True
        self.btn_scan.config(state="disabled", bg="#45475a")

        try:
            # 1. Capture Screen (Auto-scroll or single)
            if self.auto_scroll_enabled:
                self.update_status("Auto-scrolling problem (top to bottom)...", self.warning_color)
                screenshot = self.capture_auto_scroll_screen(frames=3)
            else:
                self.update_status("Capturing screen...", self.warning_color)
                screenshot = self.capture_screen()

            if not screenshot:
                self.update_status("Screen capture failed", self.error_color)
                return

            # 2. Extract Text via OCR
            self.update_status("Scanning problem text (OCR)...", self.warning_color)
            ocr_text = self.extract_text_ocr(screenshot)

            # 3. Solve with Multi-Provider Failover (Groq / Gemini / OpenRouter)
            self.update_status("Solving with Multi-AI Failover...", "#89b4fa")
            solution_data = self.solve_with_failover(ocr_text, screenshot)

            # 4. Display Results
            self.root.after(0, self.display_solution, solution_data, ocr_text)

        except Exception as e:
            err_msg = str(e)
            print(f"[Error in pipeline] {err_msg}")
            self.update_status(f"Error: {err_msg[:35]}", self.error_color)
        finally:
            self.is_processing = False
            self.btn_scan.config(state="normal", bg="#89b4fa")

    def capture_auto_scroll_screen(self, frames: int = 3) -> "Image.Image":
        """Captures multiple views while scrolling the active window and stitches them vertically."""
        images = []
        first_img = self.capture_screen()
        if not first_img:
            return None
        images.append(first_img)

        if not self.auto_scroll_enabled or frames <= 1:
            return first_img

        MOUSEEVENTF_WHEEL = 0x0800
        WHEEL_DELTA = 120
        # Scroll clicks per frame (~65% of screen height jump)
        scroll_clicks_per_frame = 7

        for i in range(1, frames):
            self.update_status(f"Auto-scrolling problem ({i+1}/{frames})...", self.warning_color)
            # Scroll down smoothly
            for _ in range(scroll_clicks_per_frame):
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -WHEEL_DELTA, 0)
                time.sleep(0.03)
            time.sleep(0.35)  # Wait for page layout/render
            img = self.capture_screen()
            if img:
                images.append(img)

        # Smoothly scroll back up to restore user's original view
        total_scroll_back = (len(images) - 1) * scroll_clicks_per_frame
        for _ in range(total_scroll_back):
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_DELTA, 0)
            time.sleep(0.015)

        return self.stitch_images(images)

    def stitch_images(self, images: list) -> "Image.Image":
        """Stitches multiple scroll captures into one tall composite image."""
        if not images:
            return None
        if len(images) == 1:
            return images[0]

        width = images[0].width
        processed_frames = []
        for idx, img in enumerate(images):
            if idx == 0:
                processed_frames.append(img)
            else:
                # In browser windows, crop the top ~80px duplicate URL/tab bar
                if img.height > 120:
                    crop_box = (0, 80, img.width, img.height)
                    processed_frames.append(img.crop(crop_box))
                else:
                    processed_frames.append(img)

        total_height = sum(f.height for f in processed_frames)
        stitched = Image.new("RGB", (width, total_height), color=(24, 24, 37))
        y_offset = 0
        for f in processed_frames:
            stitched.paste(f, (0, y_offset))
            y_offset += f.height

        return stitched

    def capture_screen(self) -> "Image.Image":
        """Captures full screen or primary monitor image."""
        try:
            if mss:
                mss_factory = getattr(mss, "MSS", getattr(mss, "mss", None))
                with mss_factory() as sct:
                    # Monitor 1 or primary monitor
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    sct_img = sct.grab(monitor)
                    return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            elif ImageGrab:
                return ImageGrab.grab()
        except Exception as e:
            print(f"[Capture error] {e}")
            if ImageGrab:
                try:
                    return ImageGrab.grab()
                except Exception:
                    pass
        return None

    def extract_text_ocr(self, img: "Image.Image") -> str:
        """Runs Tesseract OCR on preprocessed image."""
        if not pytesseract:
            return ""
        try:
            preprocessed = preprocess_image_for_ocr(img)
            # Custom Tesseract configuration for code and text
            custom_config = r"--oem 3 --psm 6"
            text = pytesseract.image_to_string(preprocessed, config=custom_config)
            return text.strip()
        except Exception as e:
            # If Tesseract is not installed, HackSolve automatically uses Gemini Multimodal Vision
            print(f"[Info] Tesseract OCR not active ({e.__class__.__name__}) — seamlessly using Gemini Multimodal Vision fallback.")
            return ""

    def solve_with_gemini(self, ocr_text: str, screenshot: "Image.Image", api_key: str, timeout: int = 25) -> dict:
        """Sends problem text (or multimodal image if OCR text is insufficient) to Gemini."""
        system_prompt = (
            "You are an elite competitive programmer and HackerRank algorithm solver. "
            "Your task is to analyze the coding question, identify the exact requirements, "
            "constraints, input format, and output format, and write the optimal, passing Python 3 solution.\n\n"
            "Rules:\n"
            "1. Output valid, clean Python 3 code with proper imports (sys, collections, heapq, math, etc.).\n"
            "2. Read input from standard input (sys.stdin.read().split() or input()) as required by HackerRank.\n"
            "3. If a specific function signature is given (e.g., 'def solve(n, arr):'), include both the function and the main caller.\n"
            "4. Ensure optimal time and space complexity to prevent TLE (Time Limit Exceeded).\n"
            "5. Format your response strictly as JSON with the following keys:\n"
            "   - 'code': Pure Python 3 solution without markdown backticks.\n"
            "   - 'explanation': Concise bullet points on approach, time complexity, and edge cases.\n"
            "   - 'problem_title': Title or summary of the detected problem.\n"
            "   - 'confidence': High / Medium / Low."
        )

        use_multimodal = (len(ocr_text) < 35)

        # Prepare request payload
        parts = []
        if use_multimodal and screenshot:
            # Compress screenshot for fast upload
            buffered = io.BytesIO()
            # Resize if screenshot is huge (> 1920 width or > 2400 height) to conserve bandwidth
            w, h = screenshot.size
            max_w, max_h = 1920, 2400
            if w > max_w or h > max_h:
                scale = min(max_w / w, max_h / h)
                screenshot = screenshot.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            screenshot.save(buffered, format="JPEG", quality=82)
            img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": img_b64
                }
            })
            parts.append({
                "text": f"{system_prompt}\n\nPlease read the coding problem shown in this screenshot and provide the optimal Python 3 solution."
            })
        else:
            parts.append({
                "text": (
                    f"{system_prompt}\n\n"
                    f"--- EXTRACTED SCREEN TEXT / PROBLEM STATEMENT ---\n"
                    f"{ocr_text}\n"
                    f"--------------------------------------------------\n"
                    "Provide the complete Python 3 solution adhering strictly to the JSON schema."
                )
            })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        }

        # Query model with fallback cascade
        models_to_try = [DEFAULT_MODEL] + FALLBACK_MODELS
        last_error = None

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                headers = {"Content-Type": "application/json"}
                data_json = json.dumps(payload).encode("utf-8")

                if requests:
                    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = self.parse_gemini_json_response(text_content)
                        parsed["usage_metadata"] = res_json.get("usageMetadata", {})
                        return parsed
                    elif resp.status_code == 429:
                        last_error = "Rate limit reached (Too many scans in 1 minute). Please wait 15 seconds."
                        print("[Warning] 429 Rate limit from Google. Waiting a few seconds recommended.")
                        break
                    else:
                        last_error = f"{resp.status_code}: {resp.text}"
                else:
                    # Standard library urllib fallback
                    import urllib.request
                    req = urllib.request.Request(url, data=data_json, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        res_body = response.read().decode("utf-8")
                        res_json = json.loads(res_body)
                        text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = self.parse_gemini_json_response(text_content)
                        parsed["usage_metadata"] = res_json.get("usageMetadata", {})
                        return parsed
            except Exception as ex:
                last_error = str(ex)
                continue

        raise RuntimeError(f"Gemini API request failed: {last_error}")

    def parse_gemini_json_response(self, text_content: str) -> dict:
        """Parses JSON response from Gemini, cleaning markdown markers if present."""
        clean_text = text_content.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        try:
            data = json.loads(clean_text)
            return data
        except Exception:
            # Fallback: if model returned raw code or text instead of JSON
            return {
                "code": clean_text,
                "explanation": "Extracted direct response",
                "problem_title": "Detected Question",
                "confidence": "Medium"
            }

    def call_single_provider(self, provider: dict, ocr_text: str, screenshot: "Image.Image", timeout: int = 5) -> dict:
        """Invokes a single AI provider (Groq, Gemini, OpenRouter) with strict timeout."""
        system_prompt = (
            "You are an elite competitive programmer and HackerRank algorithm solver. "
            "Analyze the problem and provide the optimal, passing Python 3 solution.\n"
            "Rules:\n"
            "1. Output valid, clean Python 3 with necessary imports.\n"
            "2. Read input from standard input (sys.stdin.read().split() or input()) as required by HackerRank.\n"
            "3. Format response strictly as JSON with keys: 'code', 'explanation', 'problem_title', 'confidence'."
        )

        p_type = provider["type"]
        p_name = provider["name"]
        p_key = provider["key"]
        p_model = provider["model"]
        p_url = provider["url"]

        if p_type == "openai_compat":
            prompt_text = (
                f"{system_prompt}\n\n"
                f"--- EXTRACTED SCREEN TEXT / PROBLEM STATEMENT ---\n"
                f"{ocr_text or 'Solve the coding problem shown on screen.'}\n"
                f"--------------------------------------------------\n"
                "Return JSON with 'code', 'explanation', 'problem_title', 'confidence'."
            )
            headers = {
                "Authorization": f"Bearer {p_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": p_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
            }
            resp = requests.post(p_url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                raise RuntimeError(f"{p_name} error {resp.status_code}: {resp.text[:120]}")
            res_json = resp.json()
            data_str = res_json["choices"][0]["message"]["content"]
            parsed = self.parse_gemini_json_response(data_str)
            usage = res_json.get("usage", {})
            parsed["usage_metadata"] = {
                "totalTokenCount": usage.get("total_tokens", 0),
                "promptTokenCount": usage.get("prompt_tokens", 0),
                "candidatesTokenCount": usage.get("completion_tokens", 0)
            }
            return parsed

        elif p_type == "gemini":
            return self.solve_with_gemini(ocr_text, screenshot, p_key, timeout=timeout)
        else:
            raise ValueError(f"Unknown provider type: {p_type}")

    def solve_with_failover(self, ocr_text: str, screenshot: "Image.Image") -> dict:
        """Attempts providers in order with a 5-second automatic switch timeout."""
        groq_key = get_active_groq_key()
        gemini_key = get_active_gemini_key()
        openrouter_key = get_active_openrouter_key()

        providers = []
        # Priority 1: Groq (if OCR text exists) — 14,400 req/day, blazing fast (<1s)
        if len(ocr_text.strip()) >= 25 and groq_key:
            providers.append({
                "name": "Groq",
                "type": "openai_compat",
                "key": groq_key,
                "model": GROQ_MODEL,
                "url": "https://api.groq.com/openai/v1/chat/completions"
            })

        # Priority 2: Gemini (Vision + Text) — Full multimodal vision support
        if gemini_key:
            providers.append({
                "name": "Gemini",
                "type": "gemini",
                "key": gemini_key,
                "model": DEFAULT_MODEL,
                "url": f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent"
            })

        # Priority 3: Groq with fallback model (if Gemini fails or OCR text was short)
        if groq_key and not any(p["name"] == "Groq" for p in providers):
            providers.append({
                "name": "Groq",
                "type": "openai_compat",
                "key": groq_key,
                "model": GROQ_FALLBACK_MODEL,
                "url": "https://api.groq.com/openai/v1/chat/completions"
            })

        # Priority 4: OpenRouter
        if openrouter_key:
            providers.append({
                "name": "OpenRouter",
                "type": "openai_compat",
                "key": openrouter_key,
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "url": "https://openrouter.ai/api/v1/chat/completions"
            })

        if not providers:
            raise RuntimeError("No AI keys configured! Click [🔑 API Key] to set your Groq or Gemini key.")

        last_error = None
        for p in providers:
            p_name = p["name"]
            p_model = p["model"]
            self.update_status(f"Trying {p_name} ({p_model})...", "#89b4fa")
            t_start = time.time()
            try:
                parsed = self.call_single_provider(p, ocr_text, screenshot, timeout=5)
                if parsed and parsed.get("code"):
                    elapsed = round(time.time() - t_start, 2)
                    parsed["provider_name"] = p_name
                    parsed["provider_model"] = p_model
                    parsed["elapsed_sec"] = elapsed
                    print(f"[OK] Solution received via {p_name} ({p_model}) in {elapsed}s")
                    return parsed
            except Exception as e:
                last_error = e
                elapsed = round(time.time() - t_start, 2)
                print(f"[FAIL] {p_name} failed in {elapsed}s: {e} — switching to next provider...")
                self.update_status(f"{p_name} failed, switching to backup...", self.warning_color)
                continue

        raise RuntimeError(f"All AI providers failed. Last error: {last_error}")

    def display_solution(self, solution_data: dict, ocr_text: str):
        """Renders parsed solution data into the UI widgets."""
        code = solution_data.get("code", "").strip()
        explanation = solution_data.get("explanation", "")
        title = solution_data.get("problem_title", "Problem Solved")
        confidence = solution_data.get("confidence", "High")

        if isinstance(explanation, list):
            explanation = "\n".join(f"• {item}" for item in explanation)

        self.last_solution_code = code
        self.last_explanation = explanation
        self.last_extracted_text = ocr_text

        # Update quota tracking and badge
        usage_meta = solution_data.get("usage_metadata", {})
        total_tokens = usage_meta.get("totalTokenCount", 0)
        prompt_tokens = usage_meta.get("promptTokenCount", 0)
        code_tokens = usage_meta.get("candidatesTokenCount", 0)

        self.quota_tracker.record_request(tokens=total_tokens)
        self.update_quota_display()

        # Update Code tab
        self.txt_code.delete("1.0", tk.END)
        self.txt_code.insert("1.0", code)

        # Update Explanation tab
        self.txt_exp.delete("1.0", tk.END)
        provider_name = solution_data.get("provider_name", "AI")
        provider_model = solution_data.get("provider_model", DEFAULT_MODEL)
        elapsed_sec = solution_data.get("elapsed_sec", "")
        speed_badge = f" ({elapsed_sec}s)" if elapsed_sec else ""

        provider_line = f"Provider: {provider_name} | Model: {provider_model} | Latency: {elapsed_sec or 'N/A'}s\n"
        token_info = ""
        if total_tokens > 0:
            token_info = f"Tokens: {total_tokens:,} (Prompt: {prompt_tokens:,} | Code: {code_tokens:,})\n"
        quota_info = f"Daily Remaining: {self.quota_tracker.get_remaining():,} / 1,500 questions\n"
        scroll_info = "Capture Mode: Auto-Scrolled & Stitched\n" if self.auto_scroll_enabled else "Capture Mode: Single Screen\n"
        exp_header = f"Problem: {title}\nConfidence: {confidence}\n{provider_line}{scroll_info}{token_info}{quota_info}{'='*45}\n\n"
        self.txt_exp.insert("1.0", exp_header + str(explanation))

        # Update OCR tab
        self.txt_ocr.delete("1.0", tk.END)
        if ocr_text:
            self.txt_ocr.insert("1.0", ocr_text)
        else:
            self.txt_ocr.insert("1.0", "(OCR text empty — Multimodal Vision was used directly)")

        # Switch to Code tab
        self.notebook.select(self.tab_code)
        self.update_status(f"✓ {provider_name}{speed_badge}: {title[:20]}", self.success_color)

    def update_quota_display(self):
        """Refreshes the remaining questions counter on the status bar."""
        if hasattr(self, "lbl_quota"):
            self.lbl_quota.config(text=self.quota_tracker.get_display_text())

    def show_api_key_prompt(self):
        """Displays interactive API Key Manager for Gemini, Groq, and OpenRouter."""
        active_gemini = get_active_gemini_key()
        active_groq = get_active_groq_key()
        active_openrouter = get_active_openrouter_key()

        def mask(k):
            return (k[:8] + "..." + k[-4:]) if len(k) > 12 else (k or "Not Configured")

        win = tk.Toplevel(self.root)
        win.title("🔑 Multi-AI Provider Key Manager")
        win.geometry("520x480")
        win.configure(bg="#181825")
        win.attributes("-topmost", True)
        apply_stealth_affinity(win.winfo_id())

        # Header Title
        tk.Label(
            win,
            text="⚡ Multi-AI API Key Manager (Groq + Gemini + OpenRouter)",
            bg="#181825",
            fg="#89b4fa",
            font=("Segoe UI", 11, "bold")
        ).pack(pady=(12, 4))

        # Groq Section (14,400 req/day - Primary Text LPU)
        groq_frame = tk.LabelFrame(win, text=" Groq API Key (Primary — 14,400 Free Req/Day) ", bg="#1e1e2e", fg="#a6e3a1", font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        groq_frame.pack(fill="x", padx=16, pady=4)

        tk.Label(groq_frame, text=f"Active: {mask(active_groq)}", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 8)).pack(anchor="w")
        ent_groq = tk.Entry(groq_frame, width=54, font=("Consolas", 9), bg="#313244", fg="#ffffff", insertbackground="#ffffff", bd=1, relief="solid")
        ent_groq.pack(fill="x", pady=3)
        if active_groq:
            ent_groq.insert(0, active_groq)

        lbl_groq_status = tk.Label(groq_frame, text="Ready", bg="#1e1e2e", fg="#6c7086", font=("Segoe UI", 8))
        lbl_groq_status.pack(anchor="w")

        def test_groq():
            k = ent_groq.get().strip()
            if not k:
                lbl_groq_status.config(text="✗ Please enter a Groq API key.", fg="#f38ba8")
                return
            lbl_groq_status.config(text="Testing Groq...", fg="#f9e2af")
            def _test():
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": "hi"}], "temperature": 0.2}
                try:
                    r = requests.post(url, headers=headers, json=payload, timeout=6)
                    if r.status_code == 200:
                        lbl_groq_status.config(text="✓ Groq Key VALID! (14,400 req/day active)", fg="#a6e3a1")
                    else:
                        lbl_groq_status.config(text=f"✗ Groq Error {r.status_code}: {r.text[:40]}", fg="#f38ba8")
                except Exception as ex:
                    lbl_groq_status.config(text=f"✗ Connection error: {str(ex)[:35]}", fg="#f38ba8")
            threading.Thread(target=_test, daemon=True).start()

        tk.Button(groq_frame, text="🧪 Test Groq", bg="#313244", fg="#cdd6f4", font=("Segoe UI", 8), bd=0, padx=8, pady=2, command=test_groq).pack(anchor="e", pady=(0, 2))

        # Gemini Section (1,500 req/day - Vision Multimodal)
        gemini_frame = tk.LabelFrame(win, text=" Gemini API Key (Vision Multimodal — 1,500 Free Req/Day) ", bg="#1e1e2e", fg="#89b4fa", font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        gemini_frame.pack(fill="x", padx=16, pady=4)

        tk.Label(gemini_frame, text=f"Active: {mask(active_gemini)}", bg="#1e1e2e", fg="#cdd6f4", font=("Segoe UI", 8)).pack(anchor="w")
        ent_gemini = tk.Entry(gemini_frame, width=54, font=("Consolas", 9), bg="#313244", fg="#ffffff", insertbackground="#ffffff", bd=1, relief="solid")
        ent_gemini.pack(fill="x", pady=3)
        if active_gemini:
            ent_gemini.insert(0, active_gemini)

        lbl_gemini_status = tk.Label(gemini_frame, text="Ready", bg="#1e1e2e", fg="#6c7086", font=("Segoe UI", 8))
        lbl_gemini_status.pack(anchor="w")

        def test_gemini():
            k = ent_gemini.get().strip()
            if not k:
                lbl_gemini_status.config(text="✗ Please enter a Gemini API key.", fg="#f38ba8")
                return
            lbl_gemini_status.config(text="Testing Gemini...", fg="#f9e2af")
            def _test():
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent?key={k}"
                try:
                    payload = {"contents": [{"parts": [{"text": "hi"}]}]}
                    r = requests.post(url, json=payload, timeout=8)
                    if r.status_code == 200:
                        lbl_gemini_status.config(text="✓ Gemini Key VALID and active!", fg="#a6e3a1")
                    else:
                        lbl_gemini_status.config(text=f"✗ Gemini Error {r.status_code}: {r.text[:40]}", fg="#f38ba8")
                except Exception as ex:
                    lbl_gemini_status.config(text=f"✗ Connection error: {str(ex)[:35]}", fg="#f38ba8")
            threading.Thread(target=_test, daemon=True).start()

        tk.Button(gemini_frame, text="🧪 Test Gemini", bg="#313244", fg="#cdd6f4", font=("Segoe UI", 8), bd=0, padx=8, pady=2, command=test_gemini).pack(anchor="e", pady=(0, 2))

        # Bottom Actions
        btn_frame = tk.Frame(win, bg="#181825")
        btn_frame.pack(pady=10)

        lbl_global_msg = tk.Label(win, text="", bg="#181825", font=("Segoe UI", 8))
        lbl_global_msg.pack()

        def save_all_keys():
            new_groq = ent_groq.get().strip()
            new_gemini = ent_gemini.get().strip()

            env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            try:
                with open(env_file, "w", encoding="utf-8") as f:
                    if new_gemini:
                        f.write(f"GEMINI_API_KEY={new_gemini}\n")
                    if new_groq:
                        f.write(f"GROQ_API_KEY={new_groq}\n")
            except Exception as e:
                lbl_global_msg.config(text=f"Error saving file: {e}", fg="#f38ba8")
                return

            if new_gemini:
                os.environ["GEMINI_API_KEY"] = new_gemini
                global GEMINI_API_KEY
                GEMINI_API_KEY = new_gemini
            if new_groq:
                os.environ["GROQ_API_KEY"] = new_groq
                global GROQ_API_KEY
                GROQ_API_KEY = new_groq

            lbl_global_msg.config(text="✓ All API Keys saved to .env and activated!", fg="#a6e3a1")
            self.update_status("Multi-AI Provider Keys Updated!", self.success_color)

        btn_save = tk.Button(
            btn_frame,
            text="💾 Save All Keys",
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            font=("Segoe UI", 9, "bold"),
            bd=0,
            padx=14,
            pady=4,
            cursor="hand2",
            command=save_all_keys
        )
        btn_save.pack(side="left", padx=6)

        btn_close = tk.Button(
            btn_frame,
            text="✕ Close",
            bg="#313244",
            fg="#f38ba8",
            font=("Segoe UI", 9),
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=win.destroy
        )
        btn_close.pack(side="left", padx=6)


# =====================================================================
# APPLICATION ENTRYPOINT
# =====================================================================
def main():
    root = tk.Tk()
    app = StealthOverlayApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
