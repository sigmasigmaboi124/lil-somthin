import os
import sys
import time
import subprocess
import threading
from updater_ui import start_updater_check

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def start_macro_and_bot():
    print("[*] Launching TDS Macro executable...")
    # Look for main.exe
    possible_paths = [
        os.path.join(BASE_DIR, "Goated-Macro", "Goated Macro", "main.exe"),
        os.path.join(BASE_DIR, "main.exe"),
    ]
    
    macro_exe = next((p for p in possible_paths if os.path.exists(p)), None)
    if macro_exe:
        print(f"[*] Found macro at: {macro_exe}")
        subprocess.Popen([macro_exe], cwd=os.path.dirname(macro_exe))
    else:
        print("[!] Warning: main.exe not found in standard paths.")

    print("[*] Starting Discord Remote Control Bot...")
    try:
        from discord_remote import run_bot
        run_bot()
    except Exception as e:
        print(f"[!] Error running discord bot: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("      TDS Macro Launcher & Discord Remote Control")
    print("=" * 60)
    
    # 1. Shows modern dark UI checking GitHub releases and auto-updating
    # 2. Once verified/updated, calls start_macro_and_bot()
    start_updater_check(on_finish=start_macro_and_bot)
