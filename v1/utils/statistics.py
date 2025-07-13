import time
from datetime import datetime
from typing import Dict, Any
import threading

class Statistics:
    def __init__(self):
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.reset_stats()

    def reset_stats(self):
        with self.lock:
            self.cycles_completed = 0
            self.total_offers_processed = 0
            self.total_errors = 0
            self.last_cycle_time = None
            self.last_stats_time = time.time()

    def increment_cycle(self):
        with self.lock:
            self.cycles_completed += 1
            self.last_cycle_time = time.time()

    def add_offers(self, count: int):
        with self.lock:
            self.total_offers_processed += count

    def add_error(self):
        with self.lock:
            self.total_errors += 1

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            current_time = time.time()
            uptime = current_time - self.start_time

            return {
                "uptime_seconds": uptime,
                "uptime_formatted": self._format_time(uptime),
                "cycles_completed": self.cycles_completed,
                "total_offers_processed": self.total_offers_processed,
                "total_errors": self.total_errors,
                "avg_cycle_time": uptime / self.cycles_completed if self.cycles_completed > 0 else 0,
                "last_cycle_time": datetime.fromtimestamp(self.last_cycle_time).strftime("%Y-%m-%d %H:%M:%S") if self.last_cycle_time else "N/A"
            }

    def _format_time(self, seconds: float) -> str:
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def should_print_stats(self, interval: int) -> bool:
        current_time = time.time()
        if current_time - self.last_stats_time >= interval:
            self.last_stats_time = current_time
            return True
        return False
