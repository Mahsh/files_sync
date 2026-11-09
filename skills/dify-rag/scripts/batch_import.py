#!/usr/bin/env python3
"""
Dify.AI 知识库批量导入脚本
将指定目录下的所有 .md 文件批量上传到 Dify 知识库。

用法：
  python batch_import.py \
    --api-base https://api.dify.ai \
    --api-key app-xxxxxxxxxxxx \
    --dataset-id dataset-uuid \
    --dir ./memory/knowledge-base/cloud-phone

环境变量（优先级低于命令行参数）：
  DIFY_API_BASE
  DIFY_API_KEY
  DIFY_DATASET_ID
"""

import argparse
import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path


def upload_document(api_base: str, api_key: str, dataset_id: str, name: str, text: str) -> dict:
    """通过 Dify API 上传单个文档（文本方式）"""
    url = f"{api_base}/v1/datasets/{dataset_id}/document/create_by_text"
    payload = json.dumps({
        "name": name,
        "text": text,
        "indexing_technique": "high_quality",
        "process_rule": {"mode": "automatic"},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"error": f"HTTP {e.code}", "detail": body}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="批量导入 Markdown 文件到 Dify 知识库")
    parser.add_argument("--api-base", default=os.environ.get("DIFY_API_BASE", ""))
    parser.add_argument("--api-key", default=os.environ.get("DIFY_API_KEY", ""))
    parser.add_argument("--dataset-id", default=os.environ.get("DIFY_DATASET_ID", ""))
    parser.add_argument("--dir", required=True, help="要导入的目录路径")
    parser.add_argument("--interval", type=float, default=1.5, help="每次上传间隔秒数")
    args = parser.parse_args()

    if not args.api_base or not args.api_key or not args.dataset_id:
        print("错误：请通过命令行参数或环境变量提供 DIFY_API_BASE, DIFY_API_KEY, DIFY_DATASET_ID")
        sys.exit(1)

    directory = Path(args.dir)
    if not directory.exists():
        print(f"错误：目录不存在 {directory}")
        sys.exit(1)

    md_files = sorted(directory.rglob("*.md"))
    if not md_files:
        print(f"未找到 .md 文件：{directory}")
        sys.exit(0)

    print(f"找到 {len(md_files)} 个 .md 文件，开始导入...")
    print(f"API: {args.api_base}")
    print(f"知识库 ID: {args.dataset_id}")
    print()

    success = 0
    failed = 0
    for i, fpath in enumerate(md_files, 1):
        name = fpath.name
        text = fpath.read_text(encoding="utf-8")
        if not text.strip():
            print(f"[{i}/{len(md_files)}] 跳过空文件：{name}")
            continue
        print(f"[{i}/{len(md_files)}] 上传：{name} ({len(text)} chars)...", end=" ")
        result = upload_document(args.api_base, args.api_key, args.dataset_id, name, text)
        if "error" in result:
            print(f"失败：{result['error']} - {result.get('detail', '')[:100]}")
            failed += 1
        else:
            doc_id = result.get("id", result.get("document_id", "?"))
            print(f"成功 (id={doc_id})")
            success += 1
        time.sleep(args.interval)

    print()
    print(f"导入完成：成功 {success}，失败 {failed}，总计 {len(md_files)}")


if __name__ == "__main__":
    main()
