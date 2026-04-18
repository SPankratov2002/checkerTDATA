import os
import asyncio
import json
import shutil
import time
import binascii
import sqlite3
import random
from typing import Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network import ConnectionTcpFull

from .config import *
from .utils import (
    SESSION_SEMAPHORE, GLOBAL_SEMAPHORE, ARCHIVE_EXECUTOR, ARCHIVE_SEMAPHORE,
    get_random_telethon_proxy, generate_random_template_data,
    is_phone_rate_limited, mark_phone_as_used, get_phone_lock, delete_session_files,
    cleanup_phone_locks, ProgressTracker, async_timeout,
)
from .tdata_parsing import (
    read_file, create_local_key, decrypt_local, read_user_auth, build_session,
    extract_archive, find_all_key_datas_and_tdata
)
from .convert_utils import convert_tdata_to_authkey, convert_session_to_tdata
from .checker import check_account, format_account_info, save_to_results, load_checked_phones
from .filter_check import check_all_filters, sort_session_to_filter, sort_tdata_to_filter
from .sorter import save_and_sort

# Phones already present in results.txt — populated at scan start for resume
_CHECKED_PHONES: set = set()

# Shared progress tracker — set by scan_tdatas / scan_sessions
_PROGRESS: Optional[ProgressTracker] = None


async def create_sqlite_session_file(session_path, dc_id, server_address, port, auth_key):
    try:
        os.makedirs(os.path.dirname(session_path), exist_ok=True)
        if os.path.exists(session_path):
            os.remove(session_path)
        conn = sqlite3.connect(session_path)
        cursor = conn.cursor()
        cursor.executescript("""
            PRAGMA foreign_keys=OFF;
            BEGIN TRANSACTION;
            CREATE TABLE version (version INTEGER PRIMARY KEY);
            INSERT INTO version VALUES(7);
            CREATE TABLE sessions (
                dc_id INTEGER PRIMARY KEY,
                server_address TEXT,
                port INTEGER,
                auth_key BLOB,
                takeout_id INTEGER
            );
            CREATE TABLE entities (
                id INTEGER PRIMARY KEY,
                hash INTEGER NOT NULL,
                username TEXT,
                phone INTEGER,
                name TEXT,
                date INTEGER
            );
            CREATE TABLE sent_files (
                md5_digest BLOB,
                file_size INTEGER,
                type INTEGER,
                id INTEGER,
                hash INTEGER,
                PRIMARY KEY(md5_digest, file_size, type)
            );
            CREATE TABLE update_state (
                id INTEGER PRIMARY KEY,
                pts INTEGER,
                qts INTEGER,
                date INTEGER,
                seq INTEGER
            );
            COMMIT;
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO sessions (dc_id, server_address, port, auth_key, takeout_id)
            VALUES (?, ?, ?, ?, NULL)
        """, (dc_id, server_address, port, auth_key))
        conn.commit()
        conn.close()
    except Exception:
        raise


