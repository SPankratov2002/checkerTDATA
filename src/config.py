import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.txt")

DEFAULTS = {
    "TDATAS_DIR": "accounts/tdatas",
    "SESSIONS_DIR": "accounts/sessions",
    "TDATA_TO_SESSION_DIR": "accounts/tdata_to_session",
    "SESSION_TO_TDATA_DIR": "accounts/session_to_tdata",
    "FILTERED_DIR": "accounts/filtered",
    "VALID_DIR": "accounts/valid",
    "FILTERS_FILE": "filters.txt",
    "RESULTS_FILE": "results.txt",
    "API_ID": 20544336,
    "API_HASH": "ee2a26a774c35b8d72d1f94cf24c9a81",
    "CHECK_INTERVAL": 1,
    "CHECK_GIFTS": True,
    "CHECK_CRYPTOBOT": True,
    "CHECK_SPAMBOT": True,
    "CHECK_2FA": True,
    "CHECK_FULL_INFO": True,
    "CHECK_ADMIN": True,
    "COPY_FILTERED": True,
    "DELETE_FROZEN_SESSIONS": True,
    "DELETE_USED_SESSIONS": False,
    "DELETE_INVALID_SESSIONS": True,
    "MAX_CONCURRENT": 25,
    "ARCHIVE_CONCURRENT": 8,
    "NFT_SERIAL_THRESHOLD": 500000,
    "PHONE_LOCK_DURATION": 180,
}


def load_settings():
    settings = DEFAULTS.copy()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        if "#" in value:
                            value = value.split("#", 1)[0]
                        key = key.strip()
                        value = value.strip()
                        if key in DEFAULTS:
                            default_val = DEFAULTS[key]
                            if isinstance(default_val, bool):
                                settings[key] = value.lower() in ("true", "1", "yes", "on")
                            elif isinstance(default_val, int):
                                try:
                                    settings[key] = int(value)
                                except ValueError:
                                    pass
                            else:
                                settings[key] = value
        except Exception as e:
            print(f"Ошибка загрузки settings.txt: {e}")
    return settings


def save_settings(settings):
    try:
        lines = []
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        updated_lines = []
        keys_written = set()
        for line in lines:
            original_line = line
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                updated_lines.append(original_line)
                continue
            if "=" in line_stripped:
                key = line_stripped.split("=", 1)[0].strip()
                if key in settings:
                    comment = ""
                    if "#" in line:
                        comment = " #" + line.split("#", 1)[1].rstrip()
                    indent = len(original_line) - len(original_line.lstrip())
                    updated_lines.append(" " * indent + f"{key}={settings[key]}{comment}\n")
                    keys_written.add(key)
                    continue
            updated_lines.append(original_line)
        for key in DEFAULTS:
            if key not in keys_written and key in settings:
                updated_lines.append(f"{key}={settings[key]}\n")
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        return True
    except Exception as e:
        print(f"Ошибка сохранения settings.txt: {e}")
        return False


_settings = load_settings()
globals().update(_settings)

# ============================================================================
# ТЕХНИЧЕСКИЕ КОНСТАНТЫ
# ============================================================================

DC_TABLE = {
    1: ("149.154.175.53", 443),
    2: ("149.154.167.51", 443),
    4: ("149.154.167.91", 443),
    5: ("91.108.56.130", 443),
}

DEVICE_LIST = [
    "Telegram Desktop", "Telegram Android", "Telegram iOS", "Telegram Web",
    "Samsung Galaxy S21", "iPhone 13", "Google Pixel 6", "Windows PC",
    "MacBook Pro", "Ubuntu Desktop"
]
SDK_LIST = [
    "Windows 10", "Windows 11", "Android 12", "Android 13",
    "iOS 15", "iOS 16", "macOS Ventura", "macOS Monterey",
    "Ubuntu 22.04", "Linux Generic"
]
APP_VERSION_LIST = [
    "5.14.1", "5.15.0", "6.0.0", "6.1.2", "7.0.0",
    "7.1.3", "8.0.0", "8.2.1", "9.0.0", "9.1.0"
]
LANG_CODE_LIST = ["en", "ru", "es", "fr", "de", "it", "pt", "zh", "ja", "ko"]
LANG_PACK_LIST = ["tdesktop", "android", "ios", "web", "macos"]
