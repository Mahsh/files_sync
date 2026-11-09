# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Dify.AI RAG 配置

云手机研发知识库托管在 Dify.ai，多个 OpenClaw 实例共享同一知识库。

```
DIFY_API_BASE=https://api.dify.ai
DIFY_API_KEY=app-xxxxxxxxxxxx
DIFY_DATASET_ID=dataset-uuid
```

- API Key 在 Dify 知识库设置页获取
- Dataset ID 在知识库列表页获取
- 配置方式：写入本文件，或设为环境变量
- 批量导入：`python skills/dify-rag/scripts/batch_import.py --dir ./memory/knowledge-base/cloud-phone`

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Related

- [Agent workspace](/concepts/agent-workspace)
