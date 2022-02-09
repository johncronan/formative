FROM debian:bookworm-slim

RUN mkdir -p /opt/services/djangoapp/src /opt/services/djangoapp/static
WORKDIR /opt/services/djangoapp/src

COPY pyproject.toml poetry.lock /opt/services/djangoapp/src/

# dependencies
RUN apt-get update \
    && apt-get install -y build-essential libpq-dev libqpdf-dev pip \
                          python3-dev python3-importlib-metadata ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install wheel poetry && poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root \
    && apt-get purge -y --auto-remove build-essential
# virtualenvs.create option because we don't need an extra virtualenv here

# copy the project code
COPY . /opt/services/djangoapp/src

EXPOSE 8000

# TODO: change to an app user?

CMD (cd ../requirements; \
    touch requirements.txt && pip install -r requirements.txt) \
    && gunicorn --reload --chdir . --bind :8000 config.wsgi:application
