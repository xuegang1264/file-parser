"""
Patch MinerU's models_config.yml to use available OCR models.

PDF-Extract-Kit-1.0 from ModelScope no longer ships some v3 detection models
(e.g. ch_PP-OCRv3_det_infer.pth). This script remaps the default configs to
use the v5/v6 models that are actually present in the kit.

Run once after `pip install -r requirements.txt`:
    source .venv/bin/activate
    python scripts/patch_models_config.py
"""
import os
import sys


def patch():
    try:
        import magic_pdf
    except ImportError:
        print("magic-pdf is not installed. Please install requirements first.")
        sys.exit(1)

    pkg_dir = os.path.dirname(os.path.abspath(magic_pdf.__file__))
    config_path = os.path.join(
        pkg_dir,
        "model",
        "sub_modules",
        "ocr",
        "paddleocr2pytorch",
        "pytorchocr",
        "utils",
        "resources",
        "models_config.yml",
    )

    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    # Map missing v3 detection models to available v5 models
    content = content.replace("ch_PP-OCRv3_det_infer.pth", "ch_PP-OCRv5_det_infer.pth")
    content = content.replace("en_PP-OCRv3_det_infer.pth", "en_PP-OCRv5_det_infer.pth")

    if content == original:
        print("No patch needed; models_config.yml is already up to date.")
        return

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Patched: {config_path}")


if __name__ == "__main__":
    patch()
