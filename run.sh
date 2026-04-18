#!/bin/bash
# Sommeur Checker — Linux / macOS launcher

set -e

# ── dependencies check ────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "Python3 не найден. Установите: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

# unrar required for .rar archives
if ! command -v unrar &>/dev/null && ! command -v bsdtar &>/dev/null; then
    echo "Предупреждение: unrar не найден. RAR-архивы не будут открываться."
    echo "  Установить: sudo apt install unrar"
fi

# ── venv ──────────────────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv venv
fi

source venv/bin/activate

# ── install deps ──────────────────────────────────────────────────────────────
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ── settings ──────────────────────────────────────────────────────────────────
if [ ! -f "settings.txt" ]; then
    cp settings.example.txt settings.txt
    echo ""
    echo "  ┌─────────────────────────────────────────────────────┐"
    echo "  │  Создан settings.txt из примера.                    │"
    echo "  │  Укажите API_ID и API_HASH в файле settings.txt     │"
    echo "  │  Получить можно на: https://my.telegram.org         │"
    echo "  └─────────────────────────────────────────────────────┘"
    echo ""
    exit 1
fi

# ── run ───────────────────────────────────────────────────────────────────────
clear
python3 starter.py
