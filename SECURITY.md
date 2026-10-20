# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub:
[Security → Report a vulnerability](https://github.com/michaljonik/domiq-mqtt/security/advisories/new).
Do not open a public issue for them.

## Scope

In scope: the bridge code in `src/`, the `Dockerfile`, the build workflow and the published
image `ghcr.io/michaljonik/domiq-mqtt`. The DOMIQ Base integration port is plain text without
authentication by design; keep it on a trusted network. Bugs in DOMIQ, the MQTT broker or a
dependency belong to their own projects; tell me here too if the image ships an affected version.

## Supply chain

- Python, uv and the dependencies (`uv.lock`) are pinned and bumped by Renovate.
- GitHub Actions are pinned by digest.
- Images are published only from `v<version>` tags matching `pyproject.toml`, multi-arch, with
  provenance and SBOM; the published image is scanned for known vulnerabilities daily.
