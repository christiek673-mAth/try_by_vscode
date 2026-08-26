const conversation = document.querySelector("#conversation");
const form = document.querySelector("#chat-form");
const questionInput = document.querySelector("#question");
const submitButton = document.querySelector("#submit");
const status = document.querySelector("#status");
const history = [];

function appendMessage(title, text, type = "") {
  const article = document.createElement("article");
  article.className = `message ${type}`;
  const heading = document.createElement("h2");
  heading.textContent = title;
  const content = document.createElement("div");
  content.className = "content";
  content.textContent = text;
  article.append(heading, content);
  conversation.append(article);
  article.scrollIntoView({ behavior: "smooth", block: "end" });
  return article;
}

function appendCitations(citations) {
  const section = document.createElement("section");
  section.className = "citations";
  const heading = document.createElement("h3");
  heading.textContent = "检索到的法规依据";
  section.append(heading);
  for (const citation of citations) {
    const card = document.createElement("article");
    card.className = "citation";
    const title = document.createElement("strong");
    title.textContent = `[${citation.id}] ${citation.hierarchy_path}`;
    const meta = document.createElement("p");
    meta.textContent = `来源：${citation.source}｜效力状态：${citation.legal_status || "未提供"}`;
    const excerpt = document.createElement("pre");
    excerpt.textContent = citation.excerpt;
    card.append(title, meta);
    if (citation.source_url) {
      const link = document.createElement("a");
      link.href = citation.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "打开权威来源";
      card.append(link);
    }
    card.append(excerpt);
    section.append(card);
  }
  conversation.append(section);
}

async function updateHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    status.textContent = data.ready ? `索引已就绪：${data.collection}` : `索引未就绪：${data.message}`;
    status.classList.toggle("error", !data.ready);
  } catch {
    status.textContent = "无法连接本地服务。";
    status.classList.add("error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) return;
  appendMessage("你的问题", question, "user");
  history.push({ role: "user", content: question });
  questionInput.value = "";
  submitButton.disabled = true;
  submitButton.textContent = "检索与分析中…";
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history, top_k: Number(document.querySelector("#top-k").value), legal_status: document.querySelector("#legal-status").value.trim() || null }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "服务请求失败。");
    appendMessage(data.insufficient_sources ? "检索结果不足" : "法律检索辅助", data.answer, "assistant");
    history.push({ role: "assistant", content: data.answer });
    if (data.citations.length) appendCitations(data.citations);
  } catch (error) {
    appendMessage("无法完成分析", error.message, "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "开始分析";
  }
});

updateHealth();