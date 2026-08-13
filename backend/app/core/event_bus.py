import asyncio
from typing import Callable, Dict, List, Any, Awaitable
import logging

logger = logging.getLogger(__name__)

class EventBus:
    """
    Lightweight in-process asynchronous Event Bus.
    Avoids heavy message brokers for minimum latency.
    Uses dedicated consumer tasks per subscriber to avoid
    per-tick task creation overhead.
    """
    def __init__(self):
        # We store bounded queues for each subscriber
        self._subscriber_queues: Dict[str, List[asyncio.Queue]] = {}
        # Keep track of the worker tasks so they can be cancelled if needed
        self._workers: List[asyncio.Task] = []
        # Store pending subscriptions until the loop starts
        self._pending_subscriptions = []
        self._started = False

    def subscribe(self, topic: str, callback: Callable[[Any], Awaitable[None]]):
        """
        Subscribe an async callback to a specific topic.
        """
        if not self._started:
            self._pending_subscriptions.append((topic, callback))
            return

        self._create_subscription(topic, callback)

    def _create_subscription(self, topic: str, callback: Callable[[Any], Awaitable[None]]):
        if topic not in self._subscriber_queues:
            self._subscriber_queues[topic] = []

        q = asyncio.Queue(maxsize=1000)
        self._subscriber_queues[topic].append(q)
        worker_task = asyncio.create_task(self._consume(q, callback, topic))
        self._workers.append(worker_task)
        logger.info(f"Subscribed to topic: {topic}")

    def start(self):
        """Start the event bus and process pending subscriptions."""
        self._started = True
        for topic, callback in self._pending_subscriptions:
            self._create_subscription(topic, callback)
        self._pending_subscriptions.clear()

    def publish(self, topic: str, event: Any):
        if topic in self._subscriber_queues:
            for q in self._subscriber_queues[topic]:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"Queue full for topic {topic}, dropping event.")

    async def _consume(self, queue: asyncio.Queue, callback: Callable[[Any], Awaitable[None]], topic: str):
        while True:
            try:
                event = await queue.get()
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(f"Error in subscriber for topic {topic}: {e}", exc_info=True)
                finally:
                    queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer error for topic {topic}: {e}")

event_bus = EventBus()
