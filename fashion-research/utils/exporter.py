"""
utils/exporter.py
데이터 내보내기 유틸리티 (CSV / Excel / JSON)
"""
import os
import json
from datetime import datetime
import pandas as pd
from loguru import logger

EXPORT_DIR = os.getenv("EXPORT_DIR", "./exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_csv(df: pd.DataFrame, name: str) -> str:
    path = os.path.join(EXPORT_DIR, f"{name}_{_timestamp()}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.success(f"📄 CSV 저장: {path}")
    return path


def export_excel(df: pd.DataFrame, name: str, sheet: str = "Sheet1") -> str:
    path = os.path.join(EXPORT_DIR, f"{name}_{_timestamp()}.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet, index=False)
    logger.success(f"📊 Excel 저장: {path}")
    return path


def export_json(data: dict | list, name: str) -> str:
    path = os.path.join(EXPORT_DIR, f"{name}_{_timestamp()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.success(f"📋 JSON 저장: {path}")
    return path


def list_exports() -> list[str]:
    """exports 폴더의 파일 목록 반환"""
    files = []
    for f in os.listdir(EXPORT_DIR):
        full_path = os.path.join(EXPORT_DIR, f)
        if os.path.isfile(full_path):
            files.append(full_path)
    return sorted(files, reverse=True)
