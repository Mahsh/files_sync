---
name: tech-research
description: "技术调研智能体：自动检索、并行调研、结构化输出调研报告"
user-invocable: true
allowed-tools:
  - web_search
  - web_fetch
  - sessions_spawn
  - sessions_yield
  - write
  - read
  - exec
---

# 技术调研智能体

面向云手机研发的技术调研 Skill，支持单点深度调研和多点并行调研，输出结构化 Markdown 报告。

## 触发场景

用户提到以下关键词时触发：
- "调研"、"技术调研"、"技术预研"、"技术选型"
- "查一下XX技术"、"对比一下XX方案"
- "技术雷达"、"技术动态"

## 工作流程

### 模式一：单点深度调研

当用户要求调研**单个技术点**时：

1. **明确调研目标**
   - 提取用户的核心问题（如"WebRTC QoS降档方案"）
   - 拆分为 2-3 个子问题（现状、方案对比、落地建议）

2. **检索知识库（Dify RAG）**
   - 用 `exec` 执行 curl 调用 Dify 检索 API：
     ```bash
     curl -s -X POST "${DIFY_API_BASE}/v1/datasets/${DIFY_DATASET_ID}/retrieve" \
       -H "Authorization: Bearer ${DIFY_API_KEY}" \
       -H "Content-Type: application/json" \
       -d '{"query":"<调研关键词>","top_k":5,"score_threshold":0.5}'
     ```
   - 解析返回 JSON 中 `records[].content`，提取历史方案、术语规范、架构文档
   - 如果 Dify 不可用，降级到本地 `memory_search`

3. **多维度检索**
   - 用 `web_search` 搜索中英文资料（各 3-5 条）
   - 用 `web_fetch` 抓取高质量页面内容
   - 优先选择：官方文档、技术博客、GitHub README、论文

4. **整理报告**
   - 按模板结构输出（见 `scripts/report_template.md`）
   - 包含：背景、技术原理、方案对比、优缺点、落地建议、参考资料

5. **归档**
   - 保存到 `memory/research/` 目录，文件名格式：`YYYY-MM-DD-<关键词>.md`
   - 更新 `memory/research/INDEX.md` 索引
   - 同时上传到 Dify 知识库（见 `dify-rag` skill）

### 模式二：多点并行调研

当用户要求调研**多个技术点**时：

1. **拆分任务**
   - 将用户问题拆分为 2-4 个独立子调研
   - 每个子调研明确：关键词、检索方向、预期产出

3. **并行启动子Agent**
   - 用 `sessions_spawn` 为每个子调研启动一个子Agent
   - 每个子Agent任务描述要具体，包含：
     - 调研关键词
     - 需要回答的子问题（2-3个）
     - 输出格式要求

4. **等待并汇总**
   - 用 `sessions_yield` 等待所有子Agent完成
   - 收到结果后，整合为一份完整报告
   - 补充跨子调研的关联分析和综合建议

5. **归档**
   - 同模式一

### 模式三：技术雷达（定时触发）

通过 `cron` 定时执行，每周扫描一次技术动态：

1. **扫描关注源**
   - 读取 `assets/radar_sources.json` 中的关注列表
   - 对每个源用 `web_search` 搜索最近一周的更新

2. **筛选有价值内容**
   - 过滤噪音，保留与云手机/音视频/虚拟化相关的更新
   - 按重要性排序（重大更新 > 新功能 > 社区讨论）

3. **输出技术雷达报告**
   - 格式：每条包含 [标题] [来源] [一句话摘要] [重要程度⭐]
   - 保存并推送给用户

## 输出规范

所有调研报告必须包含以下结构（详见 `scripts/report_template.md`）：

- **标题**：简洁描述调研主题
- **背景**：为什么需要调研这个技术
- **技术概述**：核心原理和关键概念
- **方案对比**：至少2个方案，表格形式对比
- **落地建议**：结合云手机场景给出推荐
- **风险与局限**：潜在问题
- **参考资料**：所有引用的URL

## 注意事项

- 每次 `web_search` 最多取 5 条结果，避免信息过载
- 优先使用 `web_fetch` 抓取完整内容而非依赖搜索摘要
- 调研报告中的事实性陈述必须标注来源
- 中文搜索 + 英文搜索都要做，覆盖更全面
- 子Agent 并行调研时，每个子Agent 最多负责 1 个子问题
