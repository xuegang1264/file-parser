"""
file-parser: 基于 MinerU (magic-pdf) 的文档解析服务。

提供独立的 HTTP 服务，接收文件上传，返回结构化 Markdown / JSON。
解析过程与结果均不持久化，仅作为 LLM / Agent / RAG 的输入。
"""
import base64
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

try:
    import magic
except ImportError:
    magic = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

# MinerU 配置文件路径：使用项目目录下的 magic-pdf.json，不依赖用户主目录
PROJECT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
MINERU_CONFIG_PATH = PROJECT_DIR / "magic-pdf.json"
if MINERU_CONFIG_PATH.exists():
    os.environ.setdefault("MINERU_TOOLS_CONFIG_JSON", str(MINERU_CONFIG_PATH))

# PyTorch 2.6+ 默认 weights_only=True，MinerU/DocLayoutYOLO 的 .pt 模型需要关闭该限制
os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

app = FastAPI(title="File Parser Server", version="0.1.0")

# CORS：允许 ai-rag 等 Agent Server 跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 默认工作目录，用于存放临时文件
WORK_DIR = Path(os.environ.get("WORK_DIR", tempfile.gettempdir())) / "file-parser"
WORK_DIR.mkdir(parents=True, exist_ok=True)

# 输出长度限制，防止超大文档直接塞爆响应
MAX_CONTENT_CHARS = int(os.environ.get("MAX_CONTENT_CHARS", "300000"))


def _get_file_mime(file_path: Path) -> str:
    """使用 libmagic 推断文件 MIME 类型；未安装时回退到 mimetypes。"""
    if magic is not None:
        try:
            return magic.from_file(str(file_path), mime=True)
        except Exception:
            pass
    mime, _ = mimetypes.guess_type(str(file_path))
    return mime or "application/octet-stream"


def _allowed_extension(filename: str) -> bool:
    """检查文件扩展名是否在 MinerU 常见支持范围内。"""
    ext = Path(filename).suffix.lower().lstrip(".")
    allowed = {
        "pdf",
        "doc", "docx",
        "ppt", "pptx",
        "xls", "xlsx",
        "png", "jpg", "jpeg", "bmp", "tiff", "tif", "gif", "webp",
    }
    return ext in allowed


def _parse_excel_directly(file_path: Path) -> dict:
    """
    直接使用 openpyxl 读取 Excel 内容，返回 Markdown 表格。

    MinerU 原生不支持 XLSX，且 LibreOffice 转 PDF 后表格仍会被当成图片，
    无法被 LLM 直接阅读。因此 Excel 单独走文本提取，保留表格结构。
    """
    if openpyxl is None:
        raise RuntimeError("未安装 openpyxl，无法解析 Excel 文件")

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except Exception as e:
        raise RuntimeError(f"读取 Excel 失败: {e}") from e

    parts = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        parts.append(f"## Sheet: {sheet_name}")
        rows = []
        for row in ws.iter_rows(values_only=True):
            # 把 None 转成空字符串，统一转 str
            cells = [str(cell) if cell is not None else "" for cell in row]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue

        # 简单 Markdown 表格
        header = rows[0]
        separator = ["---"] * len(header)
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join(separator) + " |")
        for row in rows[1:]:
            # 补齐列数
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            elif len(row) > len(header):
                row = row[:len(header)]
            lines.append("| " + " | ".join(row) + " |")
        parts.append("\n".join(lines))

    content = "\n\n".join(parts)
    return {
        "content": content[:MAX_CONTENT_CHARS],
        "metadata": {"pages": len(wb.sheetnames), "mime": _get_file_mime(file_path)},
        "pages": [],
    }


