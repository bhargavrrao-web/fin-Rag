/* FinRAG research desk. Vanilla JS, no build step.
   The conversation lives in memory only. Nothing about it is written to browser storage. */
"use strict";

const $ = (id) => document.getElementById(id);
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const wide = window.matchMedia("(min-width: 960px)");

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

/* ---------------------------------------------------------------- formatting */
const ACRONYMS = { tcs: "TCS", hcltech: "HCLTech", hcl: "HCL" };
function companyName(c) {
  const k = String(c || "").toLowerCase();
  return ACRONYMS[k] || k.charAt(0).toUpperCase() + k.slice(1);
}
const fy = (y) => "FY" + String(y).slice(-2);
const citeLabel = (c) => `${companyName(c.company)} ${fy(c.fiscal_year)}, p. ${c.page}`;
const nf = new Intl.NumberFormat("en-IN");
const pct = (v) => (v == null ? "n/a" : Math.round(v * 100) + "%");

/* ---------------------------------------------------------------- theme */
const root = document.documentElement;
const themeBtn = $("theme-toggle");
function currentTheme() {
  if (root.dataset.theme) return root.dataset.theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function syncThemeBtn() {
  const dark = currentTheme() === "dark";
  themeBtn.textContent = dark ? "Light theme" : "Dark theme";
  themeBtn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
}
try { const t = localStorage.getItem("finrag-theme"); if (t) root.dataset.theme = t; } catch (_) { /* optional */ }
themeBtn.addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  try { localStorage.setItem("finrag-theme", next); } catch (_) { /* optional */ }
  syncThemeBtn();
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncThemeBtn);
syncThemeBtn();

/* ---------------------------------------------------------------- tabs */
const tabs = [...document.querySelectorAll(".tab")];
const panels = { "tab-ask": $("panel-ask"), "tab-eval": $("panel-eval") };
let evalLoaded = false;
function selectTab(tab, focus) {
  tabs.forEach((t) => {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    panels[t.id].hidden = !on;
  });
  if (focus) tab.focus();
  if (tab.id === "tab-eval" && !evalLoaded) loadEval();
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => selectTab(t, false));
  t.addEventListener("keydown", (e) => {
    const k = e.key;
    let j = null;
    if (k === "ArrowRight") j = (i + 1) % tabs.length;
    else if (k === "ArrowLeft") j = (i - 1 + tabs.length) % tabs.length;
    else if (k === "Home") j = 0;
    else if (k === "End") j = tabs.length - 1;
    if (j !== null) { e.preventDefault(); selectTab(tabs[j], true); }
  });
});

/* ---------------------------------------------------------------- config and reports */
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}
(async function init() {
  try {
    const cfg = await getJSON("/api/config");
    $("model-name").textContent = cfg.model || "unknown";
    if (cfg.github_url) {
      for (const id of ["github-link", "footer-github"]) { const a = $(id); a.href = cfg.github_url; a.hidden = false; }
    }
  } catch (_) { $("model-name").textContent = "unavailable"; }
  try {
    const { documents } = await getJSON("/api/docs-list");
    const list = $("doc-chips");
    documents.forEach((d) => list.appendChild(el("li", null, `${companyName(d.company)} ${fy(d.fiscal_year)}`)));
    if (documents.length !== 6) {
      $("indexed-line").textContent = `${documents.length} reports indexed. Answers cite company, year and page.`;
    }
  } catch (_) { $("indexed-line").textContent = "Could not load the list of indexed reports."; }
})();

/* ---------------------------------------------------------------- source panel and highlighting */
const NUM_RE = /\d[\d,]*(?:\.\d+)?%?/g;
const normNum = (s) => s.replace(/[,%]/g, "").replace(/\.$/, "");

