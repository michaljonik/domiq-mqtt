"""Channel <-> topic mapping: dots become slashes under a prefix.

LCN.output.0.2.1        <-> domiq/LCN/output/0/2/1        (state, published by the bridge)
                            domiq/LCN/output/0/2/1/set    (command: payload is the value)
                            domiq/LCN/output/0/2/1/get    (command: ask the Base for the value)
                            domiq/refresh                 (command: ask for the whole state)
                            domiq/status                  (online / offline, retained)
"""

from dataclasses import dataclass

SET = "set"
GET = "get"
REFRESH = "refresh"
STATUS = "status"

_FORBIDDEN = set("+#/") | {"\0"}


@dataclass(frozen=True)
class Command:
    action: str  # SET, GET or REFRESH
    channel: str | None = None


def channel_to_topic(prefix: str, channel: str) -> str | None:
    """None when the channel can't be a topic (empty segment or MQTT wildcard in it)."""
    parts = channel.split(".")
    if any(not p or _FORBIDDEN & set(p) for p in parts):
        return None
    return "/".join([prefix, *parts])


def parse_command(prefix: str, topic: str) -> Command | None:
    """Command for a topic under the prefix; None for state topics and anything else."""
    if not topic.startswith(prefix + "/"):
        return None
    parts = topic[len(prefix) + 1 :].split("/")
    if parts == [REFRESH]:
        return Command(REFRESH)
    if len(parts) < 2 or parts[-1] not in (SET, GET) or not all(parts[:-1]):
        return None
    return Command(parts[-1], ".".join(parts[:-1]))
