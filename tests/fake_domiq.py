"""Stand-in for the DOMIQ Base: a TCP server that records what it gets, sends what it's told."""

import asyncio


class FakeBase:
    def __init__(self):
        self.received: asyncio.Queue[bytes] = asyncio.Queue()
        self.clients: list[asyncio.StreamWriter] = []
        self.connections = 0
        self.answer_queries = True
        self.state = b"LCN.output.0.2.1=30\r\n"

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        for w in self.clients:
            w.close()
        self.server.close()

    async def _handle(self, reader, writer):
        self.connections += 1
        self.clients.append(writer)
        while line := await reader.readline():
            await self.received.put(line)
            if line == b"?\r\n" and self.answer_queries:
                writer.write(self.state)
                await writer.drain()

    async def send(self, data: bytes):
        w = self.clients[-1]
        w.write(data)
        await w.drain()

    async def next(self, timeout=2.0) -> bytes:
        return await asyncio.wait_for(self.received.get(), timeout)
