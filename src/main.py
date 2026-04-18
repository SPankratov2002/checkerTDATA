import asyncio
import os
import re
import sys
import io
import shutil
from colorama import init, Fore, Style

# Force UTF-8 output on Windows
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

# ─── palette ─────────────────────────────────────────────────────────────────
C  = Fore.CYAN
W  = Fore.WHITE
G  = Fore.GREEN
Y  = Fore.YELLOW
R  = Fore.RED
DM = Style.DIM
BR = Style.BRIGHT
RS = Style.RESET_ALL

PANEL_W  = 60
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _vis(s: str) -> int:
    return len(_ANSI_RE.sub('', s))


def _cols() -> int:
    return shutil.get_terminal_size((120, 40)).columns


def _margin() -> str:
    return ' ' * max(0, (_cols() - PANEL_W) // 2)


def _p(line: str = ''):
    print(_margin() + line)


def _rule(char='─', color=True):
    s = char * PANEL_W
    print(_margin() + (f'{DM}{W}{s}{RS}' if color else s))


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

def _print_banner():
    cols     = _cols()
    banner_w = max(len(l) for l in _BANNER_LINES)
    pad      = ' ' * max(0, (cols - banner_w) // 2)
    print()
    for line in _BANNER_LINES:
        print(pad + BR + C + line + RS)
    sub     = 'C H E C K E R   v1.0'
    sub_pad = ' ' * max(0, (cols - len(sub)) // 2)
    print(sub_pad + DM + W + sub + RS)


# ─── helpers ─────────────────────────────────────────────────────────────────
def _prompt(msg='Выбор') -> str:
    m = _margin()
    return input(f'\n{m}{BR}{C}❯ {RS}{W}{msg}: {RS}').strip()


def _ok(msg: str):
    _p(f'{G}  ✓  {msg}{RS}')


def _err(msg: str):
    _p(f'{R}  ✗  {msg}{RS}')


def _pause():
    m = _margin()
    input(f'\n{m}{DM}{W}  Нажмите Enter...{RS}')


def _header(subtitle=''):
    _clear()
    _print_banner()
    if subtitle:
        cols = _cols()
        pad  = ' ' * max(0, (cols - len(subtitle)) // 2)
        print('\n' + pad + BR + W + subtitle + RS)
    print()
    _rule()


# ─── stats + active checks ───────────────────────────────────────────────────
def _stats_bar():
    settings     = load_settings()
    tdatas_dir   = os.path.join(BASE_DIR, settings.get('TDATAS_DIR',   'accounts/tdatas'))
    sessions_dir = os.path.join(BASE_DIR, settings.get('SESSIONS_DIR', 'accounts/sessions'))

    tdatas = archives = sessions = 0
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
        sessions = sum(1 for f in os.listdir(sessions_dir) if f.lower().endswith('.session'))

    # Files line
    parts = []
    if archives: parts.append(f'{BR}{Y}{archives}{RS}{DM}{W} архивов{RS}')
    if tdatas:   parts.append(f'{BR}{C}{tdatas}{RS}{DM}{W} tdata{RS}')
    if sessions: parts.append(f'{BR}{C}{sessions}{RS}{DM}{W} sessions{RS}')

    sep = f'  {DM}{W}·{RS}  '
    if parts:
        line = f'{DM}{W}Файлы: {RS}' + sep.join(parts)
    else:
        line = f'{DM}{W}Папки пусты — добавьте файлы в {BR}accounts/{RS}'

    cols = _cols()
    print(' ' * max(0, (cols - _vis(line)) // 2) + line)

    # Active checks line
    flags = []
    if settings.get('CHECK_GIFTS'):    flags.append('Gifts')
    if settings.get('CHECK_CRYPTOBOT'): flags.append('CryptoBot')
    if settings.get('CHECK_SPAMBOT'):  flags.append('SpamBot')
    if settings.get('CHECK_2FA'):      flags.append('2FA')
    if settings.get('CHECK_ADMIN'):    flags.append('Admin')
    if flags:
        checks_line = f'{DM}{W}Проверки: {RS}{DM}{G}' + '  '.join(flags) + RS
        print(' ' * max(0, (cols - _vis(checks_line)) // 2) + checks_line)

    print()


# ─── primary action item (highlighted) ───────────────────────────────────────
def _primary(key, label: str):
    """Big highlighted item — the main action."""
    key_s   = f'{BR}{G}[{key}]{RS}'
    label_s = f'{BR}{W}{label}{RS}'
    arrow   = f'{DM}{G}  ◄ ГЛАВНОЕ{RS}'
    _p(f'  {key_s}  {label_s}{arrow}')


def _item(key, label: str, dim=False, note=''):
    key_s   = f'{BR}{C}[{key}]{RS}'
    label_s = f'{DM}{W}{label}{RS}' if dim else f'{W}{label}{RS}'
    note_s  = f'  {DM}{W}{note}{RS}' if note else ''
    _p(f'  {key_s}  {label_s}{note_s}')


def _section(label: str):
    _p()
    _p(f'{DM}{Y}{label}{RS}')


# ─── main menu ───────────────────────────────────────────────────────────────
def main():
    while True:
        _header()
        _stats_bar()

        _primary(1, 'Сканировать tdata')
        _item(2, 'Проверить sessions')

        _section('Инструменты')
        _item(3, 'Конвертация')
        _item(4, 'Фильтры  (бот / группа)')

        _p()
        _rule('┄')
        _item('S', 'Настройки', note='API, проверки, пути')
        _item(0,   'Выход', dim=True)
        _rule('┄')

        choice = _prompt()

        if choice == '1':
            _header('◉  Сканирование tdata')
            asyncio.run(scan_tdatas())
            _ok('Сканирование завершено.')
            _pause()

        elif choice == '2':
            _header('◉  Проверка sessions')
            asyncio.run(scan_sessions())
            _ok('Проверка завершена.')
            _pause()

        elif choice == '3':
            convert_menu()

        elif choice == '4':
            edit_filters()

        elif choice.lower() == 's':
            edit_settings()

        elif choice == '0':
            _clear()
            print()
            _p(f'{DM}{W}  Выход...{RS}')
            print()
            break

        else:
            _err('Неверный выбор!')
            _pause()


# ─── convert submenu ─────────────────────────────────────────────────────────
def convert_menu():
    while True:
        _header('Конвертация')

        _p(f'{DM}{W}  Выберите направление конвертации:{RS}')
        _p()
        _item(1, 'tdata  →  session',               note='сохранить как .session')
        _item(2, 'session  →  tdata',               note='восстановить tdata')
        _p()
        _item(3, 'tdata  →  session  →  проверка',  note='конверт + чек')
        _item(4, 'session  →  tdata  →  проверка',  note='конверт + чек')
        _p()
        _item(0, 'Назад', dim=True)
        _rule('┄')

        choice = _prompt()

        if choice == '1':
            _header('tdata → session')
            asyncio.run(convert_all_tdatas())
            _ok('Конвертация завершена.')
            _pause()

        elif choice == '2':
            _header('session → tdata')
            asyncio.run(convert_all_sessions_to_tdata())
            _ok('Конвертация завершена.')
            _pause()

        elif choice == '3':
            _header('tdata → session → проверка')
            asyncio.run(convert_all_tdatas())
            _ok('Конвертация завершена, запускаю проверку...')
            from .config import TDATA_TO_SESSION_DIR
            asyncio.run(scan_sessions(TDATA_TO_SESSION_DIR))
            _ok('Готово.')
            _pause()

        elif choice == '4':
            _header('session → tdata → проверка')
            asyncio.run(convert_all_sessions_to_tdata())
            _ok('Конвертация завершена, запускаю проверку...')
            from .config import SESSION_TO_TDATA_DIR
            asyncio.run(scan_tdatas(SESSION_TO_TDATA_DIR))
            _ok('Готово.')
            _pause()

        elif choice == '0':
            break

        else:
            _err('Неверный выбор!')
            _pause()


# ─── filters ─────────────────────────────────────────────────────────────────
def edit_filters():
    settings     = load_settings()
    filters_path = os.path.join(BASE_DIR, settings.get('FILTERS_FILE', 'filters.txt'))

    def _load():
        if not os.path.exists(filters_path):
            return []
        with open(filters_path, 'r', encoding='utf-8') as f:
            return [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]

    while True:
        filters = _load()
        _header('Фильтры — бот / группа')

        _p(f'{DM}{W}  Аккаунты с совпадением будут скопированы в:{RS}')
        _p(f'{DM}{C}  accounts/filtered/<тег>/{RS}')
        _p()

        if filters:
            for i, tag in enumerate(filters, 1):
                _p(f'  {BR}{C}[{i:2}]{RS}  {W}{tag}{RS}')
        else:
            _p(f'  {DM}{W}(список пуст — аккаунты не фильтруются){RS}')

        _p()
        _rule('┄')
        _item('a', 'Добавить фильтр')
        if filters:
            _item('d', 'Удалить фильтр')
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
            _pause()
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
_SETTINGS_CATEGORIES = {
    'Что проверять': [
        ('CHECK_GIFTS',     'Подарки и NFT'),
        ('CHECK_CRYPTOBOT', 'Баланс CryptoBot'),
        ('CHECK_SPAMBOT',   'Спам-статус (@SpamBot)'),
        ('CHECK_2FA',       'Двухфакторный пароль'),
        ('CHECK_FULL_INFO', 'Bio, фото, сессии, контакты'),
        ('CHECK_ADMIN',     'Каналы и группы (admin)'),
    ],
    'Управление файлами': [
        ('DELETE_FROZEN_SESSIONS',  'Удалять замороженные сессии'),
        ('DELETE_USED_SESSIONS',    'Удалять проверенные сессии'),
        ('DELETE_INVALID_SESSIONS', 'Удалять невалидные сессии'),
        ('COPY_FILTERED',           'Копировать (не перемещать) в filtered/'),
    ],
    'Производительность': [
        ('MAX_CONCURRENT',     'Параллельных проверок'),
        ('ARCHIVE_CONCURRENT', 'Параллельных распаковок'),
        ('PHONE_LOCK_DURATION','Блокировка номера (сек)'),
        ('CHECK_INTERVAL',     'Интервал проверки'),
    ],
    'Пути и файлы': [
        ('TDATAS_DIR',          'Папка tdata'),
        ('SESSIONS_DIR',        'Папка sessions'),
        ('VALID_DIR',           'Папка valid (результаты)'),
        ('FILTERED_DIR',        'Папка filtered'),
        ('TDATA_TO_SESSION_DIR','Конверт tdata→session'),
        ('SESSION_TO_TDATA_DIR','Конверт session→tdata'),
        ('FILTERS_FILE',        'Файл фильтров'),
        ('RESULTS_FILE',        'Файл результатов'),
    ],
    'API Telegram': [
        ('API_ID',   'API ID'),
        ('API_HASH', 'API Hash'),
        ('NFT_SERIAL_THRESHOLD', 'Порог серийника NFT'),
    ],
}


def edit_settings():
    while True:
        settings = load_settings()
        key_map  = {}
        idx      = 1

        _header('Настройки')

        for category, pairs in _SETTINGS_CATEGORIES.items():
            _section(category)
            for key, label in pairs:
                if key not in settings:
                    continue
                val = settings[key]
                if isinstance(val, bool):
                    val_s = f'{G}✓ Вкл{RS}' if val else f'{DM}{R}✗ Выкл{RS}'
                else:
                    s     = str(val)
                    val_s = f'{Y}{s[:36]}{"…" if len(s) > 36 else ""}{RS}'
                num_s = f'{BR}{C}[{idx:2}]{RS}'
                _p(f'  {num_s}  {DM}{W}{label:<30}{RS} {val_s}')
                key_map[idx] = key
                idx += 1

        _p()
        _rule('┄')
        _item('s', 'Сохранить и выйти')
        _item(0,   'Выйти без сохранения', dim=True)
        _rule('┄')

        raw = _prompt('Номер / s / 0')

        if raw == '0':
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
        # Find human label
        label = key
        for pairs in _SETTINGS_CATEGORIES.values():
            for k, l in pairs:
                if k == key:
                    label = l
                    break

        _p()
        _p(f'  {W}{label}{RS}  {DM}({key}){RS}')
        _p(f'  Текущее: {Y}{current_val}{RS}')
        _p()

        if isinstance(default_val, bool):
            new_raw = _prompt('Новое значение  [1/0  или  true/false]').lower()
            settings[key] = new_raw in ('true', '1', 'yes', 'on', 'вкл')
            _ok(f'{label}: {"Вкл" if settings[key] else "Выкл"}')
        elif isinstance(default_val, int):
            try:
                settings[key] = int(_prompt('Новое значение (число)'))
                _ok(f'{label} = {settings[key]}')
            except ValueError:
                _err('Введите целое число.')
        else:
            new_val = _prompt('Новое значение')
            if new_val:
                settings[key] = new_val
                _ok(f'{label} = {settings[key]}')
            else:
                _err('Пустое значение, отменено.')
        _pause()


if __name__ == '__main__':
    main()