async def convert_tdata_to_session(tdata_path, passcode=None, archive_path=None, output_dir=None):
    async with SESSION_SEMAPHORE, GLOBAL_SEMAPHORE:
        sessions = await asyncio.get_running_loop().run_in_executor(
            ARCHIVE_EXECUTOR, convert_tdata_to_authkey, tdata_path, passcode
        )
        if not sessions:
            print(f"[{tdata_path}] Нет сессий после конвертации tdata")
            return []

        async def process_session(index, authkey_maindcid, session_string):
            async with GLOBAL_SEMAPHORE:
                auth_key_hex, dc_id = authkey_maindcid.split(":")
                dc_id = int(dc_id)
                if dc_id not in DC_TABLE:
                    print(f"[{tdata_path}] Некорректный DC: {dc_id}")
                    return None

                proxy_config = get_random_telethon_proxy()
                template_data = generate_random_template_data()

                client_kwargs = {
                    "session": StringSession(session_string),
                    "api_id": template_data["app_id"],
                    "api_hash": template_data["app_hash"],
                    "connection": ConnectionTcpFull,
                    "receive_updates": False,
                    "connection_retries": 0,
                    "timeout": 3
                }
                if proxy_config:
                    client_kwargs["proxy"] = proxy_config

                client = None
                connected = False
                phone_number = None

                try:
                    async with async_timeout(3):
                        client = TelegramClient(**client_kwargs)
                        await client.connect()
                        if await client.is_user_authorized():
                            connected = True
                            me = await client.get_me()
                            phone_number = me.phone
                except Exception as e:
                    print(f"[{tdata_path}] Ошибка подключения: {type(e).__name__}: {str(e)}")
                    return None

                if not connected or not phone_number:
                    print(f"[{tdata_path}] Не удалось авторизоваться")
                    return None

                if is_phone_rate_limited(phone_number):
                    print(f"[{phone_number}] Номер rate-limited, пропуск")
                    return None

                mark_phone_as_used(phone_number)

                async with get_phone_lock(phone_number):
                    target_dir = output_dir
                    if not target_dir:
                        target_dir = os.path.join(os.getcwd(), TDATA_TO_SESSION_DIR)
                    os.makedirs(target_dir, exist_ok=True)

                    final_session_file = os.path.join(target_dir, f"+{phone_number}.session")
                    final_json_file = os.path.join(target_dir, f"+{phone_number}.json")

                    if os.path.exists(final_session_file) or os.path.exists(final_json_file):
                        print(f"[{phone_number}] Сессия уже существует в {target_dir}, пропуск")
                        return None

                    output_name = f"+{phone_number}_{index + 1}" if len(sessions) > 1 else f"+{phone_number}"
                    temp_session_file = os.path.join(os.path.dirname(tdata_path), f"{output_name}.session")
                    temp_json_file = os.path.join(os.path.dirname(tdata_path), f"{output_name}.json")

                    await create_sqlite_session_file(
                        temp_session_file, dc_id, DC_TABLE[dc_id][0], DC_TABLE[dc_id][1],
                        binascii.unhexlify(auth_key_hex)
                    )

                    session_data = {
                        **template_data,
                        "session_file": f"+{phone_number}.session",
                        "phone": phone_number,
                        "id": me.id,
                        "first_name": me.first_name or "",
                        "username": me.username,
                        "is_premium": me.premium,
                        "last_check_time": int(time.time()),
                        "dc_id": dc_id,
                        "dc_ip": DC_TABLE[dc_id][0],
                        "dc_port": DC_TABLE[dc_id][1],
                        "auth_key": auth_key_hex,
                        "session_string": session_string,
                        "proxy": proxy_config if proxy_config else None
                    }

                    with open(temp_json_file, "w", encoding="utf-8") as f:
                        json.dump(session_data, f, indent=4)

                    shutil.move(temp_session_file, final_session_file)
                    shutil.move(temp_json_file, final_json_file)

                    print(f"[{phone_number}] - Сессия создана")

                    if client and client.is_connected():
                        await client.disconnect()
                return phone_number

        tasks = [process_session(index, authkey_maindcid, session_string)
                 for index, (authkey_maindcid, session_string) in enumerate(sessions)]
        gather_results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in gather_results if not isinstance(r, Exception) and r is not None]


async def process_session_file(session_path):
    async with SESSION_SEMAPHORE, GLOBAL_SEMAPHORE:
        json_path = session_path.replace('.session', '.json')

        session_data = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    session_data = json.loads(f.read())
            except Exception as e:
                print(f"\n[{os.path.basename(session_path)}] Ошибка чтения JSON: {e}")

        session_string = session_data.get("session_string")
        app_id = session_data.get("app_id", API_ID)
        app_hash = session_data.get("app_hash", API_HASH)

        session = StringSession(session_string) if session_string else session_path
        proxy_config = get_random_telethon_proxy()

        client_kwargs = {
            "session": session,
            "api_id": app_id,
            "api_hash": app_hash,
            "connection": ConnectionTcpFull,
            "receive_updates": False,
            "connection_retries": 0,
            "timeout": 15
        }
        if proxy_config:
            client_kwargs["proxy"] = proxy_config

        client = None
        try:
            client = TelegramClient(**client_kwargs)
            try:
                async with async_timeout(15):
                    await client.connect()
            except asyncio.TimeoutError:
                return
            except Exception as e:
                return

            if not await client.is_user_authorized():
                if DELETE_INVALID_SESSIONS:
                    await client.disconnect()
                    await delete_session_files(session_path, json_path)
                return

            me = await client.get_me()
            phone_number = me.phone
            if not phone_number:
                if _PROGRESS:
                    await _PROGRESS.increment(failed=True)
                return

            await process_active_client(client, phone_number, session_path, json_path)

        finally:
            if client and client.is_connected():
                await client.disconnect()
            try:
                journal_path = session_path + "-journal"
                if os.path.exists(journal_path):
                    os.remove(journal_path)
            except Exception:
                pass


