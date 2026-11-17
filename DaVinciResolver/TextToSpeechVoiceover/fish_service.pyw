# Fish Voiceover for DaVinci Resolve - background helper.
# The free Resolve's Lua sandbox has no file I/O, processes or HTTP. So "Fish Voiceover.lua"
# writes a FISHVO_REQ line into Resolve's log (printerr); this helper tails the log, shows the
# window, calls fish.audio, saves a stereo WAV into <root>\Projects\<project>\ and answers with
# tiny marker WAVs in the queue whose names carry the path (read via MediaStorage:GetFileList).
import array, ctypes, datetime, glob, io, json, os, re, sys, threading, time, urllib.request, urllib.error, wave
import tkinter as tk
from tkinter import ttk, messagebox

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "FishVoiceoverResolve")
# Resolve's MediaStorage can't list AppData, so the queue lives under Documents.
QUEUE = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Documents", "FishVoiceoverResolve", "queue")
RESOLVE_LOG = os.path.join(os.environ.get("APPDATA", ""), "Blackmagic Design", "DaVinci Resolve", "Support", "logs", "ResolveDebug.txt")
CONFIG = os.path.join(APP_DIR, "config.json")
MODELS = ["s2.1-pro", "s2-pro", "s2.1-pro-free", "s1", "drama-3"]
DEFAULTS = {
    "api_key": "",
    "output_root": os.path.join(os.path.expanduser("~"), "Videos"),
    "voices": {"Мака": "ffc82ee807894516b5916f631578628f"},
    "voice": "Мака",
    "volume": 3,
    "speed": 1.0,
    "model": "s2.1-pro",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def safe_name(s, limit=60):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", s).strip().rstrip(".")
    s = re.sub(r"\s+", " ", s)
    return s[:limit].strip() or "untitled"


def project_dir(cfg, project):
    return os.path.join(cfg["output_root"], "Projects", safe_name(project, 120))


def write_marker(name):
    """Tiny silent WAV in the queue: only its name matters (GetFileList lists media files only)."""
    os.makedirs(QUEUE, exist_ok=True)
    path = os.path.join(QUEUE, name)
    tmp = os.path.join(QUEUE, "tmp_" + str(os.getpid()) + "_" + str(time.time_ns()))
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 80)
    os.replace(tmp, path)


SAFE = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ._()-")


def encode_path(p):
    """GetFileList returns non-ASCII names as '?', so the path travels percent-encoded."""
    return "".join(chr(b) if b in SAFE else "%%%02X" % b for b in p.encode("utf-8"))


def send_answer(req_id, path=None, text=""):
    """Answer = res_<id>_pNNN_<chunk>.wav (encoded path) and res_<id>_tNNN_<chunk>.wav
    (encoded voiced text, becomes the clip marker), then res_<id>_end / _cancel."""
    if path:
        for kind, value in (("p", path), ("t", text[:2000])):
            enc = encode_path(value)
            for n in range(0, len(enc), 150):
                write_marker(f"res_{req_id}_{kind}{n // 150:03d}_{enc[n:n + 150]}.wav")
    write_marker(f"res_{req_id}_{'end' if path else 'cancel'}.wav")


def fish_tts(cfg, voice_id, text, volume, speed, model):
    body = {
        "text": text,
        "format": "wav",
        "sample_rate": 44100,
        "normalize": True,
        "latency": "normal",
        "prosody": {"speed": max(0.5, min(2.0, speed)), "volume": volume},
    }
    if voice_id:
        body["reference_id"] = voice_id
    req = urllib.request.Request(
        "https://api.fish.audio/v1/tts",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + cfg["api_key"], "Content-Type": "application/json", "model": model},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        hint = {401: " (check API key in Settings)", 402: " (no API credit for this model)"}.get(e.code, "")
        raise RuntimeError(f"fish.audio {e.code}{hint}: {detail}")


def write_stereo_wav(data, path):
    """Save fish.audio WAV as 16-bit stereo so it drops onto any stereo track."""
    with wave.open(io.BytesIO(data)) as src:
        ch, sw, sr = src.getnchannels(), src.getsampwidth(), src.getframerate()
        frames = src.readframes(src.getnframes())
    if ch == 1 and sw == 2:
        mono = array.array("h", frames)
        stereo = array.array("h", bytes(len(frames) * 2))
        stereo[0::2] = mono
        stereo[1::2] = mono
        frames, ch = stereo.tobytes(), 2
    with wave.open(path, "wb") as dst:
        dst.setnchannels(ch)
        dst.setsampwidth(sw)
        dst.setframerate(sr)
        dst.writeframes(frames)
    return len(frames) / (ch * sw * sr)


