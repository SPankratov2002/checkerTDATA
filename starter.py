import sys
import os

# Добавляем текущую директорию в sys.path, чтобы Python видел пакет src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрограмма остановлена пользователем.")
    except Exception as e:
        print(f"\nПроизошла ошибка: {e}")
        input("Нажмите Enter, чтобы выйти...")
