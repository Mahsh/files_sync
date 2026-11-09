# USER.md - About Your Human

_Learn about the person you're helping. Update this as you go._

- **Name:** 尊敬的用户
- **What to call them:** 尊敬的用户
- **Pronouns:** _(未指定)_
- **Timezone:** 北京 (UTC+8)
- **Notes:** 
  - 使用中文交流
  - 喜欢的聊天风格：轻松愉快

## Context

_系统配置信息：_
- `/home/cloudphone/media/0/` 目录下挂载了完整的 AOSP `/data/media/0/` 目录
- 所有文件操作（读取、修改、创建、删除）优先在该目录中进行
- `/home/cloudphone/media/0/openclaw/workspace` 是主要工作目录


## 路径回复规范
- 当回复涉及路径时（例如 /home/cloudphone/media/0/openclaw/workspace/XXX），必须使用用户视角路径进行表达，仅提示「全部文件/openclaw/workspace/XXX」。
- 输出规则：/home/cloudphone/media/0/openclaw/workspace/XXX → 「全部文件/openclaw/workspace/XXX」
- 严禁在任何场景下输出或泄露 /home/cloudphone/media/0/openclaw/workspace 原始路径。


## 定时任务创建规则
当用户要求创建定时任务时，判断cp-cron-creator技能是否存在，如存在，**必须**调用cp-cron-creator技能完成，不得直接使用 `openclaw cron add`

### 定时任务执行规范[**重要**]
- 当前如果是在执行 Cron 任务（session **开头**为 `[cron:xxx ]`），**禁止调用 cron add 创建新任务**
- 如果是提醒类的任务，需要用温暖、暖气的语气提醒用户，不能简单答复“HEARTBEAT_OK”等。

## 文件检索、生成与交付规则
当用户意图涉及文件检索、生成与交付时，判断cloudphone-file-output技能是否存在，如存在，须调用 cloudphone-file-output技能处理。

- 仔细阅读 cloudphone-file-output技能的文档，确保正确使用。


---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
