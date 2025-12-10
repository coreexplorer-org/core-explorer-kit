FROM python:3.11-alpine

# Install Alpine dependencies
RUN apk add --no-cache \
    libffi-dev \
    build-base \
    python3-dev \
    linux-headers \
    pcre-dev \
    libpq \
    postgresql-dev \
    git 

# Allow Git inside the container to read the mounted Bitcoin repo owned by the host user.
RUN git config --global --add safe.directory /app/bitcoin

# Set environment for Pipenv
ENV LANG=C.UTF-8
ENV PIPENV_IGNORE_VIRTUALENVS=1
ENV PIPENV_PYTHON=/usr/local/bin/python3.11
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install Python packages including uWSGI (use pip to ensure compatibility with base Python)
RUN pip install --no-cache-dir \
    uwsgi \
    pipenv \
    flask \
    flask_graphql \
    graphene \
    neo4j \
    GitPython \
    git-fame

RUN git config --global --add safe.directory /app/bitcoin

# Copy app source
COPY app .

# Copy WSGI files
COPY wsgi.py .
COPY wsgi.ini .

EXPOSE 5000

# Use uWSGI production server instead of Flask dev server
CMD ["uwsgi", "--ini", "wsgi.ini"]
