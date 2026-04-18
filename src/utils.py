import random
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from asyncio import Semaphore
from .config import MAX_CONCURRENT, ARCHIVE_CONCURRENT, PHONE_LOCK_DURATION
from .config import DEVICE_LIST, SDK_LIST, APP_VERSION_LIST, LANG_CODE_LIST, LANG_PACK_LIST
from .config import API_ID, API_HASH

PHONE_LOCKS: dict[str, asyncio.Lock] = {}
LAST_USED_PHONE_TIMES: dict[str, float] = {}

ARCHIVE_SEMAPHORE  = Semaphore(ARCHIVE_CONCURRENT)
SESSION_SEMAPHORE  = Semaphore(MAX_CONCURRENT)
GLOBAL_SEMAPHORE   = Semaphore(500)
# Use ARCHIVE_CONCURRENT threads — no point creating MAX_CONCURRENT threads
# when the semaphore only allows ARCHIVE_CONCURRENT concurrent extractions
ARCHIVE_EXECUTOR   = ThreadPoolExecutor(max_workers=ARCHIVE_CONCURRENT)


class ProgressTracker:
    def __init__(self, total: int, label: str = "Прогресс"):
        self.total      = total
        self.done       = 0
        self.failed     = 0
        self.skipped    = 0
        self.started_at = time.time()
        self.label      = label
        self._lock      = asyncio.Lock()

    async def increment(self, failed: bool = False, skipped: bool = False):
        async with self._lock:
            self.done += 1
            if failed:
                self.failed += 1
            elif skipped:
                self.skipped += 1
            self._print()

    def _eta_str(self) -> str:
        elapsed = time.time() - self.started_at
        if self.done == 0:
            return "ETA: ?"
        remaining = (elapsed / self.done) * (self.total - self.done)
        if remaining < 60:
            return f"ETA: {int(remaining)}с"
        return f"ETA: {int(remaining // 60)}м {int(remaining % 60)}с"

    def _print(self):
        pct         = int(self.done / self.total * 100) if self.total else 0
        elapsed     = int(time.time() - self.started_at)
        elapsed_str = f"{elapsed // 60}м {elapsed % 60}с"
        ok          = self.done - self.failed - self.skipped
        line = (
            f"\r[{self.label}] {self.done}/{self.total} ({pct}%)"
            f" | ok:{ok} skip:{self.skipped} err:{self.failed}"
            f" | {elapsed_str} | {self._eta_str()}   "
        )
        print(line, end="", flush=True)

    def finish(self):
        elapsed = int(time.time() - self.started_at)
        ok      = self.done - self.failed - self.skipped
        print(
            f"\r[{self.label}] Готово: {self.total} | "
            f"ok:{ok} skip:{self.skipped} err:{self.failed} | "
            f"Время: {elapsed // 60}м {elapsed % 60}с              "
        )


def generate_random_template_data():
    return {
        "app_id":            2040,
        "app_hash":          "b18441a1ff607e10a989891a5462e627",
        "device":            random.choice(DEVICE_LIST),
        "sdk":               random.choice(SDK_LIST),
        "app_version":       random.choice(APP_VERSION_LIST),
        "system_lang_pack":  random.choice(LANG_CODE_LIST),
        "system_lang_code":  random.choice(LANG_CODE_LIST),
        "lang_pack":         random.choice(LANG_PACK_LIST),
        "lang_code":         random.choice(LANG_CODE_LIST),
        "twoFA":             None,
        "role":              "",
        "id":                None,
        "phone":             None,
        "username":          None,
        "is_premium":        False,
        "has_profile_pic":   False,
        "register_time":     int(time.time()),
        "last_check_time":   int(time.time()),
        "avatar":            None,
        "first_name":        "",
        "last_name":         "",
        "sex":               None,
        "proxy":             None,
        "ipv6":              False,
        "session_file":      "",
    }


def get_random_telethon_proxy():
    try:
        with open('working_proxies.txt', 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
        if not proxies:
            return None
        proxy = random.choice(proxies)
        parts = proxy.split(':')
        if len(parts) != 4:
            return None
        ip, port, user, pwd = parts
        return ('http', ip, int(port), user, pwd)
    except Exception:
        return None


def get_phone_lock(phone_number: str) -> asyncio.Lock:
    if phone_number not in PHONE_LOCKS:
        PHONE_LOCKS[phone_number] = asyncio.Lock()
    return PHONE_LOCKS[phone_number]


def cleanup_phone_locks():
    """Release memory after a scan completes."""
    PHONE_LOCKS.clear()
    LAST_USED_PHONE_TIMES.clear()


async def delete_session_files(session_file, json_file=None):
    try:
        import os
        files_to_delete = []
        if session_file:
            files_to_delete.append(session_file)
            if not json_file:
                if session_file.endswith('.session'):
                    files_to_delete.append(session_file[:-8] + '.json')
                else:
                    files_to_delete.append(session_file.rsplit('.', 1)[0] + '.json')
        if json_file:
            files_to_delete.append(json_file)
        for file_path in set(files_to_delete):
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
    except Exception:
        pass


def is_phone_rate_limited(phone_number: str) -> bool:
    current_time = time.time()
    last_used    = LAST_USED_PHONE_TIMES.get(phone_number, 0)
    return current_time - last_used < PHONE_LOCK_DURATION


def mark_phone_as_used(phone_number: str):
    LAST_USED_PHONE_TIMES[phone_number] = time.time()
