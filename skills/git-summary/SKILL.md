---
name: git-summary
description: "Git 提交总结智能体：分析 git diff，自动生成结构化变更总结，识别影响面和风险提示"
user-invocable: true
allowed-tools:
  - exec
  - read
  - write
---

# Git 提交总结智能体

面向云手机研发的代码变更总结 Skill，支持单分支/多分支 `git diff` 分析、影响面识别、风险提示和结构化总结输出。

## 触发场景

用户提到以下意图时触发：
- "总结一下这个分支的改动"
- "生成 change summary"、"写提交说明"
- "这个 PR 改了什么"、"帮我 review 一下改动"
- "批量总结一下最近几个分支"

## 工作流程

### 1. 获取 Git 信息

使用 `exec` 执行：
- 当前分支：`git branch --show-current`
- 对比目标：`git diff <base>..<head>` 或 `git diff --stat`
- 提交历史：`git log <base>..<head> --oneline`
- 变更文件列表：`git diff --name-only`

### 2. 分析变更

按规则识别影响面：
- **协议层**：涉及 protobuf、RPC、API 定义、消息格式
- **业务层**：涉及业务逻辑、状态机、核心流程
- **配置层**：涉及配置文件、开关、环境变量
- **基础设施层**：CI/CD、构建脚本、依赖版本
- **文档层**：README、设计文档、API 文档

统计信息：
- 新增/删除/修改文件数
- 新增/删除行数
- 涉及模块/服务数

### 3. 生成总结

输出结构：

```
# 变更总结 - <分支名>

## 1. 基本信息
- 分支：feature/xxx
- 对比基线：main/develop
- 提交数：N
- 变更文件数：N
- 新增/删除行数：+N / -N

## 2. 核心改动摘要
- 改动点 1
- 改动点 2

## 3. 影响面分析
- 协议层：...
- 业务层：...
- 配置层：...
- 基础设施层：...

## 4. 风险提示
- 风险 1：描述 + 建议

## 5. 评审建议
- 建议 1

## 6. 关联信息
- 相关需求/PRD：
- 相关技术方案：
- 相关提交：
```

### 4. 批量总结

对多个分支：
- 逐个执行单分支总结
- 汇总为表格：分支名、核心改动、影响面、风险等级

### 5. 归档

- 保存到 `memory/knowledge-base/samples/git-summaries/`
- 文件名：`YYYY-MM-DD-<分支名>-change-summary.md`
- 更新 `memory/knowledge-base/INDEX.md`
- 同时上传到 Dify 知识库（见 `dify-rag` skill）

## 输出规范

- 必须包含影响面分层分析
- 风险必须有描述 + 应对建议
- 行数统计准确（基于 git diff --stat）
- 多分支时输出汇总表格
