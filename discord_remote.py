import os
import sys
import io
import time
import json
import psutil
import datetime
import asyncio
import subprocess
import requests
from PIL import Image, ImageGrab
import discord
from discord import app_commands
from discord.ext import commands, tasks

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config.json: {e}")
    return {}

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving config.json: {e}")

# In-Memory State & Session Telemetry
session_state = {
    "is_running": False,
    "is_paused": False,
    "start_time": time.time(),
    "macro_process": None,
    "active_config": "Default",
    "speed": 1.0,
    "timescale_tickets": 0,
    "stop_after_run": 0,
    "restart_interval_minutes": 60,
    "private_server": "",
    "total_runs": 0,
    "wins": 0,
    "losses": 0,
    "coins_earned": 0,
    "gems_earned": 0,
    "xp_earned": 0,
    "logs": []
}

def log_event(message: str):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    session_state["logs"].append(entry)
    if len(session_state["logs"]) > 100:
        session_state["logs"].pop(0)
    print(entry)

def is_roblox_running():
    for p in psutil.process_iter(['name']):
        if p.info['name'] and 'RobloxPlayerBeta' in p.info['name']:
            return True
    return False

def get_available_strategies():
    cfg = load_config()
    strategies_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), cfg.get("strategies_path", "Goated-Macro/Goated Macro/strategies"))
    if not os.path.exists(strategies_dir):
        # Fallback search
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies")
        if os.path.exists(alt):
            strategies_dir = alt
        else:
            return ["Beginner Coin Farm V2", "Gems Grind V2", "Simplicity Coins Strat", "Frost Simplicity", "U-Turn XP Farm"]
    
    dirs = [d for d in os.listdir(strategies_dir) if os.path.isdir(os.path.join(strategies_dir, d))]
    return dirs if dirs else ["Default"]

# Discord Bot Setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------- Interactive UI Components -----------------

class ConfigDropdown(discord.ui.Select):
    def __init__(self, strategies):
        options = [
            discord.SelectOption(label=strat[:100], description=f"Load {strat[:50]}", emoji="📁")
            for strat in strategies[:25] # Discord limit 25 options
        ]
        super().__init__(placeholder="Select a Strategy / Config...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        session_state["active_config"] = selected
        log_event(f"Strategy changed to: {selected}")
        await interaction.response.send_message(f"✅ Strategy successfully changed to **{selected}**!", ephemeral=True)

class ConfigSelectView(discord.ui.View):
    def __init__(self, strategies):
        super().__init__(timeout=120)
        self.add_item(ConfigDropdown(strategies))

class DashboardButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="▶️", custom_id="btn_start")
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        session_state["is_running"] = True
        session_state["is_paused"] = False
        log_event("Macro started via Discord button")
        await interaction.response.send_message("▶️ **Macro Started!**", ephemeral=True)

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.secondary, emoji="⏸️", custom_id="btn_pause")
    async def btn_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        session_state["is_paused"] = not session_state["is_paused"]
        state_txt = "Paused" if session_state["is_paused"] else "Resumed"
        log_event(f"Macro {state_txt} via Discord button")
        await interaction.response.send_message(f"⏸️ **Macro {state_txt}!**", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="btn_stop")
    async def btn_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        session_state["is_running"] = False
        log_event("Macro stopped via Discord button")
        await interaction.response.send_message("⏹️ **Macro Stopped!**", ephemeral=True)

    @discord.ui.button(label="Screenshot", style=discord.ButtonStyle.primary, emoji="📸", custom_id="btn_screenshot")
    async def btn_screenshot(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        try:
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            file = discord.File(buf, filename="screen.png")
            await interaction.followup.send("📸 **Current Screen Preview:**", file=file)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to take screenshot: {e}")

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="btn_stats")
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_stats_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Rejoin", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="btn_rejoin")
    async def btn_rejoin(self, interaction: discord.Interaction, button: discord.ui.Button):
        log_event("Rejoining Roblox session...")
        cfg = load_config()
        ps_link = cfg.get("private_server_link", "")
        if ps_link:
            os.system(f'start "" "{ps_link}"')
            await interaction.response.send_message("🔄 Rejoining via Private Server link!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ No private server link configured in `/privateserver`.", ephemeral=True)

# ----------------- Helper Functions -----------------

