# WhatsApp AI Sales

WhatsApp 外贸 AI 客服 + 私域 CRM。**v1：能聊天**（mock WhatsApp 接入、消息入库、LLM 自动回复、CRM 列表）。**v2：能按产品资料回答**（产品知识库 + RAG 检索，防 AI 乱编价格/库存/交期，无答案自动兜底）。

## 技术栈

- **FastAPI** + **SQLModel**（开发 SQLite，生产 PostgreSQL + pgvector）
- **litellm** 统一 LLM 适配层（DeepSeek / OpenAI / Claude / Gemini）
- **RAG**：切片 → MockEmbedder（确定性伪 embedding）→ 内存 MockVectorStore（启动时从 DB 重索引），接口对齐 pgvector/Qdrant，后续替换
- 测试：pytest + TestClient（内存 SQLite）

## 快速开始

```bash
uv sync
uv run fastapi dev
```

配置通过环境变量（前缀 `WAS_`，见 `src/whatsapp_ai_sales/config.py`），例如：

```bash
WAS_DATABASE_URL=sqlite:///./was.db
WAS_LLM_MODEL=deepseek/deepseek-chat
WAS_LLM_API_KEY=sk-xxx
WAS_WHATSAPP_VERIFY_TOKEN=verify-me
```

未配置 `WAS_LLM_API_KEY` 时用 `MockWhatsAppProvider` 捕获外发消息，可本地联调。启动后访问 `http://localhost:8000/admin` 打开管理后台（客户列表、聊天工作台、报表、知识库、定价录入）。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/webhooks/whatsapp` | Meta 验证握手 |
| POST | `/webhooks/whatsapp` | 接收消息 → RAG 检索 → AI 回复 → 外发 |
| GET | `/api/crm/conversations` | 会话列表（含客户信息） |
| GET | `/api/crm/conversations/{id}/messages` | 会话消息记录 |
| POST | `/api/crm/conversations/{id}/takeover` | 人工接管（AI 停止自动回复） |
| POST | `/api/crm/conversations/{id}/release` | 交还 AI 自动回复 |
| POST | `/api/crm/conversations/{id}/messages` | 人工手动回复（经 provider 外发） |
| POST | `/api/kb/products` | 录入/更新产品知识（结构化 sections → 切片入库） |
| GET | `/api/kb/products` | 产品列表 |
| DELETE | `/api/kb/products/{id}` | 删除产品（同步清理向量） |
| POST | `/api/kb/reindex` | 从 DB 重建向量索引 |
| POST | `/api/pricing/products/{id}/rule` | 录入/更新产品定价规则（阶梯价/最低价/自动成交价） |
| GET | `/api/pricing/products/{id}/rule` | 读取定价规则 |
| POST | `/api/crm/conversations/{id}/dnd` | 免打扰（暂停自动回复与跟进） |
| POST | `/api/followups/run` | 手动触发一次跟进扫描 |
| GET | `/api/reports/summary` | CRM 报表汇总 |
| GET | `/admin` | 管理后台前端（免构建 SPA） |

## 知识库录入示例

```json
POST /api/kb/products
{
  "name": "LED Strip",
  "sku": "LED-001",
  "sections": {
    "intro": "SMD2835 LED strip, 5m reel, IP20.",
    "price": "1-99pcs: $10, 100-499pcs: $8, 500+pcs: $6.5.",
    "moq": "MOQ is 100 pieces, lead time 15 days.",
    "faq": "We accept T/T and PayPal."
  }
}
```

## 报价规则示例

价格由程序计算，AI 只负责组织语言、不允许改数字：

```json
POST /api/pricing/products/1/rule
{
  "currency": "USD",
  "standard_price": 10.0,
  "min_price": 6.0,
  "auto_deal_price": 6.5,
  "sample_price": 15.0,
  "discount_allowed": true,
  "tiers": [
    {"min_quantity": 100, "unit_price": 8.0},
    {"min_quantity": 500, "unit_price": 6.5}
  ]
}
```

还价分支：报价 ≥ 自动成交价 → accept（可成交）；最低价 ≤ 报价 < 自动成交价 → negotiate（谨慎还价/通知销售）；< 最低价 → human（转人工）。

## 自动跟进

`WAS_FOLLOWUP_*` 配置阈值与文案。`start_followup_scheduler(app)`（`api/followup.py`）用 APScheduler 周期扫描；`POST /api/followups/run` 可手动触发。规则：仅 AI 接待、非免打扰、未超跟进上限（`WAS_FOLLOWUP_MAX`）且最后消息是外发的会话；发过报价且超 `WAS_FOLLOWUP_QUOTE_HOURS` 用报价跟进话术，否则超 `WAS_FOLLOWUP_NO_REPLY_HOURS` 用普通跟进话术。

## 测试

```bash
uv run pytest
```
