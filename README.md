# file-parser

基于 [MinerU](https://github.com/opendatalab/MinerU) 的独立文档解析服务。

将用户上传的 PDF / Word / PPT / Excel / 图片等文件解析为结构化 Markdown 或 JSON，供 LLM / Agent / RAG 使用。

## 支持格式

| 类型 | 格式 | 解析方式 |
|---|---|---|
| PDF | `.pdf` | MinerU 原生解析 |
| Word | `.doc`, `.docx` | MinerU 解析（底层 LibreOffice 转 PDF） |
| PPT | `.ppt`, `.pptx` | MinerU 原生解析 |
| Excel | `.xls`, `.xlsx` | `openpyxl` 直接读取单元格，输出 Markdown 表格 |
| 图片 | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.tif`, `.gif`, `.webp` | MinerU OCR 识别 |

> 注：`.gif` / `.webp` / `.tiff` 等虽在允许列表中，但实际效果取决于 MinerU OCR 对这些格式的支持，建议优先使用 PNG / JPG。

## 设计原则

- **独立部署**：可单独作为一个服务运行。
- **不存储**：上传文件与解析结果均使用临时目录，请求结束后清理。
- **纯解析**：不做持久化、不入向量库、不保留历史。

## 环境要求

- **Python 3.10**（MinerU 1.3.x 推荐版本）
- macOS / Linux / Windows
- 至少 8GB 内存，首次加载模型时较慢
- **LibreOffice**（必须，用于 DOC/DOCX/PPT/PPTX 等 Office 文件先转 PDF）

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
cd file-parser
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. 安装 LibreOffice

MinerU 解析 Word / PPT / Excel 等 Office 文档时，需要调用 LibreOffice 先转换为 PDF。

- **macOS**：
  ```bash
  brew install libreoffice
  ```
- **Ubuntu / Debian**：
  ```bash
  sudo apt update && sudo apt install -y libreoffice
  ```
- **CentOS / RHEL**：
  ```bash
  sudo yum install -y libreoffice
  ```

安装完成后确认 `soffice` 命令可用：

```bash
which soffice
soffice --version
```

### 3. 下载 MinerU 模型

```bash
source .venv/bin/activate
python -c "from modelscope import snapshot_download; snapshot_download('opendatalab/PDF-Extract-Kit-1.0', local_dir='./models/PDF-Extract-Kit-1.0')"
```

> 模型约 14GB，下载需要几分钟到几十分钟，取决于网络。

### 4. 应用 OCR 模型补丁

PDF-Extract-Kit-1.0 中部分 v3 OCR 检测模型已移除，需要 patch 到可用的 v5 模型：

```bash
source .venv/bin/activate
python scripts/patch_models_config.py
```

### 5. 配置 `magic-pdf.json`

项目已内置 `magic-pdf.json`，默认指向 `./models/PDF-Extract-Kit-1.0/models`。如需修改设备或模型，编辑该文件：

```json
{
  "models-dir": "/absolute/path/to/file-parser/models/PDF-Extract-Kit-1.0/models",
  "device-mode": "cpu",
  "layout-config": { "model": "doclayout_yolo" },
  "formula-config": { "mfd_model": "yolo_v8_mfd", "mfr_model": "unimernet_small", "enable": true },
  "table-config": { "model": "rapid_table", "enable": false, "max_time": 400 }
}
```

### 6. 启动服务

```bash
cd file-parser
source .venv/bin/activate
python main.py
```

或：

```bash
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

服务默认监听 `http://localhost:8000`。

### 7. 测试

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/parse \
  -F "file=@example.pdf" \
  -F "output_format=markdown"
```

## API

### `POST /parse`

multipart/form-data 上传文件。

- `file`: 待解析文件
- `output_format`: `markdown`（默认）或 `json`

返回示例：

```json
{
  "status": "success",
  "content": "# 文档标题\n\n正文内容...",
  "metadata": {"pages": 10, "mime": "application/pdf"},
  "pages": []
}
```

### `POST /parse/base64`

接收 base64 编码的文件内容。

- `filename`: 文件名
- `data`: base64 编码内容
- `output_format`: `markdown`（默认）或 `json`

### `GET /health`

健康检查。

## 环境变量

- `HOST`: 服务监听地址，默认 `0.0.0.0`
- `PORT`: 服务端口，默认 `8000`
- `WORK_DIR`: 临时工作目录，默认系统临时目录
- `CORS_ORIGINS`: 允许的跨域来源，逗号分隔，默认 `*`
- `MAX_CONTENT_CHARS`: 返回内容最大字符数，默认 `300000`
- `MINERU_TOOLS_CONFIG_JSON`: MinerU 配置文件路径，项目默认已设置
- `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`: PyTorch 加载模型时使用 `weights_only=False`，项目默认已设置 `1`

## Docker 部署

```bash
docker build -t file-parser .
docker run -p 8000:8000 file-parser
```

## 常见问题

| 问题 | 解决 |
|---|---|
| `magic-pdf: command not found` | 确认在虚拟环境里，且 `pip install -r requirements.txt` 成功 |
| `No module named 'doclayout_yolo'` 等 | 运行 `pip install -r requirements.txt` 安装完整依赖 |
| `FileNotFoundError: ch_PP-OCRv3_det_infer.pth` | 运行 `python scripts/patch_models_config.py` |
| `_pickle.UnpicklingError: Weights only load failed` | 项目已默认设置 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` |
| 解析特别慢 | CPU 模式正常较慢；需要 GPU 则安装 CUDA 版 PyTorch 并把 `device-mode` 改为 `cuda` |
| 大 PDF 超时 | `main.py` 中 `_run_mineru` 的 `subprocess.run(timeout=600)` 已设为 10 分钟，可按需调大 |
| DOCX 解析成功但 `content` 为空 | 先确认已安装 LibreOffice 且 `soffice` 在 PATH 中；再查看日志是否有 `UnimerMBartForCausalLM.forward() got an unexpected keyword argument 'cache_position'`，如有则将 `magic-pdf.json` 中的 `formula-config.enable` 设为 `false` |
| `UnimerMBartForCausalLM.forward() got an unexpected keyword argument 'cache_position'` | transformers 版本与 unimernet 不兼容；临时方案：在 `magic-pdf.json` 中禁用公式识别 `"formula-config": {"enable": false}` |
| Excel 解析为空或报错 `Unknown file suffix: .xlsx` | 项目已改用 `openpyxl` 直接读取单元格；确认 `pip install -r requirements.txt` 包含 `openpyxl` |
| 图片只返回图片引用没有文字 | 确认上传的是 PNG / JPG；其他格式建议先转 PNG / JPG |
