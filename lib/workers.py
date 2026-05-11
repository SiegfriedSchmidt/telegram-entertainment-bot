import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, Any

from lib.logger import main_logger


class Workers:
    def __init__(self, max_asyncio_workers: int = 3, max_thread_workers: int = 5):
        # Queue and workers for async functions
        self.async_queue = asyncio.Queue()
        self.async_workers = []
        self.async_worker_count = max_asyncio_workers

        # Thread pool for sync/heavy functions
        self.thread_executor = ThreadPoolExecutor(max_workers=max_thread_workers)

        self._started = False

    def start(self):
        """Start the asyncio worker tasks."""
        if self._started:
            return
        self.async_workers = [asyncio.create_task(self._async_worker(i)) for i in range(self.async_worker_count)]
        self._started = True

    async def _async_worker(self, worker_id: int):
        """Worker that only runs async functions (must be awaitable)."""
        while True:
            future, func, args, kwargs = await self.async_queue.get()
            try:
                result = await func(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                main_logger.error(f"Worker {worker_id} error: {e}")
                future.set_exception(e)
            finally:
                self.async_queue.task_done()

    async def enqueue(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Enqueue any function (async or sync). Returns the result (awaitable).
        For sync functions, execution is offloaded to a thread pool.
        """
        if asyncio.iscoroutinefunction(func):
            # Async function -> asyncio worker
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            await self.async_queue.put((future, func, args, kwargs))
            return await future
        else:
            # Sync function -> run in thread pool to avoid blocking the loop
            loop = asyncio.get_running_loop()
            # partial to pass args/kwargs correctly
            sync_func = partial(func, *args, **kwargs)
            return await loop.run_in_executor(self.thread_executor, sync_func)  # type: ignore

    def create_task(self, func: Callable[..., Any], *args, **kwargs) -> asyncio.Task:
        return asyncio.create_task(self.enqueue(func, *args, **kwargs))

    async def shutdown(self):
        """Clean shutdown: cancel asyncio workers and shutdown thread pool."""
        for w in self.async_workers:
            w.cancel()
        await asyncio.gather(*self.async_workers, return_exceptions=True)
        self.thread_executor.shutdown(wait=True)


async def main():
    workers.start()

    def heavy_sync_task(duration):
        print(f"  Heavy sync task started (duration {duration}s)")
        time.sleep(duration)  # This would block an asyncio task!
        print(f"  Heavy sync task finished")
        return duration * 10

    # Light async I/O task
    async def light_async_task(x):
        print('light task finished')
        await asyncio.sleep(0.5)
        return x * 2

    # Enqueue both types – none will block the main event loop
    future1 = workers.create_task(light_async_task, 10)
    future2 = workers.create_task(heavy_sync_task, 10)  # runs in thread
    future3 = workers.create_task(heavy_sync_task, 20)  # runs in another thread

    # Main loop can still do other work
    for i in range(5):
        print("Main loop is free! Tick", i)
        await asyncio.sleep(0.1)

    results = await asyncio.gather(future1, future2, future3)
    print("Results:", results)

    await workers.shutdown()


workers = Workers(max_asyncio_workers=4, max_thread_workers=4)

if __name__ == '__main__':
    asyncio.run(main())
