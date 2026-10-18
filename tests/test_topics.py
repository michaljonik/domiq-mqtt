import pytest

from domiq_mqtt.topics import GET, REFRESH, SET, Command, channel_to_topic, parse_command


def test_channel_to_topic():
    assert channel_to_topic("domiq", "LCN.keypress.0.20.A1") == "domiq/LCN/keypress/0/20/A1"


@pytest.mark.parametrize("channel", ["LCN..1", "LCN.out#", "a.b+", "a/b", ".x"])
def test_channel_to_topic_rejects(channel):
    assert channel_to_topic("domiq", channel) is None


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("domiq/LCN/output/0/2/1/set", Command(SET, "LCN.output.0.2.1")),
        ("domiq/LCN/relay/0/2/4/get", Command(GET, "LCN.relay.0.2.4")),
        ("domiq/refresh", Command(REFRESH)),
        ("domiq/LCN/output/0/2/1", None),  # state topic
        ("domiq/status", None),
        ("domiq/set", None),
        ("domiq//set", None),
        ("other/LCN/output/0/2/1/set", None),
        ("domiqx/LCN/set", None),
    ],
)
def test_parse_command(topic, expected):
    assert parse_command("domiq", topic) == expected