def build_status_embed():
    uptime_sec = int(time.time() - session_state["start_time"])
    uptime_str = str(datetime.timedelta(seconds=uptime_sec))
    roblox_active = "🟢 Active" if is_roblox_running() else "🔴 Closed"
    macro_status = "⏸️ Paused" if session_state["is_paused"] else ("🟢 Running" if session_state["is_running"] else "⏹️ Stopped")

    embed = discord.Embed(
        title="🎮 Roblox TDS Macro Control Panel",
        description=f"Current Status: **{macro_status}**\nRoblox Client: **{roblox_active}**",
        color=0x5865F2 if session_state["is_running"] else 0xED4245,
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="📁 Strategy", value=f"`{session_state['active_config']}`", inline=True)
    embed.add_field(name="⚡ Speed", value=f"`{session_state['speed']}x`", inline=True)
    embed.add_field(name="🎫 Tickets", value=f"`{session_state['timescale_tickets']}`", inline=True)
    embed.add_field(name="⏱️ Uptime", value=f"`{uptime_str}`", inline=True)
    embed.add_field(name="🏆 Total Runs", value=f"`{session_state['total_runs']}`", inline=True)
    embed.add_field(name="🛑 Stop After", value=f"`{session_state['stop_after_run'] or 'Off'}`", inline=True)
    embed.set_footer(text="Use buttons below for quick actions")
    return embed

def build_stats_embed():
    uptime_hours = max((time.time() - session_state["start_time"]) / 3600.0, 0.001)
    runs = session_state["total_runs"]
    wins = session_state["wins"]
    losses = session_state["losses"]
    winrate = f"{(wins / runs * 100):.1f}%" if runs > 0 else "N/A"
    coins_hr = int(session_state["coins_earned"] / uptime_hours)
    gems_hr = int(session_state["gems_earned"] / uptime_hours)

    embed = discord.Embed(
        title="📊 Macro Farming Telemetry & Stats",
        color=0xFEE75C,
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="📈 Matches", value=f"**Wins:** {wins} | **Losses:** {losses}\n**Winrate:** {winrate}", inline=False)
    embed.add_field(name="🪙 Coins", value=f"Total: **{session_state['coins_earned']:,}**\nRate: **{coins_hr:,} / hr**", inline=True)
    embed.add_field(name="💎 Gems", value=f"Total: **{session_state['gems_earned']:,}**\nRate: **{gems_hr:,} / hr**", inline=True)
    embed.add_field(name="⭐ XP", value=f"Total: **{session_state['xp_earned']:,}**", inline=True)
    return embed

# ----------------- Background Watchdog -----------------

@tasks.loop(seconds=30)
async def watchdog_task():
    cfg = load_config()
    channel_id = cfg.get("status_channel_id", 0)
    owner_id = cfg.get("owner_id", 0)
    
    if channel_id and session_state["is_running"]:
        channel = bot.get_channel(channel_id)
        if channel:
            # Check if Roblox disconnected/closed unexpectedly
            if not is_roblox_running():
                log_event("Watchdog: Roblox process not found while macro was running!")
                mention = f"<@{owner_id}> " if owner_id else ""
                await channel.send(f"⚠️ {mention}**Roblox Disconnect / Crash Detected!** Macro is currently waiting to rejoin.")

# ----------------- Slash Commands -----------------

@bot.tree.command(name="status", description="Show live macro status dashboard with interactive buttons")
async def cmd_status(interaction: discord.Interaction):
    embed = build_status_embed()
    view = DashboardButtons()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="screenshot", description="Capture the current screen of the macro / Roblox window")
