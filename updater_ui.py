import os
import sys

# Prevent Windows cmd code-page crash (cp1252 UnicodeEncodeError)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import time
import zipfile
import threading
import subprocess
import requests
import tkinter as tk
from tkinter import ttk

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "repo_owner": "sigmasigmaboi124",
        "repo_name": "lil-somthin",
        "current_version": "2.6.2",
    }

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Failed to save config: {e}")

class UpdaterUI(tk.Tk):
    def __init__(self, on_finish=None, force_check=False):
        super().__init__()
        self.on_finish = on_finish
        self.force_check = force_check
        self.cfg = load_config()
        self.current_ver = self.cfg.get("current_version", "2.6.2").lstrip("v")
        self.repo_owner = self.cfg.get("repo_owner", "sigmasigmaboi124")
        self.repo_name = self.cfg.get("repo_name", "lil-somthin")

        # Window Appearance
        self.title("TDS Macro Launcher & Updater")
        self.geometry("460x250")
        self.resizable(False, False)
        self.configure(bg="#181825")
        self.center_window()

        # Modern Dark Styling
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Update.Horizontal.TProgressbar",
            troughcolor="#11111b",
            background="#89b4fa",
            bordercolor="#11111b",
            lightcolor="#89b4fa",
            darkcolor="#74c7ec",
            thickness=14
        )

        # Header Title
        self.lbl_title = tk.Label(
            self,
            text="TDS Macro & Remote Control",
            font=("Segoe UI", 14, "bold"),
            fg="#cdd6f4",
            bg="#181825"
        )
        self.lbl_title.pack(pady=(22, 6))

        # Status Message
        self.lbl_status = tk.Label(
            self,
            text="Checking for latest releases...",
            font=("Segoe UI", 10),
            fg="#a6adc8",
            bg="#181825"
        )
        self.lbl_status.pack(pady=(4, 14))

        # Progress Bar
        self.progress = ttk.Progressbar(
            self,
            style="Update.Horizontal.TProgressbar",
            mode="indeterminate",
            length=380
        )
        self.progress.pack(pady=4)
        self.progress.start(12)

        # Details / Subtext
        self.lbl_detail = tk.Label(
            self,
            text=f"Installed Version: v{self.current_ver} | Repo: {self.repo_owner}/{self.repo_name}",
            font=("Segoe UI", 9),
            fg="#6c7086",
            bg="#181825"
        )
        self.lbl_detail.pack(side="bottom", pady=14)

        # Start update check thread
        threading.Thread(target=self.run_check_flow, daemon=True).start()

    def center_window(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def update_status(self, text, detail=None, color="#a6adc8"):
        self.lbl_status.config(text=text, fg=color)
        if detail is not None:
            self.lbl_detail.config(text=detail)

    def run_check_flow(self):
        time.sleep(0.5)
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        headers = {"User-Agent": "TDS-Macro-Updater/1.0", "Accept": "application/vnd.github.v3+json"}
        token = self.cfg.get("github_token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            res = requests.get(api_url, headers=headers, timeout=6)
            if res.status_code == 200:
                release_data = res.json()
                latest_tag = release_data.get("tag_name", "").lstrip("v")
                
                if latest_tag and self.is_newer_version(latest_tag, self.current_ver):
                    # Found update! Look for zip package
                    assets = release_data.get("assets", [])
                    zip_asset = next((a for a in assets if a.get("name", "").endswith(".zip")), None)
                    if zip_asset:
                        dl_url = zip_asset.get("browser_download_url")
                        self.download_and_apply(dl_url, latest_tag, release_data.get("name", ""))
                        return

            elif res.status_code == 404:
                # Repo is private or release not created yet
                pass
            
            # If we reached here, no update needed or no release package found
            self.progress.stop()
            self.progress.config(mode="determinate", value=100)
            self.update_status(f"App is up to date! (v{self.current_ver})", "Launching macro...", color="#a6e3a1")
            time.sleep(1.2)
            self.finish()

        except Exception as e:
            self.progress.stop()
            self.update_status("Skipping update check (Offline / Connection issue)", f"Error: {e}", color="#fab387")
            time.sleep(1.2)
            self.finish()

    def is_newer_version(self, latest, current):
        try:
            v_latest = [int(p) for p in latest.split(".") if p.isdigit()]
            v_curr = [int(p) for p in current.split(".") if p.isdigit()]
            return v_latest > v_curr
        except Exception:
            return latest > current

    def download_and_apply(self, download_url, new_ver, release_title):
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.update_status(f"New Version Found: v{new_ver}!", "Preparing download...", color="#89b4fa")

        temp_dir = os.path.join(os.environ.get("TEMP", "."), "tds_macro_update")
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, "release.zip")

        try:
            req = requests.get(download_url, stream=True, timeout=30)
            total_size = int(req.headers.get("content-length", 0))
            downloaded = 0

            with open(zip_path, "wb") as f:
                for chunk in req.iter_content(chunk_size=16384):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            cur_mb = downloaded / (1024 * 1024)
                            tot_mb = total_size / (1024 * 1024)
                            self.progress["value"] = pct
                            self.lbl_status.config(text=f"Downloading update v{new_ver}: {pct}%")
                            self.lbl_detail.config(text=f"{cur_mb:.2f} MB / {tot_mb:.2f} MB ({downloaded}/{total_size} bytes)")

            self.update_status("Extracting new files...", "Almost ready...", color="#f9e2af")
            extract_dir = os.path.join(temp_dir, "extracted")
            if os.path.exists(extract_dir):
                import shutil
                shutil.rmtree(extract_dir, ignore_errors=True)
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)

            # Update local config version
            self.cfg["current_version"] = new_ver
            save_config(self.cfg)

            self.update_status("Applying update & restarting...", "Restarting application...", color="#a6e3a1")
            time.sleep(0.8)
            self.apply_batch_update(extract_dir)

        except Exception as e:
            self.update_status("Update download failed!", f"Error: {e}", color="#f38ba8")
            time.sleep(2)
            self.finish()

    def apply_batch_update(self, source_dir):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pid = os.getpid()
        bat_path = os.path.join(os.environ.get("TEMP", "."), "apply_macro_update.bat")

        # Batch script that waits for Python/App to close, copies files, and relaunches
        bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
taskkill /F /PID {pid} 2>nul
timeout /t 1 /nobreak >nul

:: Copy new files into the application directory
xcopy "{source_dir}" "{base_dir}" /E /Y /I >nul

:: Relaunch Launcher
cd /d "{base_dir}"
if exist "launcher.py" (
    start "" python "launcher.py"
) else if exist "main.exe" (
    start "" "main.exe"
)

:: Self delete
del "%~f0" & exit
"""
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
        self.destroy()
        sys.exit(0)

    def finish(self):
        try:
            self.after(0, self.destroy)
        except Exception:
            try:
                self.destroy()
            except Exception:
                pass

def start_updater_check(on_finish=None):
    app = UpdaterUI()
    app.mainloop()
    if on_finish:
        on_finish()

if __name__ == "__main__":
    start_updater_check()
