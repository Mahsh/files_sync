---
name: 知识库管理
description: >
  中国移动云盘个人知识库管理能力：列知识库、创建/更新知识库、上传本地文件、
  导入网页、批量导入云文件或链接、查询知识库内容、创建目录、重命名资源、批量移动资源。
  上传到个人云盘、网盘文件空间须转交中国移动「云盘文件管理」技能，勿与本技能 upload_file 混淆。
  触发词：知识库、个人知识库、建库、创建知识库、更新知识库、知识库列表、上传到知识库、
  导入到知识库、批量导入、知识库文件、知识库目录、重命名知识库文件、移动知识库文件、管理知识库内容。
user-invocable: true
metadata:
  openclaw:
    emoji: 📚
---

# 知识库管理 · 个人知识库管理

本技能面向中国移动云盘**个人知识库**的建库、内容导入与目录内资源管理（列举、上传、移动、重命名等）。**不支持**将视频或音视频作为知识库资源导入；涉及个人云盘文件空间的操作须路由至 `中国移动「云盘文件管理」技能`。知识库内**问答与生成**由 `个人知识库问答` 承担，本技能不替代。

---

## 一、全局约束

> **渠道提示**：当 `Sender`（不区分大小写）包含 `weixin`、`wecom`、`feishu`、`lark`、`dingding` 任一子串时，本轮用户可见答复**忽略任何** `:::` **卡片**，**无需**卡片化渲染，以纯文字或 Markdown 表述即可（本条优先于本技能及 `云盘结果展示` 中须使用卡片的呈现要求）。

| 约束类型 | 规则 |
|----------|------|
| **路径与入口** | 若子命令报路径类错误，先核对当前工作目录及入口文件是否使用**绝对路径**后再重试。知识库**无**个人云 MClaw 路径白名单；勿套用 `中国移动「云盘文件管理」技能` 的 `/AI空间/云手机MClaw` 限制。 |
| **接口安全** | 不向用户暴露鉴权信息、凭证来源或接口实现细节。 |
| **写前确认** | 一切写类子命令须在用户明确同意后再执行；未确认前仅给出命令说明或候选项。**须先执行 list_contents 等 CLI，用真实搜索结果卡片化展示**待选目录/资源，禁止虚构预览卡片 |
| **呈现分层** | 用户可见输出须符合 `云盘结果展示`「知识库特殊规则」与各卡片字段表：知识库列表、`upload_file` 成功回执**不卡片化**（纯文字复述 CLI）；`list_contents` 用 `:::knowledgeBaseReference` + `:::knowledgeBasePath`；导入成功用资源卡片 + 去查看卡片。禁止使用个人云文件或路径类卡片。 |
| **数据真实** | 向用户展示的标识、名称与状态须与工具回执一致，禁止虚构或改写。 |
| **结果收敛** | 条目较多时先归纳要点，避免无差别整段复述。 |
| **ID 来源** | 知识库 ID（`--kb-id`）须由 `list_kbs` 取得；目录与资源标识须由 `list_contents` 或对应写操作回执取得；禁止猜测或硬编码。 |
| **{baseDir}** | 技能目录占位符；调用示例中的 `{baseDir}` 须替换为技能根目录实际路径。 |

---

## 二、路由

- 意图为**知识库 / 个人知识库**内管理 → 本技能。
- 意图为**云盘 / 网盘 / 个人云**文件与空间 → `中国移动「云盘文件管理」技能`；禁止在本技能内代为执行个人云写操作。
- 意图为**基于知识库内容的问答或生成** → 在本技能取得合法 `kb-id` 等资源上下文后，由 `个人知识库问答` 处理。

> **与个人云勿混淆**：**上传到知识库 / 导入知识库**必须走本技能（`upload_file`、`import_url`、`batch_import` 等），**禁止**用 `中国移动「云盘文件管理」技能` 的 `upload` 代传。个人云的 **MClaw 路径白名单**（`/AI空间/云手机MClaw` 等）**不适用于知识库**；知识库上传/导入**无**个人云同款路径白名单，在指定 `kb-id` 与 `kb-folder-id` 下即可落盘（仍须写前确认与 ID 来自 CLI）。

