FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3.9 \
    python3.9-venv \
    python3-pip \
    wget \
    file \
    binutils \
    libfuse2 \
    libxcb-xinerama0 \
    && rm -rf /var/lib/apt/lists/*

RUN python3.9 -m pip install --upgrade pip
RUN pip3 install PyQt6 Pillow pyinstaller

WORKDIR /app

CMD ["bash", "scripts/build_appimage.sh"]