#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国移动知识库管理 CLI（建库、内容管理、导入、上传）。"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import deque
from typing import Any, Dict, List, Optional

import requests

# 鉴权：将 cmcc_skills/common_auth 加入 sys.path，以便导入 cm_cloud_auth。
common_auth_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'common_auth'))
if common_auth_root not in sys.path:
    sys.path.insert(0, common_auth_root)

from cm_cloud_auth import get_kb_auth_header, kb_manage_setting as setting
from cli_timing import (
    clear_api_timings,
    flush_cli_output_buffer,
    record_api_timing,
    start_cli_output_buffer,
    write_cli_output_line,
)
from cli_validate import validate_cloud_file_ids

# -----------------------------------------------------------------------------
# 常量定义
# -----------------------------------------------------------------------------
SUCCESS_CODES = {"0", "0000"}
KB_API_PREFIX = "/richlifeApp/knowledgeBase"
# list_contents 等调用 POST .../knowledgeBase/resource/list，返回 data.list[]（PersonalKnowledgeResource）。
# 与 `:::knowledgeBaseReference` 内 `resource` 同构的 JSONL 仅在脚本内组装（勿在 SKILL 中复述白名单）：
#   - 标量键见 _RESOURCE_LIST_SCALAR_KEYS；resourceId/baseId 规范化字符串；categoryList 仅整数列表；不展开嵌套对象。
# parentFileId 对「目录」与「文件」在接口里通常都表示父目录；卡片侧 folderId/folderName 语义按行类型区分（非「只有目录才有 parentFileId」）：
#   - type=folder：本行是目录 → folderId=本目录 resourceId，folderName=原 name；去掉 name/parentFileId，避免与「当前目录」语义打架。
#   - 否则为文件等：folderId=所在目录 parentFileId，folderName 置空，保留 name 为文件名；去掉已并入 folderId 的 parentFileId。
# list_contents 等可输出 record=kbPath（renderCard=knowledgeBasePath）；字段与 :::knowledgeBasePath 卡片一致。
MAX_FORM_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024
MAX_PARTS_PER_REQUEST = 100
MAX_TOTAL_PARTS = 10000
MIN_PART_SIZE = 5 * 1024 * 1024

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_BUSINESS_ERROR = 2
EXIT_INTERNAL_ERROR = 3

# 上传文件允许的扩展名（不区分大小写）
_UPLOAD_ALLOWED_EXTS = frozenset({".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"})

_last_trace_id: str = ''
_command_trace_id: str = ''


def set_last_trace_id(response: Optional[requests.Response]) -> None:
    global _last_trace_id
    if response is None:
        return
    tid = (response.headers.get('trace_id') or '').strip()
    if tid:
        _last_trace_id = tid


def get_last_trace_id() -> str:
    return _last_trace_id


def snapshot_trace_id() -> None:
    global _command_trace_id
    _command_trace_id = _last_trace_id


def get_command_trace_id() -> str:
    return _command_trace_id


def meta_trace_id() -> str:
    return (get_command_trace_id() or get_last_trace_id()).strip()