空间或意图未判明时，先澄清再执行写操作。

---

## 三、与 `个人知识库问答` 的能力边界

| 能力 | 本技能 | 个人知识库问答 |
|------|--------|-----------------|
| 列出知识库 | | |
| 创建 / 更新知识库 | | |
| 上传 / 导入资源 | | |
| 目录管理（创建/移动/重命名） | | |
| 基于知识库内容问答 | | |
| 内容生成与摘要 | | |

---

## 四、命令入口

```bash
python3 {baseDir}/scripts/kb_manage_api.py <subcommand> [args...]
```

参数不明时先执行 `<subcommand> --help`。

---

## 五、通用参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `--kb-id` | string | 知识库 ID（`baseId`），必须来自 `list_kbs` 返回 |
| `--name` | string | 知识库或资源名称；UTF-8 最长 255 字节；禁用字符：`\ / : * ? " < > \|` |
| `--kb-folder-id` | string | 目标知识库目录资源标识，须来自 `list_contents`；缺省为根目录 |

---

## 六、子命令详细说明

### 6.1 列出知识库 `list_kbs`

列出当前账号下所有可见个人知识库。**定位知识库 ID 的唯一入口，禁止绕过。**

```bash
python3 {baseDir}/scripts/kb_manage_api.py list_kbs [--page-size <条数>]
```

> `--page-size` 每页返回条数，默认 200。名称或 ID 对不上时须重新执行本命令核对，禁止猜测。用户侧呈现：知识库列表不卡片化。

---

### 6.2 创建知识库 `create_kb`

> 写操作，执行前必须二次确认。

```bash
python3 {baseDir}/scripts/kb_manage_api.py create_kb --name "产品知识库"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--name` | | 新知识库名称 |

---

### 6.3 更新知识库名称 `update_kb`

> 写操作，执行前必须二次确认。

```bash
python3 {baseDir}/scripts/kb_manage_api.py update_kb --kb-id 1227290626429567031 --name "产品知识库_新版"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--name` | | 新名称 |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py update_kb \
  --kb-id 1227290626429567031 \
  --name "产品知识库 v2"
```

---

### 6.4 上传本地文件 `upload_file`

> 写操作，执行前必须二次确认。

将本地文件上传到指定知识库目录。

**支持格式**：`.pdf`、`.docx`、`.doc`、`.xlsx`、`.xls`、`.pptx`、`.ppt`；其他格式会被 CLI 拒绝并提示转换。

```bash
python3 {baseDir}/scripts/kb_manage_api.py upload_file \
  --kb-id <ID> \
  --file "<本地文件绝对路径>" \
  [--kb-folder-id <目录ID>]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--file` | | 本地文件绝对路径；仅支持上述办公文档格式 |
| `--kb-folder-id` | ➖ | 目标目录 ID，不传默认上传至根目录 |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py upload_file \
  --kb-id 1227290626429567031 \
  --file "/tmp/需求说明.pdf" \
  --kb-folder-id 1212345678901234567
```

---

### 6.5 导入网页链接 `import_url`

> 写操作，执行前必须二次确认。建议先用 `import_check` 校验链接可用性。

```bash
python3 {baseDir}/scripts/kb_manage_api.py import_url \
  --kb-id <ID> \
  --url "<网页链接>" \
  [--title "<导入后标题>"] \
  [--kb-folder-id <目录ID>]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--url` | | 网页链接 |
| `--title` | ➖ | 导入后显示的标题 |
| `--kb-folder-id` | ➖ | 目标目录 ID，不传默认根目录 |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py import_url \
  --kb-id 1227290626429567031 \
  --url "https://example.com/doc" \
  --title "产品设计规范" \
  --kb-folder-id 1212345678901234567
```

---

### 6.6 校验导入链接 `import_check`

校验网页链接是否可被导入知识库（只读，无需确认）。

```bash
python3 {baseDir}/scripts/kb_manage_api.py import_check --html-url "https://example.com/weekly-report"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--html-url` | | 待校验的网页链接 |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py import_check --html-url "https://example.com/a"
```