/* Figures and quoted phrases from the answer that are worth marking in the passage. */
function wantedFigures(answer) {
  const want = new Set();
  for (const m of answer.matchAll(NUM_RE)) {
    const raw = m[0].replace(/,+$/, "");
    const n = normNum(raw);
    const digits = n.replace(".", "").length;
    const isYear = /^(19|20)\d\d$/.test(n);
    if (!isYear && (raw.endsWith("%") || n.includes(".") || digits >= 3)) want.add(n);
  }
  return want;
}
function findRanges(passage, answer) {
  const want = wantedFigures(answer);
  const ranges = [];
  for (const m of passage.matchAll(NUM_RE)) {
    const raw = m[0].replace(/,+$/, "");
    if (want.has(normNum(raw))) ranges.push([m.index, m.index + raw.length]);
  }
  const lower = passage.toLowerCase();
  for (const q of answer.matchAll(/["“]([^"”]{4,80})["”]/g)) {
    const at = lower.indexOf(q[1].toLowerCase());
    if (at >= 0) ranges.push([at, at + q[1].length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([...r]);
  }
  return merged;
}
/* Builds DOM nodes, never innerHTML, so passage text cannot inject markup. */
function passageNodes(passage, ranges, sweep) {
  const frag = document.createDocumentFragment();
  let pos = 0;
  ranges.forEach((r, i) => {
    if (r[0] > pos) frag.appendChild(document.createTextNode(passage.slice(pos, r[0])));
    const mk = el("mark", "hl" + (sweep && !reduceMotion() ? " sweep" : ""), passage.slice(r[0], r[1]));
    mk.style.setProperty("--d", Math.min(i * 0.08, 0.24) + "s");
    frag.appendChild(mk);
    pos = r[1];
  });
  if (pos < passage.length) frag.appendChild(document.createTextNode(passage.slice(pos)));
  return frag;
}

function renderSource(container, cite, answer, sweep) {
  container.replaceChildren();
  const head = el("div", "source-head");
  head.appendChild(el("h3", "source-title", citeLabel(cite)));
  container.appendChild(head);
  const passage = (cite.passage || "").trim();
  if (!passage) {
    container.appendChild(el("p", "source-empty", `The text of this page is not available here. Open page ${cite.page} in the original PDF.`));
    return;
  }
  const ranges = findRanges(passage, answer);
  head.appendChild(el("p", "source-sub",
    ranges.length ? `${ranges.length} highlighted ${ranges.length === 1 ? "match" : "matches"} from the answer` : "Page text as indexed"));
  const body = el("div", "source-body");
  body.appendChild(passageNodes(passage, ranges, sweep));
  container.appendChild(body);
  if (!ranges.length) container.appendChild(el("p", "source-note", "No figure from the answer was found in this page text. Read the page to check the answer."));
  const first = body.querySelector("mark");
  if (first) scrollToMark(container, first);
}
/* Scroll only the panel (or nothing on the page), so the page does not jump. */
function scrollToMark(container, mark) {
  const scroller = $("source-panel");
  if (!wide.matches || !scroller.contains(container)) return;
  const off = mark.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
  scroller.scrollTop += off - scroller.clientHeight / 3;
}

/* ---------------------------------------------------------------- thread */
const thread = $("thread");
const form = $("ask-form");
const input = $("question");
let busy = false;

function growInput() {
  input.style.height = "auto";
  const h = Math.min(input.scrollHeight + 2, 240);
  input.style.height = h + "px";
  input.style.overflowY = input.scrollHeight + 2 > 240 ? "auto" : "hidden";
}
function updateCounter() { $("counter").textContent = `${input.value.length} of 500`; }
input.addEventListener("input", () => { growInput(); updateCounter(); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
});
$("clear-btn").addEventListener("click", () => { input.value = ""; growInput(); updateCounter(); input.focus(); });
document.querySelectorAll(".starter").forEach((b) =>
  b.addEventListener("click", () => {
    if (busy) return;
    input.value = b.dataset.q; growInput(); updateCounter(); form.requestSubmit();
  }));

function setBusy(on) {
  busy = on;
  $("submit-btn").disabled = on;
  $("submit-btn").setAttribute("aria-busy", String(on));
  $("spinner").hidden = !on;
  $("submit-label").textContent = on ? "Working" : "Get answer";
}
function scrollTo(node) {
  node.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" });
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q || busy) return;
  ask(q);
});

async function ask(question) {
  setBusy(true);
  $("empty-state")?.remove();
  $("starters").open = false;
  const turn = el("article", "turn");
  turn.appendChild(el("p", "q-echo", question));
  const working = el("div", "working");
  working.setAttribute("aria-live", "off");
  const elapsed = el("p", "elapsed", "Working... 0s");
  const sk = el("div", "skeleton");
  sk.setAttribute("aria-hidden", "true");
  sk.append(el("i"), el("i"), el("i"));
  working.append(elapsed, sk);
  turn.appendChild(working);
  thread.appendChild(turn);
  scrollTo(turn);
  input.value = ""; growInput(); updateCounter();

  const t0 = performance.now();
  const timer = setInterval(() => { elapsed.textContent = `Working... ${Math.floor((performance.now() - t0) / 1000)}s`; }, 1000);

  try {
    const res = await fetch("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
    clearInterval(timer);
    working.remove();
    if (!res.ok) turn.appendChild(errorBlock(res.status, data.detail, question, turn));
    else turn.appendChild(answerBlock(data, turn));
  } catch (_) {
    clearInterval(timer);
    working.remove();
    turn.appendChild(errorBlock(0, "", question, turn));
  } finally {
    setBusy(false);
  }
  scrollTo(turn);
}

function errorMessage(status, detail) {
  if (status === 429) {
    return /too fast|minute/i.test(detail || "")
      ? "You are asking too fast. Wait a minute, then try again."
      : "You have reached today's question limit. Try again tomorrow.";
  }
  if (status === 422) return "Questions must be 1 to 500 characters. Shorten yours and try again.";
  if (status === 503) return "The report index has not been built. Run the ingest step, then try again.";
  return "The agent could not finish this question. Try again, or shorten it.";
}
function errorBlock(status, detail, question, turn) {
  const box = el("div", "error");
  box.appendChild(el("p", null, errorMessage(status, detail)));
  if (status !== 429) {
    const retry = el("button", "btn", "Try again");
    retry.type = "button";
    retry.addEventListener("click", () => { if (busy) return; turn.remove(); ask(question); });
    box.appendChild(retry);
  }
  return box;
}

/* ---------------------------------------------------------------- answer block */
function answerBlock(data, turn) {
  const ok = data.status === "answered";
  const cites = Array.isArray(data.citations) ? data.citations : [];
  const wrap = el("div", "stack-sm");
  const box = el("div", "answer" + (ok ? "" : " is-notfound"));
  wrap.appendChild(box);

  box.appendChild(el("p", "status " + (ok ? "ok" : "warn"), ok ? "Answered" : "Not found in these reports"));
  if ((data.answer || "").trim()) box.appendChild(el("p", "answer-text", data.answer));
  if (!ok) box.appendChild(el("p", "answer-hint", "Not found in these reports. Try naming the company and fiscal year."));

  const chips = [];
  const inline = el("details", "inline-source");
  const inlineSheet = el("div", "source-sheet");
  inline.append(el("summary", null, "Show source"), inlineSheet);

  const show = (cite, btn, sweep) => {
    document.querySelectorAll(".cite[aria-pressed='true']").forEach((b) => b.setAttribute("aria-pressed", "false"));
    btn.setAttribute("aria-pressed", "true");
    if (wide.matches) renderSource($("source-sheet"), cite, data.answer || "", sweep);
    else { inline.open = true; renderSource(inlineSheet, cite, data.answer || "", sweep); }
  };

  if (cites.length) {
    const row = el("div", "cite-row");
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", "Citations");
    cites.forEach((c) => {
      const b = el("button", "cite", citeLabel(c));
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => show(c, b, true));
      row.appendChild(b);
      chips.push(b);
    });
    box.appendChild(row);
  }

  const secs = ((data.latency_ms || 0) / 1000).toFixed(1);
  const tok = (data.tokens?.prompt || 0) + (data.tokens?.completion || 0);
  box.appendChild(el("p", "meta-line", `${secs} seconds, ${nf.format(tok)} tokens`));

  if (cites.length) {
    inline.addEventListener("toggle", () => {
      if (inline.open && !inlineSheet.firstChild) show(cites[0], chips[0], true);
    });
    wrap.appendChild(inline);
  }
  if (Array.isArray(data.steps) && data.steps.length) wrap.appendChild(timeline(data.steps));

  // The one automatic motion: the cited figure is highlighted when the answer arrives.
  if (wide.matches) {
    if (cites.length) show(cites[0], chips[0], true);
    else if (!$("source-sheet").querySelector(".source-head")) {
      // Keep an earlier answer's source on screen; only fill an empty panel.
      $("source-sheet").replaceChildren(el("p", "source-empty", "This answer has no citation, so there is no page to show."));
    }
  }
  return wrap;
}

function timeline(steps) {
  const d = el("details", "timeline");
  d.appendChild(el("summary", null, `How the agent got this answer (${steps.length} ${steps.length === 1 ? "step" : "steps"})`));
  const ol = el("ol", "steps");
  const NAMES = { search_documents: "Search reports", get_pages: "Read pages", calculator: "Calculate" };
  steps.forEach((s, i) => {
    const li = el("li", "step");
    li.appendChild(el("span", "step-no", String(i + 1)));
    const head = el("div", "step-head");
    head.appendChild(el("span", "step-name", NAMES[s.tool] || s.tool));
    head.appendChild(el("span", "step-ms", `${nf.format(s.ms || 0)} ms`));
    li.appendChild(head);
    li.appendChild(el("pre", "step-args", fmtArgs(s.args)));
    const prev = String(s.result_preview || "").replace(/\s+/g, " ").trim();
    if (prev) li.appendChild(el("p", "step-result", prev.length > 220 ? prev.slice(0, 220) + "..." : prev));
    ol.appendChild(li);
  });
  d.appendChild(ol);
  return d;
}
function fmtArgs(a) {
  let o = a;
  if (typeof a === "string") { try { o = JSON.parse(a); } catch (_) { return a; } }
  if (o && typeof o === "object") {
    return Object.entries(o).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join("\n");
  }
  return String(a ?? "");
}

/* ---------------------------------------------------------------- evaluation */
async function loadEval() {
  const host = $("panel-eval");
  let data;
  try { data = await getJSON("/api/eval-results"); }
  catch (_) { host.replaceChildren(el("p", "muted", "Could not load the evaluation results. Reload the page to try again.")); return; }
  evalLoaded = true;
  host.replaceChildren();
  if (!data.available) { host.appendChild(el("p", "muted", "No evaluation has been run yet. Run the eval script to create results.")); return; }

  const { meta, summary } = data;
  const n = meta.n_questions;
  const when = new Date(meta.date);
  const dateStr = isNaN(when) ? String(meta.date) : when.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

  const head = el("div", "eval-head");
  head.appendChild(el("h2", null, `We checked three setups on ${n} questions whose answers we verified by hand`));
  head.appendChild(el("p", "eval-meta", `Run on ${dateStr} with ${meta.llm_model}.`));
  host.appendChild(head);
  if (n < 30) host.appendChild(el("p", "sample-note", "Small sample. Differences of one or two questions can change these percentages."));

  const keys = Object.keys(summary);
  host.appendChild(chart(summary, keys));
  host.appendChild(resultsTable(summary, keys));

  const defs = el("dl", "defs");
  [["hit@5", "The right page was among the top five search results."],
   ["Answer accuracy", "Questions with an answer in the reports that were answered correctly."],
   ["Refusal accuracy", "Questions with no answer in the reports that were correctly declined."],
   ["False refusals", "Answerable questions that were declined. Lower is better."]]
    .forEach(([t, d]) => { defs.appendChild(el("dt", null, t)); defs.appendChild(el("dd", null, d)); });
  host.appendChild(defs);
}

const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attrs, text) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}
function chart(summary, keys) {
  const metrics = [["hit_at_5", "hit@5"], ["answer_accuracy", "Answer accuracy"], ["refusal_accuracy", "Refusal accuracy"]];
  const W = 720, H = 300, left = 40, top = 24, bottom = 56, ph = H - top - bottom;
  const gw = (W - left - 8) / metrics.length, bw = Math.min(40, (gw - 32) / keys.length);
  const wrap = el("figure", "chart-wrap");
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
    "aria-label": "Bar chart of hit at 5, answer accuracy and refusal accuracy for each configuration. The table below lists the same values." });
  const y = (v) => top + ph * (1 - v);
  [0, 0.5, 1].forEach((t) => {
    s.appendChild(svg("line", { class: "grid", x1: left, x2: W, y1: y(t), y2: y(t) }));
    s.appendChild(svg("text", { x: left - 8, y: y(t) + 4, "text-anchor": "end" }, Math.round(t * 100) + "%"));
  });
  metrics.forEach(([key, label], gi) => {
    const gx = left + gi * gw + (gw - bw * keys.length - 6 * (keys.length - 1)) / 2;
    keys.forEach((k, ki) => {
      const v = summary[k][key];
      const x = gx + ki * (bw + 6);
      const cls = "bar-" + k.toLowerCase();
      if (v == null) {
        s.appendChild(svg("text", { x: x + bw / 2, y: y(0) - 6, "text-anchor": "middle" }, "n/a"));
      } else {
        const h = Math.max(ph * v, 1);
        s.appendChild(svg("rect", { class: cls, x, y: y(0) - h, width: bw, height: h, rx: 2 }));
        s.appendChild(svg("text", { class: "val", x: x + bw / 2, y: y(0) - h - 6, "text-anchor": "middle" }, pct(v)));
      }
      s.appendChild(svg("text", { x: x + bw / 2, y: y(0) + 16, "text-anchor": "middle" }, k));
    });
    s.appendChild(svg("text", { class: "group-label", x: left + gi * gw + gw / 2, y: H - 10, "text-anchor": "middle" }, label));
  });
  wrap.appendChild(s);
  const key = el("div", "key");
  keys.forEach((k) => {
    const item = el("span");
    const sw = el("i"); sw.className = "bar-" + k.toLowerCase(); sw.style.background = `var(--bar-${k.toLowerCase()})`;
    item.append(sw, document.createTextNode(`${k}: ${summary[k].name}`));
    key.appendChild(item);
  });
  wrap.appendChild(key);
  return wrap;
}
function resultsTable(summary, keys) {
  const cols = [
    ["hit_at_5", "hit@5", pct, "high"],
    ["answer_accuracy", "Answer accuracy", pct, "high"],
    ["refusal_accuracy", "Refusal accuracy", pct, "high"],
    ["false_refusal_rate", "False refusals", pct, "low"],
    ["avg_latency_ms", "Seconds per question", (v) => (v / 1000).toFixed(1), "low"],
    ["avg_tokens", "Tokens per question", (v) => nf.format(Math.round(v)), "low"],
    ["avg_cost_usd", "Cost per question (USD)", (v) => "$" + v.toFixed(4), "low"],
  ];
  const wrap = el("div", "stack-sm");
  const scroll = el("div", "table-scroll");
  scroll.tabIndex = 0;
  scroll.setAttribute("role", "region");
  scroll.setAttribute("aria-label", "Full results table");
  const t = el("table");
  const thead = el("thead"), hr = el("tr");
  hr.appendChild(el("th", null, "Setup"));
  hr.lastChild.scope = "col";
  cols.forEach(([, label]) => { const th = el("th", null, label); th.scope = "col"; hr.appendChild(th); });
  thead.appendChild(hr); t.appendChild(thead);
  const best = cols.map(([k, , , dir]) => {
    const vals = keys.map((c) => summary[c][k]).filter((v) => v != null);
    if (vals.length < 2 || vals.every((v) => v === vals[0])) return null;
    return dir === "high" ? Math.max(...vals) : Math.min(...vals);
  });
  const tbody = el("tbody");
  keys.forEach((k) => {
    const tr = el("tr");
    const th = el("th", null, `${k}: ${summary[k].name}`); th.scope = "row"; tr.appendChild(th);
    cols.forEach(([key, , fmt], i) => {
      const v = summary[k][key];
      const td = el("td", v != null && v === best[i] ? "best" : "", v == null ? "n/a" : fmt(v));
      if (td.classList.contains("best")) td.appendChild(el("span", "vh", " (best in column)"));
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  t.appendChild(tbody); scroll.appendChild(t);
  wrap.appendChild(scroll);
  wrap.appendChild(el("p", "table-note", "Underlined values are the best in their column. Lower is better for false refusals, time, tokens and cost."));
  return wrap;
}

growInput();
updateCounter();
