from dataclasses import dataclass, field

import pytest

from domiq_mqtt.bridge import Bridge
from domiq_mqtt.config import from_env
from domiq_mqtt.domiq import NotConnected


@dataclass
class FakeDomiq:
    connected: bool = True
    sent: list[bytes] = field(default_factory=list)
    answering: bool = False

    async def send(self, data):
        if not self.connected:
            raise NotConnected
        self.sent.append(data)


class FakeMqtt:
    def __init__(self):
        self.published = []

    async def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))


@pytest.fixture
def bridge():
    b = Bridge(from_env({"DOMIQ_HOST": "x", "HEALTH_FILE": "-"}), domiq=FakeDomiq())
    b.mqtt = FakeMqtt()
    return b


async def test_state_is_retained(bridge):
    await bridge.on_domiq_line("LCN.output.0.2.1", "30")
    assert bridge.mqtt.published == [("domiq/LCN/output/0/2/1", "30", True)]


async def test_keypress_is_not_retained(bridge):
    await bridge.on_domiq_line("LCN.keypress.0.20.A1", "hit")
    assert bridge.mqtt.published == [("domiq/LCN/keypress/0/20/A1", "hit", False)]


async def test_keypress_in_answer_to_query_is_dropped(bridge):
    bridge.domiq.answering = True
    await bridge.on_domiq_line("LCN.keypress.0.20.A1", "hit")
    await bridge.on_domiq_line("LCN.output.0.2.1", "30")
    assert bridge.mqtt.published == [("domiq/LCN/output/0/2/1", "30", True)]
    bridge.domiq.answering = False
    await bridge.on_domiq_line("LCN.keypress.0.20.A1", "hit")
    assert len(bridge.mqtt.published) == 2


async def test_commands(bridge):
    await bridge.on_mqtt_message("domiq/LCN/output/0/2/1/set", b"30", retain=False)
    await bridge.on_mqtt_message("domiq/LCN/relay/0/2/4/get", b"", retain=False)
    await bridge.on_mqtt_message("domiq/refresh", b"", retain=False)
    await bridge.on_mqtt_message("domiq/LCN/output/0/2/1", b"30", retain=False)  # state: ignored
    assert bridge.domiq.sent == [b"LCN.output.0.2.1=30\r\n", b"LCN.relay.0.2.4=?\r\n", b"?\r\n"]


async def test_retained_and_malformed_commands_are_ignored(bridge):
    await bridge.on_mqtt_message("domiq/LCN/relay/0/2/4/set", b"on", retain=True)
    await bridge.on_mqtt_message(
        "domiq/LCN/relay/0/2/4/set", b"on\nLCN.relay.0.2.5=on", retain=False
    )
    await bridge.on_mqtt_message("domiq/LCN/relay/0/2/4/set", b"\xff", retain=False)
    assert bridge.domiq.sent == []


async def test_command_while_base_is_down(bridge):
    bridge.domiq.connected = False
    await bridge.on_mqtt_message("domiq/LCN/relay/0/2/4/set", b"on", retain=False)
    await bridge.on_domiq_connection(False)
    assert bridge.mqtt.published == [("domiq/status", "offline", True)]


async def test_nothing_published_without_broker(bridge):
    bridge.mqtt = None
    await bridge.on_domiq_line("LCN.output.0.2.1", "30")  # no error
