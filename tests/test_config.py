from pathlib import Path

import pytest

from domiq_mqtt.config import ConfigError, from_env


def test_defaults():
    cfg = from_env({"DOMIQ_HOST": "10.0.0.5"})
    assert (cfg.domiq_host, cfg.domiq_port, cfg.mqtt_host, cfg.mqtt_port) == (
        "10.0.0.5",
        4224,
        "localhost",
        1883,
    )
    assert cfg.prefix == "domiq"
    assert cfg.is_event("LCN.keypress.0.20.A1")
    assert not cfg.is_event("LCN.output.0.20.1")


def test_full(tmp_path: Path):
    secret = tmp_path / "pw"
    secret.write_text("s3cret\n")
    cfg = from_env(
        {
            "DOMIQ_HOST": "base",
            "DOMIQ_PORT": "4225",
            "MQTT_HOST": "broker",
            "MQTT_PORT": "8883",
            "MQTT_USERNAME": "u",
            "MQTT_PASSWORD_FILE": str(secret),
            "MQTT_PREFIX": "/home/domiq/",
            "EVENT_CHANNELS": "LCN.keypress., C.",
            "IDLE_TIMEOUT": "15",
            "HEALTH_FILE": "-",
            "LOG_LEVEL": "debug",
        }
    )
    assert cfg.mqtt_password == "s3cret"
    assert "s3cret" not in repr(cfg)
    assert cfg.prefix == "home/domiq"
    assert cfg.event_channels == ("LCN.keypress.", "C.")
    assert cfg.idle_timeout == 15.0
    assert cfg.health_file is None
    assert cfg.log_level == "DEBUG"


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"DOMIQ_HOST": " "},
        {"DOMIQ_HOST": "b", "DOMIQ_PORT": "x"},
        {"DOMIQ_HOST": "b", "MQTT_PORT": "0"},
        {"DOMIQ_HOST": "b", "MQTT_PREFIX": "a/#"},
        {"DOMIQ_HOST": "b", "MQTT_PASSWORD_FILE": "/nonexistent"},
    ],
)
def test_invalid(env):
    with pytest.raises(ConfigError):
        from_env(env)
