import os

def concatenate_files(root_dir: str, output_file: str):
    """
    Обходит все файлы в директории root_dir и записывает их содержимое
    в один файл output_file. Перед содержимым каждого файла добавляет
    строку с относительным путём от root_dir.
    """
    with open(output_file, 'w', encoding='utf-8') as out_f:
        # Проходим по всем поддиректориям и файлам
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in sorted(filenames):
                # Полный путь к файлу
                full_path = os.path.join(dirpath, filename)
                # Относительный путь от корня root_dir
                rel_path = os.path.relpath(full_path, root_dir)
                # Записываем заголовок с путём
                out_f.write(f"=== {rel_path} ===\n")
                # Читаем и записываем содержимое файла
                try:
                    with open(full_path, 'r', encoding='utf-8') as in_f:
                        out_f.write(in_f.read())
                except UnicodeDecodeError:
                    # Если файл не текстовый — пропускаем с уведомлением
                    out_f.write("[Не удалось прочитать файл как текст]\n")
                out_f.write("\n\n")  # Разделитель между файлами

if __name__ == "__main__":
    # Директория с файлами
    root_directory = os.path.join(os.path.dirname(__file__), "v1.1")
    # Итоговый файл
    output_filename = os.path.join(os.path.dirname(__file__), "all.txt")

    concatenate_files(root_directory, output_filename)
    print(f"Содержимое всех файлов из '{root_directory}' сохранено в '{output_filename}'")
