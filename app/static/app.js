// Vanilla JS, no build step. All model/server text is inserted with textContent (never
// innerHTML), so an answer containing HTML cannot inject markup into the page.
"use strict";

const $ = (id) => document.getElementById(id);
const NAMES = { tcs: "TCS", hcltech: "HCLTech", techm: "Tech Mahindra", infosys: "Infosys", wipro: "Wipro" };

const pretty = (company) => NAMES[company] || company.charAt(0).toUpperCase() + company.slice(1);
const fy = (year) => "FY" + String(year % 100).padStart(2, "0");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ---------------------------------------------------------------- tabs
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t === tab);
      t.setAttribute("aria-selected", String(t === tab));
    });
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== tab.dataset.panel));
    if (tab.dataset.panel === "panel-eval") loadEval();
  });
});

// ---------------------------------------------------------------- page setup
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("Request failed");
  return res.json();
}

async function init() {
  try {
    const cfg = await getJSON("/api/config");
    $("model").textContent = cfg.model;
    if (cfg.github_url) {
      $("github").href = cfg.github_url;
      $("github").hidden = false;
    }
  } catch { $("model").textContent = "unknown"; }

  let docs = [];
  try { docs = (await getJSON("/api/docs-list")).documents; } catch { /* shown below */ }
  $("docs").textContent = docs.length
    ? "Indexed: " + docs.map((d) => `${pretty(d.company)} ${fy(d.fiscal_year)}`).join(", ")
    : "No documents are indexed yet.";
  buildChips(docs);
}

// Example chips are generated from whatever is indexed, so they never mention missing data.
function buildChips(docs) {
  const companies = [...new Set(docs.map((d) => d.company))];
  if (!companies.length) return;
  const a = pretty(companies[0]);
  const b = companies[1] ? pretty(companies[1]) : null;
  const questions = [
    `What was ${a}'s revenue growth in the latest year?`,
    `What is ${a}'s employee attrition rate?`,
    b ? `Compare the operating margin of ${a} and ${b}.` : `What was ${a}'s operating margin?`,
    `What will ${a}'s revenue be next year?`, // unanswerable: shows the refusal behaviour
  ];
  const box = $("chips");
  questions.forEach((q) => {
    const chip = el("button", "chip", q);
    chip.type = "button";
    chip.addEventListener("click", () => { $("question").value = q; updateCounter(); $("question").focus(); });
    box.appendChild(chip);
  });
}

function updateCounter() { $("counter").textContent = `${$("question").value.length} / 500`; }
$("question").addEventListener("input", updateCounter);

// ---------------------------------------------------------------- asking
$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (!question) return;
  const result = $("result");
  $("submit").disabled = true;
  result.replaceChildren(skeleton());
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Request failed. Please try again.");
    result.replaceChildren(renderAnswer(data));
  } catch (err) {
    result.replaceChildren(el("div", "error", err.message || "Network error. Please try again."));
  } finally {
    $("submit").disabled = false;
  }
});

function skeleton() {
  const card = el("div", "card");
  card.append(el("div", "skeleton"), el("div", "skeleton"), el("div", "skeleton short"));
  return card;
}

function renderAnswer(data) {
  const card = el("div", "card");
  const answered = data.status === "answered";
  card.appendChild(el("span", `badge ${data.status}`, answered ? "Answered" : "Not found in documents"));
  card.appendChild(el("p", "answer", data.answer));

  if (data.citations.length) {
    const cites = el("div", "cites");
    data.citations.forEach((c) =>
      cites.appendChild(el("span", "cite", `${pretty(c.company)} ${fy(c.fiscal_year)} - p.${c.page}`)));
    card.appendChild(cites);
  }
  const tokens = (data.tokens.prompt || 0) + (data.tokens.completion || 0);
  card.appendChild(el("div", "meta", `${(data.latency_ms / 1000).toFixed(1)}s, ${tokens} tokens, ${data.steps.length} tool calls`));

  const details = el("details");
  details.appendChild(el("summary", null, "How the agent got this answer"));
  const list = el("ol", "timeline");
  if (!data.steps.length) list.appendChild(el("li", "muted", "No tools were called."));
  data.steps.forEach((s) => {
    const li = el("li");
    const head = el("div", "tl-head", s.tool + " ");
    head.appendChild(el("span", "ms", `${s.ms} ms`));
    li.append(head, el("pre", null, s.args), el("pre", null, s.result_preview));
    list.appendChild(li);
  });
  details.appendChild(list);
  card.appendChild(details);
  return card;
}

// ---------------------------------------------------------------- evaluation tab
const pct = (x) => (x === null || x === undefined ? "n/a" : Math.round(x * 100) + "%");

async function loadEval() {
  const box = $("eval-content");
  try {
    const data = await getJSON("/api/eval-results");
    if (!data.available) {
      box.textContent = "Evaluation results: TBD. The evaluation has not been run yet.";
      return;
    }
    const rows = Object.entries(data.summary);
    const table = el("table");
    const head = el("tr");
    ["Config", "hit@5", "Answer acc.", "Refusal acc.", "False refusals", "Avg latency", "Avg tokens"]
      .forEach((h) => head.appendChild(el("th", null, h)));
    table.appendChild(head);
    rows.forEach(([cfg, s]) => {
      const tr = el("tr");
      [`${cfg}) ${s.name}`, pct(s.hit_at_5), pct(s.answer_accuracy), pct(s.refusal_accuracy),
        pct(s.false_refusal_rate), (s.avg_latency_ms / 1000).toFixed(1) + "s", Math.round(s.avg_tokens)]
        .forEach((v) => tr.appendChild(el("td", null, String(v))));
      table.appendChild(tr);
    });
    const wrap = el("div", "table-scroll");
    wrap.appendChild(table);
    box.replaceChildren(
      el("p", "muted", `${data.meta.n_questions} verified questions, model ${data.meta.llm_model}, run ${data.meta.date}`),
      wrap,
    );
  } catch {
    box.textContent = "Could not load evaluation results.";
  }
}

init();
