FROM nvidia/cuda:12.5.1-cudnn-devel-ubuntu22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-setuptools \
    python3-dev \
    python3-venv

RUN python3 --version

WORKDIR /app
RUN python3 -m venv venv
COPY requirements.txt ./requirements.txt
RUN venv/bin/python --version
RUN venv/bin/python -m pip install -r requirements.txt

COPY . .

CMD ["venv/bin/python", "gpustats.py"]
