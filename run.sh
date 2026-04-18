#!/bin/bash
# Sommeur Checker — Linux / macOS launcher

set -e

# ── dependencies check ────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "Python3 не найден. Установите: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

# unrar — предупреждение, не блокируем запуск
if ! command -v unrar &>/dev/null && ! command -v bsdtar &>/dev/null; then
    echo "Предупреждение: unrar не найден. RAR-архивы не будут открываться."
    echo "  Установить: sudo apt install unrar"
    echo ""
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

# ── settings — копируем если нет, но не останавливаем запуск ─────────────────
if [ ! -f "settings.txt" ]; then
    cp settings.example.txt settings.txt
fi

# ── run ───────────────────────────────────────────────────────────────────────
clear
python3 starter.py
