# WhatsApp AI Sales

WhatsApp 外贸 AI 客服 + 私域 CRM。**v1 目标：能聊天** —— mock WhatsApp 接入、消息入库、LLM 自动回复、简单 CRM 列表。

## 技术栈

- **FastAPI** + **SQLModel**（开发 SQLite，生产 PostgreSQL + pgvector）
- **litellm** 统一 LLM 适配层（DeepSeek / OpenAI / Claude / Gemini）
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
| POST | `/webhooks/whatsapp` | 接收消息 → 入库 → AI 回复 → 外发 |
| GET | `/api/crm/conversations` | 会话列表（含客户信息） |
| GET | `/api/crm/conversations/{id}/messages` | 会话消息记录 |

## 测试

```bash
uv run pytest
```
