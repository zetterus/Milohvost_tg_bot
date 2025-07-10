import os


def print_project_structure(startpath, exclude_dirs=None, exclude_files=None):
    """
    Выводит древовидную структуру проекта в консоль.

    :param startpath: Путь к корневой директории проекта.
    :param exclude_dirs: Список имен директорий, которые нужно исключить из вывода.
                         По умолчанию исключает '.venv', '.git', '__pycache__', '.idea'.
    :param exclude_files: Список имен файлов, которые нужно исключить из вывода.
                          По умолчанию исключает '.DS_Store'.
    """
    if exclude_dirs is None:
        exclude_dirs = ['.venv', '.git', '__pycache__', '.idea']
    if exclude_files is None:
        exclude_files = ['.DS_Store']

    # Вспомогательная рекурсивная функция для обхода и печати
    def _walk_and_print(current_dir, prefix=""):
        # Получаем все элементы (файлы и папки) в текущей директории
        try:
            entries = sorted(os.listdir(current_dir))
        except PermissionError:
            print(f"{prefix}├── [ДОСТУП ЗАПРЕЩЕН: {os.path.basename(current_dir)}]")
            return

        filtered_entries = []
        for entry in entries:
            full_path = os.path.join(current_dir, entry)
            if os.path.isdir(full_path):
                if entry not in exclude_dirs:
                    filtered_entries.append((entry, True))  # (имя, это_директория)
            else:
                if entry not in exclude_files:
                    filtered_entries.append((entry, False))

        for i, (entry_name, is_dir) in enumerate(filtered_entries):
            is_last = (i == len(filtered_entries) - 1)  # Проверяем, является ли текущий элемент последним

            # Определяем соединительные символы для текущей строки
            connector = "└── " if is_last else "├── "
            # Определяем префикс для следующего уровня вложенности
            next_prefix_segment = "    " if is_last else "│   "

            # Выводим текущий элемент
            print(f"{prefix}{connector}{entry_name}{'/' if is_dir else ''}")

            # Если это директория, рекурсивно вызываем функцию для нее
            if is_dir:
                _walk_and_print(os.path.join(current_dir, entry_name), prefix + next_prefix_segment)

    # Выводим имя корневой папки проекта
    print(f"{os.path.basename(startpath)}/")
    # Запускаем рекурсивный обход, начиная с корневой папки
    _walk_and_print(startpath)


if __name__ == "__main__":
    # Запуск скрипта из корневой папки проекта
    # Если скрипт находится в корневой папке проекта, os.getcwd() будет правильным.
    project_root = os.getcwd()
    print_project_structure(project_root)

    print("\nСтруктура проекта успешно выведена.")
    print("Папки .venv, .git, __pycache__, .idea и файлы .DS_Store были исключены.")