async def process_active_client(client, phone_number, session_path, json_path, tdata_path=None, original_archive=""):
    # Resume: skip if already checked
    if phone_number in _CHECKED_PHONES:
        print(f"\n[{phone_number}] Уже проверен, пропуск")
        return

    if is_phone_rate_limited(phone_number):
        print(f"\n[{phone_number}] Пропуск (Rate Limited)")
        return

    mark_phone_as_used(phone_number)

    async with get_phone_lock(phone_number):
        try:
            async with async_timeout(120):
                info = await check_account(client, phone_number)

                # Save and sort valid tdata
                saved_path = ""
                if tdata_path:
                    saved_path = await save_and_sort(tdata_path, info, original_archive)

                source = saved_path or session_path or tdata_path or ""
                print(f"\n{format_account_info(info, source=source)}")
                save_to_results(info)
                _CHECKED_PHONES.add(phone_number)

                matched = await check_all_filters(client, phone_number)
                for filter_name in matched:
                    if session_path:
                        sort_session_to_filter(session_path, json_path, filter_name)
                    elif saved_path:
                        sort_tdata_to_filter(saved_path, filter_name)

                if DELETE_USED_SESSIONS and session_path and os.path.exists(session_path):
                    await client.disconnect()
                    await delete_session_files(session_path, json_path)

        except asyncio.TimeoutError:
            print(f"\n[{phone_number}] Тайм-аут операции")
        except Exception as e:
            error_msg = str(e) if str(e) else e.__class__.__name__
            print(f"\n[{phone_number}] Ошибка: {error_msg}")
            error_str = error_msg.lower()
            is_frozen = "frozen" in error_str or "заморожен" in error_str

            bad_errors = ["frozen", "frozen_method_invalid", "not authorized", "user_deactivated",
                          "auth_key_duplicated", "auth_key_invalid", "session_revoked",
                          "invalid", "misusing the session", "заморожен"]

            if DELETE_INVALID_SESSIONS or (is_frozen and DELETE_FROZEN_SESSIONS):
                if any(x in error_str for x in bad_errors):
                    try: await client.log_out()
                    except: pass
                    await client.disconnect()
                    if session_path and os.path.exists(session_path):
                        await delete_session_files(session_path, json_path)
            elif is_frozen and session_path and os.path.exists(session_path):
                try:
                    await client.disconnect()
                    directory = os.path.dirname(session_path)
                    new_path = os.path.join(directory, f"FROZEN_{os.path.basename(session_path)}")
                    if not os.path.exists(new_path):
                        os.rename(session_path, new_path)
                        if json_path and os.path.exists(json_path):
                            os.rename(json_path, new_path.replace('.session', '.json'))
                except Exception:
                    pass


async def process_tdata_folder(tdata_path, original_archive=""):
    auth_key_datas = []
    try:
        auth_key_datas = await asyncio.get_running_loop().run_in_executor(
            ARCHIVE_EXECUTOR, convert_tdata_to_authkey, tdata_path, None
        )
    except Exception as e:
        print(f"\n[{os.path.basename(tdata_path)}] Ошибка парсинга TData: {e}")
        auth_key_datas = []

    sessions_found = False

    if auth_key_datas:
        sessions_found = True

        async def process_tdata_session(index, authkey_maindcid, session_string):
            async with GLOBAL_SEMAPHORE:
                auth_key_hex, dc_id = authkey_maindcid.split(":")
                dc_id = int(dc_id)
                template_data = generate_random_template_data()
                proxy_config = get_random_telethon_proxy()

                client_kwargs = {
                    "session": StringSession(session_string),
                    "api_id": template_data["app_id"],
                    "api_hash": template_data["app_hash"],
                    "connection": ConnectionTcpFull,
                    "receive_updates": False,
                    "connection_retries": 0,
                    "timeout": 15
                }
                if proxy_config:
                    client_kwargs["proxy"] = proxy_config

                client = None
                try:
                    client = TelegramClient(**client_kwargs)
                    try:
                        async with async_timeout(15):
                            await client.connect()
                    except (asyncio.TimeoutError, Exception) as e:
                        print(f"\n[{os.path.basename(tdata_path)}] Ошибка подключения: {e}")
                        return

                    if not await client.is_user_authorized():
                        print(f"\n[{os.path.basename(tdata_path)}] Не авторизован")
                        return

                    me = await client.get_me()
                    phone_number = me.phone
                    if not phone_number:
                        return

                    await process_active_client(client, phone_number, None, None, tdata_path=tdata_path, original_archive=original_archive)

                except Exception as e:
                    print(f"\nОшибка обработки сессии из tdata: {e}")
                finally:
                    if client and client.is_connected():
                        await client.disconnect()

        tasks = [process_tdata_session(i, d[0], d[1]) for i, d in enumerate(auth_key_datas)]
        await asyncio.gather(*tasks)

    should_delete = False
    if not sessions_found:
        if DELETE_INVALID_SESSIONS:
            should_delete = True
    else:
        if DELETE_USED_SESSIONS:
            should_delete = True

    if should_delete:
        try:
            await asyncio.sleep(1)
            if os.path.exists(tdata_path):
                shutil.rmtree(tdata_path, ignore_errors=True)
        except Exception as e:
            print(f"\n[{os.path.basename(tdata_path)}] Ошибка удаления: {e}")


