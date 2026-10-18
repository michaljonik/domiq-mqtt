import asyncio

from fake_domiq import FakeBase

from domiq_mqtt.domiq import ANSWER_GAP, DomiqClient


async def until(predicate, timeout=2.0):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def start(base, **kw):
    lines, states = [], []

    async def on_line(c, v):
        lines.append((c, v))

    async def on_conn(up):
        states.append(up)

    client = DomiqClient("127.0.0.1", base.port, on_line, on_conn, **kw)
    task = asyncio.create_task(client.run())
    return client, task, lines, states


async def test_asks_for_state_and_reads_split_lines():
    async with FakeBase() as base:
        client, task, lines, states = await start(base)
        assert await base.next() == b"?\r\n"
        await until(lambda: lines == [("LCN.output.0.2.1", "30")])
        # one line split across TCP segments, two lines in one segment, an empty line
        await base.send(b"LCN.relay.0.")
        await asyncio.sleep(0.05)
        await base.send(b"2.4=on\r\n\r\nIDS.zone.2=armed\r\n")
        await until(lambda: len(lines) == 3)
        assert lines[1:] == [("LCN.relay.0.2.4", "on"), ("IDS.zone.2", "armed")]
        assert states == [True]
        task.cancel()


async def test_reconnects_after_close():
    async with FakeBase() as base:
        client, task, lines, states = await start(base, backoff_max=0.1)
        await base.next()
        base.clients[-1].close()
        await until(lambda: base.connections == 2)
        assert await base.next() == b"?\r\n"
        await until(lambda: client.connected)
        assert states[:2] == [True, False]
        task.cancel()


async def test_silent_base_gets_probed_then_dropped():
    async with FakeBase() as base:
        client, task, lines, states = await start(base, idle_timeout=0.2, backoff_max=0.1)
        await base.next()  # initial '?', answered
        base.answer_queries = False
        assert await base.next() == b"?\r\n"  # probe after idle_timeout
        await until(lambda: base.connections == 2)  # no answer: reconnected
        task.cancel()


async def test_answer_to_query_ends_after_a_quiet_gap():
    async with FakeBase() as base:
        client, task, lines, states = await start(base)
        await base.next()
        await until(lambda: len(lines) == 1)
        assert client.answering  # still inside the answer to the initial '?'
        await asyncio.sleep(ANSWER_GAP * 1.5)
        await base.send(b"LCN.keypress.0.20.A1=hit\r\n")
        await until(lambda: len(lines) == 2)
        assert not client.answering  # a line after the gap is a real change
        task.cancel()
