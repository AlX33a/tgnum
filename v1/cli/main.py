#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cli/main.py

Точка входа для объединённого парсера и уведомителя.
"""

import argparse
import asyncio
import multiprocessing
import sys
import traceback

from utils.config import load_config
from storage.db import get_connection
from core.async_stream_parser import AsyncStreamParser

def run_single_cycle(cfg):
    """
    Выполняет один цикл парсинга.
    """
    conn = get_connection()
    try:
        from core.stream_parser import run_stream_parser
        count = run_stream_parser(cfg, conn)
        print(f"Processed offers: {count}")
    except Exception as e:
        print(f"Error in single cycle: {e}", file=sys.stderr)
        traceback.print_exc()
    finally:
        conn.close()

def notifier_entry():
    """
    Точка входа для отдельного процесса уведомителя.
    """
    from notify_floor_alerts import main as notifier_main
    notifier_main()

async def run_continuous(cfg):
    """
    Запускает непрерывную работу парсера с нотификатором.
    """
    notifier_proc = None
    if cfg.get("bot_token"):
        try:
            print("Запуск уведомителя floor alerts...")
            notifier_proc = multiprocessing.Process(
                target=notifier_entry,
                daemon=True
            )
            notifier_proc.start()
            print("Нотификатор запущен")
        except Exception as e:
            print(f"Ошибка запуска нотификатора: {e}", file=sys.stderr)
            traceback.print_exc()

    try:
        parser = AsyncStreamParser(cfg)
        await parser.run()
    finally:
        if notifier_proc and notifier_proc.is_alive():
            notifier_proc.terminate()
            notifier_proc.join()

def main():
    print("=== Запуск CLI ===")

    # Проверяем импорт зависимостей
    try:
        _ = load_config
        _ = get_connection
        _ = AsyncStreamParser
        print("Модули успешно импортированы")
    except Exception as e:
        print(f"Ошибка импортирования модулей: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="GetGems объединённый парсер с нотификацией"
    )
    parser.add_argument(
        "--profile", choices=["dev", "prod"], default="dev",
        help="Профиль конфигурации"
    )
    parser.add_argument(
        "--mode", choices=["single", "continuous"], default="continuous",
        help="Режим работы: single = один цикл, continuous = бесконечно"
    )
    parser.add_argument(
        "--cycles", type=int, default=None,
        help="Максимальное число циклов (для continuous)"
    )
    args = parser.parse_args()
    print(f"Аргументы: profile={args.profile}, mode={args.mode}, cycles={args.cycles}")

    # Загрузка конфига
    try:
        cfg = load_config(args.profile)
        print(f"Конфигурация загружена для профиля '{args.profile}'")
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    # Устанавливаем лимит циклов, если указан
    if args.cycles is not None:
        cfg["max_cycles"] = args.cycles
        print(f"Установлено max_cycles = {cfg['max_cycles']}")

    # Запуск
    try:
        if args.mode == "single":
            print(f"Выполнение одного цикла парсера с профилем '{args.profile}'")
            run_single_cycle(cfg)
            print("Цикл завершён")
        else:
            print(f"Запуск непрерывной работы парсера с нотификацией (профиль '{args.profile}')")
            asyncio.run(run_continuous(cfg))
    except KeyboardInterrupt:
        print("\nПолучен сигнал прерывания, завершаем работу")
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
