"""The bridge: DOMIQ Base channels <-> MQTT topics."""

import asyncio
import contextlib
import logging
import random

import aiomqtt
from paho.mqtt.subscribeoptions import SubscribeOptions

from . import topics
from .config import Config
from .domiq import DomiqClient, NotConnected
from .protocol import QUERY_ALL, ProtocolError, encode_get, encode_set

log = logging.getLogger(__name__)


class Bridge:
    def __init__(self, cfg: Config, domiq: DomiqClient | None = None):
        self.cfg = cfg
        self.domiq = domiq or DomiqClient(
            cfg.domiq_host,
            cfg.domiq_port,
            on_line=self.on_domiq_line,
            on_connection=self.on_domiq_connection,
            idle_timeout=cfg.idle_timeout,
        )
        self.mqtt: aiomqtt.Client | None = None
        self.status_topic = f"{cfg.prefix}/{topics.STATUS}"

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.domiq.run())
            tg.create_task(self._mqtt_loop())

    # DOMIQ Base -> MQTT

    async def on_domiq_line(self, channel: str, value: str) -> None:
        event = self.cfg.is_event(channel)
        # An event inside the answer to `?` is the last keypress repeated as current state,
        # not a new press.
        if event and self.domiq.answering:
            log.debug("skipped replayed event %s=%s", channel, value)
            return
        topic = topics.channel_to_topic(self.cfg.prefix, channel)
        if topic is None:
            log.warning("channel %r can't be mapped to a topic, skipped", channel)
            return
        # State is retained so a subscriber gets it on connect; an event is not, because
        # replaying an old keypress to a new subscriber would run its action again.
        await self._publish(topic, value, retain=not event)

    async def on_domiq_connection(self, up: bool) -> None:
        await self._publish_status()
        self._update_health()

    # MQTT -> DOMIQ Base

    async def on_mqtt_message(self, topic: str, payload: bytes | str, retain: bool) -> None:
        cmd = topics.parse_command(self.cfg.prefix, topic)
        if cmd is None:
            return
        if retain:
            # A retained command would run again on every reconnect of the bridge.
            log.warning(
                "ignored retained command on %s (clear it with an empty retained message)", topic
            )
            return
        try:
            match cmd.action:
                case topics.REFRESH:
                    data = QUERY_ALL
                case topics.GET:
                    data = encode_get(cmd.channel)
                case _:
                    value = payload.decode() if isinstance(payload, bytes) else str(payload)
                    data = encode_set(cmd.channel, value.strip())
            await self.domiq.send(data)
            log.debug("sent %r", data)
        except (ProtocolError, UnicodeDecodeError) as e:
            log.warning("rejected command on %s: %s", topic, e)
        except NotConnected:
            log.warning("dropped command on %s: DOMIQ Base not connected", topic)

    # MQTT connection

    async def _mqtt_loop(self) -> None:
        attempt = 0
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.cfg.mqtt_host,
                    port=self.cfg.mqtt_port,
                    username=self.cfg.mqtt_username,
                    password=self.cfg.mqtt_password,
                    identifier=self.cfg.mqtt_client_id,
                    protocol=aiomqtt.ProtocolVersion.V5,
                    keepalive=30,
                    will=aiomqtt.Will(self.status_topic, "offline", qos=1, retain=True),
                ) as client:
                    log.info("connected to MQTT %s:%s", self.cfg.mqtt_host, self.cfg.mqtt_port)
                    attempt = 0
                    try:
                        await self._serve(client)
                    finally:
                        self.mqtt = None
                        self._update_health()
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(
                                client.publish(self.status_topic, "offline", qos=1, retain=True), 2
                            )
            except aiomqtt.MqttError as e:
                attempt += 1
                delay = min(60, 2 ** min(attempt - 1, 10)) * random.uniform(0.8, 1.2)
                log.warning(
                    "MQTT %s:%s: %s, retry in %.0fs",
                    self.cfg.mqtt_host,
                    self.cfg.mqtt_port,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _serve(self, client: aiomqtt.Client) -> None:
        # noLocal: the broker doesn't echo the bridge's own state messages back to it.
        await client.subscribe(
            f"{self.cfg.prefix}/#", options=SubscribeOptions(qos=1, noLocal=True)
        )
        self.mqtt = client
        await self._publish_status()
        self._update_health()
        if self.domiq.connected:
            # Changes that happened while the broker was away were not published.
            with contextlib.suppress(NotConnected):
                await self.domiq.send(QUERY_ALL)
        async for message in client.messages:
            await self.on_mqtt_message(message.topic.value, message.payload, message.retain)

    async def _publish(self, topic: str, payload: str, retain: bool) -> None:
        if self.mqtt is None:
            return  # sent again after reconnect: the bridge asks the Base for the full state
        try:
            await self.mqtt.publish(topic, payload, qos=1, retain=retain)
        except aiomqtt.MqttError as e:
            log.warning("publish to %s failed: %s", topic, e)

    async def _publish_status(self) -> None:
        await self._publish(
            self.status_topic, "online" if self.domiq.connected else "offline", retain=True
        )

    def _update_health(self) -> None:
        path = self.cfg.health_file
        if path is None:
            return
        try:
            if self.mqtt is not None and self.domiq.connected:
                path.touch()
            else:
                path.unlink(missing_ok=True)
        except OSError as e:
            log.warning("health file %s: %s", path, e)
