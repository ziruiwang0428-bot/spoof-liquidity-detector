const state = {
  mode: "sample",
  rows: [],
};

const els = {
  mode: document.querySelector("#mode"),
  chainId: document.querySelector("#chainId"),
  top: document.querySelector("#top"),
  fromBlock: document.querySelector("#fromBlock"),
  toBlock: document.querySelector("#toBlock"),
  chunkSize: document.querySelector("#chunkSize"),
  rpcUrl: document.querySelector("#rpcUrl"),
  economicsPath: document.querySelector("#economicsPath"),
  venue: document.querySelector("#venue"),
  contract: document.querySelector("#contract"),
  fillTopic: document.querySelector("#fillTopic"),
  notionalSource: document.querySelector("#notionalSource"),
  makerTopicIndex: document.querySelector("#makerTopicIndex"),
  takerTopicIndex: document.querySelector("#takerTopicIndex"),
  makerAmountWord: document.querySelector("#makerAmountWord"),
  takerAmountWord: document.querySelector("#takerAmountWord"),
  feeWord: document.querySelector("#feeWord"),
  amountDecimals: document.querySelector("#amountDecimals"),
  runButton: document.querySelector("#runButton"),
  status: document.querySelector("#status"),
  rowCount: document.querySelector("#rowCount"),
  maxRisk: document.querySelector("#maxRisk"),
  maxFilled: document.querySelector("#maxFilled"),
  activeMode: document.querySelector("#activeMode"),
  tableHead: document.querySelector("#tableHead"),
  tableBody: document.querySelector("#tableBody"),
};

const accountColumns = [
  ["maker", "Maker"],
  ["account_risk_score", "Risk", formatRisk],
  ["order_count", "Orders"],
  ["near_touch_cancel_rate", "Avoid", formatPercent],
  ["far_order_ratio", "Far Ratio", formatPercent],
  ["net_profit", "Profit", formatNumber],
  ["annualized_return", "APY", formatPercent],
  ["reward_to_chain_fill_ratio", "Reward/Fill", formatRatio],
  ["reasons", "Reasons", formatList],
];

const fillColumns = [
  ["maker", "Maker"],
  ["fill_count", "Fills"],
  ["filled_notional", "Filled", formatNumber],
  ["fee_paid", "Fees", formatNumber],
  ["reward", "Reward", formatNumber],
  ["reward_to_fill_ratio", "Reward/Fill", formatRatio],
  ["blocks", "Blocks", formatBlocks],
  ["transaction_hashes", "Proof", formatProofs],
];

els.runButton.addEventListener("click", run);
els.mode.addEventListener("change", () => {
  state.mode = els.mode.value;
  updateModeControls();
  run();
});

updateModeControls();
run();

