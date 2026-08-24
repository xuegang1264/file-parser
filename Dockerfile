FROM python:3.10-slim

WORKDIR /app

# 更换 apt 源为国内镜像，加速系统依赖安装
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list

# 安装系统依赖：
# - libmagic1: python-magic 需要
# - poppler-utils: PDF 处理
# - libreoffice: doc/docx/ppt 转 PDF
# - libgl1-mesa-glx / libglib2.0-0 / libsm6 / libxext6 / libxrender-dev: OpenCV (cv2) 需要
# - fonts-wqy-zenhei: 中文字体，避免解析出的中文显示为方框
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    libreoffice \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 刷新字体缓存
RUN fc-cache -fv

COPY requirements.txt .

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

RUN pip install --no-cache-dir -r requirements.txt

# 如需使用 MinerU 的 GPU 加速，可在此安装 paddle / torch 等依赖
# 并映射 GPU 设备。

COPY . .

ENV PYTHONUNBUFFERED=1
ENV WORK_DIR=/tmp/file-parser

EXPOSE 8000

CMD ["bash", "-c", "python scripts/patch_models_config.py && python main.py"]