def _run_mineru(file_path: Path, output_dir: Path, output_format: str) -> dict:
    """
    调用 MinerU (magic-pdf) 解析文件。

    这里优先使用 subprocess 调用 CLI，避免不同 magic-pdf 版本 Python API 差异。
    输出目录结构示例：
        output_dir/
            {name}/
                auto/
                    {name}.md
                    {name}.json
                    images/
    """
    ext = file_path.suffix.lower().lstrip(".")

    # MinerU 不直接支持 Excel，直接读取单元格内容更可靠
    if ext in {"xls", "xlsx"}:
        return _parse_excel_directly(file_path)

    name = file_path.stem
    cmd = [
        "magic-pdf",
        "-p", str(file_path),
        "-o", str(output_dir),
        "-m", "auto",
    ]
    logger.info(f"Running MinerU: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError("未找到 magic-pdf 命令，请确认 MinerU 已安装") from e

    if result.returncode != 0:
        logger.error(f"magic-pdf stderr: {result.stderr}")
        raise RuntimeError(f"MinerU 解析失败: {result.stderr[:500]}")

    # 读取生成的 markdown / json
    auto_dir = output_dir / name / "auto"
    md_path = auto_dir / f"{name}.md"
    json_path = auto_dir / f"{name}.json"

    content = ""
    metadata = {"pages": 0, "mime": _get_file_mime(file_path)}
    pages = []

    if md_path.exists():
        content = md_path.read_text(encoding="utf-8")
    else:
        logger.warning(f"MinerU 未生成 markdown: {md_path}")

    # MinerU 对 doc/docx/ppt 等依赖 LibreOffice 先转 PDF；
    # 若转换失败，CLI 仍可能返回 0 但 content 为空，需要明确报错。
    if not content.strip() and not pages:
        err_hint = ""
        if result.stderr:
            err_hint = f"; stderr: {result.stderr[:300]}"
        raise RuntimeError(
            f"MinerU 未返回有效内容，可能是依赖缺失（如 LibreOffice）或文件损坏{err_hint}"
        )

    if json_path.exists():
        try:
            parsed_json = json.loads(json_path.read_text(encoding="utf-8"))
            metadata.update(parsed_json.get("metadata", {}))
            pages = parsed_json.get("pages", [])
        except Exception as e:
            logger.warning(f"解析 JSON 结果失败: {e}")

    if output_format == "json":
        # 返回按页拆分的 JSON 结构
        return {
            "content": content[:MAX_CONTENT_CHARS],
            "metadata": metadata,
            "pages": pages,
        }

    return {
        "content": content[:MAX_CONTENT_CHARS],
        "metadata": metadata,
        "pages": [],
    }


@app.get("/health")
def health():
    """健康检查。"""
    return {"status": "ok", "service": "file-parser"}


@app.post("/parse")
async def parse(
    file: UploadFile = File(..., description="待解析的文件"),
    output_format: str = Form(default="markdown", description="输出格式: markdown | json"),
):
    """
    解析上传文件，返回结构化 Markdown 或 JSON。

    - 不保存上传的文件与解析结果。
    - 解析超时默认 10 分钟。
    """
    if output_format not in {"markdown", "json"}:
        raise HTTPException(status_code=400, detail="output_format 必须是 markdown 或 json")

    request_id = str(uuid.uuid4())
    work_dir = WORK_DIR / request_id
    upload_path = work_dir / (file.filename or "upload")
    output_dir = work_dir / "output"

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存上传文件
        with open(upload_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        if not _allowed_extension(upload_path.name):
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {upload_path.suffix}")

        # 调用 MinerU 解析
        parse_result = _run_mineru(upload_path, output_dir, output_format)

        return JSONResponse(
            content={
                "status": "success",
                "content": parse_result["content"],
                "metadata": parse_result["metadata"],
                "pages": parse_result["pages"],
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("文件解析失败")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}") from e
    finally:
        # 清理临时文件，保证不存储
        try:
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"清理临时目录失败 {work_dir}: {e}")


@app.post("/parse/base64")
async def parse_base64(
    filename: str = Form(...),
    data: str = Form(..., description="文件内容的 base64 编码"),
    output_format: str = Form(default="markdown"),
):
    """
    接收 base64 编码的文件内容并解析。
    """
    try:
        file_bytes = base64.b64decode(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"base64 解码失败: {e}") from e

    request_id = str(uuid.uuid4())
    work_dir = WORK_DIR / request_id
    upload_path = work_dir / filename
    output_dir = work_dir / "output"

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(file_bytes)

        parse_result = _run_mineru(upload_path, output_dir, output_format)
        return JSONResponse(
            content={
                "status": "success",
                "content": parse_result["content"],
                "metadata": parse_result["metadata"],
                "pages": parse_result["pages"],
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("base64 文件解析失败")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}") from e
    finally:
        try:
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"清理临时目录失败 {work_dir}: {e}")


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
