FROM debian:bookworm-slim

RUN mkdir -p /opt/services/djangoapp/src /opt/services/djangoapp/static
WORKDIR /opt/services/djangoapp/src

COPY pyproject.toml poetry.lock /opt/services/djangoapp/src/

# dependencies
RUN apt-get update \
    && apt-get install -y build-essential libpq-dev libqpdf-dev pip xz-utils \
                          python3-dev python3-importlib-metadata wget redis \
    && apt-get install -y --no-install-recommends ffmpeg \
    && pip install wheel poetry && poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root -E reviewpanel \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge -y --auto-remove build-essential
# virtualenvs.create option because we don't need an extra virtualenv here

COPY . /opt/services/djangoapp/src
# install the root package too
RUN poetry install --no-dev

COPY resources/s6-rc.d /etc/s6-overlay/s6-rc.d
COPY resources/run /opt/services/djangoapp/run

ARG S6_VERSION=3.1.0.1
ARG S6_URL=https://github.com/just-containers/s6-overlay/releases/download
RUN arch="$(dpkg --print-architecture)"; \
    case "$arch" in arm64) s6arch='aarch64' ;; amd64) s6arch='amd64' ;; esac; \
    wget -O s6.tar.xz ${S6_URL}/v${S6_VERSION}/s6-overlay-noarch.tar.xz; \
    wget -O s6arch.tar.xz ${S6_URL}/v${S6_VERSION}/s6-overlay-$s6arch.tar.xz; \
    tar -C / -Jxpf s6.tar.xz; \
    tar -C / -Jxpf s6arch.tar.xz; \
    rm s6.tar.xz s6arch.tar.xz

EXPOSE 8000

ENTRYPOINT ["/init"]

# TODO: change to an app user?
CMD ["/command/with-contenv", "../run"]