async def cmd_screenshot(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        file = discord.File(buf, filename="screenshot.png")
        await interaction.followup.send(file=file)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to take screenshot: {e}")

@bot.tree.command(name="clip", description="Record a 3-second animated GIF preview to verify macro movement")
async def cmd_clip(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        frames = []
        for _ in range(8):
            img = ImageGrab.grab()
            img.thumbnail((720, 480))
            frames.append(img)
            time.sleep(0.35)
        
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=350, loop=0)
        buf.seek(0)
        file = discord.File(buf, filename="preview.gif")
        await interaction.followup.send("🎬 **3-Second Screen Clip:**", file=file)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to generate clip: {e}")

@bot.tree.command(name="start", description="Start or resume the TDS macro")
async def cmd_start(interaction: discord.Interaction):
    session_state["is_running"] = True
    session_state["is_paused"] = False
    log_event("Started via /start")
    await interaction.response.send_message("▶️ Macro started!")

@bot.tree.command(name="stop", description="Stop the TDS macro")
async def cmd_stop(interaction: discord.Interaction):
    session_state["is_running"] = False
    log_event("Stopped via /stop")
    await interaction.response.send_message("⏹️ Macro stopped!")

@bot.tree.command(name="pause", description="Pause the TDS macro")
async def cmd_pause(interaction: discord.Interaction):
    session_state["is_paused"] = True
    log_event("Paused via /pause")
    await interaction.response.send_message("⏸️ Macro paused!")

@bot.tree.command(name="resume", description="Resume the TDS macro")
async def cmd_resume(interaction: discord.Interaction):
    session_state["is_paused"] = False
    log_event("Resumed via /resume")
    await interaction.response.send_message("▶️ Macro resumed!")

@bot.tree.command(name="rejoin", description="Force rejoin Roblox or Private Server")
async def cmd_rejoin(interaction: discord.Interaction):
    cfg = load_config()
    ps_link = cfg.get("private_server_link", "")
    if ps_link:
        os.system(f'start "" "{ps_link}"')
        await interaction.response.send_message("🔄 Launching private server link!")
    else:
        await interaction.response.send_message("⚠️ Set private server link first via `/privateserver`.")

@bot.tree.command(name="configs", description="List available strategies and open dropdown selector")
async def cmd_configs(interaction: discord.Interaction):
    strategies = get_available_strategies()
    view = ConfigSelectView(strategies)
    await interaction.response.send_message("Select a strategy from the dropdown below:", view=view)

@bot.tree.command(name="config", description="Set active strategy by name")
@app_commands.describe(strategy_name="Name of strategy folder")
async def cmd_config(interaction: discord.Interaction, strategy_name: str):
    session_state["active_config"] = strategy_name
    log_event(f"Strategy set to: {strategy_name}")
    await interaction.response.send_message(f"📁 Active strategy set to: **{strategy_name}**")

@bot.tree.command(name="stats", description="Display full session stats (Wins, Losses, Coins/hr, Gems/hr)")
async def cmd_stats(interaction: discord.Interaction):
    embed = build_stats_embed()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="speed", description="Set macro replay speed multiplier")
@app_commands.describe(multiplier="Speed multiplier, e.g. 1.0 or 1.5")
async def cmd_speed(interaction: discord.Interaction, multiplier: float):
    session_state["speed"] = multiplier
    cfg = load_config()
    cfg["macro_speed"] = multiplier
    save_config(cfg)
    await interaction.response.send_message(f"⚡ Macro speed set to **{multiplier}x**")

@bot.tree.command(name="timescaletickets", description="Set timescale tickets to use")
@app_commands.describe(count="Number of tickets")
async def cmd_timescale(interaction: discord.Interaction, count: int):
    session_state["timescale_tickets"] = count
    cfg = load_config()
    cfg["timescale_tickets"] = count
    save_config(cfg)
    await interaction.response.send_message(f"🎫 Timescale tickets set to **{count}**")

@bot.tree.command(name="stopafterrun", description="Stop macro automatically after N matches")
@app_commands.describe(runs="Number of runs (0 to disable)")
async def cmd_stopafterrun(interaction: discord.Interaction, runs: int):
    session_state["stop_after_run"] = runs
    await interaction.response.send_message(f"🛑 Macro will stop after **{runs if runs > 0 else 'Disabled'}** runs.")

@bot.tree.command(name="restartinterval", description="Set minutes before restarting client")
@app_commands.describe(minutes="Interval in minutes")
async def cmd_restartinterval(interaction: discord.Interaction, minutes: int):
    session_state["restart_interval_minutes"] = minutes
    cfg = load_config()
    cfg["restart_interval_minutes"] = minutes
    save_config(cfg)
    await interaction.response.send_message(f"⏱️ Client restart interval set to **{minutes}m**")

