#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import signal
import random
import time
from datetime import datetime

from utils.logging_cfg import setup_logger
from utils.statistics import Statistics
from storage.db import get_connection
from core.stream_parser import run_stream_parser

class AsyncStreamParser:
    def __init__(self, cfg):
        self.cfg = cfg
        self.logger = setup_logger("async_stream_parser", cfg["log_level"])
        self.statistics = Statistics()
        self.running = True
        self.cycle_count = 0
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        self.logger.info(f"Signal {sig} received, shutting down")
        self.running = False

    def _calculate_cycle_delay(self) -> float:
        base = self.cfg["cycle_interval"]
        rnd = self.cfg.get("cycle_randomization", 0.5)
        delay = base + random.uniform(0, base * rnd)
        self.logger.debug(f"Cycle delay: {delay:.2f}s")
        return delay

    async def run_single_cycle(self) -> bool:
        start = time.time()
        self.logger.info(f"Cycle #{self.cycle_count+1} start")
        conn = get_connection()
        try:
            count = run_stream_parser(self.cfg, conn)
            # Сначала фиксируем успешный цикл
            self.statistics.increment_cycle()
            self.statistics.add_offers(count)
            self.logger.info(f"Cycle #{self.cycle_count} processed {count} offers")
        except Exception as e:
            self.logger.error(f"Parser error: {e}")
            self.statistics.add_error()
            return False
        finally:
            conn.close()

        elapsed = time.time() - start
        self.logger.info(f"Cycle #{self.cycle_count} done in {elapsed:.2f}s")
        return True

    async def print_stats(self):
        if not self.cfg.get("enable_statistics", True):
            return
        stats = self.statistics.get_stats()
        self.logger.info("=== STATISTICS ===")
        self.logger.info(f"Uptime: {stats['uptime_formatted']}")
        self.logger.info(f"Cycles: {stats['cycles_completed']}")
        self.logger.info(f"Offers: {stats['total_offers_processed']}")
        self.logger.info(f"Errors: {stats['total_errors']}")
        self.logger.info(f"Avg cycle time: {stats['avg_cycle_time']:.2f}s")
        self.logger.info(f"Last cycle at: {stats['last_cycle_time']}")
        self.logger.info("==================")

    async def run(self):
        self.logger.info("Starting async parser")
        self.logger.info(f"Interval: {self.cfg['cycle_interval']}s ±{int(self.cfg.get('cycle_randomization',0.5)*100)}%")
        self.logger.info(f"Max cycles: {self.cfg['max_cycles'] or 'infinite'}")

        while self.running:
            # Проверка лимита циклов
            if self.cfg["max_cycles"] and self.cycle_count >= self.cfg["max_cycles"]:
                self.logger.info("Max cycles reached")
                break

            success = await self.run_single_cycle()

            if success and self.statistics.should_print_stats(self.cfg["stats_interval"]):
                await self.print_stats()

            if not self.running:
                break

            await asyncio.sleep(self._calculate_cycle_delay())
