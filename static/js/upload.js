/**
 * upload.js — Handles drag-and-drop, file selection, and API call
 * for the receipt upload page.
 */

(function () {
  "use strict";

  // ---- DOM refs ----
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const fileInfo = document.getElementById("file-info");
  const fileName = document.getElementById("file-name");
  const clearBtn = document.getElementById("clear-file");
  const filePreview = document.getElementById("file-preview");
  const previewImg = document.getElementById("preview-img");
  const analyzeBtn = document.getElementById("analyze-btn");
  const btnLabel = analyzeBtn.querySelector(".btn-label");
  const btnSpinner = analyzeBtn.querySelector(".btn-spinner");
  const uploadError = document.getElementById("upload-error");
  const resultsPanel = document.getElementById("results-panel");

  let selectedFile = null;

  // ---- CSRF helper ----
  function getCookie(name) {
    const cookies = document.cookie.split(";");
    for (const cookie of cookies) {
      const [key, val] = cookie.trim().split("=");
      if (key === name) return decodeURIComponent(val);
    }
    return null;
  }

  // ---- File selection ----
  function handleFile(file) {
    if (!file) return;
    selectedFile = file;
    fileName.textContent = file.name;
    fileInfo.classList.remove("hidden");
    analyzeBtn.disabled = false;
    hideError();
    resultsPanel.classList.add("hidden");

    if (file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        previewImg.src = e.target.result;
        filePreview.classList.remove("hidden");
      };
      reader.readAsDataURL(file);
    } else {
      filePreview.classList.add("hidden");
    }
  }

  function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    fileInfo.classList.add("hidden");
    filePreview.classList.add("hidden");
    analyzeBtn.disabled = true;
    resultsPanel.classList.add("hidden");
    hideError();
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

  // ---- Loading state ----
  function setLoading(loading) {
    analyzeBtn.disabled = loading;
    btnLabel.classList.toggle("hidden", loading);
    btnSpinner.classList.toggle("hidden", !loading);
  }

  // ---- Render results ----
  function renderResults(data, receiptId) {
    const est = data.establishment || {};
    document.getElementById("res-vendor").textContent = est.name || "—";
    document.getElementById("res-date").textContent = est.date || "—";
    document.getElementById("res-time").textContent = est.time || "—";
    document.getElementById("res-address").textContent = est.address || "—";

    // Items
    const tbody = document.getElementById("res-items");
    tbody.innerHTML = "";
    const items = data.items || [];
    if (items.length) {
      items.forEach((item) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${escHtml(item.name || "—")}</td>
          <td>${escHtml(String(item.quantity || "—"))}</td>
          <td>${escHtml(String(item.unit_price || "—"))}</td>
          <td>${escHtml(String(item.total || "—"))}</td>
        `;
        tbody.appendChild(tr);
      });
    } else {
      tbody.innerHTML =
        '<tr><td colspan="4" style="color:var(--text-muted)">No items found</td></tr>';
    }

    // Summary
    const summary = data.bill_summary || {};
    const summaryEl = document.getElementById("res-summary");
    summaryEl.innerHTML = "";
    const summaryFields = [
      ["Subtotal", summary.subtotal],
      ["Tax", summary.tax],
      ["Discount", summary.discount],
      ["Tip", summary.tip],
    ];
    summaryFields.forEach(([label, val]) => {
      if (val !== undefined && val !== null && val !== "") {
        const row = document.createElement("div");
        row.className = "summary-row";
        row.innerHTML = `<span>${escHtml(label)}</span><span>${escHtml(String(val))}</span>`;
        summaryEl.appendChild(row);
      }
    });
    if (summary.grand_total !== undefined && summary.grand_total !== null) {
      const totalRow = document.createElement("div");
      totalRow.className = "summary-row summary-total";
      totalRow.innerHTML = `<span>Grand Total</span><span>${escHtml(String(summary.grand_total))}</span>`;
      summaryEl.appendChild(totalRow);
    }

    // Insights — handle both array and dict from AI response
    const insightsCard = document.getElementById("insights-card");
    const insightsList = document.getElementById("res-insights");
    insightsList.innerHTML = "";
    let insights = data.insights || [];
    // If insights is a plain object (dict), convert its values to an array
    if (!Array.isArray(insights)) {
      insights = Object.entries(insights).map(([k, v]) => `${k}: ${v}`);
    }
    if (insights.length) {
      insightsCard.classList.remove("hidden");
      insights.forEach((insight) => {
        const li = document.createElement("li");
        li.textContent = insight;
        insightsList.appendChild(li);
      });
    } else {
      insightsCard.classList.add("hidden");
    }

    // View detail link
    if (receiptId) {
      const detailLink = document.getElementById("view-detail-link");
      detailLink.href = `/receipt/${receiptId}/`;
    }

    resultsPanel.classList.remove("hidden");
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---- XSS helper ----
  function escHtml(str) {
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
  }

  // ---- Upload API call ----
  async function uploadReceipt() {
    if (!selectedFile) return;

    hideError();
    setLoading(true);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await fetch("/api/upload/", {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: formData,
      });

      let json;
      try {
        json = await res.json();
      } catch (_) {
        showError(`Server error (${res.status}). Please try again.`);
        return;
      }

      if (!res.ok) {
        showError(json.error || `Error ${res.status}: upload failed.`);
        return;
      }

      renderResults(json.data, json.receipt_id);
    } catch (err) {
      showError("Network error — please check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  // ---- Event listeners ----
  dropZone.addEventListener("click", (e) => {
    // Let the <label for="file-input"> handle its own click naturally.
    // Only open the picker when clicking the drop zone background itself.
    if (e.target.closest("label") || e.target === fileInput) return;
    fileInput.click();
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) handleFile(fileInput.files[0]);
  });

  clearBtn.addEventListener("click", clearFile);

  analyzeBtn.addEventListener("click", uploadReceipt);
})();