def bring_to_front(win):
    """Background processes can't take focus on Windows without this nudge."""
    win.deiconify()
    win.lift()
    win.attributes("-topmost", True)
    try:
        user32 = ctypes.windll.user32
        hwnd = int(win.wm_frame(), 16)
        user32.keybd_event(0x12, 0, 0, 0)  # Alt down/up unlocks SetForegroundWindow
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    win.focus_force()
    win.after(400, lambda: win.attributes("-topmost", False))


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, cfg):
        super().__init__(master)
        self.cfg, self.saved = cfg, False
        self.title("Fish Voiceover - Settings")
        self.transient(master)
        self.resizable(False, False)
        pad = {"padx": 8, "pady": 4}
        ttk.Label(self, text="fish.audio API key").grid(row=0, column=0, sticky="w", **pad)
        self.key = ttk.Entry(self, width=60, show="•")
        self.key.insert(0, cfg["api_key"])
        self.key.grid(row=0, column=1, **pad)
        ttk.Label(self, text="Output root").grid(row=1, column=0, sticky="w", **pad)
        self.root_dir = ttk.Entry(self, width=60)
        self.root_dir.insert(0, cfg["output_root"])
        self.root_dir.grid(row=1, column=1, **pad)
        ttk.Label(self, text="Files go to <root>\\Projects\\<project name>\\", foreground="#777").grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(self, text="Voices\n(Name = model ID,\none per line)").grid(row=3, column=0, sticky="nw", **pad)
        self.voices = tk.Text(self, width=60, height=6)
        self.voices.insert("1.0", "\n".join(f"{n} = {i}" for n, i in cfg["voices"].items()))
        self.voices.grid(row=3, column=1, **pad)
        b = ttk.Frame(self)
        b.grid(row=4, column=1, sticky="e", **pad)
        ttk.Button(b, text="Save", command=self.save).pack(side="right", padx=4)
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        self.grab_set()

    def save(self):
        voices = {}
        for line in self.voices.get("1.0", "end").splitlines():
            if "=" in line:
                n, i = line.split("=", 1)
                if n.strip() and i.strip():
                    voices[n.strip()] = i.strip()
        if not voices:
            messagebox.showerror("Fish Voiceover", "Add at least one voice: Name = model ID", parent=self)
            return
        self.cfg.update(api_key=self.key.get().strip(), output_root=self.root_dir.get().strip(), voices=voices)
        save_config(self.cfg)
        self.saved = True
        self.destroy()


