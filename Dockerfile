FROM python:3.11-slim

# 补丁版 Chrome 发布版本号（对应 Chromium 版本，GitHub Releases tag: chrome-<CHROME_VERSION>）
ARG CHROME_VERSION=153.0.7991.0
# buildx 多架构：amd64 / arm64（映射到发布包架构名 x64 / arm64）
ARG TARGETARCH=amd64

ENV CHROME_PATH=/opt/patched-chrome/chrome
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN
ENV LC_ALL=zh_CN.UTF-8
ENV DISPLAY=:99

RUN mkdir -p /app/

COPY . /app/
COPY supervisord.conf /etc/supervisord.conf
COPY start.sh /start.sh
RUN chmod +x /start.sh

# 安装 uv 与系统依赖
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    wget \
    gnupg \
    ca-certificates \
    xvfb \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-freefont-ttf \
    fonts-noto-color-emoji \
    locales \
    curl \
    supervisor \
    x11vnc \
    net-tools \
    git \
    python3-numpy \
    python3-pil \
    # Chrome 运行时依赖（google-chrome 包的解包依赖，不安装 Chrome 本体，
    # 补丁版 Chrome 由下方 GitHub Release 下载）
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libu2f-udev \
    nginx && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# nginx 统一入口（9850）：/chromeN/ 路由到各实例 websockify，/ 代理 FastAPI（内部 9851）
COPY deploy/nginx.conf /etc/nginx/nginx.conf

# 下载补丁版 Chrome 发布包（GitHub Releases）+ SHA256 校验 + 解包到 /opt/patched-chrome
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) arch="x64" ;; \
      arm64) arch="arm64" ;; \
      *) echo "不支持的架构 ${TARGETARCH}"; exit 1 ;; \
    esac; \
    mkdir -p /opt/patched-chrome; \
    base="https://github.com/linyuan0213/nexus-chrome-bin/releases/download/chrome-${CHROME_VERSION}"; \
    curl -fsSL -o /tmp/chrome.tar.gz "${base}/chrome-${CHROME_VERSION}-${arch}.tar.gz"; \
    curl -fsSL -o /tmp/chrome.sha256 "${base}/chrome-${CHROME_VERSION}-${arch}.tar.gz.sha256"; \
    (cd /tmp && sha256sum -c chrome.sha256); \
    tar -xzf /tmp/chrome.tar.gz -C /opt/patched-chrome; \
    chmod +x /opt/patched-chrome/chrome /opt/patched-chrome/chrome_crashpad_handler; \
    rm -f /tmp/chrome.tar.gz /tmp/chrome.sha256

# 生成中文区域设置
RUN echo "zh_CN.UTF-8 UTF-8" > /etc/locale.gen && \
    locale-gen zh_CN.UTF-8 && \
    update-locale LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh LC_ALL=zh_CN.UTF-8

# Windows 核心字体（Arial/Times/Verdana/Georgia/Tahoma/Courier 等）：
# 伪装 Windows/macOS 指纹时 canvas 字体度量需要真实字体，否则全部回退到同一
# Linux 字体（会被 Google/Cloudflare 的严格检测识别为字体不一致）。
# 需要 contrib non-free 组件（ttf-mscorefonts-installer 在 non-free）。
RUN set -eux; \
    sed -i 's/Components: main/Components: main contrib non-free/' /etc/apt/sources.list.d/*.sources 2>/dev/null || \
    sed -i 's/^\(deb .* main\)$/\1 contrib non-free/' /etc/apt/sources.list 2>/dev/null || true; \
    echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | debconf-set-selections; \
    apt-get update; \
    apt-get install -y --no-install-recommends ttf-mscorefonts-installer fonts-crosextra-carlito fonts-crosextra-caladea; \
    fc-cache -f; \
    rm -rf /var/lib/apt/lists/*

# Office 字体度量兼容别名：Calibri→Carlito、Cambria→Caladea（canvas 字体指纹与真实
# Office 字体度量一致；Segoe UI 无兼容开源字体，保留默认回退）
COPY scripts/fontconfig-ms-office-aliases.conf /etc/fonts/conf.d/60-ms-office-aliases.conf

# noVNC 静态资源（每个实例的 websockify 都会 --web 指向这里，供浏览器直接访问）
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /opt/noVNC && \
    git clone --depth 1 https://github.com/novnc/websockify /opt/noVNC/utils/websockify && \
    ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html && \
    # 默认 Local scaling：画布缩放铺满查看标签页，避免四周黑底
    sed -i "s/UI.initSetting('resize', 'off')/UI.initSetting('resize', 'scale')/" /opt/noVNC/app/ui.js

# 使用 uv 安装 Python 依赖
RUN cd /app && \
    uv venv .venv && \
    uv sync --frozen --no-cache && \
    rm -rf /root/.cache

# 对外统一入口：nginx :9850（/chromeN/ → 各实例 noVNC；/ → FastAPI 内部 9851）
# 每实例内部端口：Xvfb :N / x11vnc 5900+N / Chrome CDP 9222+N / websockify 6080+N
EXPOSE 9850 5900-5910 6080-6100

WORKDIR /app

CMD ["/start.sh"]
