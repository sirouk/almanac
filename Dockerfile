FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    ARCLINK_REPO_DIR=/home/arclink/arclink \
    ARCLINK_PRIV_DIR=/home/arclink/arclink/arclink-priv \
    ARCLINK_CONFIG_FILE=/home/arclink/arclink/arclink-priv/config/docker.env \
    ARCLINK_API_INTERNAL_URL=http://control-api:8900 \
    RUNTIME_DIR=/opt/arclink/runtime \
    UV_INSTALL_DIR=/usr/local/bin \
    HOME=/home/arclink \
    PATH=/home/arclink/.local/bin:/opt/arclink/runtime/hermes-venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && install -m 0755 -d /etc/apt/keyrings \
  && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
  && chmod a+r /etc/apt/keyrings/docker.asc \
  && . /etc/os-release \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends \
    acl \
    bash \
    docker-ce-cli \
    docker-compose-plugin \
    file \
    git \
    inotify-tools \
    iproute2 \
    jq \
    openssh-client \
    poppler-utils \
    procps \
    python3 \
    python3-pip \
    python3-venv \
    rsync \
    sqlite3 \
    tini \
    util-linux \
  && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN useradd --create-home --home-dir /home/arclink --shell /bin/bash arclink

WORKDIR /home/arclink/arclink
COPY . /home/arclink/arclink

RUN pin_value() { \
      python3 -c 'import json, sys; print(json.load(open("config/pins.json"))["components"][sys.argv[1]][sys.argv[2]])' "$1" "$2"; \
    } \
  && curl -LsSf https://astral.sh/uv/install.sh | sh \
  && qmd_version="$(pin_value qmd version)" \
  && npm install -g "@tobilu/qmd@${qmd_version}" \
  && hermes_repo="$(pin_value hermes-agent repo)" \
  && hermes_ref="$(pin_value hermes-agent ref)" \
  && mkdir -p /opt/arclink/runtime \
  && git clone "$hermes_repo" /opt/arclink/runtime/hermes-agent-src \
  && git -C /opt/arclink/runtime/hermes-agent-src checkout --force --detach "$hermes_ref" \
  && uv venv /opt/arclink/runtime/hermes-venv --python /usr/bin/python3 --seed \
  && uv pip install --python /opt/arclink/runtime/hermes-venv/bin/python3 \
    "/opt/arclink/runtime/hermes-agent-src[cli,mcp,messaging,cron,web]" \
    PyYAML \
    requests \
    stripe \
  && if [ -d /opt/arclink/runtime/hermes-agent-src/web ]; then \
       cd /opt/arclink/runtime/hermes-agent-src/web \
       && npm ci --no-audit --no-fund \
       && npm run build \
       && /opt/arclink/runtime/hermes-venv/bin/python3 -c 'from pathlib import Path; import hermes_cli, shutil; source = Path("/opt/arclink/runtime/hermes-agent-src/hermes_cli/web_dist"); target = Path(hermes_cli.__file__).resolve().parent / "web_dist"; shutil.rmtree(target, ignore_errors=True); shutil.copytree(source, target) if source.is_dir() else None'; \
     fi \
  && if [ -f /home/arclink/arclink/web/package-lock.json ]; then \
       cd /home/arclink/arclink/web \
       && npm ci --no-audit --no-fund \
       && npm run build; \
     fi \
  && chown -R arclink:arclink /home/arclink /opt/arclink

ENTRYPOINT ["/usr/bin/tini", "--", "/home/arclink/arclink/bin/docker-entrypoint.sh"]
CMD ["./bin/arclink-docker.sh", "health"]
