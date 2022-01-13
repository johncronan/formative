FROM python:3.10-slim-bullseye

RUN mkdir -p /opt/services/djangoapp/src /opt/services/djangoapp/static
WORKDIR /opt/services/djangoapp/src

COPY Pipfile Pipfile.lock /opt/services/djangoapp/src/

# dependencies
RUN apt-get update \
    && apt-get install -y build-essential libpq-dev python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install pipenv \
    && pipenv install --system \
    && apt-get purge -y --auto-remove build-essential
# --system flag because we don't need an extra virtualenv

# copy the project code
COPY . /opt/services/djangoapp/src

EXPOSE 8000

# TODO: change to an app user?

CMD ["gunicorn", "--reload", "--chdir", ".", "--bind", ":8000", \
     "config.wsgi:application"]
