@echo off
chcp 65001 >nul
title Sommeur Checker

if not exist venv (
    python -m venv venv
)

call venv\Scripts\activate

pip install -q -r requirements.txt 2>nul

cls
python -m src.main
