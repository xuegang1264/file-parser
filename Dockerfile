FROM python:3.10-slim

WORKDIR /app

# 更换 apt 源为国内镜像，加速系统依赖安装
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list

# 安装系统依赖：libmagic 用于 python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

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
