import os
import json
import binascii
from .tdata_parsing import (
    read_file, create_local_key, decrypt_local, read_user_auth, build_session,
    read_encrypted_file, account_data_string
)
from .config import DC_TABLE, TDATAS_DIR, SESSION_TO_TDATA_DIR, TDATA_TO_SESSION_DIR
from telethon.sessions import StringSession
from telethon import TelegramClient

def convert_tdata_to_authkey(tdata_path, passcode=None):
    try:
        norm_tdata_path = os.path.normpath(tdata_path)
        key_datas_path = os.path.join(norm_tdata_path, "key_datas")
        if not os.path.exists(key_datas_path):
            return []
        if not os.path.isfile(key_datas_path):
            print(f"[{norm_tdata_path}] key_datas не является файлом")
            return []
            
        stream = read_file(key_datas_path)
        salt = stream.read_buffer()
        if len(salt) != 32:
            raise Exception("invalid salt length")
        key_encrypted = stream.read_buffer()
        info_encrypted = stream.read_buffer()
        
        passcode_key = create_local_key(passcode or b"", salt)
        key_inner_data = decrypt_local(key_encrypted, passcode_key)
        local_key = key_inner_data.read(256)
        if len(local_key) != 256:
            raise Exception("invalid local key")
            
        sessions = []
        info_data = decrypt_local(info_encrypted, local_key)
        count = info_data.read_uint32()
        
        for i in range(count):
            index = info_data.read_uint32()
            try:
                dc, key = read_user_auth(norm_tdata_path, local_key, index)
                # dc, key are returned from read_user_auth
                
                if dc not in DC_TABLE:
                     # daun2 skips if not in table inside loop? 
                     # daun2: ip, port = DC_TABLE[dc] -> KeyError if not in table
                     continue

                ip, port = DC_TABLE[dc]
                session_string = build_session(dc, ip, port, key)
                sessions.append((f"{binascii.hexlify(key).decode()}:{dc}", session_string))
            except FileNotFoundError as e:
                print(f"[{norm_tdata_path}] FileNotFoundError для index {index}: {str(e)}")
                continue
            except Exception as e:
                print(f"[{norm_tdata_path}] Ошибка для index {index}: {type(e).__name__}: {str(e)}")
                continue
        return sessions
    except OSError as e:
        print(f"[{norm_tdata_path}] Ошибка ввода-вывода: {str(e)}")
        return []
    except Exception as e:
        print(f"[{norm_tdata_path}] Ошибка конвертации tdata: {type(e).__name__}: {str(e)}")
        return []


def convert_session_to_tdata(session_path, output_dir=None):
    """
    Конвертирует .session файл в tdata папку используя tgconvertor.
    Возвращает список созданных tdata путей.
    """
    import subprocess
    import hashlib
    
    created_tdatas = []
    
    if output_dir is None:
        output_dir = SESSION_TO_TDATA_DIR
    
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Генерируем имя папки для tdata
        session_basename = os.path.basename(session_path).replace('.session', '')
        # Используем имя файла (номер) как имя папки
        tdata_folder_name = session_basename
        tdata_output_path = os.path.join(output_dir, tdata_folder_name)
        
        # Используем tgconvertor для конвертации
        # tgconvertor convert session.session -f telethon -t tdata -o tdata_folder
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [
                "tgconvertor", "convert", session_path,
                "-f", "telethon",
                "-t", "tdata",
                "-o", tdata_output_path
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            env=env
        )
        
        if result.returncode == 0 and os.path.exists(tdata_output_path):
            created_tdatas.append(tdata_output_path)
            print(f"Успешная конвертация: {os.path.basename(session_path)} -> {tdata_folder_name}")
        else:
            error_msg = result.stderr if result.stderr else "Неизвестная ошибка"
            print(f"Не удалось конвертировать {os.path.basename(session_path)}: {error_msg}")
        
    except subprocess.TimeoutExpired:
        print(f"Не удалось конвертировать {os.path.basename(session_path)}: Превышено время ожидания")
    except FileNotFoundError:
        print(f"Не удалось конвертировать {os.path.basename(session_path)}: tgconvertor не найден. Установите: pip install TGConvertor")
    except Exception as e:
        print(f"Не удалось конвертировать {os.path.basename(session_path)}: {str(e)}")
    
    return created_tdatas

