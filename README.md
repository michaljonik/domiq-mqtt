# domiq-mqtt

[![Test, Build & Push Docker Image](https://github.com/michaljonik/domiq-mqtt/actions/workflows/docker-image.yml/badge.svg)](https://github.com/michaljonik/domiq-mqtt/actions/workflows/docker-image.yml)
[![CVE scan](https://github.com/michaljonik/domiq-mqtt/actions/workflows/cve-scan.yml/badge.svg)](https://github.com/michaljonik/domiq-mqtt/actions/workflows/cve-scan.yml)
[![Release](https://img.shields.io/github/v/release/michaljonik/domiq-mqtt)](https://github.com/michaljonik/domiq-mqtt/releases/latest)
[![Renovate](https://img.shields.io/badge/renovate-enabled-brightgreen?logo=renovate)](https://github.com/michaljonik/domiq-mqtt/issues?q=is%3Aissue+Renovate)
[![License](https://img.shields.io/github/license/michaljonik/domiq-mqtt)](LICENSE)
[![Image](https://img.shields.io/badge/ghcr.io-michaljonik%2Fdomiq--mqtt-blue?logo=docker)](https://github.com/michaljonik/domiq-mqtt/pkgs/container/domiq-mqtt)

A bridge between a [DOMIQ Base](https://domiq.eu) controller and an MQTT broker. Every channel
the Base knows about (LCN outputs, relays and keypads, alarm zones, variables) becomes an MQTT
topic, and messages published to `…/set` topics go back to the Base as commands. Home
Assistant, Node-RED or anything else that speaks MQTT can then use the installation without
knowing about the Base.

```sh
docker pull ghcr.io/michaljonik/domiq-mqtt:0.1.0
```

It uses the Base's [TCP integration port](https://domiq.eu/wiki/domiq-modules/integration-with-domiq-base/)
(4224): plain text, one `CHANNEL=VALUE` per line, in both directions.

## Topics

Dots in a channel name become slashes under a prefix (`domiq` by default):

| Topic | Direction | Payload |
|---|---|---|
| `domiq/LCN/output/0/2/1` | bridge → broker | current value, retained |
| `domiq/LCN/keypress/0/20/A1` | bridge → broker | `hit`, `make`, …, not retained |
| `domiq/LCN/output/0/2/1/set` | broker → Base | the value to set, e.g. `30` or `on` |
| `domiq/LCN/output/0/2/1/get` | broker → Base | ignored; the Base answers on the state topic |
| `domiq/refresh` | broker → Base | ignored; the Base sends the whole state again |
| `domiq/status` | bridge → broker | `online` / `offline`, retained (also the MQTT last will) |

`/set` payloads are passed through as they are, so anything the Base accepts works
(`LCN.output.0.2.1=30` is `30` on `domiq/LCN/output/0/2/1/set`).

## Behaviour

- State is retained, events are not. A subscriber that connects later gets the current
  state of every output, but not the last button press: replaying a keypress would run its
  automation again. Channels starting with `LCN.keypress.` are treated as events; change the
  list with `EVENT_CHANNELS`.
- Retained commands are ignored. A retained message on a `/set` topic would be executed
  again on every reconnect, so the bridge logs a warning and skips it. Clear it with an empty
  retained message (`mosquitto_pub -t <topic> -n -r`).
- After connecting, the bridge asks the Base for its whole state (`?`). It
  asks again after reconnecting to the broker, so nothing changed in the meantime is lost.
  Keypresses that come back as part of that answer are dropped as replays.
- TCP keepalive is on, and a link that stays silent for
  `IDLE_TIMEOUT` seconds is probed with `?`. Without an answer it is closed and reopened, with
  exponential backoff. This covers a Base that restarted without closing the old socket.
- A payload containing a line break is rejected, so a single MQTT message can never send two
  commands to the Base.

## Configuration

Environment variables only:

| Variable | Default | |
|---|---|---|
| `DOMIQ_HOST` | (required) | address of the DOMIQ Base |
| `DOMIQ_PORT` | `4224` | |
| `MQTT_HOST` | `localhost` | |
| `MQTT_PORT` | `1883` | |
| `MQTT_USERNAME` | | |
| `MQTT_PASSWORD` | | or `MQTT_PASSWORD_FILE` with a path, for Docker secrets |
| `MQTT_CLIENT_ID` | `domiq-mqtt` | |
| `MQTT_PREFIX` | `domiq` | |
| `EVENT_CHANNELS` | `LCN.keypress.` | comma-separated channel prefixes published without retain |
| `IDLE_TIMEOUT` | `60` | seconds of silence before the Base is probed |
| `HEALTH_FILE` | `/tmp/domiq-mqtt.healthy` | `-` turns it off |
| `LOG_LEVEL` | `INFO` | `DEBUG` logs every command sent to the Base |

The password is never logged.

## Usage

```yaml
services:
  domiq-mqtt:
    image: ghcr.io/michaljonik/domiq-mqtt:0.1.0
    restart: unless-stopped
    environment:
      DOMIQ_HOST: 192.0.2.10
      MQTT_HOST: mosquitto
      MQTT_USERNAME: domiq
      MQTT_PASSWORD_FILE: /run/secrets/mqtt_password
    secrets:
      - mqtt_password
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
```

A complete example with Mosquitto is in [compose.example.yml](compose.example.yml). The image
runs as `nobody` and reports `healthy` only while it is connected to both the Base and the
broker.

The integration port has no encryption or authentication. Keep the Base on a trusted network
and never forward port 4224 to the internet.

## Home Assistant

The bridge publishes plain topics, so Home Assistant entities are defined with
[MQTT](https://www.home-assistant.io/integrations/mqtt/) configuration, for example:

```yaml
mqtt:
  light:
    - name: Kitchen
      state_topic: domiq/LCN/output/0/2/1
      command_topic: domiq/LCN/output/0/2/1/set
      brightness_state_topic: domiq/LCN/output/0/2/1
      brightness_command_topic: domiq/LCN/output/0/2/1/set
      brightness_scale: 100
      on_command_type: brightness
      state_value_template: "{{ 'ON' if value | int(0) > 0 else 'OFF' }}"
      payload_off: "0"
      availability_topic: domiq/status
```

Keypads are easiest to handle with an automation triggered on `domiq/LCN/keypress/#`.

## Tags

| Tag | Meaning |
|---|---|
| `0.1.0` | one release, never moves: use this one in compose files |
| `0.1` | the latest release of 0.1 |
| `latest` | the most recent release |

Images are built for `linux/amd64` and `linux/arm64`.

## Development

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

The tests need no hardware: a small fake Base (a TCP server on a random port) stands in for
the controller.

- **Pinned inputs.** Python and uv versions are fixed in the [Dockerfile](Dockerfile),
  dependencies in `uv.lock`, GitHub Actions by digest; Renovate proposes updates.
- **Scanned image.** A daily [CVE scan](.github/workflows/cve-scan.yml) (Grype) checks the
  published image and reports to Security → Code scanning.
- **No emulated builds.** All dependencies are pure Python, so the virtualenv is built once on
  the runner and copied into the `amd64` and `arm64` images.
- **Releases are tags.** `v0.1.0` runs the tests and publishes the image with an SBOM and a
  provenance attestation ([workflow](.github/workflows/docker-image.yml)). A tag that doesn't
  match the version in `pyproject.toml` is rejected.

## License

[MIT](LICENSE). DOMIQ is a trademark of its owner; this project is not affiliated with it.
