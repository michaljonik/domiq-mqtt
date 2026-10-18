"""Configuration from environment variables only."""

import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    domiq_host: str
    domiq_port: int = 4224
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = field(default=None, repr=False)
    mqtt_client_id: str = "domiq-mqtt"
    prefix: str = "domiq"
    event_channels: tuple[str, ...] = ("LCN.keypress.",)
    idle_timeout: float = 60.0
    health_file: Path | None = Path("/tmp/domiq-mqtt.healthy")
    log_level: str = "INFO"

    def is_event(self, channel: str) -> bool:
        return channel.startswith(self.event_channels)


def from_env(env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ if env is None else env)

    def get(name: str) -> str | None:
        value = env.get(name, "").strip()
        return value or None

    def number(name: str, default: float, cast=int):
        raw = get(name)
        if raw is None:
            return default
        try:
            value = cast(raw)
        except ValueError:
            raise ConfigError(f"{name} must be a number, got {raw!r}") from None
        if value <= 0:
            raise ConfigError(f"{name} must be positive, got {raw!r}")
        return value

    host = get("DOMIQ_HOST")
    if host is None:
        raise ConfigError("DOMIQ_HOST is required (address of the DOMIQ Base)")

    password = get("MQTT_PASSWORD")
    if password_file := get("MQTT_PASSWORD_FILE"):
        try:
            password = Path(password_file).read_text().strip()
        except OSError as e:
            raise ConfigError(f"MQTT_PASSWORD_FILE: {e}") from None

    prefix = (get("MQTT_PREFIX") or "domiq").strip("/")
    if not prefix or set("+#") & set(prefix):
        raise ConfigError(f"MQTT_PREFIX is not a valid topic prefix: {prefix!r}")

    events = get("EVENT_CHANNELS")
    event_channels = (
        tuple(p.strip() for p in events.split(",") if p.strip())
        if events is not None
        else Config.event_channels
    )

    health = get("HEALTH_FILE")
    return Config(
        domiq_host=host,
        domiq_port=number("DOMIQ_PORT", 4224),
        mqtt_host=get("MQTT_HOST") or "localhost",
        mqtt_port=number("MQTT_PORT", 1883),
        mqtt_username=get("MQTT_USERNAME"),
        mqtt_password=password,
        mqtt_client_id=get("MQTT_CLIENT_ID") or "domiq-mqtt",
        prefix=prefix,
        event_channels=event_channels,
        idle_timeout=number("IDLE_TIMEOUT", 60.0, float),
        health_file=None if health == "-" else Path(health) if health else Config.health_file,
        log_level=(get("LOG_LEVEL") or "INFO").upper(),
    )