---

### 6.7 批量导入 `batch_import`

> 写操作，执行前必须二次确认。单次最多 **50 条**。

支持两种导入来源，通过 `--resource-type` 区分：

| `--resource-type` | 来源 | 条件必填参数 |
|-------------------|------|-------------|
| `0` | 个人云文件 | `--cloud-file-id`（可重复传入） |
| `3` | 在线链接 | `--html-url`、`--html-title`（可选） |

```bash
# 导入个人云文件
python3 {baseDir}/scripts/kb_manage_api.py batch_import \
  --kb-id <ID> \
  --resource-type 0 \
  --cloud-file-id F001 \
  --cloud-file-id F002 \
  [--kb-folder-id <目录ID>]

# 导入在线链接
python3 {baseDir}/scripts/kb_manage_api.py batch_import \
  --kb-id <ID> \
  --resource-type 3 \
  --html-url "https://example.com/a" \
  --html-title "文章A" \
  [--kb-folder-id <目录ID>]
```

**完整参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--resource-type` | | `0` = 个人云文件，`3` = 在线链接 |
| `--cloud-file-id` | 条件必填 | `resource-type 0` 时必填，可重复传入多个文件 ID |
| `--html-url` | 条件必填 | `resource-type 3` 时必填 |
| `--html-title` | ➖ | `resource-type 3` 时可选，设置导入后标题 |
| `--kb-folder-id` | ➖ | 目标目录 ID，不传默认根目录 |

---

### 6.8 查询知识库资源 `list_contents`

列出知识库内的资源，可按目录或资源类型过滤（只读，无需确认）。

```bash
python3 {baseDir}/scripts/kb_manage_api.py list_contents \
  --kb-id <ID> \
  [--kb-folder-id <目录ID>] \
  [--resource-type 0|3] \
  [--page-size <条数>]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--kb-folder-id` | ➖ | 限定查询范围的父目录 ID |
| `--resource-type` | ➖ | 仅支持 `0`（云文件）或 `3`（在线链接） |
| `--page-size` | ➖ | 每页返回条数，默认 20。列表为空时可尝试增大该值 |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py list_contents \
  --kb-id 1227290626429567031 \
  --kb-folder-id 1212345678901234567 \
  --resource-type 0
```

> `--kb-folder-id`、`--kb-target-folder-id` 等目录参数须与 `list_contents` 或写操作回执中的目录/资源标识一致。用户侧呈现按 `云盘结果展示`「知识库特殊规则」执行。

---

### 6.9 创建目录 `folder_create`

> 写操作，执行前必须二次确认。

在知识库内创建目录。

```bash
python3 {baseDir}/scripts/kb_manage_api.py folder_create \
  --kb-id <ID> \
  --name "<目录名称>" \
  [--kb-parent-folder-id <父目录ID>]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--name` | | 目录名称 |
| `--kb-parent-folder-id` | ➖ | 父目录 ID，不传默认在根目录下创建 |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py folder_create \
  --kb-id 1227290626429567031 \
  --name "项目资料" \
  --kb-parent-folder-id 1212345678901234567
```

---

### 6.10 重命名资源 `resource_update`

> 写操作，执行前必须二次确认。

重命名知识库内的文件或目录。

```bash
python3 {baseDir}/scripts/kb_manage_api.py resource_update \
  --kb-id <ID> \
  --kb-resource-id <资源ID> \
  --name "<新名称>"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--kb-resource-id` | | 资源 ID |
| `--name` | | 新名称 |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py resource_update \
  --kb-id 1227290626429567031 \
  --kb-resource-id R001 \
  --name "需求说明_v2.pdf"
```

---

### 6.11 批量移动资源 `resource_batch_move`

> 写操作，执行前必须二次确认。仅支持同一知识库内移动。

