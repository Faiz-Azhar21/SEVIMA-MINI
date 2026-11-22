(() => {
  const state = {
    dashboard: null,
    aiReport: null,
    selectedSemester: "",
    sse: null,
  };

  const $ = (id) => document.getElementById(id);

  function esc(val) {
    return String(val ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatRp(num) {
    return "Rp " + Math.round(Number(num || 0)).toLocaleString("id-ID");
  }

  function toast(message, type = "info") {
    const container = $("toastContainer");
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  async function apiJson(url, options = {}) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = new Error(
        typeof data.detail === "string"
          ? data.detail
          : data.detail?.message || `HTTP ${resp.status}`
      );
      err.status = resp.status;
      err.payload = data;
      throw err;
    }
    return data;
  }

  // ---------------- Dashboard Load & Render ----------------
  async function loadDashboard() {
    const qs = state.selectedSemester
      ? `?semester=${encodeURIComponent(state.selectedSemester)}`
      : "";
    const data = await apiJson(`/api/dashboard${qs}`);
    state.dashboard = data;

    syncSemesterDropdown(data.available_semesters);
    renderKpis(data.summary);
    renderMonthlyChart(data.monthly_chart);
    renderProdi(data.per_program_studi, data.summary.status_counts);
    renderStudentsTable();
    renderWebhookAndKrsSelectors(data.per_mahasiswa);
    renderRecentOps(data.recent_payments, data.recent_emails);

    const updatedTime = new Date(data.generated_at).toLocaleTimeString("id-ID");
    $("lastUpdatedLabel").textContent = `Update real-time: ${updatedTime}`;
  }

  function syncSemesterDropdown(semesters) {
    const sel = $("semesterFilter");
    const currentVal = state.selectedSemester;
    const existing = Array.from(sel.options).map((o) => o.value);
    const desired = ["", ...semesters];
    if (JSON.stringify(existing) === JSON.stringify(desired)) return;

    sel.innerHTML = `<option value="">Semua Semester</option>`;
    semesters.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      sel.appendChild(opt);
    });
    sel.value = currentVal;
  }

  function renderKpis(s) {
    $("kpiTotalTagihan").textContent = s.total_tagihan_formatted;
    $("kpiTotalTagihanSub").textContent = `${s.total_mahasiswa_tertagih} mahasiswa tertagih`;

    $("kpiTotalBayar").textContent = s.total_terbayar_formatted;
    $("kpiTotalBayarSub").textContent = `${s.collection_rate_amount}% dari nominal tagihan`;

    $("kpiTotalSisa").textContent = s.total_sisa_formatted;
    $("kpiTotalDendaSub").textContent = `Termasuk denda keterlambatan ${s.total_denda_formatted}`;

    $("kpiCollectionRate").textContent = `${s.collection_rate_students}%`;
    $("kpiKrsBlockedSub").textContent = `${s.mahasiswa_lunas} lunas · ${s.mahasiswa_diblokir_krs} diblokir KRS`;
  }

  function renderMonthlyChart(items) {
    const wrap = $("monthlyChartContainer");
    if (!items || items.length === 0) {
      wrap.innerHTML = `<div class="empty-state">Belum ada transaksi pembayaran tercatat.</div>`;
      return;
    }

    const width = 640;
    const height = 250;
    const pad = { top: 28, right: 20, bottom: 44, left: 68 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const maxVal = Math.max(...items.map((d) => d.total_amount), 1);
    const barSlot = plotW / items.length;
    const barW = Math.min(54, Math.max(22, barSlot * 0.56));

    let gridSvg = "";
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const y = pad.top + plotH - (plotH * i) / steps;
      const val = (maxVal * i) / steps;
      const shortVal =
        val >= 1_000_000 ? `${(val / 1_000_000).toFixed(1)} jt` : `${Math.round(val / 1000)} rb`;
      gridSvg += `
        <line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="#e2e8f0" stroke-dasharray="3 3" />
        <text x="${pad.left - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="#64748b">${esc(shortVal)}</text>
      `;
    }

    let barsSvg = "";
    items.forEach((d, idx) => {
      const x = pad.left + idx * barSlot + (barSlot - barW) / 2;
      const barH = Math.max(4, (d.total_amount / maxVal) * plotH);
      const y = pad.top + plotH - barH;
      const labelShort =
        d.total_amount >= 1_000_000
          ? `${(d.total_amount / 1_000_000).toFixed(1)}jt`
          : `${Math.round(d.total_amount / 1000)}rb`;

      barsSvg += `
        <g class="chart-bar">
          <title>${esc(d.label)}: ${esc(d.total_amount_formatted)} (${d.transaction_count} transaksi)</title>
          <rect x="${x}" y="${y}" width="${barW}" height="${barH}" rx="6" fill="url(#barGrad)" />
          <text x="${x + barW / 2}" y="${y - 6}" text-anchor="middle" font-size="11" font-weight="700" fill="#1e293b">${esc(labelShort)}</text>
          <text x="${x + barW / 2}" y="${height - 20}" text-anchor="middle" font-size="11" fill="#475569">${esc(d.label)}</text>
          <text x="${x + barW / 2}" y="${height - 6}" text-anchor="middle" font-size="10" fill="#94a3b8">${d.transaction_count} trx</text>
        </g>
      `;
    });

    wrap.innerHTML = `
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Grafik Pembayaran per Bulan">
        <defs>
          <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#2563eb" />
            <stop offset="100%" stop-color="#60a5fa" />
          </linearGradient>
        </defs>
        ${gridSvg}
        ${barsSvg}
      </svg>
    `;
  }

  function renderProdi(prodiList, statusCounts) {
    const container = $("prodiContainer");
    if (!prodiList || prodiList.length === 0) {
      container.innerHTML = `<div class="empty-state">Belum ada data program studi.</div>`;
    } else {
      container.innerHTML = prodiList
        .map(
          (p) => `
          <div class="prodi-item">
            <div class="prodi-top">
              <span class="prodi-name">${esc(p.program_studi)}</span>
              <span class="prodi-rate">${p.collection_rate_students}% lunas</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill" style="width:${Math.min(100, p.collection_rate_students)}%"></div>
            </div>
            <div class="prodi-meta">
              <span>${p.mahasiswa_lunas}/${p.total_mahasiswa_tertagih} mahasiswa lunas</span>
              <span>Terkumpul: <strong>${esc(p.total_terbayar_formatted)}</strong> (${p.collection_rate_amount}%)</span>
            </div>
          </div>
        `
        )
        .join("");
    }

    $("statusSummaryRow").innerHTML = `
      <span class="badge badge-paid">Paid: ${statusCounts.paid}</span>
      <span class="badge badge-partial">Partial: ${statusCounts.partial}</span>
      <span class="badge badge-unpaid">Unpaid: ${statusCounts.unpaid}</span>
      <span class="badge badge-overdue">Overdue: ${statusCounts.overdue}</span>
    `;
  }

  function statusBadge(status) {
    const map = {
      paid: "badge-paid",
      partial: "badge-partial",
      unpaid: "badge-unpaid",
      overdue: "badge-overdue",
    };
    return `<span class="badge ${map[status] || "badge-neutral"}">${esc(status)}</span>`;
  }

  function renderStudentsTable() {
    if (!state.dashboard) return;
    const q = $("searchInput").value.trim().toLowerCase();
    const prodiF = $("prodiFilter").value;
    const statusF = $("statusFilter").value;

    const rows = state.dashboard.per_mahasiswa.filter((m) => {
      if (q && !m.nim.toLowerCase().includes(q) && !m.nama.toLowerCase().includes(q)) return false;
      if (prodiF && m.program_studi !== prodiF) return false;
      if (statusF && m.status_ringkas !== statusF) return false;
      return true;
    });

    const tbody = $("studentTableBody");
    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state">Tidak ada mahasiswa yang cocok dengan filter.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows
      .map((m) => {
        const openBilling = m.billings.find((b) => b.status !== "paid" && b.remaining_amount > 0);
        const krsBadge = m.krs_blocked
          ? `<span class="badge badge-overdue">Diblokir</span>`
          : `<span class="badge badge-paid">Diizinkan</span>`;
        const dendaNote =
          m.total_denda > 0 ? `<div class="student-sub">Denda: ${esc(formatRp(m.total_denda))}</div>` : "";
        const activeTag = m.status_aktif ? "" : ` <span class="badge badge-neutral">Non-Aktif</span>`;

        const payBtn = openBilling
          ? `<button class="btn btn-outline btn-xs" data-pay-id="${openBilling.billing_id}" data-pay-rem="${openBilling.remaining_amount}" data-pay-label="${esc(m.nim + " - " + m.nama + " (" + openBilling.billing_code + ")")}">Bayar</button>`
          : "";
        const whBtn = openBilling
          ? `<button class="btn btn-outline btn-xs" data-wh-id="${openBilling.billing_id}" data-wh-rem="${openBilling.remaining_amount}">Webhook</button>`
          : "";
        const krsBtn = `<button class="btn btn-outline btn-xs" data-krs-nim="${esc(m.nim)}">Cek KRS</button>`;

        return `
          <tr>
            <td>
              <div class="student-name">${esc(m.nama)}${activeTag}</div>
              <div class="student-sub">${esc(m.nim)} · ${esc(m.email)}</div>
            </td>
            <td>${esc(m.program_studi)}</td>
            <td class="num">${esc(m.total_tagihan_formatted)}${dendaNote}</td>
            <td class="num">${esc(m.sudah_bayar_formatted)}</td>
            <td class="num"><strong>${esc(m.sisa_formatted)}</strong></td>
            <td>${statusBadge(m.status_ringkas)}</td>
            <td>${krsBadge}</td>
            <td><div class="actions-cell">${payBtn}${whBtn}${krsBtn}</div></td>
          </tr>
        `;
      })
      .join("");
  }

  function renderWebhookAndKrsSelectors(students) {
    const whSel = $("whBillingSelect");
    const prevWh = whSel.value;
    const openBills = [];
    students.forEach((m) => {
      m.billings.forEach((b) => {
        if (b.status !== "paid" && b.remaining_amount > 0) {
          openBills.push({ ...b, nim: m.nim, nama: m.nama });
        }
      });
    });

    if (openBills.length === 0) {
      whSel.innerHTML = `<option value="">Semua tagihan sudah lunas</option>`;
    } else {
      whSel.innerHTML = openBills
        .map(
          (b) =>
            `<option value="${b.billing_id}" data-rem="${b.remaining_amount}">${esc(
              `${b.billing_code} | ${b.nim} ${b.nama} | Sisa ${formatRp(b.remaining_amount)} (${b.status})`
            )}</option>`
        )
        .join("");
      if (prevWh && openBills.some((b) => String(b.billing_id) === prevWh)) {
        whSel.value = prevWh;
      }
      if (!$("whAmount").value) {
        const selectedOpt = whSel.options[whSel.selectedIndex];
        if (selectedOpt?.dataset.rem) $("whAmount").value = selectedOpt.dataset.rem;
      }
    }

    const krsSel = $("krsNimSelect");
    const prevKrs = krsSel.value;
    krsSel.innerHTML = students
      .map(
        (m) =>
          `<option value="${esc(m.nim)}">${esc(
            `${m.nim} - ${m.nama} (${m.program_studi}) [${m.krs_blocked ? "DIBLOKIR" : "BEBAS"}]`
          )}</option>`
      )
      .join("");
    if (prevKrs) krsSel.value = prevKrs;
  }

  function renderRecentOps(payments, emails) {
    $("recentPaymentsList").innerHTML =
      payments.length === 0
        ? `<div class="empty-state">Belum ada pembayaran.</div>`
        : payments
            .map(
              (p) => `
            <div class="log-item">
              <div class="log-item-head">
                <span>${esc(p.nama)} (${esc(p.nim)})</span>
                <span>${esc(p.amount_formatted)}</span>
              </div>
              <div class="log-item-sub">
                ${esc(p.transaction_id)} · ${esc(p.method)} · <span class="badge badge-neutral">${esc(p.source)}</span>
              </div>
            </div>
          `
            )
            .join("");

    $("recentEmailsList").innerHTML =
      emails.length === 0
        ? `<div class="empty-state">Belum ada email terkirim. Coba kirim webhook atau klik "Hitung Denda & Reminder".</div>`
        : emails
            .map(
              (e) => `
            <div class="log-item">
              <div class="log-item-head">
                <span>${esc(e.subject)}</span>
                <span class="badge ${e.email_type === "receipt" ? "badge-paid" : "badge-partial"}">${esc(e.email_type)}</span>
              </div>
              <div class="log-item-sub">
                Ke: ${esc(e.recipient_email)} · Status: ${esc(e.delivery_status)} · ${new Date(e.sent_at).toLocaleString("id-ID")}
              </div>
            </div>
          `
            )
            .join("");
  }

  // ---------------- Scheduler Info ----------------
  async function loadSchedulerJobs() {
    const res = await apiJson("/api/scheduler/jobs");
    const list = $("schedulerJobsList");
    list.innerHTML = res.jobs
      .map(
        (j) => `
        <div class="log-item">
          <div class="log-item-head">
            <span>${esc(j.name)}</span>
            <span class="badge ${j.running ? "badge-paid" : "badge-neutral"}">${j.running ? "ACTIVE" : "READY"}</span>
          </div>
          <div class="log-item-sub">
            ID: <code>${esc(j.id)}</code> · Trigger: ${esc(j.trigger)}<br/>
            Next run: ${j.next_run_time ? new Date(j.next_run_time).toLocaleString("id-ID") : "-"}
          </div>
        </div>
      `
      )
      .join("");
  }

  // ---------------- AI Financial Report ----------------
  async function loadAiReport(source = "live") {
    const data = await apiJson(`/api/ai-report?source=${encodeURIComponent(source)}`);
    renderAiReport(data);
  }

  function renderAiReport(data) {
    state.aiReport = data;
    $("aiRecommendationBanner").textContent = `Rekomendasi AI: ${data.rekomendasi}`;
    $("aiRevenueBulanIni").textContent = data.summary.total_revenue_bulan_ini_formatted;
    $("aiCollectionRate").textContent = data.summary.collection_rate_text;
    $("aiOverdue2m").textContent = `${data.tunggakan_lebih_2_bulan.count} mahasiswa`;
    $("aiEngineInfo").textContent = `${data.engine} (${data.data_source || "csv"})`;

    const tbody = $("aiTop10Body");
    if (!data.top_10_tunggakan || data.top_10_tunggakan.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Tidak ada mahasiswa dengan tunggakan.</td></tr>`;
    } else {
      tbody.innerHTML = data.top_10_tunggakan
        .map(
          (row) => `
          <tr>
            <td><strong>#${row.rank}</strong></td>
            <td>
              <div class="student-name">${esc(row.nama)}</div>
              <div class="student-sub">${esc(row.nim)} · ${esc(row.program_studi)}</div>
            </td>
            <td>${statusBadge(row.status)}</td>
            <td>${row.lama_tunggakan_bulan} bln</td>
            <td class="num"><strong>${esc(row.total_tunggakan_formatted)}</strong></td>
          </tr>
        `
        )
        .join("");
    }

    $("aiInsightsList").innerHTML = (data.ai_narrative_insights || [])
      .map((line) => `<li>${esc(line)}</li>`)
      .join("");
    $("aiRawJsonPre").textContent = JSON.stringify(data, null, 2);
  }

  // ---------------- Webhook Helpers ----------------
  function genTxId() {
    return "GW-TRX-" + Date.now().toString().slice(-8);
  }

  async function buildWebhookPreview() {
    const billingId = Number($("whBillingSelect").value);
    const amount = Number($("whAmount").value);
    if (!billingId || !amount) {
      $("webhookCurlPre").textContent = "Pilih tagihan dan nominal terlebih dahulu.";
      return null;
    }
    const payload = {
      transaction_id: $("whTxId").value.trim() || genTxId(),
      billing_id: billingId,
      amount,
      status: $("whStatus").value,
      payment_method: $("whMethod").value,
    };
    $("whTxId").value = payload.transaction_id;

    const preview = await apiJson("/api/webhook/sign-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("webhookCurlPre").textContent = preview.curl_command;
    return preview;
  }

  // ---------------- KRS Helpers ----------------
  function renderKrsResult(isBlocked, title, detailsObj) {
    const el = $("krsResultCard");
    el.className = `result-panel ${isBlocked ? "blocked" : "allowed"}`;
    el.innerHTML = `
      <div style="font-weight:700;margin-bottom:8px;">${esc(title)}</div>
      <pre style="margin:0;white-space:pre-wrap;font-size:0.8rem;">${esc(JSON.stringify(detailsObj, null, 2))}</pre>
    `;
  }

  // ---------------- SSE Real-Time Connection ----------------
  function connectSSE() {
    if (state.sse) state.sse.close();
    const sse = new EventSource("/api/dashboard/stream");
    state.sse = sse;

    sse.addEventListener("connected", () => {
      $("liveBadge").classList.remove("offline");
      $("liveStatusText").textContent = "LIVE Real-Time (SSE)";
    });

    sse.addEventListener("update", async (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        toast(`Update real-time: ${msg.event}`, "success");
      } catch (_) {}
      await Promise.all([loadDashboard(), loadAiReport("live")]);
    });

    sse.onerror = () => {
      $("liveBadge").classList.add("offline");
      $("liveStatusText").textContent = "Auto-refresh aktif";
    };
  }

  // ---------------- Event Bindings ----------------
  function bindEvents() {
    // Tabs
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $(btn.dataset.tab).classList.add("active");
      });
    });

    // Filters
    $("semesterFilter").addEventListener("change", (e) => {
      state.selectedSemester = e.target.value;
      loadDashboard();
    });
    $("searchInput").addEventListener("input", renderStudentsTable);
    $("prodiFilter").addEventListener("change", renderStudentsTable);
    $("statusFilter").addEventListener("change", renderStudentsTable);

    // Table quick actions (event delegation)
    $("studentTableBody").addEventListener("click", (e) => {
      const payBtn = e.target.closest("[data-pay-id]");
      if (payBtn) {
        $("payBillingId").value = payBtn.dataset.payId;
        $("payAmount").value = payBtn.dataset.payRem;
        $("payModalInfo").textContent = `Tagihan: ${payBtn.dataset.payLabel} · Sisa: ${formatRp(payBtn.dataset.payRem)}`;
        $("payModal").classList.remove("hidden");
        return;
      }

      const whBtn = e.target.closest("[data-wh-id]");
      if (whBtn) {
        document.querySelector('[data-tab="tab-webhook"]').click();
        $("whBillingSelect").value = whBtn.dataset.whId;
        $("whAmount").value = whBtn.dataset.whRem;
        $("whTxId").value = genTxId();
        buildWebhookPreview();
        $("tab-webhook").scrollIntoView({ behavior: "smooth" });
        return;
      }

      const krsBtn = e.target.closest("[data-krs-nim]");
      if (krsBtn) {
        document.querySelector('[data-tab="tab-krs"]').click();
        $("krsNimSelect").value = krsBtn.dataset.krsNim;
        $("btnCheckKrs").click();
        $("tab-krs").scrollIntoView({ behavior: "smooth" });
      }
    });

    // Generate Billing Modal
    $("btnOpenGenModal").addEventListener("click", () => $("genModal").classList.remove("hidden"));
    $("btnCloseGenModal").addEventListener("click", () => $("genModal").classList.add("hidden"));
    $("btnCancelGen").addEventListener("click", () => $("genModal").classList.add("hidden"));

    $("genBillingForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await apiJson("/api/billing/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            semester: $("genSemester").value.trim(),
            semester_start: $("genStartDate").value,
          }),
        });
        $("genModal").classList.add("hidden");
        toast(`Berhasil generate ${res.created_count} tagihan baru (${res.skipped_existing_count} sudah ada).`, "success");
        await Promise.all([loadDashboard(), loadAiReport("live")]);
      } catch (err) {
        toast(err.message, "error");
      }
    });

    // Manual Payment Modal
    $("btnClosePayModal").addEventListener("click", () => $("payModal").classList.add("hidden"));
    $("btnCancelPay").addEventListener("click", () => $("payModal").classList.add("hidden"));

    $("manualPayForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await apiJson("/api/billing/pay", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            billing_id: Number($("payBillingId").value),
            amount: Number($("payAmount").value),
            method: $("payMethod").value,
            notes: $("payNotes").value.trim() || null,
          }),
        });
        $("payModal").classList.add("hidden");
        $("payNotes").value = "";
        toast(`${res.message} Status: ${res.previous_status} → ${res.new_status}`, "success");
        await Promise.all([loadDashboard(), loadAiReport("live")]);
      } catch (err) {
        toast(err.message, "error");
      }
    });

    // Apply Overdue & Reminders
    $("btnRunOverdue").addEventListener("click", async () => {
      try {
        const res = await apiJson("/api/billing/apply-overdue?send_reminders=true", { method: "POST" });
        toast(
          `Selesai: ${res.overdue_updated} tagihan diperbarui overdue/denda, ${res.reminders_sent} email reminder dikirim.`,
          "success"
        );
        await Promise.all([loadDashboard(), loadAiReport("live")]);
      } catch (err) {
        toast(err.message, "error");
      }
    });

    // AI Report controls
    $("btnAiLive").addEventListener("click", () => loadAiReport("live"));
    $("btnAiSample").addEventListener("click", () => loadAiReport("sample_csv"));
    $("btnToggleJson").addEventListener("click", () => $("aiRawJsonBox").classList.toggle("hidden"));
    $("btnCopyAiJson").addEventListener("click", () => {
      navigator.clipboard?.writeText($("aiRawJsonPre").textContent);
      toast("JSON AI Financial Report disalin ke clipboard.", "success");
    });

    $("csvUploadInput").addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      try {
        const data = await apiJson("/api/ai-report/analyze-csv", { method: "POST", body: fd });
        renderAiReport(data);
        toast(`CSV '${file.name}' berhasil dianalisis.`, "success");
      } catch (err) {
        toast(err.message, "error");
      } finally {
        e.target.value = "";
      }
    });

    // Webhook controls
    $("whBillingSelect").addEventListener("change", (e) => {
      const opt = e.target.options[e.target.selectedIndex];
      if (opt?.dataset.rem) $("whAmount").value = opt.dataset.rem;
      $("whTxId").value = genTxId();
      buildWebhookPreview();
    });
    $("btnPreviewCurl").addEventListener("click", buildWebhookPreview);
    $("btnCopyCurl").addEventListener("click", () => {
      navigator.clipboard?.writeText($("webhookCurlPre").textContent);
      toast("Perintah curl disalin ke clipboard.", "success");
    });

    $("webhookForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const preview = await buildWebhookPreview();
        if (!preview) return;
        const res = await apiJson("/api/webhook/payment", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Signature": preview.signature,
          },
          body: preview.raw_payload,
        });
        $("webhookRespPre").textContent = JSON.stringify(res, null, 2);
        $("whTxId").value = genTxId();
        toast(res.message, "success");
        await Promise.all([loadDashboard(), loadAiReport("live")]);
      } catch (err) {
        $("webhookRespPre").textContent = JSON.stringify(err.payload || { error: err.message }, null, 2);
        toast(err.message, "error");
      }
    });

    // KRS controls
    $("btnCheckKrs").addEventListener("click", async () => {
      const nim = $("krsNimSelect").value;
      if (!nim) return;
      try {
        const res = await apiJson(`/api/krs/${encodeURIComponent(nim)}/eligibility`);
        renderKrsResult(
          res.krs_blocked,
          res.krs_blocked ? `KRS DIBLOKIR — ${res.reason}` : `KRS DIIZINKAN — ${res.reason}`,
          res
        );
      } catch (err) {
        toast(err.message, "error");
      }
    });

    $("krsForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const matkul = $("krsMatkul")
        .value.split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      try {
        const res = await apiJson("/api/krs/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            nim: $("krsNimSelect").value,
            semester: $("krsSemester").value.trim(),
            mata_kuliah: matkul,
            total_sks: Number($("krsSks").value),
          }),
        });
        renderKrsResult(false, "HTTP 201 — KRS Berhasil Disubmit!", res);
        toast("KRS berhasil disimpan!", "success");
      } catch (err) {
        renderKrsResult(true, `HTTP ${err.status || 403} — Pengisian KRS Ditolak`, err.payload || { error: err.message });
        toast(err.message, "error");
      }
    });
  }

  // ---------------- Boot ----------------
  async function init() {
    $("whTxId").value = genTxId();
    bindEvents();
    await Promise.all([loadDashboard(), loadAiReport("live"), loadSchedulerJobs()]);
    buildWebhookPreview().catch(() => {});
    connectSSE();
    // Fallback periodic refresh setiap 15 detik
    setInterval(() => {
      loadDashboard().catch(() => {});
    }, 15000);
  }

  init().catch((err) => {
    console.error(err);
    toast("Gagal memuat dashboard: " + err.message, "error");
  });
})();