async function run() {
  state.mode = els.mode.value;
  setBusy(true);
  try {
    const payload = await fetchJson(buildUrl());
    state.rows = payload.rows || [];
    render();
    els.status.textContent = "Loaded";
  } catch (error) {
    state.rows = [];
    render();
    els.status.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function buildUrl() {
  const top = encodeURIComponent(els.top.value || "10");
  if (state.mode === "sample") {
    return `/api/sample/accounts?top=${top}`;
  }
  const params = buildChainParams();
  if (state.mode === "generic") {
    params.set("venue", els.venue.value || "custom-evm");
    params.set("contract", els.contract.value.trim());
    params.set("fill_topic", els.fillTopic.value.trim());
    params.set("notional_source", els.notionalSource.value || "max");
    params.set("maker_topic_index", els.makerTopicIndex.value || "2");
    params.set("taker_topic_index", els.takerTopicIndex.value || "3");
    params.set("maker_amount_word", els.makerAmountWord.value || "2");
    params.set("taker_amount_word", els.takerAmountWord.value || "3");
    params.set("fee_word", els.feeWord.value || "4");
    params.set("amount_decimals", els.amountDecimals.value || "6");
    return `/api/evm/fills?${params.toString()}`;
  }
  return `/api/polymarket/fills?${params.toString()}`;
}

function buildChainParams() {
  const params = new URLSearchParams({
    chain_id: els.chainId.value || "137",
    from_block: els.fromBlock.value,
    to_block: els.toBlock.value || "latest",
    chunk_size: els.chunkSize.value || "1000",
    top: els.top.value || "10",
  });
  if (els.rpcUrl.value.trim()) {
    params.set("rpc_url", els.rpcUrl.value.trim());
  }
  if (els.economicsPath.value.trim()) {
    params.set("economics_path", els.economicsPath.value.trim());
  }
  return params;
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function render() {
  const columns = state.mode === "sample" ? accountColumns : fillColumns;
  els.tableHead.innerHTML = `<tr>${columns.map(([, label]) => `<th>${escapeHtml(label)}</th>`).join("")}</tr>`;
  if (state.rows.length === 0) {
    els.tableBody.innerHTML = `<tr><td class="empty" colspan="${columns.length}">No rows</td></tr>`;
  } else {
    els.tableBody.innerHTML = state.rows.map((row) => renderRow(row, columns)).join("");
  }
  renderSummary();
}

function renderRow(row, columns) {
  const cells = columns.map(([key, , formatter]) => {
    const value = formatter ? formatter(row[key], row) : row[key];
    const className = key.includes("maker") || key.includes("hash") || key === "transaction_hashes" ? "mono" : riskClass(key, row[key]);
    return `<td class="${className}">${escapeHtml(value)}</td>`;
  });
  return `<tr>${cells.join("")}</tr>`;
}

function renderSummary() {
  els.rowCount.textContent = String(state.rows.length);
  els.activeMode.textContent = modeLabel();
  const maxRisk = Math.max(0, ...state.rows.map((row) => Number(row.account_risk_score || 0)));
  const maxFilled = Math.max(0, ...state.rows.map((row) => Number(row.filled_notional || row.chain_filled_notional || 0)));
  els.maxRisk.textContent = maxRisk ? maxRisk.toFixed(3) : "-";
  els.maxFilled.textContent = maxFilled ? formatNumber(maxFilled) : "-";
}

function updateModeControls() {
  const chainControls = [els.chainId, els.fromBlock, els.toBlock, els.chunkSize, els.rpcUrl];
  chainControls.forEach((input) => {
    input.disabled = els.mode.value === "sample";
  });
  els.economicsPath.disabled = els.mode.value === "sample";
  document.querySelector(".generic-controls").classList.toggle("is-hidden", els.mode.value !== "generic");
  document.querySelectorAll(".generic-controls input, .generic-controls select").forEach((input) => {
    input.disabled = els.mode.value !== "generic";
  });
}

function modeLabel() {
  if (state.mode === "sample") return "Sample";
  if (state.mode === "generic") return "Generic EVM";
  return "Polymarket";
}

function setBusy(value) {
  els.runButton.disabled = value;
  els.runButton.textContent = value ? "Running" : "Run Scan";
  if (value) {
    els.status.textContent = "Loading";
  }
}

function formatRisk(value) {
  return Number(value || 0).toFixed(4);
}

function formatNumber(value) {
  const number = Number(value || 0);
  return number.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function formatRatio(value) {
  if (value === "inf") return "inf";
  return formatNumber(value);
}

function formatList(value) {
  return Array.isArray(value) ? value.join(", ") : value || "";
}

function formatBlocks(value) {
  if (!Array.isArray(value) || value.length === 0) return "";
  return value.length === 1 ? String(value[0]) : `${value[0]}-${value[value.length - 1]}`;
}

function formatProofs(value) {
  if (!Array.isArray(value)) return "";
  return value.slice(0, 2).map(shorten).join(", ");
}

function shorten(value) {
  const text = String(value || "");
  return text.length <= 18 ? text : `${text.slice(0, 10)}...${text.slice(-6)}`;
}

function riskClass(key, value) {
  if (!key.includes("risk")) return "";
  const number = Number(value || 0);
  if (number >= 0.7) return "risk-high";
  if (number >= 0.4) return "risk-medium";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
