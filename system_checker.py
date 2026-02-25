import sys
import os
import subprocess
import threading
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import wmi
import pythoncom
import platform
import re

def get_base_dir():
    """مسیر صحیح چه در حالت .py چه .exe"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

try:
    import jdatetime
    JDATETIME_AVAILABLE = True
except ImportError:
    JDATETIME_AVAILABLE = False

try:
    import sounddevice as sd
    import numpy as np
    import soundfile as sf
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from fpdf import FPDF
    import fpdf
    FPDF2 = hasattr(fpdf, '__version__') and fpdf.__version__ >= '2.0.0'
except ImportError:
    FPDF_AVAILABLE = False
    FPDF2 = False
else:
    FPDF_AVAILABLE = True

# ── Palette ──────────────────────────────────────────────────────────────────
BG          = "#F4F5FB"
SURFACE     = "#FFFFFF"
SURFACE2    = "#ECEEF8"
ACCENT      = "#5B5BD6"
ACCENT_H    = "#4747B8"
ACCENT_LITE = "#EEEEFF"
TEXT        = "#1A1A2E"
TEXT_DIM    = "#7878A0"
OK_BG       = "#00B894"
OK_LITE     = "#E0FBF4"
OK_FG       = "#007A63"
NOK_BG      = "#E17055"
NOK_LITE    = "#FFF0EC"
NOK_FG      = "#A0412E"
BORDER      = "#DDE0F0"
ROW_ODD     = "#FFFFFF"
ROW_EVEN    = "#F7F8FD"
HDR_STRIP   = "#5B5BD6"

FONT_TITLE  = ("Segoe UI", 13, "bold")
FONT_LABEL  = ("Segoe UI",  9, "bold")
FONT_BODY   = ("Segoe UI",  9)
FONT_SMALL  = ("Segoe UI",  8)
FONT_MONO   = ("Consolas",  9)

ROW_H = 32   # pixel height per row

# ─────────────────────────────────────────────────────────────────────────────
# Detection
# ─────────────────────────────────────────────────────────────────────────────
def detect_model():
    try:
        pythoncom.CoInitialize()
        for s in wmi.WMI().Win32_ComputerSystem(): return s.Model.strip()
    except: return "N/A"
    finally: pythoncom.CoUninitialize()

def detect_serial():
    try:
        pythoncom.CoInitialize()
        for b in wmi.WMI().Win32_BIOS(): return b.SerialNumber.strip()
    except: return "N/A"
    finally: pythoncom.CoUninitialize()

def detect_cpu():
    try:
        pythoncom.CoInitialize()
        for p in wmi.WMI().Win32_Processor(): return p.Name.strip()
    except: return "N/A"
    finally: pythoncom.CoUninitialize()

def detect_ram():
    try:
        pythoncom.CoInitialize()
        for cs in wmi.WMI().Win32_ComputerSystem():
            return f"{round(int(cs.TotalPhysicalMemory)/(1024**3))} GB"
    except: return "N/A"
    finally: pythoncom.CoUninitialize()

def _disk_type(disk_obj):
    m = (disk_obj.Model or "").upper()
    if "NVME" in m.replace(" ", ""): return "NVMe"
    if "SSD" in m: return "SSD"
    try:
        pythoncom.CoInitialize()
        ns = wmi.WMI(namespace=r"root\microsoft\windows\storage")
        for pd in ns.MSFT_PhysicalDisk():
            if (disk_obj.SerialNumber or "").strip() in (pd.SerialNumber or "") \
               or m in (pd.FriendlyName or "").upper():
                mt = int(pd.MediaType)
                if mt == 4: return "SSD"
                if mt == 3: return "HDD"
    except: pass
    finally:
        try: pythoncom.CoUninitialize()
        except: pass
    media = (disk_obj.MediaType or "").lower()
    return "SSD" if ("solid" in media or "ssd" in media) else "HDD"

def detect_hard():
    try:
        pythoncom.CoInitialize()
        drives = []
        for d in wmi.WMI().Win32_DiskDrive():
            sz = int(d.Size) if d.Size else 0
            if sz == 0: continue
            gb = sz / (1024**3)
            s  = f"{gb/1024:.1f} TB" if gb >= 1024 else f"{int(gb)} GB"
            drives.append(f"{_disk_type(d)} {s}")
        return ",  ".join(drives) if drives else "N/A"
    except: return "N/A"
    finally: pythoncom.CoUninitialize()

def detect_gpu():
    try:
        pythoncom.CoInitialize()
        gpus = []
        for g in wmi.WMI().Win32_VideoController():
            n = g.Name.strip()
            if n not in gpus: gpus.append(n)
        return ", ".join(gpus) if gpus else "N/A"
    except: return "N/A"
    finally: pythoncom.CoUninitialize()

def detect_display():
    try:
        import ctypes
        try:    ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except:
            try: ctypes.windll.user32.SetProcessDPIAware()
            except: pass
        u = ctypes.windll.user32; g = ctypes.windll.gdi32
        hdc = u.GetDC(0)
        w = g.GetDeviceCaps(hdc, 118); h = g.GetDeviceCaps(hdc, 117)
        u.ReleaseDC(0, hdc)
        return f"{w}x{h}" if w > 0 and h > 0 else \
               f"{u.GetSystemMetrics(0)}x{u.GetSystemMetrics(1)}"
    except: return "N/A"

def detect_windows_version():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        v, _ = winreg.QueryValueEx(k, "DisplayVersion"); return v
    except: return platform.version()

def detect_battery(): return ""

# ─────────────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────────────
def _runas(p):
    import ctypes
    ctypes.windll.shell32.ShellExecuteW(None, "runas", p, None, None, 1)

def run_passmark():
    e = os.path.join(get_base_dir(), "Passmark", "PerformanceTestPortable.exe")
    _runas(e) if os.path.exists(e) else messagebox.showerror("خطا", f"یافت نشد:\n{e}")

def run_crystaldisk():
    e = os.path.join(get_base_dir(), "CrystalDiskInfo.9.7.2.Portable", "CrystalDiskInfoPortable.exe")
    _runas(e) if os.path.exists(e) else messagebox.showerror("خطا", f"یافت نشد:\n{e}")

def run_monitor_test():
    e = os.path.join(get_base_dir(), "تست مانیتور.exe")
    _runas(e) if os.path.exists(e) else messagebox.showerror("خطا", "تست مانیتور.exe یافت نشد.")


def play_beep(channel='both'):
    if not SOUNDDEVICE_AVAILABLE:
        messagebox.showerror("خطا", "pip install sounddevice"); return
    dur, freq, sr = 0.5, 1000, 44100
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    w = 0.3 * np.sin(2 * np.pi * freq * t)
    if   channel == 'left':  s = np.zeros((len(w), 2)); s[:, 0] = w
    elif channel == 'right': s = np.zeros((len(w), 2)); s[:, 1] = w
    else:                    s = np.column_stack((w, w))
    sd.play(s, sr)

def stop_sound():
    if SOUNDDEVICE_AVAILABLE: sd.stop()

mic_recordings = {}

def record_microphone(record_btn, play_btn, row_idx):
    if not SOUNDDEVICE_AVAILABLE:
        messagebox.showerror("خطا", "pip install sounddevice numpy soundfile"); return
    duration, sr = 5, 44100
    record_btn.config(state=tk.DISABLED); play_btn.config(state=tk.DISABLED)
    def countdown(n):
        if n > 0: record_btn.config(text=f"⏺  {n}s"); record_btn.after(1000, countdown, n-1)
        else:     record_btn.config(text="● ضبط ۵ ثانیه")
    def _rec():
        rec = sd.rec(int(duration*sr), samplerate=sr, channels=1, dtype='float64')
        sd.wait()
        mic_recordings[row_idx] = (rec, sr)
        play_btn.config(state=tk.NORMAL, command=lambda: play_mic(row_idx))
        record_btn.config(state=tk.NORMAL, text="● ضبط ۵ ثانیه")
    countdown(duration); threading.Thread(target=_rec, daemon=True).start()

def play_mic(row_idx):
    if row_idx in mic_recordings:
        d, sr = mic_recordings[row_idx]; sd.play(d, sr)

def open_camera():
    try: subprocess.Popen(["explorer", "microsoft.windows.camera:"])
    except Exception as e: messagebox.showerror("خطا", f"دوربین باز نشد:\n{e}")

def run_keyboard_test():
    e = os.path.join(get_base_dir(), "تست کیبورد.exe")
    _runas(e) if os.path.exists(e) else messagebox.showerror("خطا", "تست کیبورد.exe یافت نشد.")

def run_battery_test():
    e = os.path.join(get_base_dir(), "تست باطری.exe")
    _runas(e) if os.path.exists(e) else messagebox.showerror("خطا", "تست باطری.exe یافت نشد.")
# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────
def create_pdf(filename, model, serial, shop, date_str, rows_data, notes):
    if not FPDF_AVAILABLE:
        raise Exception("کتابخانه FPDF نصب نیست.")

    class PDF(FPDF):
        def header(self): pass
        def footer(self):
            self.set_y(-12); self.set_font("Tahoma", size=7)
            self.set_text_color(160, 160, 180)
            self.cell(0, 8, f"System Checker  |  {date_str}", align="C")

    pdf = PDF(); pdf.set_auto_page_break(auto=True, margin=14); pdf.add_page()

    fp = "C:\\Windows\\Fonts\\tahoma.ttf"
    if not os.path.exists(fp): raise Exception("فونت Tahoma یافت نشد.")
    if FPDF2: pdf.add_font("Tahoma", "", fp)
    else:
        pdf.add_font('Tahoma', '', fp, uni=True)
        bp = "C:\\Windows\\Fonts\\tahomabd.ttf"
        if os.path.exists(bp): pdf.add_font('Tahoma', 'B', bp, uni=True)

    WING = False
    wp = "C:\\Windows\\Fonts\\wingding.ttf"
    if os.path.exists(wp):
        try:
            if FPDF2: pdf.add_font("Wingdings", "", wp)
            else:     pdf.add_font('Wingdings', '', wp, uni=True)
            WING = True
        except: pass

    def r(t):
        try:
            from bidi.algorithm import get_display
            import arabic_reshaper
            return get_display(arabic_reshaper.reshape(str(t)))
        except:
            s = str(t); return s[::-1] if any('\u0600'<=c<='\u06FF' for c in s) else s

    # ── cover strip ──────────────────────────────────────────────
    pdf.set_fill_color(91, 91, 214)
    pdf.rect(0, 0, 210, 26, 'F')
    pdf.set_xy(0, 7); pdf.set_font("Tahoma", size=14); pdf.set_text_color(255, 255, 255)
    pdf.cell(210, 12, r("System Checker"), align='C')

    # ── info cards ───────────────────────────────────────────────
    def info_card(label, value, x, y, w=88):
        pdf.set_fill_color(238, 238, 255)
        pdf.rect(x, y, w, 14, 'F')
        pdf.set_text_color(120, 120, 170); pdf.set_xy(x+3, y+2)
        pdf.set_font("Tahoma", size=7); pdf.cell(w-6, 5, label)
        pdf.set_text_color(26, 26, 46);  pdf.set_xy(x+3, y+7)
        pdf.set_font("Tahoma", size=9); pdf.cell(w-6, 6, value[:40])

    info_card("Date",  date_str, 10, 32)
    info_card("Store", shop,     103, 32)
    info_card("Model",         model,    10,  50, 181)
    info_card("Serial / S/N",  serial,   10,  68, 181)

    # ── table ────────────────────────────────────────────────────
    pdf.set_xy(10, 88)
    pdf.set_fill_color(91, 91, 214); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Tahoma", size=9)
    pdf.cell(42, 9, "Section",       1, 0, 'C', True)
    pdf.cell(85, 9, "Specification", 1, 0, 'C', True)
    pdf.cell(24, 9, "OK",            1, 0, 'C', True)
    pdf.cell(24, 9, "NOT OK",        1, 1, 'C', True)

    for idx, (label, spec, ok, notok) in enumerate(rows_data):
        even = idx % 2 == 0
        base_fill = (245, 245, 255) if even else (255, 255, 255)
        pdf.set_fill_color(*base_fill); pdf.set_text_color(26, 26, 46)
        has_fa = any('\u0600' <= c <= '\u06FF' for c in spec)
        pdf.set_font("Tahoma", size=9)
        pdf.cell(42, 8, label,                         1, 0, 'L', even)
        pdf.cell(85, 8, r(spec) if has_fa else spec,   1, 0, 'R' if has_fa else 'L', even)

        # OK cell
        if ok == "✓":
            pdf.set_fill_color(0, 184, 148); pdf.set_text_color(255, 255, 255)
            if WING: pdf.set_font("Wingdings", size=11); pdf.cell(24, 8, "\u00FC", 1, 0, 'C', True); pdf.set_font("Tahoma", size=9)
            else:    pdf.set_font("Tahoma", size=8);     pdf.cell(24, 8, "OK",     1, 0, 'C', True)
        else:
            pdf.set_fill_color(*base_fill); pdf.set_text_color(26, 26, 46)
            pdf.cell(24, 8, "", 1, 0, 'C', even)

        # NOT OK cell
        if notok == "✓":
            pdf.set_fill_color(225, 112, 85); pdf.set_text_color(255, 255, 255)
            if WING: pdf.set_font("Wingdings", size=11); pdf.cell(24, 8, "\u00FC", 1, 1, 'C', True); pdf.set_font("Tahoma", size=9)
            else:    pdf.set_font("Tahoma", size=8);     pdf.cell(24, 8, "Not OK",    1, 1, 'C', True)
        else:
            pdf.set_fill_color(*base_fill); pdf.set_text_color(26, 26, 46)
            pdf.cell(24, 8, "", 1, 1, 'C', even)

    # ── notes ────────────────────────────────────────────────────
    if notes:
        pdf.ln(6); pdf.set_text_color(91, 91, 214); pdf.set_font("Tahoma", size=9)
        pdf.cell(0, 8, r("توضیحات") + " :", ln=True, align='L')
        pdf.set_text_color(26, 26, 46); pdf.set_fill_color(248, 248, 255)
        has_fa = any('\u0600' <= c <= '\u06FF' for c in notes)
        pdf.multi_cell(0, 7, r(notes) if has_fa else notes,
                       border=1, align='R' if has_fa else 'L', fill=True)

    pdf.output(filename)

# ─────────────────────────────────────────────────────────────────────────────
# UI atoms
# ─────────────────────────────────────────────────────────────────────────────
def flat_btn(parent, text, command,
             bg=ACCENT, fg="#fff", hbg=ACCENT_H, hfg="#fff",
             px=10, py=4, font=FONT_SMALL):
    b = tk.Button(parent, text=text, command=command,
                  bg=bg, fg=fg, activebackground=hbg, activeforeground=hfg,
                  relief=tk.FLAT, font=font, cursor="hand2",
                  padx=px, pady=py, bd=0, highlightthickness=0)
    b.bind("<Enter>", lambda e: b.config(bg=hbg, fg=hfg))
    b.bind("<Leave>", lambda e: b.config(bg=bg,  fg=fg))
    return b

def pill_toggle(parent, var, on_bg, on_fg, off_bg, off_fg,
                on_txt, off_txt, w=72, h=24):
    cv = tk.Canvas(parent, width=w, height=h,
                   bg=parent["bg"], highlightthickness=0, cursor="hand2")
    rr = h // 2
    def draw(*_):
        cv.delete("all")
        val = var.get()
        cbg = on_bg if val else off_bg
        cfg = on_fg if val else off_fg
        txt = on_txt if val else off_txt
        cv.create_oval(0, 0, h, h, fill=cbg, outline="")
        cv.create_oval(w-h, 0, w, h, fill=cbg, outline="")
        cv.create_rectangle(rr, 0, w-rr, h, fill=cbg, outline="")
        cv.create_text(w//2, h//2, text=txt, fill=cfg,
                       font=("Segoe UI", 7, "bold"))
    cv.bind("<Button-1>", lambda e: var.set(not var.get()))
    var.trace_add("write", draw); draw()
    return cv

# ─────────────────────────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────────────────────────
class SystemCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("System Checker")
        self.root.resizable(True, True)
        self.root.configure(bg=BG)

        s = ttk.Style(); s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=FONT_BODY)
        s.configure("TFrame",    background=BG)
        s.configure("TLabel",    background=BG, foreground=TEXT)
        s.configure("TCombobox", fieldbackground=SURFACE2, foreground=TEXT,
                    background=SURFACE2, arrowcolor=ACCENT, borderwidth=0)
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE2)],
              foreground=[("readonly", TEXT)])
        s.configure("TScrollbar", background=SURFACE2, troughcolor=BG,
                    arrowcolor=ACCENT, borderwidth=0)

        self.model_var  = tk.StringVar(value="در حال تشخیص...")
        self.serial_var = tk.StringVar(value="در حال تشخیص...")
        self.shop_var   = tk.StringVar()
        self.shops      = ["IFA", "DIBA(huawei)", "VISTA", "DIVA(Naghsh)"]
        self.date_var   = tk.StringVar()
        self.update_date()

        self._topbar()
        self._fields()
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)
        self._table()
        self._notes()

        self.root.update_idletasks()
        self.root.geometry(f"1120x{130 + len(self.rows)*ROW_H + 200}")
        self.root.minsize(980, 540)
        self.detect_all()

    # ── top bar ──────────────────────────────────────────────────
    def _topbar(self):
        bar = tk.Frame(self.root, bg=SURFACE, pady=10)
        bar.pack(fill=tk.X)
        left = tk.Frame(bar, bg=SURFACE); left.pack(side=tk.LEFT, padx=16)
        tk.Label(left, text="⬡", bg=SURFACE, fg=ACCENT,
                 font=("Segoe UI", 18)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(left, text="System Checker", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        tk.Label(left, text=" 🔥 ", bg=SURFACE, fg=TEXT_DIM,
                 font=("Segoe UI", 10)).pack(side=tk.LEFT)
        flat_btn(bar, "  💾  ذخیره PDF  ", self.save_pdf,
                 bg=ACCENT, fg="#fff", hbg=ACCENT_H, hfg="#fff",
                 px=18, py=9, font=FONT_LABEL).pack(side=tk.RIGHT, padx=16)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

    # ── fields ───────────────────────────────────────────────────
    def _fields(self):
        row = tk.Frame(self.root, bg=BG, pady=8)
        row.pack(fill=tk.X, padx=14)
        def lbl(t):
            tk.Label(row, text=t, bg=BG, fg=TEXT_DIM,
                     font=FONT_SMALL).pack(side=tk.LEFT, padx=(10, 3))
        def ent(var, w, mono=False):
            e = tk.Entry(row, textvariable=var, width=w,
                         bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
                         relief=tk.FLAT, font=FONT_MONO if mono else FONT_BODY,
                         bd=0, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT)
            e.pack(side=tk.LEFT, padx=(0, 6), ipady=4)
        lbl("MODEL:"); ent(self.model_var, 42)
        lbl("S/N:");   ent(self.serial_var, 26, True)
        tk.Label(row, text="مغازه:", bg=BG, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side=tk.LEFT, padx=(10, 3))
        cb = ttk.Combobox(row, textvariable=self.shop_var,
                          values=self.shops, state="readonly", width=15)
        cb.pack(side=tk.LEFT, padx=(0, 6), ipady=3); cb.current(0)
        lbl("تاریخ:"); ent(self.date_var, 13)

    # ── table ────────────────────────────────────────────────────
    def _table(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 0))

        # ── header row using grid ─────────────────────────────────
        hdr = tk.Frame(outer, bg=HDR_STRIP)
        hdr.pack(fill=tk.X, side=tk.TOP)
        hdr.grid_columnconfigure(0, minsize=160, weight=0)
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_columnconfigure(2, minsize=260, weight=0)
        hdr.grid_columnconfigure(3, minsize=180, weight=0)
        for c, txt in enumerate(["بخش", "مشخصات (قابل ویرایش)", "عملیات", "وضعیت"]):
            tk.Label(hdr, text=txt, bg=HDR_STRIP, fg="#fff",
                     font=FONT_LABEL, pady=7, anchor="center")\
              .grid(row=0, column=c, sticky="nsew", padx=1)

        # ── scrollable canvas ─────────────────────────────────────
        cf = tk.Frame(outer, bg=BG); cf.pack(fill=tk.BOTH, expand=True)
        cv = tk.Canvas(cf, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(cf, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # body frame inside canvas — uses grid for columns
        body = tk.Frame(cv, bg=BG)
        wid  = cv.create_window((0, 0), window=body, anchor="nw")

        def _resize(e=None):
            cv.configure(scrollregion=cv.bbox("all"))
            cv.itemconfig(wid, width=cv.winfo_width())

        body.bind("<Configure>", _resize)
        cv.bind("<Configure>",   lambda e: cv.itemconfig(wid, width=e.width))
        cv.bind_all("<MouseWheel>",
                    lambda e: cv.yview_scroll(-1*(e.delta//120), "units"))

        # body grid columns mirror header
        body.grid_columnconfigure(0, minsize=160, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, minsize=260, weight=0)
        body.grid_columnconfigure(3, minsize=180, weight=0)

        self.rows = [
            ("CPU",                detect_cpu,             [("▶ Passmark",        run_passmark)]),
            ("RAM",                detect_ram,             []),
            ("HARD",               detect_hard,            [("▶ CrystalDiskInfo", run_crystaldisk)]),
            ("GPU",                detect_gpu,             []),
            ("DISPLAY",            detect_display,         [("▶ تست مانیتور",     run_monitor_test)]),
            ("WIFI",               lambda: "",             []),
            ("SOUND",              lambda: "",             [("◀ چپ",  lambda: play_beep('left')),
                                                            ("راست ▶",lambda: play_beep('right')),
                                                            ("■ قطع", stop_sound)]),
            ("MICROPHONE",         lambda: "",             []),
            ("CAMERA",             lambda: "",             [("📷 دوربین", open_camera)]),
            ("TOUCHPAD",           lambda: "",             []),
            ("KEYBOARD",           lambda: "",             [("▶ تست کیبورد", run_keyboard_test)]),
            ("BATTERY",            detect_battery,         [("▶ تست باطری",  run_battery_test)]),
            ("INSTALL ALL DRIVER", lambda: "",             []),
            ("INSTALL WINDOWS",    detect_windows_version, []),
            ("TIME WORK",          lambda: "",             []),
            ("AUX",                lambda: "",             []),
            ("USB PORTS",          lambda: "",             []),
            ("HDMI VGA",           lambda: "",             []),
            ("DVD",                lambda: "",             []),
            ("LAN",                lambda: "",             []),
        ]
        self.spec_vars = []; self.ok_vars = []; self.notok_vars = []

        for i, (label, _, actions) in enumerate(self.rows):
            row_bg = ROW_ODD if i % 2 == 0 else ROW_EVEN

            # col 0 — section label
            lf = tk.Frame(body, bg=SURFACE2, height=ROW_H)
            lf.grid(row=i, column=0, sticky="nsew", padx=(0,1), pady=1)
            lf.grid_propagate(False)
            tk.Label(lf, text=label, bg=SURFACE2, fg=ACCENT,
                     font=FONT_LABEL, anchor="w", padx=10)\
              .place(relx=0, rely=0.5, anchor="w", x=0, y=0,
                     relwidth=1, relheight=1)

            # col 1 — spec entry
            sv = tk.StringVar()
            ef = tk.Frame(body, bg=row_bg, height=ROW_H)
            ef.grid(row=i, column=1, sticky="nsew", padx=1, pady=1)
            ef.grid_propagate(False)
            tk.Entry(ef, textvariable=sv, bg=row_bg, fg=TEXT,
                     insertbackground=ACCENT, relief=tk.FLAT,
                     font=FONT_MONO, highlightthickness=0, bd=4)\
              .place(relx=0, rely=0, relwidth=1, relheight=1)

            # col 2 — actions
            af = tk.Frame(body, bg=row_bg, height=ROW_H)
            af.grid(row=i, column=2, sticky="nsew", padx=1, pady=1)
            af.grid_propagate(False)
            inner_a = tk.Frame(af, bg=row_bg)
            inner_a.place(relx=0, rely=0.5, anchor="w", x=4)

            if label == "MICROPHONE":
                play_btn = flat_btn(inner_a, "▶ پخش", lambda: None,
                                    bg=SURFACE2, fg=TEXT_DIM,
                                    hbg=ACCENT_LITE, hfg=ACCENT)
                play_btn.config(state=tk.DISABLED)
                rec_btn  = flat_btn(inner_a, "● ضبط ۵ ثانیه", lambda: None,
                                    bg=ACCENT_LITE, fg=ACCENT,
                                    hbg=ACCENT, hfg="#fff")
                rec_btn.config(command=lambda rb=rec_btn, pb=play_btn, idx=i:
                                   record_microphone(rb, pb, idx))
                rec_btn.pack(side=tk.LEFT, padx=3)
                play_btn.pack(side=tk.LEFT, padx=3)
            else:
                for txt, cb in actions:
                    flat_btn(inner_a, txt, cb,
                             bg=ACCENT_LITE, fg=ACCENT,
                             hbg=ACCENT, hfg="#fff")\
                        .pack(side=tk.LEFT, padx=3)

            # col 3 — OK / NOK toggles
            sf = tk.Frame(body, bg=row_bg, height=ROW_H)
            sf.grid(row=i, column=3, sticky="nsew", padx=1, pady=1)
            sf.grid_propagate(False)
            inner_s = tk.Frame(sf, bg=row_bg)
            inner_s.place(relx=0.5, rely=0.5, anchor="center")

            ov = tk.BooleanVar(); nv = tk.BooleanVar()
            pill_toggle(inner_s, ov,
                        OK_BG,  "#fff", OK_LITE,  OK_FG,  "✓  OK",  "  OK")\
                .pack(side=tk.LEFT, padx=4)
            pill_toggle(inner_s, nv,
                        NOK_BG, "#fff", NOK_LITE, NOK_FG, "✗ Not OK", " Not OK")\
                .pack(side=tk.LEFT, padx=4)

            self.spec_vars.append(sv)
            self.ok_vars.append(ov)
            self.notok_vars.append(nv)

    # ── notes ────────────────────────────────────────────────────
    def _notes(self):
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X, pady=(4, 0))
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill=tk.X, padx=12, pady=(4, 10))
        tk.Label(foot, text="توضیحات :", bg=BG, fg=TEXT_DIM,
                 font=FONT_LABEL).pack(anchor=tk.E, pady=(0, 3))
        tf = tk.Frame(foot, bg=SURFACE2,
                      highlightthickness=1, highlightbackground=BORDER)
        tf.pack(fill=tk.X)
        sb = ttk.Scrollbar(tf); sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.notes_text = tk.Text(
            tf, height=4, bg=SURFACE2, fg=TEXT,
            insertbackground=ACCENT, relief=tk.FLAT,
            font=FONT_BODY, wrap=tk.WORD,
            yscrollcommand=sb.set, padx=10, pady=6, bd=0)
        self.notes_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sb.config(command=self.notes_text.yview)

    # ── detection ────────────────────────────────────────────────
    def update_date(self):
        if JDATETIME_AVAILABLE:
            self.date_var.set(jdatetime.datetime.now().strftime("%Y/%m/%d"))
        else:
            self.date_var.set(datetime.datetime.now().strftime("%Y-%m-%d"))

    def detect_all(self):
        threading.Thread(target=self._upd_ms, daemon=True).start()
        for i, (_, fn, _) in enumerate(self.rows):
            threading.Thread(target=self._upd_spec, args=(i, fn), daemon=True).start()

    def _upd_ms(self):
        m, s = detect_model(), detect_serial()
        self.root.after(0, lambda: self.model_var.set(m))
        self.root.after(0, lambda: self.serial_var.set(s))

    def _upd_spec(self, idx, fn):
        try:    v = fn()
        except Exception as e: v = f"خطا: {e}"
        self.root.after(0, lambda: self.spec_vars[idx].set(v))

    # ── save PDF ─────────────────────────────────────────────────
    def save_pdf(self):
        if not FPDF_AVAILABLE:
            messagebox.showerror("خطا", "pip install fpdf"); return
        model, serial = self.model_var.get(), self.serial_var.get()
        shop, date_str = self.shop_var.get(), self.date_var.get()
        cl = lambda s: re.sub(r'[\\/*?:"<>|]', "", s)
        cd = cl(date_str.split()[0] if " " in date_str else date_str)
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=f"{cd}-{cl(model)}-{cl(shop)}.pdf",
            title="محل ذخیره PDF")
        if not path: return
        rows = [(lbl,
                 self.spec_vars[i].get(),
                 "✓" if self.ok_vars[i].get()    else "",
                 "✓" if self.notok_vars[i].get() else "")
                for i, (lbl, _, _) in enumerate(self.rows)]
        notes = self.notes_text.get("1.0", tk.END).strip()
        try:
            create_pdf(path, model, serial, shop, date_str, rows, notes)
            messagebox.showinfo("ذخیره شد", f"PDF ذخیره شد:\n{path}")
        except Exception as e:
            messagebox.showerror("خطا", f"خطا:\n{e}")

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    SystemCheckerApp(root)
    root.mainloop()