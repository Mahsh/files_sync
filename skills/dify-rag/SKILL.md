---
name: dify-rag
description: "Dify.AI 线上 RAG 知识库集成：检索共享知识库、上传文档，支持多 OpenClaw 实例共享"
user-invocable: true
allowed-tools:
  - exec
  - read
  - write
  - web_fetch
---

# Dify.AI RAG 知识库集成 Skill

通过 Dify.ai 线上 RAG 服务，实现跨 OpenClaw 实例共享的云手机研发知识库。

## 设计动机

| 方案 | 优势 | 劣势 |
|------|------|------|
| 本地 `memory_search` | 零依赖、快 | 仅本机可用，无法跨实例共享 |
| Dify.AI 线上 RAG | 多 OpenClaw 共享、统一管理、支持海量文档 | 需联网、有 API 延迟 |

本 Skill 作为**所有其他 Skill 的公共检索层**，tech-research / prd-generator / tech-doc / git-summary 在需要检索知识库时统一调用本 Skill。

## 配置

在 `workspace/TOOLS.md` 或环境变量中配置以下参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| `DIFY_API_BASE` | Dify API 地址 | `https://api.dify.ai` 或自部署地址 |
| `DIFY_API_KEY` | Dify API Key（知识库读写权限） | `app-xxxxxxxxxxxx` |
| `DIFY_DATASET_ID` | 知识库 ID | `dataset-uuid` |

也可通过环境变量传入：
```
DIFY_API_BASE=https://api.dify.ai
DIFY_API_KEY=app-xxxxxxxxxxxx
DIFY_DATASET_ID=dataset-uuid
```

## 核心接口

### 1. 检索知识库（retrieve）

用 `exec` 执行 curl 调用 Dify 检索 API：

```bash
curl -s -X POST "${DIFY_API_BASE}/v1/datasets/${DIFY_DATASET_ID}/retrieve" \
  -H "Authorization: Bearer ${DIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"query":"WebRTC 弱网自适应","top_k":5,"score_threshold":0.5}'
```

返回 JSON 中 `records[]` 包含：
- `content`：文档片段内容
- `title`：文档标题
- `score`：相关性分数
- `metadata`：元信息

**调用方式**：其他 Skill 通过 `exec` 执行上述 curl 命令，解析返回 JSON 提取相关内容。

### 2. 上传文档（upload）

用文本创建文档：

```bash
curl -s -X POST "${DIFY_API_BASE}/v1/datasets/${DIFY_DATASET_ID}/document/create_by_text" \
  -H "Authorization: Bearer ${DIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"name":"文档标题","text":"文档内容...","indexing_technique":"high_quality","process_rule":{"mode":"automatic"}}'
```

### 3. 批量导入（batch_import）

调用 `scripts/batch_import.py` 脚本批量上传目录下所有 Markdown 文件：

```bash
python scripts/batch_import.py --api-base $DIFY_API_BASE --api-key $DIFY_API_KEY --dataset-id $DIFY_DATASET_ID --dir ./memory/knowledge-base/cloud-phone
```

## 其他 Skill 调用方式

其他 Skill 不直接调 Dify API，而是：
1. 用 `exec` 执行 curl 调用 Dify 检索
2. 解析返回的 JSON
3. 提取 `records[].content` 作为检索结果

示例（在 prd-generator 中）：

```
## 检索历史 PRD（Dify RAG）
用 exec 执行：
curl -s -X POST "$DIFY_API_BASE/v1/datasets/$DIFY_DATASET_ID/retrieve" \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"云手机 PRD 需求文档","top_k":5}'
解析返回 JSON，提取 records[].content 作为参考。
```

## 注意事项

- API Key 存储在 TOOLS.md 或环境变量中，不硬编码到 Skill 文件
- 检索失败时降级到本地 `memory_search`（如果可用）
- 批量导入时注意 Dify 的 QPS 限制，建议间隔 1-2 秒
- 文档更新时需要先删除旧文档再上传新文档
