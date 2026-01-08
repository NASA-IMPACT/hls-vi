FROM python:3.12-slim

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libexpat1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /hls_vi

COPY ./ ./
RUN pip install '.[test]' && pip install tox

ENTRYPOINT [ "tox" ]
