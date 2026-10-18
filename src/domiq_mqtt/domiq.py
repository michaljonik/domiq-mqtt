"""TCP client for the DOMIQ Base: one connection, reconnect with backoff, dead-link detection."""

import asyncio
import logging
import random
import socket
from collections.abc import Awaitable, Callable

from .protocol import QUERY_ALL, parse_line

log = logging.getLogger(__name__)

OnLine = Callable[[str, str], Awaitable[None]]
OnConnection = Callable[[bool], Awaitable[None]]

# The Base answers `?` with one burst of lines. The answer is over once the stream has been
# quiet for this long.
ANSWER_GAP = 0.3


class NotConnected(ConnectionError):
    pass


class DomiqClient:
    """Keeps one connection to the Base open and hands every `CHANNEL=VALUE` line to `on_line`.

    A connection that stays silent for `idle_timeout` seconds gets a `?`; if that brings no
    answer within the same time, the link is considered dead and reopened. This catches a Base
    that restarted without closing the socket, which TCP alone notices only after hours.
    """

    def __init__(
        self,
        host: str,
        port: int,
        on_line: OnLine,
        on_connection: OnConnection,
        idle_timeout: float = 60.0,
        backoff_max: float = 60.0,
    ):
        self.host = host
        self.port = port
        self._on_line = on_line
        self._on_connection = on_connection
        self._idle_timeout = idle_timeout
        self._backoff_max = backoff_max
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        # Lines from the Base never say whether they answer a `?` or report a real change.
        # True while an answer to `?` is still arriving: the bridge uses it to tell a replayed
        # keypress from a fresh one.
        self.answering = False
        self._last_activity = 0.0

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def send(self, data: bytes) -> None:
        if self._writer is None:
            raise NotConnected("not connected to DOMIQ Base")
        async with self._write_lock:
            if data == QUERY_ALL:
                self.answering = True
                self._last_activity = asyncio.get_running_loop().time()
            self._writer.write(data)
            await self._writer.drain()

    async def run(self) -> None:
        attempt = 0
        while True:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=10
                )
            except (OSError, TimeoutError) as e:
                attempt += 1
                delay = self._delay(attempt)
                log.warning(
                    "DOMIQ Base %s:%s unreachable (%s), retry in %.0fs",
                    self.host,
                    self.port,
                    e or type(e).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            _enable_keepalive(writer)
            self._writer = writer
            log.info("connected to DOMIQ Base %s:%s", self.host, self.port)
            attempt = 0
            try:
                await self._on_connection(True)
                await self.send(QUERY_ALL)  # initial state
                await self._read(reader)
            except (OSError, ConnectionError, TimeoutError) as e:
                log.warning("DOMIQ Base connection lost: %s", e or type(e).__name__)
            finally:
                self._writer = None
                writer.close()
                await self._on_connection(False)
            attempt += 1
            await asyncio.sleep(self._delay(attempt))

    async def _read(self, reader: asyncio.StreamReader) -> None:
        probed = False
        while True:
            try:
                raw = await asyncio.wait_for(reader.readline(), self._idle_timeout)
            except TimeoutError:
                if probed:
                    raise TimeoutError(
                        f"no answer to '?' within {self._idle_timeout:.0f}s"
                    ) from None
                log.debug("idle for %.0fs, probing with '?'", self._idle_timeout)
                await self.send(QUERY_ALL)
                probed = True
                continue
            if not raw:
                raise ConnectionError("closed by DOMIQ Base")
            probed = False
            now = asyncio.get_running_loop().time()
            if self.answering and now - self._last_activity > ANSWER_GAP:
                self.answering = False
            self._last_activity = now
            if parsed := parse_line(raw):
                await self._on_line(*parsed)
            elif raw.strip():
                log.debug("ignored line: %r", raw)

    def _delay(self, attempt: int) -> float:
        base = min(self._backoff_max, 2 ** min(attempt - 1, 10))
        return base * random.uniform(0.8, 1.2)


def _enable_keepalive(writer: asyncio.StreamWriter) -> None:
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # Linux names; macOS has only TCP_KEEPALIVE (idle). Missing ones keep the OS defaults.
    for name, value in (("TCP_KEEPIDLE", 30), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 3)):
        if hasattr(socket, name):
            sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), value)
