"use strict";

const $ = (sel) => document.querySelector(sel);
const views = document.querySelectorAll(".view");
const navButtons = document.querySelectorAll("nav button");

function showView(name) {
  views.forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "conversations") loadConversations();
  if (name === "reports") loadReports();
  if (name === "kb") loadProducts();
  if (name === "pricing") loadPricingProducts();
}
navButtons.forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

// ---------- conversations ----------
let selectedConversation = null;

async function loadConversations() {
  const rows = await api("/api/crm/conversations");
  const list = $("#conv-list");
  list.innerHTML = "";
  for (const row of rows) {
    const item = document.createElement("button");
    item.className = "conv-item";
    item.dataset.id = row.id;
    const level = row.lead_level ? ` [${row.lead_level}:${row.lead_score}]` : "";
    item.textContent = `${row.wa_id}${row.customer_name ? " " + row.customer_name : ""}${level} · ${row.handler}${row.dnd ? " · muted" : ""}`;
    item.addEventListener("click", () => selectConversation(row.id));
    if (row.id === selectedConversation) item.classList.add("selected");
    list.appendChild(item);
  }
}

async function selectConversation(id) {
  selectedConversation = id;
  const [messages, conversations] = await Promise.all([
    api(`/api/crm/conversations/${id}/messages`),
    api("/api/crm/conversations"),
  ]);
  const row = conversations.find((c) => c.id === id);
  const chat = $("#chat");
  chat.innerHTML = "";
  const header = document.createElement("div");
  header.className = "chat-header";
  header.innerHTML = `
    <strong>${row.wa_id}</strong> · handler: ${row.handler}
    ${row.interested_product ? ` · 产品: ${row.interested_product}` : ""}
    ${row.quantity ? ` · 数量: ${row.quantity}` : ""}
    <div class="chat-actions">
      <button data-act="takeover">接管</button>
      <button data-act="release">交还AI</button>
      <button data-act="dnd">${row.dnd ? "取消免打扰" : "免打扰"}</button>
    </div>`;
  chat.appendChild(header);

  const log = document.createElement("div");
  log.className = "chat-log";
  for (const m of messages) {
    const line = document.createElement("div");
    line.className = `msg ${m.role}`;
    line.textContent = m.content;
    log.appendChild(line);
  }
  chat.appendChild(log);

  const composer = document.createElement("div");
  composer.className = "composer";
  const input = document.createElement("input");
  input.placeholder = "人工回复…";
  const send = document.createElement("button");
  send.textContent = "发送";
  send.addEventListener("click", async () => {
    await api(`/api/crm/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content: input.value }),
    });
    input.value = "";
    selectConversation(id);
  });
  composer.append(input, send);
  chat.appendChild(composer);

  header.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", async () => {
      const act = b.dataset.act;
      if (act === "dnd") {
        await api(`/api/crm/conversations/${id}/dnd`, {
          method: "POST",
          body: JSON.stringify({ enabled: !row.dnd }),
        });
      } else {
        await api(`/api/crm/conversations/${id}/${act}`, { method: "POST" });
      }
      selectConversation(id);
    })
  );
}

// ---------- reports ----------
async function loadReports() {
  const r = await api("/api/reports/summary");
  const cards = [
    ["客户总数", r.total_customers],
    ["7日新增", r.new_customers],
    ["高意向", r.high_intent],
    ["已报价会话", r.quotes_sent],
    ["转人工", r.handoffs],
    ["客户回复率", `${Math.round(r.reply_rate * 100)}%`],
    ["AI 回复成功率", `${Math.round(r.ai_reply_success_rate * 100)}%`],
  ];
  $("#report-cards").innerHTML = cards
    .map(([k, v]) => `<div class="card"><div class="card-value">${v}</div><div class="card-label">${k}</div></div>`)
    .join("");
  $("#report-countries").innerHTML = Object.entries(r.countries)
    .map(([k, v]) => `<div class="card"><div class="card-value">${v}</div><div class="card-label">${k}</div></div>`)
    .join("") || "<p>暂无数据</p>";
}

// ---------- knowledge base ----------
async function loadProducts() {
  const rows = await api("/api/kb/products");
  $("#pricing-product").innerHTML = rows
    .map((p) => `<option value="${p.id}">${p.name}</option>`)
    .join("");
}

$("#kb-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.target);
  try {
    const sections = JSON.parse(data.get("sections"));
    await api("/api/kb/products", {
      method: "POST",
      body: JSON.stringify({ name: data.get("name"), sku: data.get("sku"), sections }),
    });
    $("#kb-result").textContent = "已保存";
    loadProducts();
  } catch (err) {
    $("#kb-result").textContent = `失败: ${err.message}`;
  }
});

// ---------- pricing ----------
$("#pricing-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.target);
  try {
    const tiers = data.get("tiers") ? JSON.parse(data.get("tiers")) : [];
    await api(`/api/pricing/products/${data.get("product")}/rule`, {
      method: "POST",
      body: JSON.stringify({
        standard_price: Number(data.get("standard_price")),
        min_price: Number(data.get("min_price")),
        auto_deal_price: Number(data.get("auto_deal_price")),
        tiers,
      }),
    });
    $("#pricing-result").textContent = "已保存";
  } catch (err) {
    $("#pricing-result").textContent = `失败: ${err.message}`;
  }
});

showView("conversations");