@bot.tree.command(name="privateserver", description="Configure Roblox VIP Server link")
@app_commands.describe(link="Full Roblox VIP private server URL")
async def cmd_privateserver(interaction: discord.Interaction, link: str):
    cfg = load_config()
    cfg["private_server_link"] = link
    save_config(cfg)
    await interaction.response.send_message("🔒 Private server link saved successfully!")

@bot.tree.command(name="showlogs", description="Show last 15 macro log events")
async def cmd_showlogs(interaction: discord.Interaction):
    recent = session_state["logs"][-15:]
    txt = "\n".join(recent) if recent else "No log events recorded yet."
    await interaction.response.send_message(f"```txt\n{txt}\n```")

@bot.tree.command(name="pcstatus", description="Monitor host PC hardware and resource usage")
async def cmd_pcstatus(interaction: discord.Interaction):
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    embed = discord.Embed(title="🖥️ Host PC Health & Resources", color=0x3ba55d)
    embed.add_field(name="CPU Usage", value=f"`{cpu}%`", inline=True)
    embed.add_field(name="RAM Usage", value=f"`{ram.percent}%` ({ram.used // (1024**2)}MB / {ram.total // (1024**2)}MB)", inline=True)
    embed.add_field(name="Disk Free", value=f"`{disk.free // (1024**3)} GB`", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="killroblox", description="Force terminate hanging RobloxPlayerBeta.exe processes")
async def cmd_killroblox(interaction: discord.Interaction):
    count = 0
    for p in psutil.process_iter(['name']):
        if p.info['name'] and 'RobloxPlayerBeta' in p.info['name']:
            try:
                p.kill()
                count += 1
            except Exception:
                pass
    await interaction.response.send_message(f"💀 Terminated {count} Roblox process(es).")

@bot.tree.command(name="update", description="Check for new releases and update the macro app remotely")
async def cmd_update(interaction: discord.Interaction):
    await interaction.response.defer()
    cfg = load_config()
    repo_owner = cfg.get("repo_owner", "sigmasigmaboi124")
    repo_name = cfg.get("repo_name", "lil-somthin")
    cur_ver = cfg.get("current_version", "2.6.2")

    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    try:
        res = requests.get(api_url, timeout=6)
        if res.status_code == 200:
            data = res.json()
            latest = data.get("tag_name", "").lstrip("v")
            if latest and latest > cur_ver:
                await interaction.followup.send(f"🚀 **New Release Found: v{latest}!** Launching updater and restarting application...")
                # Launch updater UI to apply update
                from updater_ui import start_updater_check
                start_updater_check()
                return
        await interaction.followup.send(f"✅ App is already up to date! (v{cur_ver})")
    except Exception as e:
        await interaction.followup.send(f"❌ Error checking updates: {e}")

@bot.tree.command(name="help", description="List all available commands and explanations")
async def cmd_help(interaction: discord.Interaction):
    commands_list = """
**🎮 Macro Controls:**
`/status` - Interactive live dashboard with control buttons
`/screenshot` - Grab high-res screen preview
`/clip` - Record 3-second animated GIF preview
`/start` / `/stop` - Start or stop macro execution
`/pause` / `/resume` - Pause or resume macro
`/rejoin` - Rejoin match or VIP server

**📁 Strategy & Config:**
`/configs` - Interactive dropdown to pick a strategy
`/config <name>` - Set active strategy
`/speed <x>` - Adjust macro replay speed
`/timescaletickets <n>` - Set timescale ticket usage
`/stopafterrun <n>` - Stop after completing N games
`/privateserver <url>` - Set Roblox private server link

**📊 Stats & System:**
`/stats` - Session wins, losses, winrate, coins/hr & gems/hr
`/showlogs` - View recent activity logs
`/pcstatus` - Host CPU, RAM, and Disk metrics
`/killroblox` - Force close stuck Roblox client
`/update` - Check for new releases and auto-update
    """
    embed = discord.Embed(title="📖 TDS Remote Control Help", description=commands_list, color=0x5865F2)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} application slash commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    
    if not watchdog_task.is_running():
        watchdog_task.start()

def run_bot():
    cfg = load_config()
    token = cfg.get("bot_token", "")
    if not token or token == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("="*60)
        print("⚠️ NOTICE: 'bot_token' is not set in config.json!")
        print("Please edit config.json and enter your Discord bot token.")
        print("="*60)
        return
    bot.run(token)

if __name__ == "__main__":
    run_bot()
