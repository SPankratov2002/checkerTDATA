import os
import shutil
import asyncio
from .config import BASE_DIR, VALID_DIR

_counter_lock = asyncio.Lock()

# Phone prefix → country code lookup
_PHONE_PREFIXES = {
    "7": "RU/KZ", "380": "UA", "375": "BY", "374": "AM",
    "995": "GE", "994": "AZ", "998": "UZ", "996": "KG",
    "992": "TJ", "993": "TM", "371": "LV", "372": "EE",
    "370": "LT", "48": "PL", "49": "DE", "44": "GB",
    "33": "FR", "39": "IT", "34": "ES", "31": "NL",
    "46": "SE", "47": "NO", "358": "FI", "45": "DK",
    "1": "US/CA", "55": "BR", "52": "MX", "54": "AR",
    "86": "CN", "81": "JP", "82": "KR", "91": "IN",
    "62": "ID", "66": "TH", "84": "VN", "63": "PH",
    "60": "MY", "65": "SG", "20": "EG", "234": "NG",
    "27": "ZA", "212": "MA", "90": "TR", "972": "IL",
    "966": "SA", "971": "AE", "98": "IR",
}


def _get_country(phone: str) -> str:
    phone = phone.lstrip('+')
    for prefix_len in (3, 2, 1):
        prefix = phone[:prefix_len]
        if prefix in _PHONE_PREFIXES:
            return f"+{prefix} {_PHONE_PREFIXES[prefix]}"
    return f"+{phone[:2]}"


def _get_next_number_sync() -> int:
    counter_file = os.path.join(BASE_DIR, VALID_DIR, ".counter")
    os.makedirs(os.path.join(BASE_DIR, VALID_DIR), exist_ok=True)
    n = 1
    if os.path.exists(counter_file):
        try:
            with open(counter_file) as f:
                n = int(f.read().strip()) + 1
        except Exception:
            pass
    with open(counter_file, 'w') as f:
        f.write(str(n))
    return n


async def _get_next_number() -> int:
    async with _counter_lock:
        return await asyncio.get_running_loop().run_in_executor(None, _get_next_number_sync)


def _determine_categories(info: dict) -> list:
    cats = []
    if info.get('is_premium'):
        cats.append('premium_yes')
    else:
        cats.append('premium_no')
    if info.get('has_2fa'):
        cats.append('twofa_on')
    else:
        cats.append('twofa_off')
    if info.get('nft_count', 0) > 0:
        cats.append('with_nft')
    if info.get('gift_count', 0) > 0 or info.get('gifts_stars_value', 0) > 0:
        cats.append('with_gift')
    if info.get('stars_balance', 0) > 0:
        cats.append('with_stars')
    uid_len = len(str(info.get('id', '') or ''))
    if uid_len >= 10:
        cats.append('id_long')
    else:
        cats.append('id_short')
    if info.get('ch_admin'):
        cats.append('admin_channels')
    if info.get('gr_admin'):
        cats.append('admin_groups')
    if info.get('usdt_balance', 0) > 0 or info.get('ton_balance', 0) > 0:
        cats.append('with_crypto')
    return cats


def _write_info_txt(dest_tdata: str, info: dict, archive_path: str, number: int):
    username = info.get('username', '')
    profile_link = f"https://t.me/{username}" if username else "N/A"
    phone = str(info.get('phone', ''))
    country = _get_country(phone) if phone else "N/A"

    lines = [
        f"truncated_folder: {archive_path}",
        f"status: Valid",
        f"profile_link: {profile_link}",
        f"user_number: {phone}",
        f"premium: {info.get('is_premium', False)}",
        f"stars_count: {info.get('stars_balance', 0)}",
        f"gifts_count: {info.get('gift_count', 0)}",
        f"nft: {info.get('nft_count', 0)}",
        f"usdt: {info.get('usdt_balance', 0.0):.6f}",
        f"ton: {info.get('ton_balance', 0.0):.6f}",
        f"count_dialogs: {info.get('dialogs_count', 0)}",
        f"contacts_count: {info.get('contacts_count', 0)}",
        f"sessions_count: {info.get('sessions_count', 0)}",
        f"spam_status: {info.get('spam_status', 'unknown')}",
        f"two_fa_enabled: {info.get('has_2fa', False)}",
        f"user_id: {info.get('id', '')}",
        f"user_id_length: {len(str(info.get('id', '') or ''))}",
        f"country: {country}",
        f"bio: {info.get('bio', '')}",
        f"ch_admin: {info.get('ch_admin', {})}",
        f"gr_admin: {info.get('gr_admin', {})}",
    ]
    with open(os.path.join(dest_tdata, "INFO.txt"), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _update_results_txt(category: str, info: dict, tdata_name: str):
    results_dir = os.path.join(BASE_DIR, VALID_DIR, "sorted", "results")
    os.makedirs(results_dir, exist_ok=True)

    username = info.get('username', '')
    ident = f"@{username}" if username else f"+{info.get('phone', '')}"

    extras = {
        'admin_channels': f"{len(info.get('ch_admin', {}))} ch",
        'admin_groups':   f"{len(info.get('gr_admin', {}))} gr",
        'with_gift':      f"{info.get('gift_count', 0)} gifts ({info.get('gifts_stars_value', 0)}⭐)",
        'with_stars':     f"{info.get('stars_balance', 0)} stars",
        'with_nft':       f"{info.get('nft_count', 0)} NFT",
        'with_crypto':    f"{info.get('usdt_balance', 0):.4f} USDT  {info.get('ton_balance', 0):.4f} TON",
        'premium_yes':    "PREMIUM",
        'twofa_on':       "2FA",
    }
    extra = extras.get(category, "")
    line = f"{ident}  |  {extra}  |  {tdata_name}".strip(" |")

    with open(os.path.join(results_dir, f"{category}.txt"), 'a', encoding='utf-8') as f:
        f.write(line + '\n')


async def save_and_sort(tdata_path: str, info: dict, archive_path: str = "") -> str:
    """Copy tdata to accounts/valid/tdata_N/, write INFO.txt, sort into categories."""
    if not tdata_path or not os.path.exists(tdata_path):
        return ""

    number = await _get_next_number()
    tdata_name = f"tdata_{number}"
    dest = os.path.join(BASE_DIR, VALID_DIR, tdata_name)

    try:
        shutil.copytree(tdata_path, dest)
    except Exception as e:
        print(f"\nОшибка сохранения tdata: {e}")
        return ""

    try:
        _write_info_txt(dest, info, archive_path, number)
    except Exception as e:
        print(f"\nОшибка INFO.txt: {e}")

    categories = _determine_categories(info)
    for cat in categories:
        cat_dest = os.path.join(BASE_DIR, VALID_DIR, "sorted", cat, tdata_name)
        try:
            os.makedirs(os.path.dirname(cat_dest), exist_ok=True)
            # Copy FROM already-saved valid/tdata_N/, not from original temp path
            shutil.copytree(dest, cat_dest)
            _write_info_txt(cat_dest, info, archive_path, number)
        except Exception:
            pass
        try:
            _update_results_txt(cat, info, tdata_name)
        except Exception:
            pass

    return dest
