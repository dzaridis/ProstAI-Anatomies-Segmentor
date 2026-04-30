# syntax=docker/dockerfile:1.6
# ---------- Stage 1: builder ----------
FROM nvcr.io/nvidia/cuda:11.7.0-cudnn8-devel-ubuntu20.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        ca-certificates \
        curl && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.9 \
        python3.9-dev \
        python3.9-distutils \
        python3.9-venv \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# Build everything inside an isolated venv so transitive deps cannot be skipped.
RUN python3.9 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# ---------- Stage 2: runtime ----------
FROM nvcr.io/nvidia/cuda:11.7.0-cudnn8-runtime-ubuntu20.04

LABEL name="prostate-zone-segmentor" \
      version="2.1.0" \
      description="Prostate whole-gland, zonal (PZ/TZ) and lesion segmentation from prostate MRI using cascaded nnU-Net v2 + ProLesA-Net." \
      maintainer="Dimitrios Zaridis <dimzaridis@gmail.com>" \
      authorization="This Dockerfile is intended to build a container image that will be publicly accessible in the EUCAIM images repository." \
      image.source="https://github.com/dzaridis/ProstAI-Anatomies-Segmentor" \
      image.revision="main" \
      image.version="2.1.0"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=/opt/models \
    WORK_DIR=/tmp/nnunet_workdir \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONPATH=/app

ARG USER_UID=2323
ARG USER_GID=2323

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        ca-certificates \
        passwd && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.9 \
        python3.9-distutils && \
    /usr/sbin/groupadd -g ${USER_GID} eucaim && \
    /usr/sbin/useradd  -r -u ${USER_UID} -g eucaim -d /home/eucaim -m -s /usr/sbin/nologin eucaim && \
    apt-get purge -y software-properties-common && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Copy the fully resolved venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY Utils /app/Utils
COPY __main__.py /app/__main__.py
COPY healthcheck.py /app/healthcheck.py

COPY nnUnet_paths/nnUNet_results /opt/models/nnUNet_results
COPY Lesion_weights /opt/models/lesion

RUN mkdir -p ${WORK_DIR} && \
    chown -R root:eucaim /app /opt/models /opt/venv ${WORK_DIR} && \
    chmod -R 755 /app /opt/models /opt/venv && \
    chmod -R 775 ${WORK_DIR}

USER eucaim

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python /app/healthcheck.py || exit 1

ENTRYPOINT ["python", "/app/__main__.py"]
CMD ["--help"]

ENV DEBIAN_FRONTEND=
