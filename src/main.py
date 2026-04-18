import asyncio
import os
import re
import sys
import io
import shutil
from colorama import init, Fore, Style

# Force UTF-8 output on Windows — prevents UnicodeEncodeError with cyrillic/box chars
if hasattr(sys.stdout, 'buffer') and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer') and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

init(autoreset=True)

from .session_manager import (
    scan_tdatas, scan_sessions,
    convert_all_tdatas, convert_all_sessions_to_tdata
)
from .filter_check import invalidate_filters_cache
from .config import load_settings, save_settings, DEFAULTS, BASE_DIR

# ─── palette ────────────────────────────────────────────────────────────────
C  = Fore.CYAN
W  = Fore.WHITE
G  = Fore.GREEN
Y  = Fore.YELLOW
R  = Fore.RED
DM = Style.DIM
BR = Style.BRIGHT
RS = Style.RESET_ALL

# ─── layout constants ────────────────────────────────────────────────────────
PANEL_W = 60          # visible width of the UI panel
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _vis(s: str) -> int:
    """Visible (non-ANSI) length of a string."""
    return len(_ANSI_RE.sub('', s))


def _margin() -> str:
    cols = shutil.get_terminal_size((120, 40)).columns
    return ' ' * max(0, (cols - PANEL_W) // 2)


def _p(line: str = ''):
    """Print one line with auto left-margin centering."""
    print(_margin() + line)


def _rule(char='─'):
    print(_margin() + f'{DM}{W}' + char * PANEL_W + RS)


def _clear():
    os.system('cls' if os.name == 'nt' else 'clear')


# ─── banner ──────────────────────────────────────────────────────────────────
_BANNER_LINES = [
    "███████╗ ██████╗ ███╗   ███╗███╗   ███╗███████╗██╗   ██╗██████╗ ",
    "██╔════╝██╔═══██╗████╗ ████║████╗ ████║██╔════╝██║   ██║██╔══██╗",
    "███████╗██║   ██║██╔████╔██║██╔████╔██║█████╗  ██║   ██║██████╔╝",
    "╚════██║██║   ██║██║╚██╔╝██║██║╚██╔╝██║██╔══╝  ██║   ██║██╔══██╗",
    "███████║╚██████╔╝██║ ╚═╝ ██║██║ ╚═╝ ██║███████╗╚██████╔╝██║  ██║",
    "╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝",
]
# Banner is wider than PANEL_W — center it independently
def _print_banner():
    cols = shutil.get_terminal_size((120, 40)).columns
    banner_w = max(len(l) for l in _BANNER_LINES)
    pad = ' ' * max(0, (cols - banner_w) // 2)
    print()
    for line in _BANNER_LINES:
        print(pad + BR + C + line + RS)
    subtitle = 'C H E C K E R   v1.0'
    sub_pad = ' ' * max(0, (cols - len(subtitle)) // 2)
    print(sub_pad + DM + W + subtitle + RS)
    print()


# ─── helpers ─────────────────────────────────────────────────────────────────
def _section(label: str):
    _p()
    _p(f'{DM}{Y}{label}{RS}')


def _item(key, label: str, dim=False):
    key_s   = f'{BR}{C}[{key}]{RS}'
    label_s = f'{DM}{W}{label}{RS}' if dim else f'{W}{label}{RS}'
    _p(f'  {key_s}  {label_s}')


def _prompt(msg='Выбор') -> str:
    m = _margin()
    return input(f'\n{m}{BR}{C}❯ {RS}{W}{msg}: {RS}').strip()


def _ok(msg: str):
    _p(f'{G}✓  {msg}{RS}')


def _err(msg: str):
    _p(f'{R}✗  {msg}{RS}')


def _pause():
    m = _margin()
    input(f'\n{m}{DM}{W}Нажмите Enter...{RS}')


def _header(subtitle=''):
    _clear()
    _print_banner()
    if subtitle:
        cols = shutil.get_terminal_size((120, 40)).columns
        pad  = ' ' * max(0, (cols - len(subtitle)) // 2)
        print(pad + BR + W + subtitle + RS)
    _rule('─')


def _stats_bar():
    settings     = load_settings()
    tdatas_dir   = os.path.join(BASE_DIR, settings.get('TDATAS_DIR',   'accounts/tdatas'))
    sessions_dir = os.path.join(BASE_DIR, settings.get('SESSIONS_DIR', 'accounts/sessions'))

    tdatas = archives = sessions = 0

    # Single-level scan — fast even with 2500+ files
    if os.path.isdir(tdatas_dir):
        for entry in os.listdir(tdatas_dir):
            lower = entry.lower()
            if lower.endswith('.zip') or lower.endswith('.rar'):
                archives += 1
            else:
                full = os.path.join(tdatas_dir, entry)
                if os.path.isdir(full) and os.path.isfile(os.path.join(full, 'key_datas')):
                    tdatas += 1

    if os.path.isdir(sessions_dir):
        sessions = sum(
            1 for f in os.listdir(sessions_dir)
            if f.lower().endswith('.session')
        )

    parts = []
    if tdatas:   parts.append(f'{BR}{C}{tdatas}{RS} {DM}{W}tdata{RS}')
    if sessions: parts.append(f'{BR}{C}{sessions}{RS} {DM}{W}sessions{RS}')
    if archives: parts.append(f'{BR}{C}{archives}{RS} {DM}{W}архивов{RS}')

    if parts:
        sep  = f'  {DM}{W}·{RS}  '
        line = f'{DM}{W}Найдено: {RS}' + sep.join(parts)
        cols = shutil.get_terminal_size((120, 40)).columns
        pad  = ' ' * max(0, (cols - _vis(line)) // 2)
        print('\n' + pad + line)
    else:
        _p(f'{DM}{W}Папки пусты — добавьте файлы в accounts/{RS}')


# ─── main menu ───────────────────────────────────────────────────────────────
def main():
    while True:
        _header()
        _stats_bar()

        _section('Проверка аккаунтов')
        _item(1, 'Проверка tdata')
        _item(2, 'Проверка sessions')

        _section('Конвертация')
        _item(3, 'tdata  →  session')
        _item(4, 'session  →  tdata')
        _item(5, 'tdata  →  session  →  проверка')
        _item(6, 'session  →  tdata  →  проверка')

        _section('Прочее')
        _item(7, 'Фильтры  (бот / группа)')
        _item(9, 'Настройки')
        _item(0, 'Выход', dim=True)

        _p()
        _rule('┄')
        choice = _prompt()

        if choice == '1':
            _header('Проверка tdata')
            asyncio.run(scan_tdatas())
            _ok('Проверка завершена.')
            _pause()

        elif choice == '2':
            _header('Проверка sessions')
            asyncio.run(scan_sessions())
            _ok('Проверка завершена.')
            _pause()

        elif choice == '3':
            _header('Конверт tdata → session')
            asyncio.run(convert_all_tdatas())
            _ok('Конверт завершён.')
            _pause()

        elif choice == '4':
            _header('Конверт session → tdata')
            asyncio.run(convert_all_sessions_to_tdata())
            _ok('Конверт завершён.')
            _pause()

        elif choice == '5':
            _header('tdata → session → проверка')
            asyncio.run(convert_all_tdatas())
            _ok('Конвертация завершена, запускаю проверку...')
            from .config import TDATA_TO_SESSION_DIR
            asyncio.run(scan_sessions(TDATA_TO_SESSION_DIR))
            _ok('Операция завершена.')
            _pause()

        elif choice == '6':
            _header('session → tdata → проверка')
            asyncio.run(convert_all_sessions_to_tdata())
            _ok('Конвертация завершена, запускаю проверку...')
            from .config import SESSION_TO_TDATA_DIR
            asyncio.run(scan_tdatas(SESSION_TO_TDATA_DIR))
            _ok('Операция завершена.')
            _pause()

        elif choice == '7':
            edit_filters()

        elif choice == '9':
            edit_settings()

        elif choice == '0':
            _clear()
            print()
            _p(f'{DM}{W}Выход...{RS}')
            print()
            break

        else:
            _err('Неверный выбор!')
            _pause()


# ─── filters ─────────────────────────────────────────────────────────────────
def edit_filters():
    settings = load_settings()
    filters_path = os.path.join(BASE_DIR, settings.get('FILTERS_FILE', 'filters.txt'))

    def _load():
        if not os.path.exists(filters_path):
            return []
        with open(filters_path, 'r', encoding='utf-8') as f:
            return [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]

    while True:
        filters = _load()
        _header('Фильтры — бот / группа')
        _p(f'{DM}{W}Аккаунты с совпадением → accounts/filtered/<тег>/{RS}')
        _p()

        if filters:
            for i, tag in enumerate(filters, 1):
                _p(f'  {BR}{C}[{i:2}]{RS}  {W}{tag}{RS}')
        else:
            _p(f'  {DM}{W}(список пуст){RS}')

        _p()
        _item('a', 'Добавить')
        if filters:
            _item('d', 'Удалить')
        _item(0, 'Назад', dim=True)
        _rule('┄')

        action = _prompt('Действие').lower()

        if action == '0':
            break
        elif action == 'a':
            tag = _prompt('@тег бота или группы').strip()
            if tag:
                if not tag.startswith('@'):
                    tag = '@' + tag
                fresh = _load()
                if tag not in fresh:
                    fresh.append(tag)
                    _save_filters(filters_path, fresh)
                    invalidate_filters_cache()
                    _ok(f'Добавлен: {tag}')
                else:
                    _err('Уже есть в списке.')
        elif action == 'd' and filters:
            try:
                idx = int(_prompt('Номер для удаления')) - 1
                fresh = _load()
                if 0 <= idx < len(fresh):
                    removed = fresh.pop(idx)
                    _save_filters(filters_path, fresh)
                    invalidate_filters_cache()
                    _ok(f'Удалён: {removed}')
                else:
                    _err('Неверный номер.')
            except ValueError:
                _err('Введите число.')
        _pause()


def _save_filters(path, filters):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('# Теги ботов/групп для фильтрации аккаунтов.\n')
        f.write('# Аккаунты с диалогом совпадения попадут в accounts/filtered/<тег>/\n')
        f.write('# Формат: по одному @тегу на строку\n\n')
        for tag in filters:
            f.write(tag + '\n')


# ─── settings ────────────────────────────────────────────────────────────────
def edit_settings():
    _CATEGORIES = {
        'Директории':          ['TDATAS_DIR', 'SESSIONS_DIR', 'TDATA_TO_SESSION_DIR',
                                 'SESSION_TO_TDATA_DIR', 'FILTERED_DIR', 'VALID_DIR'],
        'API':                 ['API_ID', 'API_HASH'],
        'Файлы':               ['FILTERS_FILE', 'RESULTS_FILE'],
        'Что проверять':       ['CHECK_GIFTS', 'CHECK_CRYPTOBOT', 'CHECK_SPAMBOT',
                                 'CHECK_2FA', 'CHECK_FULL_INFO', 'CHECK_ADMIN'],
        'Фильтрация':          ['COPY_FILTERED'],
        'Управление сессиями': ['DELETE_FROZEN_SESSIONS', 'DELETE_USED_SESSIONS',
                                 'DELETE_INVALID_SESSIONS'],
        'Параметры':           ['CHECK_INTERVAL', 'MAX_CONCURRENT', 'ARCHIVE_CONCURRENT',
                                 'PHONE_LOCK_DURATION', 'NFT_SERIAL_THRESHOLD'],
    }

    while True:
        settings  = load_settings()
        key_map   = {}
        idx       = 1

        _header('Настройки')

        for category, keys in _CATEGORIES.items():
            _section(category)
            for key in keys:
                if key not in settings:
                    continue
                val = settings[key]
                if isinstance(val, bool):
                    val_s = f'{G}True{RS}' if val else f'{R}False{RS}'
                else:
                    s = str(val)
                    val_s = f'{Y}{s[:40]}{"..." if len(s) > 40 else ""}{RS}'
                num_s = f'{BR}{C}[{idx:2}]{RS}'
                _p(f'  {num_s}  {DM}{W}{key:<28}{RS} {val_s}')
                key_map[idx] = key
                idx += 1

        _p()
        _rule('┄')
        _item('s', 'Сохранить и выйти')
        _item(0,   'Выйти без сохранения', dim=True)
        _rule('┄')

        raw = _prompt('Номер / s / 0')

        if raw == '0':
            _err('Изменения не сохранены.')
            break
        elif raw.lower() == 's':
            if save_settings(settings):
                _ok('Сохранено. Перезапустите программу для применения.')
            else:
                _err('Ошибка сохранения!')
            _pause()
            break

        try:
            choice = int(raw)
        except ValueError:
            _err('Неверный ввод.')
            _pause()
            continue

        if choice not in key_map:
            _err('Неверный номер.')
            _pause()
            continue

        key         = key_map[choice]
        default_val = DEFAULTS[key]
        current_val = settings[key]

        _p(f'\n  {W}{key}{RS} = {Y}{current_val}{RS}  {DM}({type(default_val).__name__}){RS}')

        if isinstance(default_val, bool):
            new_raw = _prompt('Новое значение (true / false)').lower()
            settings[key] = new_raw in ('true', '1', 'yes', 'on')
            _ok(f'{key} = {settings[key]}')
        elif isinstance(default_val, int):
            try:
                settings[key] = int(_prompt('Новое значение (число)'))
                _ok(f'{key} = {settings[key]}')
            except ValueError:
                _err('Неверное число.')
        else:
            new_val = _prompt('Новое значение')
            if new_val:
                settings[key] = new_val
                _ok(f'{key} = {settings[key]}')
            else:
                _err('Пустое значение, отменено.')
        _pause()


if __name__ == '__main__':
    main()
