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

未配置 `WAS_LLM_API_KEY` 时用 `MockWhatsAppProvider` 捕获外发消息，可本地联调。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/webhooks/whatsapp` | Meta 验证握手 |
| POST | `/webhooks/whatsapp` | 接收消息 → RAG 检索 → AI 回复 → 外发 |
| GET | `/api/crm/conversations` | 会话列表（含客户信息） |
| GET | `/api/crm/conversations/{id}/messages` | 会话消息记录 |
| POST | `/api/kb/products` | 录入/更新产品知识（结构化 sections → 切片入库） |
| GET | `/api/kb/products` | 产品列表 |
| DELETE | `/api/kb/products/{id}` | 删除产品（同步清理向量） |
| POST | `/api/kb/reindex` | 从 DB 重建向量索引 |

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

## 测试

```bash
uv run pytest
```
