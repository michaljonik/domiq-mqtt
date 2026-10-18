"""DOMIQ Base integration protocol: plain text over TCP, one `CHANNEL=VALUE` per line.

- Base -> client: every change of any channel, as `CHANNEL=VALUE`.
- client -> Base: `CHANNEL=VALUE` sets a channel, `CHANNEL=?` asks for one value,
  a lone `?` asks for the whole state (Base answers with the non-zero channels).
"""

QUERY_ALL = b"?\r\n"


class ProtocolError(ValueError):
    pass


def parse_line(raw: bytes) -> tuple[str, str] | None:
    """`b"LCN.output.0.2.1=30\\r\\n"` -> `("LCN.output.0.2.1", "30")`; None for anything else."""
    line = raw.decode("utf-8", errors="replace").strip()
    channel, sep, value = line.partition("=")
    channel = channel.strip()
    if not sep or not channel:
        return None
    return channel, value.strip()


def encode_set(channel: str, value: str) -> bytes:
    _check(channel, "channel")
    _check(value, "value")
    if "=" in channel:
        raise ProtocolError(f"'=' in channel name: {channel!r}")
    return f"{channel}={value}\r\n".encode()


def encode_get(channel: str) -> bytes:
    return encode_set(channel, "?")


def _check(text: str, what: str) -> None:
    # One MQTT message must never turn into two commands on the Base.
    if not text or "\r" in text or "\n" in text:
        raise ProtocolError(f"empty or multi-line {what}: {text!r}")
