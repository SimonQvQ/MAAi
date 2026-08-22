FROM ubuntu:22.04

ARG MAAFW_URL=""
ARG MXU_URL=""

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      xvfb x11vnc libgtk-3-0 libwebkit2gtk-4.0-37 libwebp7 libjpeg-turbo8 \
      libsdl2-2.0-0 libasound2 libpulse0 python3 curl unzip ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99
ENV LD_LIBRARY_PATH=/opt/maai/maafw/bin
WORKDIR /opt/maai

# 占位文件（未提供 URL 时的兜底；提供 URL 会被下面 RUN 覆盖为真实运行库）
COPY maafw/ /opt/maai/maafw/
COPY mxu /opt/maai/mxu
COPY interface.json /opt/maai/interface.json
COPY resource/ /opt/maai/resource/
COPY bridge/ /opt/maai/bridge/
COPY entry.sh /opt/maai/entry.sh

# MaaFramework 运行库（zip）
RUN if [ -n "$MAAFW_URL" ]; then \
        rm -rf /opt/maai/maafw && mkdir -p /opt/maai/maafw && \
        curl -fsSL --retry 3 "$MAAFW_URL" -o /tmp/maafw.zip && \
        unzip -q /tmp/maafw.zip -d /opt/maai/maafw && \
        chmod -R +x /opt/maai/maafw 2>/dev/null || true; \
    fi

# MXU 可执行文件（tar.gz 解出 mxu）
RUN if [ -n "$MXU_URL" ]; then \
        curl -fsSL --retry 3 "$MXU_URL" -o /tmp/mxu_pkg && \
        (tar xzf /tmp/mxu_pkg -C /tmp && install -m 755 /tmp/mxu /opt/maai/mxu) || true; \
    fi

RUN chmod +x /opt/maai/mxu /opt/maai/entry.sh && mkdir -p /opt/maai/config /opt/maai/debug

EXPOSE 17171 5800
CMD ["/opt/maai/entry.sh"]
