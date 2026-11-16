"""Bounded per-symbol signal pipeline for observational analysis only.

The pipeline never places broker orders. It isolates symbol workloads, preserves
FIFO ordering per symbol, and exposes backlog/failure state for health checks.
"""
import queue
import threading
import time
from collections import defaultdict


class SymbolPipeline:
    def __init__(self, handler, max_queue_per_symbol=100):
        self.handler = handler
        self.max_queue_per_symbol = max_queue_per_symbol
        self._lock = threading.RLock()
        self._queues = {}
        self._workers = {}
        self._failures = defaultdict(int)
        self._completed = defaultdict(int)
        self._dropped = defaultdict(int)

    def enqueue(self, symbol, payload):
        with self._lock:
            q = self._queues.get(symbol)
            if q is None:
                q = queue.Queue(maxsize=self.max_queue_per_symbol)
                self._queues[symbol] = q
                worker = threading.Thread(target=self._worker, args=(symbol, q), daemon=True,
                                          name="bigben-symbol-" + symbol.replace(":", "_"))
                self._workers[symbol] = worker
                worker.start()
            try:
                q.put_nowait(payload)
            except queue.Full:
                self._dropped[symbol] += 1
                return False
            return True

    def _worker(self, symbol, q):
        while True:
            payload = q.get()
            try:
                self.handler(symbol, payload)
                with self._lock:
                    self._completed[symbol] += 1
            except Exception:
                with self._lock:
                    self._failures[symbol] += 1
            finally:
                q.task_done()

    def snapshot(self):
        with self._lock:
            return {
                "symbols": len(self._queues),
                "queued": sum(q.qsize() for q in self._queues.values()),
                "per_symbol": {
                    symbol: {
                        "queued": q.qsize(),
                        "completed": self._completed[symbol],
                        "failures": self._failures[symbol],
                        "dropped": self._dropped[symbol],
                    }
                    for symbol, q in self._queues.items()
                },
            }
