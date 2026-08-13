import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


Callback = Callable[[Any], Any]


class EventBus:
    """
    Lightweight in-process asynchronous Event Bus.

    Features:
    - bounded per-subscriber queues
    - dedicated consumer task per subscriber
    - non-blocking event publication
    - supports synchronous and asynchronous callbacks
    - explicit start/stop lifecycle
    - subscriptions can be registered before startup
    - subscriber failures do not stop the event bus
    """

    def __init__(self):
        self._subscriber_queues: Dict[
            str, List[asyncio.Queue]
        ] = {}

        self._workers: List[asyncio.Task] = []

        self._pending_subscriptions: List[
            Tuple[str, Callback]
        ] = []

        self._started = False

    # =========================================================
    # SUBSCRIPTION
    # =========================================================

    def subscribe(
        self,
        event_type: str,
        callback: Callback,
    ) -> None:
        """
        Subscribe a callback to an event type.

        Subscriptions made before the event bus starts are
        stored and activated during start().
        """

        if not self._started:
            self._pending_subscriptions.append(
                (event_type, callback)
            )
            return

        self._create_subscription(
            event_type,
            callback,
        )

    def _create_subscription(
        self,
        event_type: str,
        callback: Callback,
    ) -> None:

        if event_type not in self._subscriber_queues:
            self._subscriber_queues[event_type] = []

        queue: asyncio.Queue = asyncio.Queue(
            maxsize=1000
        )

        self._subscriber_queues[event_type].append(
            queue
        )

        worker = asyncio.create_task(
            self._consume(
                queue,
                callback,
                event_type,
            )
        )

        self._workers.append(worker)

        logger.info(
            "Subscribed to event: %s",
            event_type,
        )

    # =========================================================
    # START / STOP
    # =========================================================

    def start(self) -> None:
        """
        Start the Event Bus and activate pending
        subscriptions.
        """

        if self._started:
            return

        self._started = True

        pending = list(
            self._pending_subscriptions
        )

        self._pending_subscriptions.clear()

        for event_type, callback in pending:
            self._create_subscription(
                event_type,
                callback,
            )

        logger.info("Event Bus started.")

    async def stop(self) -> None:
        """
        Stop all subscriber workers cleanly.
        """

        if not self._started:
            return

        self._started = False

        for worker in self._workers:
            worker.cancel()

        if self._workers:
            await asyncio.gather(
                *self._workers,
                return_exceptions=True,
            )

        self._workers.clear()
        self._subscriber_queues.clear()

        logger.info("Event Bus stopped.")

    # =========================================================
    # PUBLISH
    # =========================================================

    async def publish(
        self,
        event_type: str,
        data: Any,
    ) -> None:
        """
        Publish an event without waiting for subscribers
        to finish processing it.

        Events are placed into bounded subscriber queues.

        This preserves compatibility with existing code
        using:

            await event_bus.publish(...)
        """

        if not self._started:
            logger.debug(
                "Event Bus is not started; "
                "dropping event: %s",
                event_type,
            )
            return

        queues = self._subscriber_queues.get(
            event_type,
            [],
        )

        for queue in queues:
            try:
                queue.put_nowait(data)

            except asyncio.QueueFull:
                logger.warning(
                    "Queue full for event %s; "
                    "dropping event.",
                    event_type,
                )

    # =========================================================
    # CONSUMER
    # =========================================================

    async def _consume(
        self,
        queue: asyncio.Queue,
        callback: Callback,
        event_type: str,
    ) -> None:

        while True:
            try:
                event = await queue.get()

                try:
                    result = callback(event)

                    if inspect.isawaitable(result):
                        await result

                except Exception:
                    logger.exception(
                        "Error in subscriber for "
                        "event %s",
                        event_type,
                    )

                finally:
                    queue.task_done()

            except asyncio.CancelledError:
                break

            except Exception:
                logger.exception(
                    "Consumer error for event %s",
                    event_type,
                )


event_bus = EventBus()