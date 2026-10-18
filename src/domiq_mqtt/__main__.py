import asyncio
import logging
import signal
import sys

from .bridge import Bridge
from .config import ConfigError, from_env

log = logging.getLogger("domiq_mqtt")


async def _run(bridge: Bridge) -> None:
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        await bridge.run()
    except asyncio.CancelledError:
        log.info("stopped")


def main() -> None:
    try:
        cfg = from_env()
    except ConfigError as e:
        print(f"domiq-mqtt: {e}", file=sys.stderr)
        sys.exit(2)

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log.info(
        "DOMIQ Base %s:%s <-> MQTT %s:%s, prefix %r, user %s",
        cfg.domiq_host,
        cfg.domiq_port,
        cfg.mqtt_host,
        cfg.mqtt_port,
        cfg.prefix,
        cfg.mqtt_username or "(none)",
    )
    asyncio.run(_run(Bridge(cfg)))


if __name__ == "__main__":
    main()
