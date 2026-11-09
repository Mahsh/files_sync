#!/usr/bin/env node
/**
 * Intent Router - 智能体路由引擎
 * 
 * 在 OpenClaw Gateway 接收用户消息后、加载 Skill 前，
 * 通过 rules.json 计算每条规则与用户消息的匹配度，
 * 返回最高分的 Skill 名。
 * 
 * 使用方式（由外部调用）：
 *   node intent-router.js "帮我调研云手机推流技术"
 *   # 输出: {"matched": "tech-research", "score": 0.9, "rule": {...}}
 */

const fs = require('fs');
const path = require('path');

const RULES_PATH = path.join(__dirname, 'rules.json');

/**
 * 核心路由逻辑
 */
function route(message) {
  const config = JSON.parse(fs.readFileSync(RULES_PATH, 'utf8'));
  const rules = config.rules;
  const msg = message.toLowerCase().trim();

  let bestMatch = null;
  let bestScore = 0;

  for (const rule of rules) {
    if (!rule.keywords || rule.keywords.length === 0) continue;

    // 关键词匹配得分
    let matchCount = 0;
    const matchedKeywords = [];
    for (const kw of rule.keywords) {
      if (msg.includes(kw.toLowerCase())) {
        matchCount++;
        matchedKeywords.push(kw);
      }
    }

    if (matchCount === 0) continue;

    // 综合得分 = 命中词数 / 规则总词数 * 权重
    const keywordScore = matchCount / rule.keywords.length;
    const totalScore = keywordScore * (rule.priority / 10);

    if (totalScore > bestScore) {
      bestScore = totalScore;
      bestMatch = {
        skill: rule.skill,
        intent: rule.intent,
        score: Math.round(totalScore * 100) / 100,
        matched_keywords: matchedKeywords,
        priority: rule.priority,
      };
    }
  }

  return bestMatch ? { ...bestMatch, rule: config.routing_engine } : null;
}

// CLI 模式
if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error('Usage: node intent-router.js "<user message>"');
    process.exit(1);
  }

  const result = route(args.join(' '));
  console.log(JSON.stringify(result, null, 2));
}

module.exports = { route };
