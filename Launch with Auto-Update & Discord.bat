@echo off
title Goated Macro Launcher ^& Auto-Updater
cd /d "%~dp0"
python launcher.py
if errorlevel 1 pause