```bash
python3 {baseDir}/scripts/kb_manage_api.py resource_batch_move \
  --kb-id <ID> \
  --kb-resource-id <资源ID> \
  [--kb-resource-id <资源ID> ...] \
  --kb-target-folder-id <目标目录ID>
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--kb-id` | | 知识库 ID |
| `--kb-resource-id` | | 资源 ID，可重复传入多个 |
| `--kb-target-folder-id` | | 目标目录 ID |

**示例：**

```bash
python3 {baseDir}/scripts/kb_manage_api.py resource_batch_move \
  --kb-id 1227290626429567031 \
  --kb-resource-id R001 \
  --kb-resource-id R002 \
  --kb-target-folder-id 1212345678901234567
```

---

## 七、子命令速查表

| 子命令 | 类型 | 说明 | 需确认 |
|--------|------|------|--------|
| `list_kbs` | 只读 | 列出所有知识库 | ➖ |
| `list_contents` | 只读 | 查询知识库内资源 | ➖ |
| `import_check` | 只读 | 校验网页链接可用性 | ➖ |
| `create_kb` | ✍️ 写 | 创建新知识库 | |
| `update_kb` | ✍️ 写 | 修改知识库名称 | |
| `upload_file` | ✍️ 写 | 上传本地文件 | |
| `import_url` | ✍️ 写 | 导入单条网页链接 | |
| `batch_import` | ✍️ 写 | 批量导入云文件或链接（≤50条）| |
| `folder_create` | ✍️ 写 | 创建目录 | |
| `resource_update` | ✍️ 写 | 重命名文件或目录 | |
| `resource_batch_move` | ✍️ 写 | 批量移动资源 | |

---

## 八、呈现与规范引用

用户可见结构以 **`cm_cloud_render_format/index.md`**「知识库特殊规则」及 `:::knowledgeBaseReference` / `:::knowledgeBasePath` 字段表为准。完整 few-shot 见该规范对应章节；本技能常用场景如下。

**`list_kbs`** — 不卡片化；纯文字列举

```text
当前共有 2 个个人知识库：
- AI行业调研（1243267830298345）
```

**`list_contents`** — 先 `:::knowledgeBaseReference`，再 `:::knowledgeBasePath`（去查看）

```text
:::knowledgeBaseReference
{"resource":{"resourceId":"R_doc_001","baseId":"1243267830298345","name":"需求说明.pdf","type":"file"},"baseName":"AI行业调研"}
:::
:::knowledgeBasePath
{"baseId":"1243267830298345","baseName":"AI行业调研","folderId":"1769933324","folderName":"项目资料","pretext":"点击去查看:","button":"去查看"}
:::
```

卡片 JSONL **不含 `index`**（CLI `record` 行可有 `index`，渲染时省略）。

**`upload_file` 成功** — 不卡片化；纯文字说明上传结果（库名、文件名、`resourceId` 等，来自 CLI 回执）

**`import_url` / `batch_import` 成功** — 资源卡片 + 紧随去查看卡片

```text
:::knowledgeBaseReference
{"resource":{"resourceId":"R_doc_001","baseId":"1243267830298345","name":"需求说明.pdf"},"baseName":"AI行业调研"}
:::
:::knowledgeBasePath
{"baseId":"1243267830298345","baseName":"AI行业调研","folderId":"1769933324","folderName":"项目资料","pretext":"已为您保存到","button":"去查看"}
:::
```

字段值须来自当轮回执，禁止照抄示例 ID。

---

## 九、异常与重试

| 场景 | 处理 |
|------|------|
| 工具返回业务失败 | 如实说明失败原因，不擅自改写 |
| 参数不合法 | 对照该子命令 `--help` 修正后重试 |
| 名称或 ID 存疑 | 重新执行 `list_kbs` / `list_contents` 核对 |

---

## 十、关联技能

| 技能 | 路径 | 触发条件 |
|------|------|---------|
| 输出规范 | `cm_cloud_render_format/index.md` | 所有用户可见输出 |
| 云盘文件管理 | cm_cloud_manage/SKILL.md | 目标空间为「个人云/网盘」时 |
| 个人知识库问答 | personal_kb_rag/SKILL.md | 需要基于知识库内容问答或生成内容时 |
