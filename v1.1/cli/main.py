#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cli/main.py

Точка входа для асинхронного парсера GetGems (core/async_stream_parser.py)
с единым asyncio-циклом и плавным завершением по Ctrl+C.
"""

import argparse
import asyncio
import signal
import sys
import traceback
import contextlib

from utils.config import load_config
from core.async_stream_parser import AsyncStreamParser

def _handle_exit(signame: str, loop: asyncio.AbstractEventLoop):
    """Грейсфул-шатдаун при сигнале."""
    print(f"Получен сигнал {signame}, завершаем работу…", file=sys.stderr)
    for task in asyncio.all_tasks(loop):
        task.cancel()

async def main_async(cfg: dict):
    # Инициализация парсера
    parser = AsyncStreamParser(cfg)
    # Запуск основного цикла
    await parser.run()

def main():
    print("=== Запуск CLI ===")
    p = argparse.ArgumentParser(
        description="GetGems асинхронный парсер с нотификацией"
    )
    p.add_argument(
        "--profile", choices=["dev", "prod"], default="dev",
        help="Конфигурационный профиль"
    )
    args = p.parse_args()

    try:
        cfg = load_config(args.profile)
        print(f"Конфигурация загружена для профиля '{args.profile}'")
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    loop = asyncio.get_event_loop()

    # Кроссплатформенная регистрация Ctrl+C и SIGTERM
    signal.signal(signal.SIGINT, lambda sig, frame: _handle_exit("SIGINT", loop))
    try:
        signal.signal(signal.SIGTERM, lambda sig, frame: _handle_exit("SIGTERM", loop))
    except AttributeError:
        # На Windows SIGTERM может отсутствовать
        pass

    try:
        loop.run_until_complete(main_async(cfg))
    except asyncio.CancelledError:
        # Graceful shutdown via CancelledError
        pass
    except Exception as e:
        print(f"Критическая ошибка: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Завершение всех асинхронных генераторов
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        print("Парсер завершён.")

if __name__ == "__main__":
    main()
