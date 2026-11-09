import os
import sys
import time
import subprocess

# Prevent Windows cmd code-page crash (cp1252 UnicodeEncodeError)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from updater_ui import start_updater_check

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def start_macro():
    print("[*] Launching Goated Macro executable...")
    possible_paths = [
        os.path.join(BASE_DIR, "Goated-Macro", "Goated Macro", "main.exe"),
        os.path.join(BASE_DIR, "Goated-Macro", "main.exe"),
        os.path.join(BASE_DIR, "main.exe"),
    ]
    
    macro_exe = next((p for p in possible_paths if os.path.exists(p)), None)
    if macro_exe:
        print(f"[+] Found Goated Macro at: {macro_exe}")
        proc = subprocess.Popen([macro_exe], cwd=os.path.dirname(macro_exe))
        print(f"[+] Goated Macro started successfully (PID {proc.pid})!")
        print("[+] Remote Discord Control & Auto-Equip are active inside the macro.")
        print("[*] You can keep this window open or minimize it.")
    else:
        print("[!] Error: main.exe not found in standard paths.")
        print("    Make sure Goated-Macro folder exists alongside this launcher.")

if __name__ == "__main__":
    print("=" * 60)
    print("      Goated Macro Launcher & Auto-Updater")
    print("=" * 60)
    
    # 1. Shows modern dark UI checking GitHub releases and auto-updating
    # 2. Once verified/updated, launches Goated Macro
    start_updater_check(on_finish=start_macro)
