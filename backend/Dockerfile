FROM python:3.11-alpine

# Install Alpine dependencies
RUN apk add --no-cache \
    uwsgi \
    uwsgi-python3 \
    libffi-dev \
    build-base \
    python3-dev \
    linux-headers \
    pcre-dev \
    libpq \
    postgresql-dev

# Set environment for Pipenv
ENV LANG=C.UTF-8
ENV PIPENV_IGNORE_VIRTUALENVS=1
ENV PIPENV_PYTHON=/usr/local/bin/python3.11
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install pipenv
RUN pip install pipenv

# Copy and install dependencies
COPY Pipfile ./
RUN pipenv install --deploy

# Copy app source
COPY app .


EXPOSE 5000

CMD ["uwsgi", "--ini", "/app/wsgi.ini"]
