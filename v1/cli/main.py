#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
import multiprocessing
import sys
import traceback

def run_single_cycle(cfg):
    from storage.db import get_connection
    from core.stream_parser import run_stream_parser
    
    conn = get_connection()
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    print(f"SQLite journal_mode = {mode}")
    try:
        count = run_stream_parser(cfg, conn)
        print(f"Обработано офферов: {count}")
    finally:
        conn.close()

async def run_continuous(cfg):
    notifier_proc = None
    if cfg.get("bot_token"):
        try:
            print("Запуск уведомителя floor alerts...")
            from notify_floor_alerts import main as notifier_main
            notifier_proc = multiprocessing.Process(target=notifier_main, args=(cfg,), daemon=True)
            notifier_proc.start()
            print("Нотификатор запущен")
        except Exception as e:
            print(f"Ошибка запуска нотификатора: {e}")
            traceback.print_exc()

    try:
        from core.async_stream_parser import AsyncStreamParser
        parser = AsyncStreamParser(cfg)
        await parser.run()
    finally:
        if notifier_proc and notifier_proc.is_alive():
            notifier_proc.terminate()
            notifier_proc.join()

def main():
    print("=== Запуск CLI ===")
    
    try:
        from utils.config import load_config
        from storage.db import get_connection
        from core.async_stream_parser import AsyncStreamParser
        print("Модули успешно импортированы")
    except ImportError as e:
        print(f"Ошибка импорта модулей: {e}")
        traceback.print_exc()
        return

    parser = argparse.ArgumentParser(
        description="GetGems объединённый парсер с нотификацией"
    )
    parser.add_argument(
        "--profile", choices=["dev", "prod"], default="dev",
        help="Профиль конфигурации"
    )
    parser.add_argument(
        "--mode", choices=["single", "continuous"], default="continuous",
        help="Режим работы"
    )
    parser.add_argument(
        "--cycles", type=int, default=None,
        help="Количество циклов"
    )
    args = parser.parse_args()
    print(f"Аргументы: profile={args.profile}, mode={args.mode}, cycles={args.cycles}")

    try:
        cfg = load_config(args.profile)
        print(f"Конфигурация загружена для профиля '{args.profile}'")
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
        traceback.print_exc()
        sys.exit(1)

    if args.cycles is not None:
        cfg["max_cycles"] = args.cycles
        print(f"Установлено max_cycles={cfg['max_cycles']}")

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
        print(f"Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