class VoiceoverWindow(tk.Toplevel):
    def __init__(self, master, req_id, project, timecode):
        super().__init__(master)
        self.req_id, self.project, self.cfg, self.answered = req_id, project, load_config(), False
        self.title(f"Fish Voiceover - {project}")
        self.minsize(600, 380)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text=f"Insert at {timecode}  •  first free audio track").pack(side="left")
        ttk.Button(top, text="Settings", command=self.open_settings).pack(side="right")

        self.text = tk.Text(self, wrap="word", height=10, font=("Segoe UI", 11), undo=True)
        self.text.pack(fill="both", expand=True, **pad)

        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Voice").pack(side="left")
        self.voice = ttk.Combobox(row, state="readonly", width=16)
        self.voice.pack(side="left", padx=(4, 12))
        ttk.Label(row, text="Volume (dB)").pack(side="left")
        self.volume = ttk.Spinbox(row, from_=-20, to=20, increment=1, width=5)
        self.volume.set(self.cfg["volume"])
        self.volume.pack(side="left", padx=(4, 12))
        ttk.Label(row, text="Speed").pack(side="left")
        self.speed = ttk.Spinbox(row, from_=0.5, to=2.0, increment=0.05, width=5)
        self.speed.set(self.cfg["speed"])
        self.speed.pack(side="left", padx=(4, 12))
        ttk.Label(row, text="Model").pack(side="left")
        self.model = ttk.Combobox(row, values=MODELS, state="readonly", width=13)
        self.model.set(self.cfg["model"] if self.cfg["model"] in MODELS else MODELS[0])
        self.model.pack(side="left", padx=4)
        self.refresh_voices()

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        self.status = ttk.Label(bottom, text=f"Saves to {project_dir(self.cfg, project)}", foreground="#666")
        self.status.pack(side="left", fill="x", expand=True)
        self.go = ttk.Button(bottom, text="Generate & Insert  (Ctrl+Enter)", command=self.generate)
        self.go.pack(side="right")
        ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side="right", padx=6)
        self.bind("<Control-Return>", lambda e: (self.generate(), "break"))
        self.bind("<Escape>", lambda e: self.cancel())
        bring_to_front(self)
        self.text.focus_set()
        if not self.cfg["api_key"]:
            self.after(300, self.open_settings)

    def answer(self, path=None, text=""):
        if not self.answered:
            self.answered = True
            send_answer(self.req_id, path, text)

    def cancel(self):
        self.answer()
        self.destroy()

    def refresh_voices(self):
        names = list(self.cfg["voices"])
        self.voice["values"] = names
        self.voice.set(self.cfg["voice"] if self.cfg["voice"] in names else names[0])

    def open_settings(self):
        d = SettingsDialog(self, self.cfg)
        self.wait_window(d)
        if d.saved:
            self.refresh_voices()
            self.status.config(text=f"Saves to {project_dir(self.cfg, self.project)}")

    def generate(self):
        text = self.text.get("1.0", "end").strip()
        if not text:
            return messagebox.showwarning("Fish Voiceover", "Enter the text to voice.", parent=self)
        if not self.cfg["api_key"]:
            return self.open_settings()
        try:
            volume, speed = float(self.volume.get()), float(self.speed.get())
        except ValueError:
            return messagebox.showwarning("Fish Voiceover", "Volume and Speed must be numbers.", parent=self)
        voice, model = self.voice.get(), self.model.get()
        self.cfg.update(voice=voice, volume=volume, speed=speed, model=model)
        save_config(self.cfg)
        self.go.state(["disabled"])
        self.status.config(text="Generating...")
        threading.Thread(target=self.worker, args=(text, voice, volume, speed, model), daemon=True).start()

    def worker(self, text, voice, volume, speed, model):
        try:
            data = fish_tts(self.cfg, self.cfg["voices"].get(voice, ""), text, volume, speed, model)
            folder = project_dir(self.cfg, self.project)
            os.makedirs(folder, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(folder, f"{stamp}_{safe_name(voice, 20)}_{safe_name(text, 30)}.wav")
            write_stereo_wav(data, path)
            self.after(0, lambda: (self.answer(path, text), self.destroy()))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self.fail(msg))

    def fail(self, msg):
        self.go.state(["!disabled"])
        self.status.config(text="Error")
        messagebox.showerror("Fish Voiceover", msg, parent=self)


def decode_line(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1251", "replace")


class Service:
    def __init__(self):
        os.makedirs(QUEUE, exist_ok=True)
        self.root = tk.Tk()
        self.root.withdraw()
        self.seen = set()
        self.pos = os.path.getsize(RESOLVE_LOG) if os.path.exists(RESOLVE_LOG) else 0
        self.buf = b""
        self.root.after(200, self.poll)
        self.root.after(1000, self.cleanup)

    def poll(self):
        try:
            for line in self.new_log_lines():
                parts = line.split("\t")
                if parts[0] == "FISHVO_REQ" and len(parts) >= 4 and parts[1] not in self.seen:
                    self.seen.add(parts[1])
                    write_marker(f"ack_{parts[1]}.wav")
                    VoiceoverWindow(self.root, parts[1], parts[2] or "Untitled Project", parts[3])
                elif parts[0] == "FISHVO_MSG" and len(parts) >= 2:
                    self.show_message("\n".join(parts[1:]))
        except Exception:
            pass
        self.root.after(200, self.poll)

    def new_log_lines(self):
        if not os.path.exists(RESOLVE_LOG):
            return []
        size = os.path.getsize(RESOLVE_LOG)
        if size < self.pos:  # log rotated on Resolve restart
            self.pos, self.buf = 0, b""
        if size == self.pos:
            return []
        with open(RESOLVE_LOG, "rb") as f:
            f.seek(self.pos)
            data = f.read(size - self.pos)
        self.pos = size
        chunks = (self.buf + data).split(b"\n")
        self.buf = chunks.pop()
        return [decode_line(c).strip("\r") for c in chunks if b"FISHVO_" in c]

    def cleanup(self):
        try:
            for path in glob.glob(os.path.join(QUEUE, "*")):
                if time.time() - os.path.getmtime(path) > 120:
                    os.remove(path)
        except Exception:
            pass
        self.root.after(30000, self.cleanup)

    def show_message(self, text):
        top = tk.Toplevel(self.root)
        top.withdraw()
        bring_to_front(top)
        top.withdraw()
        messagebox.showerror("Fish Voiceover", text, parent=top)
        top.destroy()

    def run(self):
        self.root.mainloop()


def single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "FishVoiceoverResolveService")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if single_instance():
        Service().run()
