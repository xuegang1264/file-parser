FROM python:3.10-slim

WORKDIR /app

# 如需支持旧版 .doc/.ppt，取消下面这行的注释并重新构建镜像
# RUN apt-get update && apt-get install -y --no-install-recommends libreoffice && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# pip 使用阿里云 PyPI 镜像，加速国内下载
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV WORK_DIR=/tmp/file-parser

EXPOSE 8000

CMD ["python", "main.py"]