# -----------------------------------------------------------------------------
# 异常定义
# -----------------------------------------------------------------------------
class CliError(Exception):
    """带语义化退出码的 CLI 异常。"""
    
    def __init__(self, message: str, exit_code: int = EXIT_BUSINESS_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


# -----------------------------------------------------------------------------
# 工具服务层
# -----------------------------------------------------------------------------
class FileUtils:
    """文件处理工具类。"""
    
    @staticmethod
    def calc_sha256(file_path: str) -> str:
        """计算文件 SHA256 哈希。"""
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def recommend_part_size(file_size: int) -> int:
        """根据文件大小推荐分片大小。"""
        return max(MIN_PART_SIZE, (file_size + MAX_TOTAL_PARTS - 1) // MAX_TOTAL_PARTS)

    @staticmethod
    def build_part_infos(file_size: int, part_size: int) -> List[Dict[str, Any]]:
        """按分片大小生成上传分片信息。"""
        if part_size < MIN_PART_SIZE:
            raise CliError(f"分片大小过小，必须 >= {MIN_PART_SIZE} 字节。", EXIT_INPUT_ERROR)
            
        part_infos = []
        offset = 0
        part_number = 1
        while offset < file_size:
            current_size = min(part_size, file_size - offset)
            part_infos.append({
                "partNumber": part_number,
                "partSize": current_size,
                "partOffset": offset
            })
            offset += current_size
            part_number += 1
        return part_infos


# -----------------------------------------------------------------------------
# 核心网络层
# -----------------------------------------------------------------------------
class APIClient:
    """统一的 API 请求封装客户端。"""
    
    @staticmethod
    def _get_headers(content_type: str = "") -> Dict[str, str]:
        headers = dict(get_kb_auth_header())
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @staticmethod
    def _build_url(path: str) -> str:
        host = (setting.host or "").rstrip("/")
        if not host:
            raise CliError("接口地址为空，请配置 CM_CLOUD_HOST。", EXIT_INPUT_ERROR)
        return f"{host}/{path.lstrip('/')}"

    @staticmethod
    def _extract_error_msg(response: Optional[requests.Response]) -> str:
        """从接口响应中提取原始错误 message。"""
        if response is None:
            return ""
        body = (response.text or "").strip()
        if not body:
            return ""
        try:
            data = response.json()
            if isinstance(data, dict):
                msg = data.get("message")
                if msg is not None and str(msg).strip():
                    return str(msg)
        except ValueError:
            pass
        return body

    @staticmethod
    def _handle_response(result: dict) -> dict:
        """校验接口响应并提取 data。"""
        code = str(result.get("code", ""))
        success = result.get("success")
        if (success is True or success is None) and code in SUCCESS_CODES:
            return result.get("data", {})
        raise CliError(
            f"接口错误: code={code}, message={result.get('message', '')}", 
            EXIT_BUSINESS_ERROR
        )

    @classmethod
    def post(cls, path: str, payload: dict, timeout: Optional[int] = None) -> dict:
        """发送 POST JSON 请求并返回业务数据。"""
        url = cls._build_url(path)
        wait = setting.timeout if timeout is None else timeout
        response: Optional[requests.Response] = None
        started = time.perf_counter()
        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=cls._get_headers("application/json"), 
                timeout=wait
            )
            record_api_timing(path, (time.perf_counter() - started) * 1000)
            set_last_trace_id(response)
            response.raise_for_status()
            result = response.json()
            return cls._handle_response(result)
        except requests.exceptions.Timeout:
            record_api_timing(path, (time.perf_counter() - started) * 1000)
            raise CliError(f"请求超时: {path}", EXIT_BUSINESS_ERROR)
        except requests.exceptions.RequestException as exc:
            record_api_timing(path, (time.perf_counter() - started) * 1000)
            raw_msg = cls._extract_error_msg(getattr(exc, "response", None) or response)
            raise CliError(f"请求异常: {raw_msg or exc}", EXIT_BUSINESS_ERROR)
        except ValueError:
            record_api_timing(path, (time.perf_counter() - started) * 1000)
            raw_msg = cls._extract_error_msg(response)
            raise CliError(f"响应解析失败{': ' + raw_msg if raw_msg else '。'}", EXIT_INTERNAL_ERROR)

    @classmethod
    def put_raw(cls, url: str, data: bytes, timeout: int = 180, error_context: str = "上传") -> None:
        """原生 PUT 请求，用于分片数据上传。"""
        response: Optional[requests.Response] = None
        try:
            response = requests.put(url, data=data, timeout=timeout)
            set_last_trace_id(response)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raw_msg = cls._extract_error_msg(getattr(exc, "response", None) or response)
            raise CliError(f"{error_context}失败: {raw_msg or exc}", EXIT_BUSINESS_ERROR)

    @classmethod
    def post_form(cls, url: str, form_data: dict, files: dict, timeout: int = 180, error_context: str = "表单上传") -> None:
        """表单 POST 请求，用于小文件直传。"""
        response: Optional[requests.Response] = None
        try:
            response = requests.post(url, data=form_data, files=files, timeout=timeout)
            set_last_trace_id(response)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raw_msg = cls._extract_error_msg(getattr(exc, "response", None) or response)
            raise CliError(f"{error_context}失败: {raw_msg or exc}", EXIT_BUSINESS_ERROR)


# -----------------------------------------------------------------------------
# 业务逻辑服务层
# -----------------------------------------------------------------------------
class KnowledgeBaseService:
    """中国移动知识库核心业务逻辑服务。"""

    @staticmethod
    def _normalize_kb(item: dict) -> dict:
        return {
            "kb_id": item.get("baseId", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "item_count": item.get("totalCount", 0),
            "updated_at": item.get("updatedAt", ""),
        }

    # POST .../knowledgeBase/resource/list 单条 list[i] → stdout JSONL 的 resource 对象（与 knowledgeBaseReference 同构）。
    # 字段白名单与接口 PersonalKnowledgeResource 标量对齐；勿在 SKILL 中复述。
    _RESOURCE_LIST_SCALAR_KEYS = (
        "resourceType",
        "parentFileId",
        "createdAt",
        "updatedAt",
        "aiStatus",
        "auditStatus",
        "errorMessage",
        "htmlUrl",
        "type",
        "category",
        "size",
        "fileExtension",
        "contentHash",
        "contentHashAlgorithm",
        "createdBy",
    )

    @staticmethod
    def _api_item_to_card_resource(item: dict) -> Dict[str, Any]:
        """resource/list 单行 → 卡片 `resource` 同构对象（目录带 folderId/folderName；文件带 name 与 folderId）。"""
        res: Dict[str, Any] = {
            "resourceId": str(item.get("resourceId") or "").strip(),
            "baseId": str(item.get("baseId") or "").strip(),
            "name": str(item.get("name") or "").strip(),
        }
        for k in KnowledgeBaseService._RESOURCE_LIST_SCALAR_KEYS:
            if k not in item:
                continue
            v = item[k]
            if v is None:
                continue
            if isinstance(v, dict):
                continue
            if isinstance(v, list):
                continue
            res[k] = v
        raw_cl = item.get("categoryList")
        if isinstance(raw_cl, list) and raw_cl:
            nums: List[int] = []
            for x in raw_cl:
                if isinstance(x, bool) or not isinstance(x, (int, float)):
                    nums = []
                    break
                nums.append(int(x))
            if nums:
                res["categoryList"] = nums
        # 目录行：folderId/folderName 表示本目录；文件行：folderId 表示父目录（接口 parentFileId），name 为文件名
        rtype = str(res.get("type") or "").lower()
        if rtype == "folder":
            res.pop("parentFileId", None)
            nm = res.pop("name", None)
            rid = str(res.get("resourceId") or "").strip()
            if rid:
                res["folderId"] = rid
            if nm is not None and str(nm).strip():
                res["folderName"] = str(nm).strip()
        else:
            pid = str(res.get("parentFileId") or "").strip()
            if pid:
                res["folderId"] = pid
                res["folderName"] = ""
                res.pop("parentFileId", None)
        return res

    @staticmethod
    def _normalize_resource(item: dict) -> dict:
        """内部列表项：`resource` 与卡片内结构一致；`item_id`/`title` 供翻页与脚本逻辑。"""
        if not isinstance(item, dict):
            return {}
        res = KnowledgeBaseService._api_item_to_card_resource(item)
        rid = str(res.get("resourceId") or "").strip()
        name = str(res.get("folderName") or res.get("name") or "").strip()
        return {"item_id": rid, "title": name, "resource": res}

    @classmethod
    def _find_resource_via_list(
        cls,
        kb_id: str,
        parent_resource_id: str = "",
        resource_id: str = "",
        name: str = "",
    ) -> Optional[dict]:
        """在 resource/list 结果中按 resourceId 或文件名定位条目。"""
        rid = (resource_id or "").strip()
        nm = (name or "").strip()
        if not rid and not nm:
            return None
        parent = (parent_resource_id or "").strip()
        name_match: Optional[dict] = None
        for item in cls.list_kb_contents_all(kb_id, parent_resource_id=parent):
            res = item.get("resource") if isinstance(item.get("resource"), dict) else {}
            item_rid = str(res.get("resourceId") or "").strip()
            if rid and item_rid == rid:
                return item
            item_name = str(res.get("name") or "").strip()
            if nm and item_name == nm and name_match is None:
                name_match = item
        return name_match

    @classmethod
    def resolve_folder_display(cls, kb_id: str, folder_resource_id: str) -> tuple[str, str]:
        """解析知识库目录 resourceId 与展示名（供 knowledgeBasePath.folderId / folderName）。"""
        fid = str(folder_resource_id or "").strip()
        if not fid:
            return "", ""

        found = cls._find_resource_via_list(kb_id, "", resource_id=fid)
        if found:
            res = found.get("resource") if isinstance(found.get("resource"), dict) else {}
            name = str(res.get("folderName") or res.get("name") or "").strip()
            return fid, name

        queue: deque[str] = deque([""])
        visited_parents: set[str] = set()
        while queue:
            parent = queue.popleft()
            if parent in visited_parents:
                continue
            visited_parents.add(parent)
            for item in cls.list_kb_contents_all(kb_id, parent):
                res = item.get("resource") if isinstance(item.get("resource"), dict) else {}
                rid = str(res.get("resourceId") or "").strip()
                if rid == fid:
                    name = str(res.get("folderName") or res.get("name") or "").strip()
                    return fid, name
                if str(res.get("type") or "").lower() == "folder" and rid:
                    queue.append(rid)
        return fid, ""

    @staticmethod
    def build_knowledge_base_path_entry(
        kb_id: str,
        base_name: str,
        folder_id: str,
        folder_name: str,
        *,
        pretext: str = "点击去查看:",
        button: str = "去查看",
    ) -> Dict[str, str]:
        return {
            "baseId": str(kb_id or "").strip(),
            "baseName": str(base_name or "").strip(),
            "folderId": str(folder_id or "").strip(),
            "folderName": str(folder_name or "").strip(),
            "pretext": pretext,
            "button": button,
        }

    @classmethod
    def _enrich_upload_result(
        cls,
        kb_id: str,
        folder_id: str,
        file_name: str,
        result: dict,
    ) -> dict:
        """上传完成后用 resource/list 富化 resource，与 list_contents 卡片字段一致。"""
        res = result.get("resource") if isinstance(result.get("resource"), dict) else None
        rid = str(res.get("resourceId") or "").strip() if res else ""
        found = cls._find_resource_via_list(
            kb_id,
            parent_resource_id=folder_id or "",
            resource_id=rid,
            name=file_name,
        )
        if found and isinstance(found.get("resource"), dict):
            out = dict(result)
            out["resource"] = found["resource"]
            return out
        return result

    @classmethod
    def get_knowledge_base(cls, kb_id: str) -> dict:
        data = APIClient.post(f"{KB_API_PREFIX}/base/batchGet", {"baseIdList": [kb_id]})
        items = data if isinstance(data, list) else data.get("baseList", [])
        if not items:
            raise CliError(f"知识库不存在: {kb_id}", EXIT_BUSINESS_ERROR)
        return cls._normalize_kb(items[0])

    @classmethod
    def assert_kb_name_available(cls, name: str, exclude_kb_id: str = "") -> str:
        target = (name or "").strip()
        if not target:
            raise CliError("name 不能为空。", EXIT_INPUT_ERROR)
        
        for kb in cls.list_all_knowledge_bases(page_size=200):
            if kb.get("name", "").strip() == target:
                if exclude_kb_id and kb.get("kb_id", "").strip() == exclude_kb_id.strip():
                    return target
                raise CliError(
                    f"知识库名称「{target}」已存在（kb_id={kb.get('kb_id','')}）。请改名后重试。", 
                    EXIT_BUSINESS_ERROR
                )
        return target

    @classmethod
    def create_knowledge_base(cls, name: str) -> dict:
        target_name = cls.assert_kb_name_available(name)
        data = APIClient.post(
            f"{KB_API_PREFIX}/create", 
            {"name": target_name, "description": "", "openLevel": 0}
        )
        base = cls._normalize_kb(data.get("base", {}))
        
        if base.get("kb_id"):
            return cls.get_knowledge_base(base["kb_id"])
            
        # 兼容兜底方案：如果建库接口未返回全量字段，尝试再次全量拉取过滤
        for kb in cls.list_all_knowledge_bases(page_size=200):
            if kb.get("name", "").strip() == target_name:
                return kb
        return base

    @classmethod
    def update_knowledge_base(cls, kb_id: str, name: str) -> dict:
        if not (kb_id or "").strip():
            raise CliError("kb_id 不能为空。", EXIT_INPUT_ERROR)
            
        target_name = cls.assert_kb_name_available(name, exclude_kb_id=kb_id)
        data = APIClient.post(
            f"{KB_API_PREFIX}/update", 
            {"baseId": kb_id.strip(), "name": target_name}
        )
        return cls._normalize_kb(data.get("base", {}))

    @classmethod
    def list_kbs_page(cls, page: int, page_size: int, cursor: str = "") -> Dict[str, Any]:
        """获取单页知识库列表，支持传入游标。"""
        payload = {"pageInfo": {"page": int(page), "pageSize": int(page_size)}}
        
        # 核心修复：将游标带入请求中
        if cursor:
            # 兼容处理：通常中移动体系的游标放在 pageInfo 内，部分接口在最外层，一并带上防坑
            payload["pageInfo"]["nextPageCursor"] = cursor
            payload["nextPageCursor"] = cursor

        data = APIClient.post(f"{KB_API_PREFIX}/list", payload)
        
        result = {
            "list": [cls._normalize_kb(item) for item in data.get("baseList", [])],
            "total": int(data.get("totalCount", 0) or 0),
        }
        
        if "nextPageCursor" in data:
            result["next_page_cursor"] = data["nextPageCursor"]
            
        return result

    @classmethod
    def list_all_knowledge_bases(cls, page_size: int = 20) -> List[dict]:
        """拉取全部知识库列表，已修复游标状态丢失问题。"""
        all_items: List[dict] = []
        page = 1
        prev_page_signature: Optional[List[str]] = None
        current_cursor = ""  # 新增：维护当前游标状态
        
        while True:
            # 发起请求时带上 cursor
            result = cls.list_kbs_page(page, page_size, cursor=current_cursor)
            items = result.get("list", [])
            page_signature = [str(item.get("kb_id", "")) for item in items]

            # 触发这里的条件大概率是因为上一页和这一页数据一样（比如上游忽略了 page 且没传 cursor）
            if prev_page_signature is not None and page_signature == prev_page_signature:
                break

            all_items.extend(items)
            
            if not items:
                break
                
            total = result.get("total", 0)
            if total and len(all_items) >= total:
                break

            # 提取下一页的游标，准备给下一次循环使用
            if "next_page_cursor" in result:
                current_cursor = result.get("next_page_cursor")
                if not current_cursor:  # 最后一页 cursor 为空
                    break
            else:
                if len(items) < page_size:
                    break

            prev_page_signature = page_signature
            page += 1
            
        return all_items

    @classmethod
    def list_kb_contents_all(
        cls,
        kb_id: str,
        parent_resource_id: str = "",
        resource_type: Optional[int] = None,
        page_size: int = 20,
    ) -> List[dict]:
        """拉取指定知识库下的全部内容，同步升级带游标的自动翻页逻辑。"""
        all_items: List[dict] = []
        page = 1
        prev_page_signature: Optional[List[str]] = None
        current_cursor = ""  # 新增：维护当前游标状态
        
        while True:
            payload = {
                "baseId": kb_id,
                "pageInfo": {"page": page, "pageSize": page_size},
            }
            
            # 核心修复：将游标带入请求中
            if current_cursor:
                payload["pageInfo"]["nextPageCursor"] = current_cursor
                payload["nextPageCursor"] = current_cursor
                
            if parent_resource_id:
                payload["parentResoureId"] = parent_resource_id
            if resource_type is not None:
                payload["resourceType"] = int(resource_type)
                
            data = APIClient.post(f"{KB_API_PREFIX}/resource/list", payload)
            items = [cls._normalize_resource(item) for item in data.get("list", [])]
            page_signature = [str(item.get("item_id", "")) for item in items]

            if prev_page_signature is not None and page_signature == prev_page_signature:
                break

            all_items.extend(items)
            
            if not items:
                break
                
            total = int(data.get("totalCount", 0) or 0)
            if total and len(all_items) >= total:
                break

            # 提取下一页的游标
            if "nextPageCursor" in data:
                current_cursor = data["nextPageCursor"]
                if not current_cursor:
                    break
            else:
                if len(items) < page_size:
                    break

            prev_page_signature = page_signature
            page += 1
            
        return all_items

    @classmethod
    def check_import_url(cls, url: str) -> dict:
        data = APIClient.post(
            f"{KB_API_PREFIX}/importResource/check", 
            {"resourceType": 3, "htmlUrl": url}
        )
        if not data.get("checkResult", False):
            raise CliError(data.get("failMessage", "网页链接校验失败"), EXIT_BUSINESS_ERROR)
        return {"check_result": True}

    @classmethod
    def batch_import_resources(
        cls,
        kb_id: str,
        resource_type: int,
        file_id_list: Optional[List[str]] = None,
        html_url: str = "",
        html_title: str = "",
        parent_file_id: str = "",
    ) -> dict:
        if resource_type not in {0, 3}:
            raise CliError("resource_type 仅支持 0（云盘文件）或 3（在线链接）。", EXIT_INPUT_ERROR)
            
        payload = {"resourceType": int(resource_type), "baseId": kb_id}
        if parent_file_id and parent_file_id != "/":
            payload["parentFileId"] = parent_file_id
            
        if resource_type == 0:
            file_ids = [str(x).strip() for x in (file_id_list or []) if str(x).strip()]
            if not file_ids:
                raise CliError("resource_type=0 时必须至少传一个 --cloud-file-id。", EXIT_INPUT_ERROR)
            payload["fileList"] = [{"fileId": fid} for fid in file_ids]
        else:
            url = html_url.strip()
            if not url:
                raise CliError("resource_type=3 时必须传 --html-url。", EXIT_INPUT_ERROR)
            cls.check_import_url(url)
            payload["htmlInfo"] = {"url": url}
            if html_title.strip():
                payload["htmlInfo"]["title"] = html_title.strip()
                
        data = APIClient.post(f"{KB_API_PREFIX}/file/batchImport", payload)
        return {"task_id": data.get("taskId", ""), "raw": data}

    @classmethod
    def import_url(cls, kb_id: str, url: str, title: str = "", folder_id: str = "") -> dict:
        result = cls.batch_import_resources(
            kb_id=kb_id,
            resource_type=3,
            html_url=url,
            html_title=title,
            parent_file_id=folder_id,
        )
        return {
            "status": "processing", 
            "task_id": result.get("task_id", ""), 
            "title": title or url
        }

    @classmethod
    def move_resources(cls, kb_id: str, resource_id_list: List[str], to_parent_file_id: str) -> dict:
        if not resource_id_list:
            raise CliError("resource_id_list 不能为空。", EXIT_INPUT_ERROR)
        data = APIClient.post(
            f"{KB_API_PREFIX}/resource/batchMove",
            {"baseId": kb_id, "resourceIdList": resource_id_list, "toParentFileId": to_parent_file_id},
            timeout=max(setting.timeout, 60),
        )
        return {"task_id": data.get("taskId", ""), "resource_id_list": resource_id_list}

    @classmethod
    def create_folder(
        cls, 
        kb_id: str, 
        name: str, 
        parent_file_id: str = "/", 
        rename_mode: str = "force_rename"
    ) -> dict:
        data = APIClient.post(
            f"{KB_API_PREFIX}/folder/create",
            {"baseId": kb_id, "name": name, "parentFileId": parent_file_id, "renameMode": rename_mode},
        )
        return cls._normalize_resource(data.get("resource", data))

    @classmethod
    def update_resource(cls, kb_id: str, resource_id: str, name: str, rename_mode: str = "force_rename") -> dict:
        data = APIClient.post(
            f"{KB_API_PREFIX}/resource/update",
            {"baseId": kb_id, "resourceId": resource_id, "name": name, "renameMode": rename_mode},
        )
        return cls._normalize_resource(data.get("resource", data))

    # --- 核心文件上传体系 ---

    @classmethod
    def _create_upload_task(
        cls,
        kb_id: str,
        name: str,
        size: int,
        part_infos: Optional[list] = None,
        folder_id: str = "",
        content_hash: str = "",
        form_upload: bool = False,
        parallel_upload: bool = False,
    ) -> dict:
        payload = {
            "baseId": kb_id,
            "name": name,
            "size": size,
            "uploadType": "1",
            "fileRenameMode": "force_rename",
        }
        if folder_id:
            payload["parentFileId"] = folder_id
        if content_hash:
            payload["contentHash"] = content_hash
            payload["contentHashAlgorithm"] = "sha256"
            
        if form_upload:
            payload["formUpload"] = True
        else:
            payload["parallelUpload"] = bool(parallel_upload)
            payload["partInfos"] = [
                {
                    "partNumber": item["partNumber"],
                    "partSize": item["partSize"],
                    "partOffset": item["partOffset"],
                    "parallelUpload": bool(parallel_upload),
                }
                for item in (part_infos or [])
            ]
            
        data = APIClient.post(f"{KB_API_PREFIX}/file/upload/createFile", payload)
        return {
            "file_id": data.get("fileId", ""),
            "upload_id": data.get("uploadId", ""),
            "rapid_upload": bool(data.get("rapidUpload", False)),
            "form_info": data.get("formInfo", {}),
            "part_infos": data.get("partInfos", []),
        }

    @classmethod
    def _get_upload_urls(cls, file_id: str, upload_id: str, part_infos: list) -> dict:
        data = APIClient.post(
            f"{KB_API_PREFIX}/file/upload/getUploadUrl",
            {"fileId": file_id, "uploadId": upload_id, "partInfos": part_infos},
        )
        return {"part_infos": data.get("partInfos", [])}

    @classmethod
    def _complete_upload(cls, kb_id: str, file_id: str, upload_id: str, content_hash: str) -> dict:
        data = APIClient.post(
            f"{KB_API_PREFIX}/file/upload/complete",
            {
                "baseId": kb_id,
                "fileId": file_id,
                "uploadId": upload_id,
                "uploadType": "1",
                "contentHash": content_hash,
                "contentHashAlgorithm": "sha256",
            },
        )
        return cls._normalize_resource(data.get("resource", data))

    @classmethod
    def upload_file(cls, kb_id: str, file_path: str, folder_id: str = "") -> dict:
        """上传本地文件到知识库并自动选择上传模式。"""
        if not os.path.exists(file_path):
            raise CliError(f"文件不存在: {file_path}", EXIT_INPUT_ERROR)

        _, ext = os.path.splitext(file_path)
        if ext.lower() not in _UPLOAD_ALLOWED_EXTS:
            raise CliError(
                "仅支持 pdf/docx/doc/xlsx/xls/pptx/ppt 格式，请转换后重试",
                EXIT_INPUT_ERROR,
            )
            
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        content_hash = FileUtils.calc_sha256(file_path)

        # 模式一：表单直传
        if file_size <= MAX_FORM_UPLOAD_SIZE:
            task = cls._create_upload_task(
                kb_id=kb_id,
                name=file_name,
                size=file_size,
                folder_id=folder_id,
                content_hash=content_hash,
                form_upload=True,
            )
            if task.get("rapid_upload"):
                return cls._enrich_upload_result(
                    kb_id,
                    folder_id,
                    file_name,
                    {"title": file_name, "status": "completed", "upload_mode": "rapid"},
                )

            form_info = task.get("form_info", {})
            with open(file_path, "rb") as f:
                APIClient.post_form(
                    url=form_info.get("uploadUrl", ""),
                    form_data=form_info.get("formData", {}),
                    files={form_info.get("dataField", "file"): (file_name, f)},
                )
            result = cls._complete_upload(kb_id, task["file_id"], task["upload_id"], content_hash)
            result["upload_mode"] = "form"
            return cls._enrich_upload_result(kb_id, folder_id, file_name, result)

        # 模式二：分片上传
        part_size = FileUtils.recommend_part_size(file_size)
        part_infos = FileUtils.build_part_infos(file_size, part_size=part_size)
        
        task = cls._create_upload_task(
            kb_id=kb_id,
            name=file_name,
            size=file_size,
            folder_id=folder_id,
            content_hash=content_hash,
            part_infos=part_infos[:MAX_PARTS_PER_REQUEST],
            parallel_upload=True,
        )
        if task.get("rapid_upload"):
            return cls._enrich_upload_result(
                kb_id,
                folder_id,
                file_name,
                {"title": file_name, "status": "completed", "upload_mode": "rapid"},
            )

        file_id = task.get("file_id", "")
        upload_id = task.get("upload_id", "")
        
        # 共享同一个文件句柄以优化 I/O 性能
        with open(file_path, "rb") as f:
            for index in range(0, len(part_infos), MAX_PARTS_PER_REQUEST):
                batch = part_infos[index : index + MAX_PARTS_PER_REQUEST]
                
                remote_parts = task.get("part_infos", []) if index == 0 else \
                               cls._get_upload_urls(file_id, upload_id, batch).get("part_infos", [])
                               
                if len(remote_parts) != len(batch):
                    raise CliError(
                        f"分片上传地址数量不匹配: expected={len(batch)}, actual={len(remote_parts)}",
                        EXIT_INTERNAL_ERROR,
                    )
                    
                for remote_part, local_part in zip(remote_parts, batch):
                    f.seek(local_part["partOffset"])
                    body = f.read(local_part["partSize"])
                    APIClient.put_raw(
                        url=remote_part.get("uploadUrl", ""), 
                        data=body, 
                        error_context="分片上传"
                    )
                    
        result = cls._complete_upload(kb_id, file_id, upload_id, content_hash)
        result["upload_mode"] = "multipart"
        return cls._enrich_upload_result(kb_id, folder_id, file_name, result)


# -----------------------------------------------------------------------------
# CLI 展现与交互控制层
# -----------------------------------------------------------------------------
class CliController:
    """处理 CLI 请求绑定并格式化打印输出。"""
    
    @staticmethod
    def _item_to_str(item: dict) -> str:
        r = item.get("resource") if isinstance(item.get("resource"), dict) else {}
        node = str(r.get("type") or r.get("category") or "").lower()
        icon = "📁" if node == "folder" else "📄"
        try:
            size_kb = int(r.get("size") or 0) // 1024
        except (TypeError, ValueError):
            size_kb = 0
        rid = item.get("item_id", "")
        label = item.get("title") or r.get("folderName") or r.get("name") or "（无标题）"
        ext = str(r.get("fileExtension") or r.get("category") or "")
        return (
            f"{icon} {label} [{ext}] "
            f"大小: {size_kb} KB  创建时间: {r.get('createdAt', '')}  "
            f"resourceId: {rid}"
        )

    @staticmethod
    def _emit_jsonl(data: Dict[str, Any]) -> None:
        """stdout JSONL；trace_id 出现在 record=meta 与 record=error（响应头 trace_id）。"""
        ordered: Dict[str, Any] = {}
        if data.get('record') in ('meta', 'error'):
            tid = meta_trace_id()
            if tid:
                ordered['trace_id'] = tid
        if data.get('record') == 'meta' and data.get('status') == 'success' and data.get('command'):
            ordered['renderHint'] = (
                f'已完成{data["command"]}，输出前必须阅读 '
                'cm_cloud_render_format/index.md'
                ' 并严格遵循输出规范，以卡片格式展示结果'
            )
        for key in ('record', 'status', 'command', 'message'):
            if key in data:
                ordered[key] = data[key]
        for key, val in data.items():
            if key not in ordered:
                ordered[key] = val
        write_cli_output_line(json.dumps(ordered, ensure_ascii=False))

    @classmethod
    def _emit_meta(
        cls,
        *,
        command: str,
        total_count: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "record": "meta",
            "status": "success",
            "command": command,
            "totalCount": int(total_count),
            "message": str(message),
        }
        if extra:
            payload.update(extra)
        cls._emit_jsonl(payload)

    @classmethod
    def _emit_error(cls, *, command: str, message: str) -> None:
        snapshot_trace_id()
        cls._emit_jsonl({"record": "error", "status": "error", "command": command, "message": message})

    @staticmethod
    def _build_kb_record(kb: Dict[str, Any]) -> Dict[str, Any]:
        """将知识库对象映射为统一输出字段。"""
        return {
            "baseId": str(kb.get("kb_id") or ""),
            "baseName": str(kb.get("name") or ""),
        }

    @staticmethod
    def _emit_knowledge_base_resource_line(
        resource: Dict[str, Any],
        base_name: str,
        *,
        with_render_hint: bool = False,
        index: int = 0,
    ) -> None:
        """一行 CLI JSONL：`list_contents` 等与 `POST .../knowledgeBase/resource/list` 对齐，`resource` 与 `:::knowledgeBaseReference` 单行同构（外加 `record`）。"""
        if not isinstance(resource, dict):
            return
        rid = str(resource.get("resourceId") or "").strip()
        bid = str(resource.get("baseId") or "").strip()
        if not rid or not bid:
            return
        payload: Dict[str, Any] = {
            "record": "resource",
            "resource": dict(resource),
            "baseName": str(base_name or ""),
        }
        if index > 0:
            payload["index"] = index
        if with_render_hint:
            payload["renderCard"] = "knowledgeBaseReference"
        CliController._emit_jsonl(payload)

    @staticmethod
    def _emit_knowledge_base_path_line(
        path_entry: Dict[str, Any],
        *,
        with_render_hint: bool = False,
    ) -> None:
        if not path_entry.get("baseId"):
            return
        payload: Dict[str, Any] = {
            "record": "kbPath",
            **path_entry,
        }
        if with_render_hint:
            payload["renderCard"] = "knowledgeBasePath"
        CliController._emit_jsonl(payload)

    @classmethod
    def cmd_create_kb(cls, args: argparse.Namespace) -> None:
        result = KnowledgeBaseService.create_knowledge_base(args.name)
        snapshot_trace_id()
        cls._emit_meta(command="create_kb", total_count=1, message="创建知识库请求成功")
        cls._emit_jsonl({"record": "kb", **cls._build_kb_record(result)})

    @classmethod
    def cmd_update_kb(cls, args: argparse.Namespace) -> None:
        result = KnowledgeBaseService.update_knowledge_base(args.kb_id, args.name)
        snapshot_trace_id()
        cls._emit_meta(command="update_kb", total_count=1, message="更新知识库请求成功")
        cls._emit_jsonl({"record": "kb", **cls._build_kb_record(result)})

    @classmethod
    def cmd_list_kbs(cls, args: argparse.Namespace) -> None:
        items = KnowledgeBaseService.list_all_knowledge_bases(page_size=args.page_size)
        snapshot_trace_id()
        n = len(items)
        cls._emit_meta(
            command="list_kbs",
            total_count=n,
            message="查询成功，未命中知识库" if n == 0 else f"共 {n} 个知识库",
            extra={},
        )
        for idx, kb in enumerate(items, start=1):
            cls._emit_jsonl({"record": "kb", "index": idx, **cls._build_kb_record(kb)})

    @classmethod
    def cmd_upload_file(cls, args: argparse.Namespace) -> None:
        result = KnowledgeBaseService.upload_file(args.kb_id, args.file, folder_id=args.kb_folder_id or "")
        kb = KnowledgeBaseService.get_knowledge_base(args.kb_id)
        snapshot_trace_id()
        res = result.get("resource") if isinstance(result.get("resource"), dict) else None
        if res and str(res.get("resourceId") or "").strip():
            res = dict(res)
            if not str(res.get("baseId") or "").strip():
                res["baseId"] = str(args.kb_id)
            cls._emit_meta(command="upload_file", total_count=1, message="上传成功")
            cls._emit_knowledge_base_resource_line(res, str(kb.get("name", "")), index=1)
        else:
            cls._emit_meta(command="upload_file", total_count=0, message="上传请求已提交")
            cls._emit_jsonl({
                "record": "task",
                "status": str(result.get("status") or ""),
                "uploadMode": str(result.get("upload_mode") or ""),
                "name": str(result.get("title") or os.path.basename(args.file)),
                "baseId": str(args.kb_id),
                "baseName": str(kb.get("name", "")),
            })

    @classmethod
    def cmd_import_check(cls, args: argparse.Namespace) -> None:
        KnowledgeBaseService.check_import_url(args.html_url)
        snapshot_trace_id()
        cls._emit_meta(command="import_check", total_count=1, message="网页链接通过导入校验")
        cls._emit_jsonl({"record": "check", "checkResult": True})

    @classmethod
    def cmd_import_url(cls, args: argparse.Namespace) -> None:
        result = KnowledgeBaseService.import_url(
            args.kb_id, args.url, title=args.title or "", folder_id=args.kb_folder_id or ""
        )
        kb = KnowledgeBaseService.get_knowledge_base(args.kb_id)
        snapshot_trace_id()
        cls._emit_meta(command="import_url", total_count=1, message="导入请求已提交")
        cls._emit_jsonl({
            "record": "task",
            "status": str(result.get("status", "")),
            "taskId": str(result.get("task_id", "")),
            "name": str(result.get("title", "")),
            "baseId": str(args.kb_id),
            "baseName": str(kb.get("name", "")),
        })

    @classmethod
    def cmd_batch_import(cls, args: argparse.Namespace) -> None:
        try:
            cloud_file_ids = validate_cloud_file_ids(
                args.cloud_file_id_list,
                context="cloud_file_id_list",
            )
        except ValueError as exc:
            raise CliError(str(exc), EXIT_INPUT_ERROR) from exc
        result = KnowledgeBaseService.batch_import_resources(
            kb_id=args.kb_id,
            resource_type=args.resource_type,
            file_id_list=cloud_file_ids,
            html_url=args.html_url or "",
            html_title=args.html_title or "",
            parent_file_id=args.kb_folder_id or "",
        )
        kb = KnowledgeBaseService.get_knowledge_base(args.kb_id)
        snapshot_trace_id()
        cls._emit_meta(command="batch_import", total_count=1, message="批量导入请求已提交")
        cls._emit_jsonl({
            "record": "task",
            "taskId": str(result.get("task_id", "")),
            "baseId": str(args.kb_id),
            "baseName": str(kb.get("name", "")),
            "resourceType": int(args.resource_type),
        })

    @classmethod
    def cmd_list_contents(cls, args: argparse.Namespace) -> None:
        if args.resource_type is not None and args.resource_type not in (0, 3):
            raise CliError("本技能仅支持 --resource-type 0（云盘文件）或 3（在线链接）。", EXIT_INPUT_ERROR)
            
        items = KnowledgeBaseService.list_kb_contents_all(
            kb_id=args.kb_id,
            parent_resource_id=args.kb_folder_id or "",
            resource_type=args.resource_type,
            page_size=args.page_size,
        )
        kb = KnowledgeBaseService.get_knowledge_base(args.kb_id)
        resources: List[Dict[str, Any]] = []
        for item in items:
            raw = item.get("resource") if isinstance(item.get("resource"), dict) else None
            if not raw or not str(raw.get("resourceId") or "").strip():
                continue
            res = dict(raw)
            if not str(res.get("baseId") or "").strip():
                res["baseId"] = str(args.kb_id)
            resources.append(res)
        snapshot_trace_id()
        n = len(resources)
        extra: Dict[str, Any] = {
            "baseId": str(args.kb_id),
            "baseName": str(kb.get("name", "")),
        }
        folder_id, folder_name = KnowledgeBaseService.resolve_folder_display(
            str(args.kb_id),
            str(args.kb_folder_id or ""),
        )
        path_entry = KnowledgeBaseService.build_knowledge_base_path_entry(
            str(args.kb_id),
            str(kb.get("name", "")),
            folder_id,
            folder_name,
        )
        if n > 0:
            extra["renderCards"] = ["knowledgeBaseReference", "knowledgeBasePath"]
        cls._emit_meta(
            command="list_contents",
            total_count=n,
            message="查询成功，未命中资源" if n == 0 else f"共 {n} 项",
            extra=extra,
        )
        bn = str(kb.get("name", ""))
        for idx, res in enumerate(resources, start=1):
            cls._emit_knowledge_base_resource_line(res, bn, with_render_hint=True, index=idx)
        if n > 0:
            cls._emit_knowledge_base_path_line(path_entry, with_render_hint=True)

    @classmethod
    def cmd_resource_batch_move(cls, args: argparse.Namespace) -> None:
        result = KnowledgeBaseService.move_resources(
            args.kb_id, args.kb_resource_id_list, args.kb_target_folder_id
        )
        snapshot_trace_id()
        kb = KnowledgeBaseService.get_knowledge_base(args.kb_id)
        cls._emit_meta(command="resource_batch_move", total_count=1, message="移动请求已提交")
        cls._emit_jsonl({
            "record": "task",
            "taskId": str(result.get("task_id", "")),
            "baseId": str(args.kb_id),
            "resourceIdList": result.get("resource_id_list", []),
            "targetFolderId": str(args.kb_target_folder_id),
        })

    @classmethod
    def cmd_folder_create(cls, args: argparse.Namespace) -> None:
        result = KnowledgeBaseService.create_folder(
            args.kb_id,
            args.name,
            parent_file_id=args.kb_parent_folder_id,
            rename_mode=args.rename_mode,
        )
        kb = KnowledgeBaseService.get_knowledge_base(args.kb_id)
        res = result.get("resource") if isinstance(result.get("resource"), dict) else None
        if res and str(res.get("resourceId") or "").strip():
            res = dict(res)
            if not str(res.get("baseId") or "").strip():
                res["baseId"] = str(args.kb_id)
            snapshot_trace_id()
            cls._emit_meta(command="folder_create", total_count=1, message="创建目录成功")
            cls._emit_knowledge_base_resource_line(res, str(kb.get("name", ""), index=1)

    @classmethod
    def cmd_resource_update(cls, args: argparse.Namespace) -> None:
        result = KnowledgeBaseService.update_resource(
            args.kb_id, args.kb_resource_id, args.name, rename_mode=args.rename_mode
        )
        kb = KnowledgeBaseService.get_knowledge_base(args.kb_id)
        res = result.get("resource") if isinstance(result.get("resource"), dict) else None
        if res and str(res.get("resourceId") or "").strip():
            res = dict(res)
            if not str(res.get("baseId") or "").strip():
                res["baseId"] = str(args.kb_id)
            snapshot_trace_id()
            cls._emit_meta(command="resource_update", total_count=1, message="重命名成功")
            cls._emit_knowledge_base_resource_line(res, str(kb.get("name", ""), index=1)


# -----------------------------------------------------------------------------
# 解析与主函数入口
# -----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="中国移动知识库建库与内容管理 CLI")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    p = subparsers.add_parser("create_kb", help="新建知识库")
    p.add_argument("--name", required=True, help="知识库名称")

    p = subparsers.add_parser("update_kb", help="更新知识库名称")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument("--name", required=True, help="新知识库名称")

    p = subparsers.add_parser("list_kbs", help="自动分页列出全部知识库")
    p.add_argument("--page-size", dest="page_size", type=int, default=200, help="每页返回条数，默认 200")

    p = subparsers.add_parser("upload_file", help="上传本地文件到知识库")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument("--file", required=True, help="本地文件绝对路径")
    p.add_argument("--kb-folder-id", dest="kb_folder_id", default="", help="目标知识库目录 ID")

    p = subparsers.add_parser("import_check", help="校验网页链接是否可导入")
    p.add_argument("--html-url", required=True, dest="html_url", help="待校验网页链接")

    p = subparsers.add_parser("import_url", help="导入单个网页链接")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument("--url", required=True, help="网页链接")
    p.add_argument("--title", default="", help="导入后标题")
    p.add_argument("--kb-folder-id", dest="kb_folder_id", default="", help="目标知识库目录 ID")

    p = subparsers.add_parser("batch_import", help="批量导入云盘文件或网页链接")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument(
        "--resource-type",
        required=True,
        dest="resource_type",
        type=int,
        choices=[0, 3],
        help="资源类型：0=云盘文件，3=网页链接",
    )
    p.add_argument("--cloud-file-id", action="append", dest="cloud_file_id_list", default=[], help="个人云 fileId，可重复传入多个")
    p.add_argument("--html-url", default="", dest="html_url", help="网页链接")
    p.add_argument("--html-title", default="", dest="html_title", help="网页标题")
    p.add_argument("--kb-folder-id", default="", dest="kb_folder_id", help="目标知识库目录 ID")

    p = subparsers.add_parser("list_contents", help="自动分页列出知识库资源")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument("--kb-folder-id", default="", dest="kb_folder_id", help="父目录资源 ID")
    p.add_argument("--resource-type", type=int, default=None, dest="resource_type", help="资源类型：0=云盘文件，3=在线链接；不传不限")
    p.add_argument("--page-size", dest="page_size", type=int, default=20, help="每页返回条数，默认 20")

    p = subparsers.add_parser("resource_batch_move", help="批量移动资源")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument("--kb-resource-id", action="append", required=True, dest="kb_resource_id_list", help="资源 ID，可重复")
    p.add_argument("--kb-target-folder-id", required=True, dest="kb_target_folder_id", help="目标目录资源 ID")

    p = subparsers.add_parser("folder_create", help="创建知识库文件夹")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument("--name", required=True, help="目录名称")
    p.add_argument("--kb-parent-folder-id", default="/", dest="kb_parent_folder_id", help="父目录资源 ID")
    p.add_argument("--rename-mode", default="force_rename", dest="rename_mode", help="重名处理策略；默认 force_rename")

    p = subparsers.add_parser("resource_update", help="重命名知识库资源")
    p.add_argument("--kb-id", required=True, dest="kb_id", help="知识库 ID")
    p.add_argument("--kb-resource-id", required=True, dest="kb_resource_id", help="资源 ID")
    p.add_argument("--name", required=True, help="新资源名称")
    p.add_argument("--rename-mode", default="force_rename", dest="rename_mode", help="重名处理策略；默认 force_rename")

    return parser


def main() -> int:
    """程序入口并负责命令分发。"""
    parser = build_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return EXIT_INPUT_ERROR
        
    command_dispatch = {
        "create_kb": CliController.cmd_create_kb,
        "update_kb": CliController.cmd_update_kb,
        "list_kbs": CliController.cmd_list_kbs,
        "upload_file": CliController.cmd_upload_file,
        "import_check": CliController.cmd_import_check,
        "import_url": CliController.cmd_import_url,
        "batch_import": CliController.cmd_batch_import,
        "list_contents": CliController.cmd_list_contents,
        "resource_batch_move": CliController.cmd_resource_batch_move,
        "folder_create": CliController.cmd_folder_create,
        "resource_update": CliController.cmd_resource_update,
    }

    clear_api_timings()
    start_cli_output_buffer()
    exit_code = EXIT_OK
    try:
        handler = command_dispatch.get(args.command)
        if handler:
            handler(args)
        else:
            exit_code = EXIT_INPUT_ERROR
    except CliError as exc:
        cmd = str(getattr(args, "command", "") or "")
        CliController._emit_error(command=cmd, message=str(exc))
        exit_code = exc.exit_code
    except Exception as exc:
        cmd = str(getattr(args, "command", "") or "")
        CliController._emit_error(command=cmd, message=f"内部错误: {exc}")
        exit_code = EXIT_INTERNAL_ERROR
    finally:
        flush_cli_output_buffer()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
