FROM ubuntu:22.04

# 在 FROM 之后声明，RUN 里才能读到
ARG MAAFW_URL=""
ARG MAA5_RES_URL="https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/v5.12.2/MAA-v5.12.2-win-x64.zip"
ARG MEOW_RESOURCE_URL=""

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-pip curl unzip ca-certificates libjpeg-turbo8 \
    && rm -rf /var/lib/apt/lists/*

# MAAi bridge 依赖：official maafw 绑定 + cv2（截图 JPEG 解码）
RUN pip3 install --no-cache-dir "maafw==5.12.3" opencv-python-headless numpy

ENV LD_LIBRARY_PATH=/opt/maai/maafw
WORKDIR /opt/maai

COPY bridge/ /opt/maai/bridge/
COPY entry.sh /opt/maai/entry.sh
COPY fetch_official_resources.sh /opt/maai/fetch_official_resources.sh
COPY convert_maares.py /opt/maai/convert_maares.py
COPY fetch_resource.sh /opt/maai/fetch_resource.sh

# MaaFramework 运行库（可选，为 MXU/未来扩展预留）
RUN if [ -n "$MAAFW_URL" ]; then \
        mkdir -p /opt/maai/maafw /tmp/maafw_pkg && \
        curl -fsSL --retry 3 "$MAAFW_URL" -o /tmp/maafw.zip && \
        unzip -q /tmp/maafw.zip -d /tmp/maafw_pkg && \
        cp -a /tmp/maafw_pkg/*/bin/. /opt/maai/maafw/ && \
        chmod -R +x /opt/maai/maafw 2>/dev/null || true; \
    fi

# 官方 MAA 资源（下载 + 转换为标准 MaaFramework bundle），烘焙进镜像
RUN bash /opt/maai/fetch_official_resources.sh "$MAA5_RES_URL" /opt/maai/resource

# 可选 MaaResource 动态数据覆盖（如提供 URL 则叠加）
RUN if [ -n "$MEOW_RESOURCE_URL" ]; then \
        bash /opt/maai/fetch_resource.sh "$MEOW_RESOURCE_URL" /opt/maai/resource; \
    fi

RUN chmod +x /opt/maai/entry.sh /opt/maai/fetch_official_resources.sh /opt/maai/fetch_resource.sh \
    && mkdir -p /opt/maai/config /opt/maai/debug

EXPOSE 17171 8080
CMD ["/opt/maai/entry.sh"]