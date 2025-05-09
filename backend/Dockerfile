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
    postgresql-dev \
    git 

# Set environment for Pipenv
ENV LANG=C.UTF-8
ENV PIPENV_IGNORE_VIRTUALENVS=1
ENV PIPENV_PYTHON=/usr/local/bin/python3.11
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install pipenv
RUN pip install pipenv flask flask_graphql graphene neo4j GitPython git-fame


# Copy app source
COPY app .

EXPOSE 5000

CMD ["python", "app.py"]
