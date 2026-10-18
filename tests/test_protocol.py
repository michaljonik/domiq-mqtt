import pytest

from domiq_mqtt.protocol import ProtocolError, encode_get, encode_set, parse_line


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"LCN.output.0.2.1=30\r\n", ("LCN.output.0.2.1", "30")),
        (b"LCN.relay.0.2.4=on\n", ("LCN.relay.0.2.4", "on")),
        (b"VAR.text=a=b\r\n", ("VAR.text", "a=b")),  # only the first '=' separates
        (b"LCN.output.0.2.1=\r\n", ("LCN.output.0.2.1", "")),
        (b" IDS.zone.2 = armed \r\n", ("IDS.zone.2", "armed")),
    ],
)
def test_parse_line(raw, expected):
    assert parse_line(raw) == expected


@pytest.mark.parametrize("raw", [b"", b"\r\n", b"garbage\r\n", b"=value\r\n", b"?\r\n"])
def test_parse_line_rejects(raw):
    assert parse_line(raw) is None


def test_encode():
    assert encode_set("LCN.output.0.2.1", "30") == b"LCN.output.0.2.1=30\r\n"
    assert encode_get("LCN.relay.0.2.4") == b"LCN.relay.0.2.4=?\r\n"


@pytest.mark.parametrize(
    ("channel", "value"),
    [
        ("LCN.relay.0.2.4", "on\r\nLCN.relay.0.2.5=on"),
        ("a\nb", "1"),
        ("", "1"),
        ("x", ""),
        ("a=b", "1"),
    ],
)
def test_encode_rejects_injection_and_empty(channel, value):
    with pytest.raises(ProtocolError):
        encode_set(channel, value)
