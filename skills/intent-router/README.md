# Intent Router - 多 Skill 路由引擎

本模块替代原生的关键词匹配，实现基于**规则+权重+上下文**的智能 Intent 路由。

## 架构

```
User Message
    │
    ▼
┌─────────────────┐
│ Intent Router    │──① 解析用户意图
│ (intent-router)  │──② 计算各 Skill 得分
│                  │──③ 返回最高分 Skill
└────────┬────────┘
         │ matched_skill
         ▼
┌─────────────────┐
│ Skill Loader     │──加载 SKILL.md content
│ (built-in)       │──注入 system prompt
└────────┬────────┘
         │ enriched_prompt
         ▼
┌─────────────────┐
│ Agent Execution  │──LLM 执行
│ (deepseek-v4)    │
└─────────────────┘
```

## 使用方式

在 `workspace/intent-router/rules.json` 中定义路由规则：

```json
{
  "rules": [
    {
      "intent": "technical_research",
      "keywords": ["调研", "技术预研", "查一下", "对比"],
      "skill": "tech-research",
      "priority": 10,
      "fallback_chain": ["default"]
    },
    {
      "intent": "prd_generation",
      "keywords": ["PRD", "需求文档", "写个需求", "需求说明"],
      "skill": "prd-generator",
      "priority": 8,
      "fallback_chain": ["default"]
    },
    {
      "intent": "tech_doc",
      "keywords": ["技术方案", "技术选型", "架构图", "评审"],
      "skill": "tech-doc",
      "priority": 7,
      "fallback_chain": ["default"]
    },
    {
      "intent": "git_summary",
      "keywords": ["提交总结", "change summary", "review改动", "分支总结"],
      "skill": "git-summary",
      "priority": 6,
      "fallback_chain": ["default"]
    }
  ]
}
```

## 运行逻辑

1. 用户发消息时，先经过 `intent-router.js` 路由
2. 对每条 rule 计算匹配分数：`score = keyword_matches * weight + context_bonus`
3. 选最高分的 Skill 注入到 Gateway 的 prompt 中
4. 如果所有规则都不匹配，走默认 Skill

## 优势

- **可配置**：新 Skill 只需加一条规则，不用改 Gateway 源码
- **优先级可控**：避免多 Skill 同时命中的歧义
- **可扩展**：未来可替换为 NLP 分类器（当前关键词匹配足够覆盖研发场景）
