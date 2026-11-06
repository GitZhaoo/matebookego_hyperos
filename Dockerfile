FROM debian:bookworm-slim

# 国内链路优先；国际链路经常超时。构建机在境外时可自行改回 deb.debian.org。
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 e2fsprogs attr zstd android-sdk-libsparse-utils \
        openjdk-17-jre-headless ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
