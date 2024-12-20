FROM osgeo/gdal:ubuntu-small-3.0.3

RUN : \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    python3.6 \
    python3-dev \
    python3-pip \
    python3-venv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --upgrade pip setuptools \
    && pip3 install --no-cache-dir rasterio==1.1.3 tox tox-venv --no-binary rasterio \
    && :

WORKDIR /hls_vi
COPY ./ ./

ENTRYPOINT [ "tox" ]
