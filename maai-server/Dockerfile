FROM ubuntu:22.04

# 在 FROM 之后声明，RUN 里才能读到
ARG MAAFW_URL=""
ARG MXU_URL=""
ARG MEOW_RESOURCE_URL=""

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      xvfb x11vnc libgtk-3-0 libwebkit2gtk-4.0-37 libwebp7 libjpeg-turbo8 \
      libsdl2-2.0-0 libasound2 libpulse0 python3 python3-pip curl unzip ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

# MAAi bridge 依赖：official maafw 绑定 + cv2（截图 JPEG 解码）
RUN pip3 install --no-cache-dir maafw opencv-python-headless numpy

ENV DISPLAY=:99
ENV LD_LIBRARY_PATH=/opt/maai/maafw
WORKDIR /opt/maai

# 占位文件（未提供 URL 时的兜底；提供 URL 会被下面 RUN 覆盖）
COPY maafw/ /opt/maai/maafw/
COPY mxu /opt/maai/mxu
COPY interface.json /opt/maai/interface.json
COPY resource/ /opt/maai/resource/
COPY bridge/ /opt/maai/bridge/
COPY entry.sh /opt/maai/entry.sh
COPY fetch_resource.sh /opt/maai/fetch_resource.sh

# MaaFramework 运行库（zip）
RUN if [ -n "$MAAFW_URL" ]; then \
        rm -rf /opt/maai/maafw /tmp/maafw_pkg && mkdir -p /opt/maai/maafw /tmp/maafw_pkg && \
        curl -fsSL --retry 3 "$MAAFW_URL" -o /tmp/maafw.zip && \
        unzip -q /tmp/maafw.zip -d /tmp/maafw_pkg && \
        cp -a /tmp/maafw_pkg/*/bin/. /opt/maai/maafw/ && \
        chmod -R +x /opt/maai/maafw 2>/dev/null || true; \
    fi

# MXU 可执行文件（tar.gz 解出 mxu）
RUN if [ -n "$MXU_URL" ]; then \
        curl -fsSL --retry 3 "$MXU_URL" -o /tmp/mxu_pkg && \
        (tar xzf /tmp/mxu_pkg -C /tmp && install -m 755 /tmp/mxu /opt/maai/mxu) || true; \
    fi

# MAA 资源包（官方 MaaResource main.zip，解压 resource/ 进镜像）
RUN if [ -n "$MEOW_RESOURCE_URL" ]; then \
        rm -rf /opt/maai/resource && \
        bash /opt/maai/fetch_resource.sh "$MEOW_RESOURCE_URL" /opt/maai/resource; \
    fi

RUN chmod +x /opt/maai/mxu /opt/maai/entry.sh /opt/maai/fetch_resource.sh \
    && mkdir -p /opt/maai/config /opt/maai/debug

EXPOSE 17171 5800
CMD ["/opt/maai/entry.sh"]
