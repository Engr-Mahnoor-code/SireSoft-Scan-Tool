/**
 * upload.js — Multi-receipt upload page.
 *
 * Users can queue several receipts (limit read from data-max-files), then each
 * one is sent to /api/upload/ in its own request so results stream in per
 * receipt and a single failure never takes down the rest of the batch.
 */

(function () {
  "use strict";

  // ---- DOM refs ----
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const queueSection = document.getElementById("queue-section");
  const queueList = document.getElementById("file-queue");
  const queueCount = document.getElementById("queue-count");
  const clearAllBtn = document.getElementById("clear-all");
  const analyzeBtn = document.getElementById("analyze-btn");
  const btnLabel = analyzeBtn.querySelector(".btn-label");
  const btnSpinner = analyzeBtn.querySelector(".btn-spinner");
  const uploadError = document.getElementById("upload-error");
  const progressBox = document.getElementById("upload-progress");
  const progressFill = document.getElementById("progress-fill");
  const progressText = document.getElementById("progress-text");
  const resultsPanel = document.getElementById("results-panel");
  const tabsEl = document.getElementById("result-tabs");
  const panelsEl = document.getElementById("result-panels");
  const resultTemplate = document.getElementById("result-template");
  const errorTemplate = document.getElementById("error-template");

  const MAX_FILES = parseInt(dropZone.dataset.maxFiles, 10) || 5;
  const MAX_SIZE = parseInt(dropZone.dataset.maxSize, 10) || 10 * 1024 * 1024;
  const ALLOWED_TYPES = [
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
  ];

  /** Queue entries: {id, file, previewUrl, status, error, data, receiptId} */
  let queue = [];
  let nextId = 1;
  let running = false;

  // ---- CSRF helper ----
  function getCookie(name) {
    const cookies = document.cookie.split(";");
    for (const cookie of cookies) {
      const [key, val] = cookie.trim().split("=");
      if (key === name) return decodeURIComponent(val);
    }
    return null;
  }

  // ---- Formatting helpers ----
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function toNumber(value) {
    if (typeof value === "number") return value;
    if (value === null || value === undefined || value === "") return null;
    const cleaned = String(value).replace(/[^\d.\-]/g, "");
    const num = parseFloat(cleaned);
    return isNaN(num) ? null : num;
  }

  function formatMoney(value) {
    const num = toNumber(value);
    if (num === null) return "—";
    return (
      "$" +
      num.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  }

  // ---- Error display ----
  function showError(msg) {
    uploadError.textContent = msg;
    uploadError.classList.remove("hidden");
  }

  function hideError() {
    uploadError.classList.add("hidden");
    uploadError.textContent = "";
  }

  // ---- Queue management ----
  function addFiles(fileList) {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;

    hideError();
    const rejected = [];
    let skippedForLimit = 0;

    incoming.forEach((file) => {
      if (queue.length >= MAX_FILES) {
        skippedForLimit++;
        return;
      }
      const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
      if (!ALLOWED_TYPES.includes(file.type) && !isPdf) {
        rejected.push(`${file.name} — unsupported file type`);
        return;
      }
      if (file.size > MAX_SIZE) {
        rejected.push(`${file.name} — larger than ${formatSize(MAX_SIZE)}`);
        return;
      }
      const duplicate = queue.some(
        (item) => item.file.name === file.name && item.file.size === file.size,
      );
      if (duplicate) {
        rejected.push(`${file.name} — already added`);
        return;
      }

      queue.push({
        id: nextId++,
        file: file,
        previewUrl: file.type.startsWith("image/")
          ? URL.createObjectURL(file)
          : null,
        status: "pending",
        error: null,
        data: null,
        receiptId: null,
      });
    });

    const problems = rejected.slice();
    if (skippedForLimit) {
      problems.push(
        `${skippedForLimit} file(s) skipped — you can analyze up to ${MAX_FILES} receipts at a time.`,
      );
    }
    if (problems.length) showError(problems.join(" · "));

    renderQueue();
  }

  function removeItem(id) {
    const index = queue.findIndex((item) => item.id === id);
    if (index === -1) return;
    if (queue[index].previewUrl) URL.revokeObjectURL(queue[index].previewUrl);
    queue.splice(index, 1);
    removeResultFor(id);
    renderQueue();
  }

  function clearAll() {
    queue.forEach((item) => {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    });
    queue = [];
    fileInput.value = "";
    tabsEl.innerHTML = "";
    panelsEl.innerHTML = "";
    resultsPanel.classList.add("hidden");
    progressBox.classList.add("hidden");
    hideError();
    renderQueue();
  }

  const STATUS_LABELS = {
    pending: "Ready",
    uploading: "Analyzing…",
    done: "Done",
    error: "Failed",
  };

  function renderQueue() {
    queueList.innerHTML = "";

    queue.forEach((item, index) => {
      const li = document.createElement("li");
      li.className = "queue-item queue-item-" + item.status;

      const thumb = document.createElement("div");
      thumb.className = "queue-thumb";
      if (item.previewUrl) {
        const img = document.createElement("img");
        img.src = item.previewUrl;
        img.alt = "";
        thumb.appendChild(img);
      } else {
        thumb.classList.add("queue-thumb-pdf");
        thumb.textContent = "PDF";
      }

      const meta = document.createElement("div");
      meta.className = "queue-meta";

      const name = document.createElement("span");
      name.className = "queue-name";
      name.textContent = `${index + 1}. ${item.file.name}`;
      name.title = item.file.name;

      const sub = document.createElement("span");
      sub.className = "queue-sub";
      sub.textContent = formatSize(item.file.size);

      meta.appendChild(name);
      meta.appendChild(sub);

      const badge = document.createElement("span");
      badge.className = "queue-status queue-status-" + item.status;
      badge.textContent = STATUS_LABELS[item.status] || item.status;

      li.appendChild(thumb);
      li.appendChild(meta);
      li.appendChild(badge);

      if (!running) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "btn-icon";
        remove.title = "Remove";
        remove.innerHTML = "&times;";
        remove.addEventListener("click", () => removeItem(item.id));
        li.appendChild(remove);
      }

      queueList.appendChild(li);
    });

    queueSection.classList.toggle("hidden", queue.length === 0);
    queueCount.textContent = `${queue.length} / ${MAX_FILES}`;
    dropZone.classList.toggle("drop-zone-full", queue.length >= MAX_FILES);
    updateAnalyzeButton();
  }

  function pendingItems() {
    return queue.filter(
      (item) => item.status === "pending" || item.status === "error",
    );
  }

  function updateAnalyzeButton() {
    if (running) return;
    const count = pendingItems().length;
    analyzeBtn.disabled = count === 0;
    btnLabel.textContent =
      count === 0
        ? "Analyze Receipts"
        : count === 1
          ? "Analyze 1 Receipt"
          : `Analyze ${count} Receipts`;
  }

  function setLoading(loading) {
    running = loading;
    analyzeBtn.disabled = loading;
    btnLabel.classList.toggle("hidden", loading);
    btnSpinner.classList.toggle("hidden", !loading);
    dropZone.classList.toggle("drop-zone-disabled", loading);
    clearAllBtn.disabled = loading;
    if (!loading) updateAnalyzeButton();
  }

  function setProgress(done, total) {
    progressBox.classList.remove("hidden");
    const pct = total ? Math.round((done / total) * 100) : 0;
    progressFill.style.width = pct + "%";
    progressText.textContent = `Analyzed ${done} of ${total} receipts`;
  }

  // ---- Results: tabs + panels ----
  function tabIdFor(item) {
    return "tab-" + item.id;
  }

  function panelIdFor(item) {
    return "panel-" + item.id;
  }

  function removeResultFor(id) {
    const tab = document.getElementById("tab-" + id);
    const panel = document.getElementById("panel-" + id);
    const wasActive = tab && tab.classList.contains("active");
    if (tab) tab.remove();
    if (panel) panel.remove();
    if (wasActive) {
      const firstTab = tabsEl.querySelector(".result-tab");
      if (firstTab) firstTab.click();
    }
    if (!tabsEl.children.length) resultsPanel.classList.add("hidden");
    renumberTabs();
    updateStats();
  }

  /** Keep tab numbers in step with the queue after a removal. */
  function renumberTabs() {
    queue.forEach((item, index) => {
      const tab = document.getElementById(tabIdFor(item));
      if (!tab) return;
      const num = tab.querySelector(".result-tab-num");
      if (num) num.textContent = index + 1;
    });
  }

  function activateTab(item) {
    tabsEl.querySelectorAll(".result-tab").forEach((tab) => {
      tab.classList.remove("active");
      tab.setAttribute("aria-selected", "false");
    });
    panelsEl.querySelectorAll(".result-group").forEach((panel) => {
      panel.classList.add("hidden");
    });
    const tab = document.getElementById(tabIdFor(item));
    const panel = document.getElementById(panelIdFor(item));
    if (tab) {
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
    }
    if (panel) panel.classList.remove("hidden");
  }

  function upsertTab(item, label, state) {
    let tab = document.getElementById(tabIdFor(item));
    if (!tab) {
      tab = document.createElement("button");
      tab.type = "button";
      tab.id = tabIdFor(item);
      tab.className = "result-tab";
      tab.setAttribute("role", "tab");
      tab.addEventListener("click", () => activateTab(item));
      tabsEl.appendChild(tab);
    }
    tab.classList.remove("result-tab-error", "result-tab-ok");
    tab.classList.add(state === "error" ? "result-tab-error" : "result-tab-ok");
    tab.innerHTML = "";

    const num = document.createElement("span");
    num.className = "result-tab-num";
    num.textContent = queue.indexOf(item) + 1;

    const text = document.createElement("span");
    text.className = "result-tab-label";
    text.textContent = label;

    tab.appendChild(num);
    tab.appendChild(text);
    tab.title = label;
  }

  function mountPanel(item, node) {
    const existing = document.getElementById(panelIdFor(item));
    node.id = panelIdFor(item);
    node.classList.add("hidden");
    if (existing) {
      existing.replaceWith(node);
    } else {
      panelsEl.appendChild(node);
    }
    resultsPanel.classList.remove("hidden");
  }

  function renderSuccess(item) {
    const data = item.data || {};
    const est = data.establishment || {};
    const node = resultTemplate.content.firstElementChild.cloneNode(true);
    const field = (name) => node.querySelector(`[data-field="${name}"]`);

    field("heading").textContent = est.name || "Establishment";
    field("filename").textContent = item.file.name;
    field("vendor").textContent = est.name || "—";
    field("date").textContent = est.date || "—";
    field("time").textContent = est.time || "—";
    field("address").textContent = est.address || "—";

    const detailLink = field("detail-link");
    if (item.receiptId) {
      detailLink.href = `/receipt/${item.receiptId}/`;
    } else {
      detailLink.classList.add("hidden");
    }

    // Items
    const tbody = field("items");
    const items = Array.isArray(data.items) ? data.items : [];
    if (items.length) {
      items.forEach((row) => {
        const tr = document.createElement("tr");
        [
          row.name || "—",
          row.quantity === undefined || row.quantity === null
            ? "—"
            : String(row.quantity),
          row.unit_price === undefined || row.unit_price === null
            ? "—"
            : String(row.unit_price),
          row.total === undefined || row.total === null
            ? "—"
            : String(row.total),
        ].forEach((value) => {
          const td = document.createElement("td");
          td.textContent = value;
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    } else {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 4;
      td.style.color = "var(--text-muted)";
      td.textContent = "No items found";
      tr.appendChild(td);
      tbody.appendChild(tr);
    }

    // Summary
    const summary = data.bill_summary || {};
    const summaryEl = field("summary");
    [
      ["Subtotal", summary.subtotal],
      ["Tax", summary.tax],
      ["Discount", summary.discount],
      ["Tip", summary.tip],
      ["Payment Method", summary.payment_method],
    ].forEach(([label, value]) => {
      if (value === undefined || value === null || value === "") return;
      const row = document.createElement("div");
      row.className = "summary-row";
      const left = document.createElement("span");
      left.textContent = label;
      const right = document.createElement("span");
      right.textContent = String(value);
      row.appendChild(left);
      row.appendChild(right);
      summaryEl.appendChild(row);
    });
    if (summary.grand_total !== undefined && summary.grand_total !== null) {
      const row = document.createElement("div");
      row.className = "summary-row summary-total";
      const left = document.createElement("span");
      left.textContent = "Grand Total";
      const right = document.createElement("span");
      right.textContent = String(summary.grand_total);
      row.appendChild(left);
      row.appendChild(right);
      summaryEl.appendChild(row);
    }

    // Insights — the model returns either a list or a dict
    const insightsCard = field("insights-card");
    const insightsList = field("insights");
    let insights = data.insights || [];
    if (!Array.isArray(insights)) {
      insights = Object.entries(insights).map(([k, v]) => `${k}: ${v}`);
    }
    if (insights.length) {
      insights.forEach((insight) => {
        const li = document.createElement("li");
        li.textContent = insight;
        insightsList.appendChild(li);
      });
    } else {
      insightsCard.remove();
    }

    mountPanel(item, node);
    upsertTab(item, est.name || item.file.name, "ok");
  }

  function renderFailure(item) {
    const node = errorTemplate.content.firstElementChild.cloneNode(true);
    const field = (name) => node.querySelector(`[data-field="${name}"]`);
    field("filename").textContent = item.file.name;
    field("error").textContent = item.error || "Something went wrong.";
    field("retry").addEventListener("click", () => {
      if (running) return;
      runBatch([item]);
    });
    mountPanel(item, node);
    upsertTab(item, item.file.name, "error");
  }

  function updateStats() {
    const processed = queue.filter(
      (item) => item.status === "done" || item.status === "error",
    );
    const succeeded = queue.filter((item) => item.status === "done");
    const failed = processed.length - succeeded.length;

    document.getElementById("stat-processed").textContent = processed.length;
    document.getElementById("stat-success").textContent = succeeded.length;
    document.getElementById("stat-failed").textContent = failed;

    let combined = null;
    succeeded.forEach((item) => {
      const summary = (item.data && item.data.bill_summary) || {};
      const total = toNumber(summary.grand_total);
      if (total !== null) combined = (combined || 0) + total;
    });
    document.getElementById("stat-total").textContent =
      combined === null ? "—" : formatMoney(combined);
  }

  // ---- Upload ----
  async function uploadOne(item) {
    const formData = new FormData();
    formData.append("files", item.file);

    const res = await fetch("/api/upload/", {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
      body: formData,
    });

    let json;
    try {
      json = await res.json();
    } catch (_) {
      throw new Error(`Server error (${res.status}). Please try again.`);
    }

    const result = (json.results && json.results[0]) || null;
    if (result && result.status === "success") {
      return result;
    }
    throw new Error(
      (result && result.error) ||
        json.error ||
        `Error ${res.status}: upload failed.`,
    );
  }

  async function runBatch(items) {
    if (!items.length || running) return;

    hideError();
    setLoading(true);
    renderQueue();

    let done = 0;
    setProgress(0, items.length);

    for (const item of items) {
      item.status = "uploading";
      renderQueue();
      try {
        const result = await uploadOne(item);
        item.status = "done";
        item.data = result.data;
        item.receiptId = result.receipt_id;
        item.error = null;
        renderSuccess(item);
      } catch (err) {
        item.status = "error";
        item.error =
          err.message || "Network error — please check your connection.";
        renderFailure(item);
      }
      done++;
      setProgress(done, items.length);
      updateStats();
      renderQueue();

      // Show the first finished receipt straight away.
      if (!panelsEl.querySelector(".result-group:not(.hidden)")) {
        activateTab(item);
      }
    }

    setLoading(false);
    renderQueue();

    const failedCount = items.filter((item) => item.status === "error").length;
    if (failedCount) {
      showError(
        `${failedCount} of ${items.length} receipt(s) could not be processed. Open their tab to retry.`,
      );
    }
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---- Event listeners ----
  dropZone.addEventListener("click", (e) => {
    // Let the <label for="file-input"> handle its own click naturally.
    if (running) return;
    if (e.target.closest("label") || e.target === fileInput) return;
    fileInput.click();
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    if (running) return;
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    if (running) return;
    addFiles(e.dataTransfer.files);
  });

  fileInput.addEventListener("change", () => {
    addFiles(fileInput.files);
    fileInput.value = "";
  });

  clearAllBtn.addEventListener("click", () => {
    if (!running) clearAll();
  });

  analyzeBtn.addEventListener("click", () => runBatch(pendingItems()));

  renderQueue();
})();
