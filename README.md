# Sommeur Checker

Read-only Telegram account checker. Supports **tdata**, **sessions**, and **archives** (.zip / .rar).

---

## Быстрый старт

### Windows
```bat
1run.bat
```

### Linux / Ubuntu / macOS
```bash
chmod +x run.sh
./run.sh
```

---

## Установка вручную

### 1. Зависимости системы (Ubuntu / Debian)
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv unrar
```

> `unrar` нужен для распаковки `.rar` архивов.  
> Если его нет — `.zip` всё равно работают.

### 2. Виртуальное окружение
```bash
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
# или: venv\Scripts\activate    # Windows
```

### 3. Python-зависимости
```bash
pip install -r requirements.txt
```

### 4. Настройки
```bash
cp settings.example.txt settings.txt
nano settings.txt   # или любой редактор
```

Обязательно заполните:
```
API_ID=ваш_api_id
API_HASH=ваш_api_hash
```

Получить `API_ID` и `API_HASH` → [my.telegram.org](https://my.telegram.org)

### 5. Запуск
```bash
python3 starter.py
```

---

## Структура папок

```
accounts/
├── tdatas/      ← сюда кладёте tdata-папки или .zip/.rar архивы
├── sessions/    ← сюда кладёте .session файлы
├── valid/       ← валидные аккаунты после проверки (создаётся автоматически)
│   ├── tdata_1/
│   │   └── INFO.txt
│   └── sorted/
│       ├── premium_yes/
│       ├── with_nft/
│       ├── with_crypto/
│       └── results/
└── filtered/    ← аккаунты, совпавшие с фильтрами
```

---

## Возможности

| Функция | Описание |
|---------|----------|
| tdata / sessions | Проверка через Telethon |
| Архивы .zip / .rar | Автораспаковка, параллельно до 8 потоков |
| Подарки и NFT | Подсчёт, без передачи |
| CryptoBot | Чтение баланса USDT/TON, сообщения удаляются |
| SpamBot | Проверка статуса, сообщения удаляются |
| 2FA | Наличие пароля |
| Admin | Каналы и группы где аккаунт — admin |
| Фильтры | Сортировка по членству в боте/группе |
| Сортировка | Копии по категориям: premium, nft, crypto, 2fa… |
| Resume | Повторный запуск пропускает уже проверенные |

---

## Возможные проблемы

**`ModuleNotFoundError: No module named 'cryptg'`**
```bash
pip install cryptg
# если не помогает:
sudo apt install python3-dev build-essential
pip install cryptg --no-binary :all:
```

**RAR архивы не открываются**
```bash
sudo apt install unrar
```

**`UnicodeDecodeError` или кракозябры в терминале**
```bash
export PYTHONIOENCODING=utf-8
python3 starter.py
```

**`asyncio.timeout` не найден (Python < 3.11)**
```bash
python3 --version   # нужна 3.11+
sudo apt install python3.11 python3.11-venv
python3.11 -m venv venv
```
