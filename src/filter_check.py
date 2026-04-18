import asyncio
import os
import shutil
from .config import FILTERS_FILE, FILTERED_DIR, COPY_FILTERED, BASE_DIR

# Cached after first load — file doesn't change during a run
_FILTERS_CACHE: list | None = None


async def load_filters() -> list:
    global _FILTERS_CACHE
    if _FILTERS_CACHE is not None:
        return _FILTERS_CACHE
    filters = []
    filters_path = os.path.join(BASE_DIR, FILTERS_FILE)
    if not os.path.exists(filters_path):
        _FILTERS_CACHE = filters
        return filters
    try:
        with open(filters_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("@"):
                    line = "@" + line
                filters.append(line)
    except Exception as e:
        print(f"Ошибка загрузки filters.txt: {e}")
    _FILTERS_CACHE = filters
    return filters


def invalidate_filters_cache():
    """Call after editing filters.txt so next run reloads from disk."""
    global _FILTERS_CACHE
    _FILTERS_CACHE = None


async def check_all_filters(client, phone_number) -> list:
    """Returns list of filter tags that match this account.
    Loads all dialogs once, then checks every filter against that set."""
    filters = await load_filters()
    if not filters:
        return []

    # Collect dialog usernames in a single pass
    dialog_usernames: set[str] = set()
    try:
        async with asyncio.timeout(20):
            async for dialog in client.iter_dialogs(limit=500):
                username = getattr(dialog.entity, 'username', None)
                if username:
                    dialog_usernames.add(username.lower())
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print(f"[{phone_number}] Ошибка загрузки диалогов для фильтров: {e}")

    matched = []
    for target in filters:
        target_clean = target.lstrip('@').lower()
        if target_clean in dialog_usernames:
            matched.append(target)
            print(f"[{phone_number}] Фильтр совпал: {target}")
    return matched


def _safe_name(filter_name: str) -> str:
    return filter_name.lstrip('@').replace('/', '_').replace('\\', '_')


def sort_session_to_filter(session_path, json_path, filter_name: str):
    """Copy or move session + json files to accounts/filtered/<filter_name>/."""
    target_dir = os.path.join(BASE_DIR, FILTERED_DIR, _safe_name(filter_name))
    os.makedirs(target_dir, exist_ok=True)
    for src in [session_path, json_path]:
        if src and os.path.exists(src):
            dst = os.path.join(target_dir, os.path.basename(src))
            try:
                if COPY_FILTERED:
                    shutil.copy2(src, dst)
                else:
                    shutil.move(src, dst)
            except Exception as e:
                print(f"Ошибка сортировки {os.path.basename(src)}: {e}")


def sort_tdata_to_filter(tdata_path: str, filter_name: str):
    """Copy or move tdata folder to accounts/filtered/<filter_name>/."""
    target_dir = os.path.join(BASE_DIR, FILTERED_DIR, _safe_name(filter_name))
    os.makedirs(target_dir, exist_ok=True)
    dst = os.path.join(target_dir, os.path.basename(tdata_path))
    try:
        if COPY_FILTERED:
            shutil.copytree(tdata_path, dst, dirs_exist_ok=True)
        else:
            shutil.move(tdata_path, dst)
    except Exception as e:
        print(f"Ошибка сортировки tdata {os.path.basename(tdata_path)}: {e}")