async def process_tdata_archive(archive_path):
    """Extract archive, check accounts in-memory, then remove temp dir."""
    async with ARCHIVE_SEMAPHORE:
        archive_name = os.path.basename(archive_path)
        temp_dir = os.path.join(
            os.path.dirname(archive_path),
            f"temp_{int(time.time())}_{random.randint(1000, 9999)}"
        )
        try:
            extracted = await asyncio.get_running_loop().run_in_executor(
                ARCHIVE_EXECUTOR,
                lambda: _extract_sync(archive_path, temp_dir)
            )
            if not extracted:
                # Extraction failed — still counts as processed (failed)
                if _PROGRESS:
                    await _PROGRESS.increment(failed=True)
                return

            tdata_paths = await find_all_key_datas_and_tdata(temp_dir)
            if tdata_paths:
                # Pass only the archive filename (not full path) for INFO.txt
                tasks = [
                    process_tdata_folder(tp, original_archive=archive_name)
                    for tp in tdata_paths
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                print(f"\n[{archive_name}] tdata не найдена внутри архива")
                if _PROGRESS:
                    await _PROGRESS.increment(failed=True)
        except Exception as e:
            print(f"\n[{archive_name}] Ошибка: {e}")
            if _PROGRESS:
                await _PROGRESS.increment(failed=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            if DELETE_USED_SESSIONS:
                try:
                    os.remove(archive_path)
                except Exception:
                    pass


def _extract_sync(archive_path: str, temp_dir: str) -> bool:
    """Synchronous archive extraction (runs in thread pool)."""
    import zipfile
    import rarfile
    os.makedirs(temp_dir, exist_ok=True)
    try:
        ext = archive_path.lower()
        if ext.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(temp_dir)
            return True
        elif ext.endswith('.rar'):
            with rarfile.RarFile(archive_path, 'r') as rf:
                rf.extractall(temp_dir)
            return True
    except Exception as e:
        print(f"\n[{os.path.basename(archive_path)}] Ошибка распаковки: {e}")
    return False


async def worker_tdata_folders(queue: asyncio.Queue, worker_id: int):
    while True:
        tdata_path = await queue.get()
        failed = False
        try:
            await process_tdata_folder(tdata_path)
        except Exception:
            failed = True
        finally:
            if _PROGRESS:
                await _PROGRESS.increment(failed=failed)
            queue.task_done()


async def worker_tdata_archives(queue: asyncio.Queue, worker_id: int):
    while True:
        archive_path = await queue.get()
        failed = False
        try:
            await process_tdata_archive(archive_path)
        except Exception:
            failed = True
        finally:
            if _PROGRESS:
                await _PROGRESS.increment(failed=failed)
            queue.task_done()


async def worker_sessions(queue: asyncio.Queue, worker_id: int):
    while True:
        session_path = await queue.get()
        failed = False
        try:
            await process_session_file(session_path)
        except asyncio.TimeoutError:
            failed = True
        except Exception as e:
            error_msg = str(e) if str(e) else e.__class__.__name__
            print(f"\nОшибка {os.path.basename(session_path)}: {error_msg}")
            failed = True
        finally:
            if _PROGRESS:
                await _PROGRESS.increment(failed=failed)
            queue.task_done()


async def scan_tdatas(tdatas_dir=None):
    global _CHECKED_PHONES, _PROGRESS
    if tdatas_dir is None:
        tdatas_dir = TDATAS_DIR
    os.makedirs(tdatas_dir, exist_ok=True)

    _CHECKED_PHONES = load_checked_phones()
    if _CHECKED_PHONES:
        print(f"Resume: найдено {len(_CHECKED_PHONES)} уже проверенных аккаунтов, они будут пропущены.\n")

    # --- Folders ---
    tdata_folders = []
    for root, dirs, files in os.walk(tdatas_dir):
        if "key_datas" in files:
            tdata_folders.append(os.path.normpath(root))

    if tdata_folders:
        print(f"Найдено {len(tdata_folders)} папок tdata.")
        _PROGRESS = ProgressTracker(len(tdata_folders), "tdata-папки")
        queue = asyncio.Queue()
        for folder in tdata_folders:
            await queue.put(folder)
        workers = [asyncio.create_task(worker_tdata_folders(queue, i)) for i in range(MAX_CONCURRENT)]
        await queue.join()
        for w in workers:
            w.cancel()
        _PROGRESS.finish()

    # --- Archives ---
    archive_files = []
    for root, dirs, files in os.walk(tdatas_dir):
        for f in files:
            if f.lower().endswith(('.zip', '.rar')):
                archive_files.append(os.path.join(root, f))
    archive_files.sort()

    if archive_files:
        print(f"\nНайдено {len(archive_files)} архивов.")
        _PROGRESS = ProgressTracker(len(archive_files), "архивы")
        queue = asyncio.Queue()
        for archive_path in archive_files:
            await queue.put(archive_path)
        workers = [asyncio.create_task(worker_tdata_archives(queue, i)) for i in range(ARCHIVE_CONCURRENT)]
        await queue.join()
        for w in workers:
            w.cancel()
        _PROGRESS.finish()

    cleanup_phone_locks()


async def scan_sessions(sessions_dir=None):
    global _CHECKED_PHONES, _PROGRESS
    if sessions_dir is None:
        sessions_dir = SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)

    _CHECKED_PHONES = load_checked_phones()
    if _CHECKED_PHONES:
        print(f"Resume: найдено {len(_CHECKED_PHONES)} уже проверенных аккаунтов, они будут пропущены.\n")

    session_files = []
    for root, dirs, files in os.walk(sessions_dir):
        for f in files:
            if f.endswith('.session'):
                session_files.append(os.path.join(root, f))

    if not session_files:
        print("Сессий не найдено.")
        return

    print(f"Найдено {len(session_files)} сессий.")
    _PROGRESS = ProgressTracker(len(session_files), "sessions")

    queue = asyncio.Queue()
    for session_path in session_files:
        await queue.put(session_path)
    workers = [asyncio.create_task(worker_sessions(queue, i)) for i in range(MAX_CONCURRENT)]
    await queue.join()
    for w in workers:
        w.cancel()
    _PROGRESS.finish()
    cleanup_phone_locks()


async def convert_all_tdatas(passcode=None):
    os.makedirs(TDATAS_DIR, exist_ok=True)
    os.makedirs(TDATA_TO_SESSION_DIR, exist_ok=True)

    tdata_folders = []
    for root, dirs, files in os.walk(TDATAS_DIR):
        if "key_datas" in files:
            tdata_folders.append(os.path.normpath(root))

    if not tdata_folders:
        print("Папок tdata не найдено.")
        return

    print(f"Найдено {len(tdata_folders)} папок tdata для конвертации.")
    tasks = [convert_tdata_to_session(folder, passcode, None, output_dir=TDATA_TO_SESSION_DIR)
             for folder in tdata_folders]
    await asyncio.gather(*tasks)


async def convert_all_sessions_to_tdata(output_dir=None):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    if output_dir is None:
        output_dir = SESSION_TO_TDATA_DIR
    os.makedirs(output_dir, exist_ok=True)

    session_files = []
    for root, dirs, files in os.walk(SESSIONS_DIR):
        for f in files:
            if f.endswith('.session'):
                session_files.append(os.path.join(root, f))

    if not session_files:
        print("Сессий не найдено.")
        return

    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def convert_wrapper(session_path):
        async with sem:
            created = await loop.run_in_executor(None, convert_session_to_tdata, session_path, output_dir)
            if created:
                for td in created:
                    print(f"Создано tdata: {td}")

    await asyncio.gather(*[convert_wrapper(s) for s in session_files])
