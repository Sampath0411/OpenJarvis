/* ================= JARVIS HUD v5 — Glass Core ================= */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const icon = (name, extra) =>
    `<svg class="ic${extra ? " " + extra : ""}"><use href="#ic-${name}"/></svg>`;

  const els = {
    log: $("log"), input: $("input"), composer: $("composer"),
    micBtn: $("micBtn"), attachBtn: $("attachBtn"), fileInput: $("fileInput"),
    seeBtn: $("seeBtn"),
    resetBtn: $("resetBtn"), exportBtn: $("exportBtn"),
    settings: $("settings"), closeSettings: $("closeSettings"),
    apiKey: $("apiKey"), toggleKey: $("toggleKey"),
    model: $("model"), modelCustom: $("modelCustom"),
    persona: $("persona"), language: $("language"), theme: $("theme"), pin: $("pin"),
    voiceToggle: $("voiceToggle"), soundToggle: $("soundToggle"),
    saveSettings: $("saveSettings"), settingsMsg: $("settingsMsg"),
    lanInfo: $("lanInfo"),
    statusDot: $("statusDot"), modelLabel: $("modelLabel"),
    reactorState: $("reactorState"),
    brandTitle: $("brandTitle"), boot: $("boot"), bootLog: $("bootLog"),
    toasts: $("toasts"),
    palette: $("palette"), paletteInput: $("paletteInput"), paletteList: $("paletteList"),
    approval: $("approval"), approvalPrompt: $("approvalPrompt"),
    approvalArgs: $("approvalArgs"), approvalEngage: $("approvalEngage"),
    approvalDeny: $("approvalDeny"), approvalTimeout: $("approvalTimeout"),
    contactsModal: $("contactsModal"),
    closeContacts: $("closeContacts"), contactsList: $("contactsList"),
    contactName: $("contactName"), contactPhone: $("contactPhone"),
    contactAliases: $("contactAliases"), contactAdd: $("contactAdd"),
    contactMsg: $("contactMsg"),
    sessionsModal: $("sessionsModal"),
    closeSessions: $("closeSessions"), sessionsList: $("sessionsList"),
    qrModal: $("qrModal"), closeQr: $("closeQr"),
    qrImg: $("qrImg"), qrUrl: $("qrUrl"), qrCopy: $("qrCopy"), qrDone: $("qrDone"),
    menuBtn: $("menuBtn"), topMenu: $("topMenu"),
    clock: $("clock"), dateStr: $("dateStr"), weatherVal: $("weatherVal"),
    indBatt: $("indBatt"), indCpu: $("indCpu"), indRam: $("indRam"),
    // New elements
    gallery: $("gallery"), galleryImg: $("galleryImg"),
    galleryClose: $("galleryClose"), galleryCaption: $("galleryCaption"),
    filesModal: $("filesModal"), closeFiles: $("closeFiles"),
    fileList: $("fileList"), filePath: $("filePath"),
    fileRefresh: $("fileRefresh"), fileSearch: $("fileSearch"),
    filePreview: $("filePreview"), filePreviewName: $("filePreviewName"),
    filePreviewContent: $("filePreviewContent"), filePreviewClose: $("filePreviewClose"),
    emailModal: $("emailModal"), closeEmail: $("closeEmail"),
    emailTo: $("emailTo"), emailSubject: $("emailSubject"),
    emailBody: $("emailBody"), emailSend: $("emailSend"),
    emailMsg: $("emailMsg"), emailInboxList: $("emailInboxList"),
    emailRefreshInbox: $("emailRefreshInbox"), emailStatus: $("emailStatus"),
    remindersModal: $("remindersModal"), closeReminders: $("closeReminders"),
    reminderText: $("reminderText"), reminderWhen: $("reminderWhen"),
    reminderAdd: $("reminderAdd"), remindersList: $("remindersList"),
    reminderMsg: $("reminderMsg"),
    pluginsModal: $("pluginsModal"), closePlugins: $("closePlugins"),
    pluginsList: $("pluginsList"), pluginMsg: $("pluginMsg"),
    chatTabsScroll: $("chatTabsScroll"), chatTabAdd: $("chatTabAdd"),
    chatSearchInput: $("chatSearchInput"), chatSearchBtn: $("chatSearchBtn"),
    chatSearchClose: $("chatSearchClose"),
    themeToggle: $("themeToggle"), themeGrid: $("themeGrid"),
    searchResults: $("searchResults"), searchResultsList: $("searchResultsList"),
    searchResultsClose: $("searchResultsClose"), searchResultsEmpty: $("searchResultsEmpty"),
  };

  // Menu item references
  els.paletteBtn = els.topMenu ? els.topMenu.querySelector('[data-act="palette"]') : null;
  els.qrTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="qr"]') : null;
  els.contactsTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="contacts"]') : null;
  els.sessionsTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="sessions"]') : null;
  els.backupBtn = els.topMenu ? els.topMenu.querySelector('[data-act="backup"]') : null;
  els.settingsTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="settings"]') : null;
  els.filesTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="files"]') : null;
  els.emailTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="email"]') : null;
  els.remindersTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="reminders"]') : null;
  els.pluginsTopBtn = els.topMenu ? els.topMenu.querySelector('[data-act="plugins"]') : null;

  let voiceOn = true, soundFx = true, busy = false;
  const PIN_KEY = "jarvis_pin";
  let accessPin = localStorage.getItem(PIN_KEY) || "";

  const layout = document.querySelector(".app-layout");
  const isMobile = () => window.innerWidth <= 880;

  function mview(v) {
    if (!isMobile()) return;
    layout.setAttribute("data-mview", v);
    document.querySelectorAll(".mnav-btn[data-view]").forEach(x =>
      x.classList.toggle("active", x.dataset.view === v));
  }
  layout.setAttribute("data-mview", "main");

  // ── Sound Effects (Web Audio API) ──
  let audioCtx = null;
  function getAudioCtx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
  }
  function playTone(freq, duration, type, volume) {
    if (!soundFx) return;
    try {
      const ctx = getAudioCtx();
      if (ctx.state === "suspended") ctx.resume();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type || "sine";
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      gain.gain.setValueAtTime(volume || 0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + duration);
    } catch (_) {}
  }
  function soundBoot() {
    if (!soundFx) return;
    playTone(440, 0.15, "sine", 0.06);
    setTimeout(() => playTone(660, 0.2, "sine", 0.06), 120);
    setTimeout(() => playTone(880, 0.3, "sine", 0.06), 280);
  }
  function soundSend() { playTone(800, 0.08, "sine", 0.04); }
  function soundReceive() { playTone(600, 0.12, "sine", 0.04); }
  function soundError() { playTone(200, 0.3, "sawtooth", 0.04); }
  function soundAlert() { playTone(880, 0.1, "square", 0.03); setTimeout(() => playTone(660, 0.1, "square", 0.03), 120); }

  /* ---------- API wrapper ---------- */
  async function api(path, opts = {}) {
    opts.headers = Object.assign(
      { "Content-Type": "application/json" },
      opts.headers,
      accessPin ? { "X-Jarvis-Pin": accessPin } : {}
    );
    let res = await fetch(path, opts);
    if (res.status === 401) {
      const entered = prompt("This device needs the JARVIS access PIN:");
      if (entered) {
        accessPin = entered.trim();
        localStorage.setItem(PIN_KEY, accessPin);
        opts.headers["X-Jarvis-Pin"] = accessPin;
        res = await fetch(path, opts);
      }
    }
    return res;
  }

  /* ---------- Arc Reactor (compact) ---------- */
  const canvas = $("reactor"), ctx = canvas && canvas.getContext("2d");
  const C = canvas ? canvas.width / 2 : 0;
  let t = 0, energy = 0.35, targetEnergy = 0.35, flash = 0, flashColor = null;
  let liveLevel = 0;

  const particles = canvas ? Array.from({ length: 16 }, () => ({
    a: Math.random() * Math.PI * 2,
    r: 30 + Math.random() * 60,
    sp: (0.004 + Math.random() * 0.01) * (Math.random() < 0.5 ? -1 : 1),
    sz: 0.5 + Math.random() * 1.4,
  })) : [];

  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  function rgba(varName, a) {
    const hex = css(varName).replace("#", "");
    const n = parseInt(hex.length === 3 ? hex.split("").map(c => c + c).join("") : hex, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  function ring(r, w, color, glow, dash) {
    ctx.beginPath(); ctx.arc(C, C, r, 0, Math.PI * 2);
    ctx.lineWidth = w; ctx.strokeStyle = color; ctx.shadowBlur = glow; ctx.shadowColor = color;
    ctx.setLineDash(dash || []); ctx.stroke();
  }
  function seg(r, count, len, rot, color, w) {
    ctx.strokeStyle = color; ctx.lineWidth = w; ctx.shadowBlur = 10; ctx.shadowColor = color; ctx.setLineDash([]);
    for (let i = 0; i < count; i++) {
      const a = rot + (i / count) * Math.PI * 2;
      ctx.beginPath(); ctx.arc(C, C, r, a, a + len); ctx.stroke();
    }
  }

  function drawReactor() {
    if (!canvas || !ctx) return;
    const eTarget = Math.max(targetEnergy, liveLevel);
    energy += (eTarget - energy) * 0.06; t += 0.016;
    liveLevel *= 0.9;
    if (flash > 0) flash -= 0.03;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let cyan = rgba("--primary", 0.5 + energy * 0.5), gold = rgba("--accent", 0.4 + energy * 0.5);
    if (flash > 0 && flashColor) cyan = `rgba(${flashColor},${0.5 + flash})`;

    ctx.save(); ctx.shadowBlur = 6; ctx.shadowColor = cyan; ctx.fillStyle = cyan;
    for (const p of particles) {
      p.a += p.sp * (1 + energy);
      const px = C + Math.cos(p.a) * p.r, py = C + Math.sin(p.a) * p.r;
      ctx.globalAlpha = 0.2 + energy * 0.5;
      ctx.beginPath(); ctx.arc(px, py, p.sz, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();

    seg(68, 24, 0.15, t * 0.4, cyan, 2);
    seg(58, 3, 1.2, -t * 0.9, gold, 3);
    ring(50, 1, rgba("--primary", 0.3), 4, [3, 6]);
    ctx.save(); ctx.translate(C, C); ctx.rotate(-t * 0.6); ctx.translate(-C, -C);
    ring(42, 4, cyan, 12, [2, 10]); ctx.restore();
    ctx.save(); ctx.translate(C, C); ctx.rotate(t * 0.5); ctx.translate(-C, -C);
    ring(34, 1.5, gold, 8, [12, 8]); ctx.restore();
    seg(26, 3, 1.5, t * 0.7, cyan, 5);
    const pulse = 16 + Math.sin(t * 3) * (2 + energy * 4);
    const g = ctx.createRadialGradient(C, C, 3, C, C, pulse);
    g.addColorStop(0, "rgba(220,250,255,0.9)");
    g.addColorStop(0.4, rgba("--primary", 0.6 + energy * 0.3));
    g.addColorStop(1, rgba("--primary", 0));
    ctx.beginPath(); ctx.arc(C, C, pulse, 0, Math.PI * 2);
    ctx.fillStyle = g; ctx.shadowBlur = 30; ctx.shadowColor = cyan; ctx.fill();
    ring(18, 2, "rgba(220,248,255,0.9)", 16, []);
    ctx.shadowBlur = 0; ctx.setLineDash([]);
    requestAnimationFrame(drawReactor);
  }
  if (canvas) drawReactor();

  function setState(label, e, cls) {
    if (!els.reactorState) return;
    els.reactorState.textContent = label;
    els.reactorState.className = "reactor-status" + (cls ? " " + cls : "");
    targetEnergy = e;
  }
  function pulseFlash(kind) {
    flash = 1; flashColor = kind === "err" ? "255,82,82" : "46,204,113";
    if (kind === "err") soundError(); else soundReceive();
  }

  /* ---------- Waveform ---------- */
  const wave = $("waveform"), wctx = wave && wave.getContext("2d");
  let audioCtxWave = null, analyser = null, micStream = null, freq = null;
  let waveMode = null;

  async function startMicAnalyser() {
    if (!navigator.mediaDevices?.getUserMedia) return;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtxWave = audioCtxWave || new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtxWave.createAnalyser(); analyser.fftSize = 128;
      audioCtxWave.createMediaStreamSource(micStream).connect(analyser);
      freq = new Uint8Array(analyser.frequencyBinCount);
    } catch (_) {}
  }
  function stopMicAnalyser() {
    if (micStream) { micStream.getTracks().forEach(tr => tr.stop()); micStream = null; }
    analyser = null;
  }
  function setWave(mode) {
    waveMode = mode;
    if (wave) wave.classList.toggle("live", !!mode);
    if (mode === "mic") startMicAnalyser(); else stopMicAnalyser();
  }

  function drawWave() {
    requestAnimationFrame(drawWave);
    if (!wctx || !waveMode) return;
    const W = wave.width, H = wave.height, bars = 30, gap = 2;
    wctx.clearRect(0, 0, W, H);
    wctx.fillStyle = css("--primary");
    let level = 0;
    if (waveMode === "mic" && analyser) {
      analyser.getByteFrequencyData(freq);
      for (let i = 0; i < freq.length; i++) level += freq[i];
      level = level / freq.length / 255;
    }
    const bw = (W - gap * (bars - 1)) / bars;
    for (let i = 0; i < bars; i++) {
      let h;
      if (waveMode === "mic" && analyser) {
        h = (freq[i % freq.length] / 255) * H;
      } else {
        h = (0.25 + 0.75 * Math.abs(Math.sin(t * 6 + i * 0.5))) * H * (0.4 + energy * 0.6);
        level = energy;
      }
      const y = (H - h) / 2;
      wctx.globalAlpha = 0.4 + (h / H) * 0.6;
      wctx.fillRect(i * (bw + gap), y, bw, Math.max(2, h));
    }
    liveLevel = Math.max(liveLevel, level);
  }
  drawWave();

  /* ════════════════════════════════════════════════════════════
     MARKDOWN RENDERER (lightweight)
     ════════════════════════════════════════════════════════════ */

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ── Markdown renderer ──
     Processed in strict order so code blocks survive untouched.
  */
  function renderMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);

    // 1. Fenced code blocks — extract FIRST so nothing inside them gets formatted.
    const codeBlocks = [];
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const cleaned = code
        .replace(/&amp;/g, "&").replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
      let highlighted = cleaned;
      if (window.hljs && lang) {
        try { highlighted = hljs.highlight(cleaned, { language: lang }).value; } catch (_) {}
      }
      const idx = codeBlocks.length;
      codeBlocks.push(`<pre><code class="language-${lang} hljs">${highlighted}</code><button class="copy-code" onclick="navigator.clipboard.writeText(this.parentElement.querySelector('code').textContent);this.textContent='${icon("check")} COPIED'">${icon("copy")} COPY</button></pre>`);
      return `%%CODEBLOCK${idx}%%`;
    });

    // 2. Inline code — protect from other formatting
    const inlineCodes = [];
    html = html.replace(/`([^`]+)`/g, (_, code) => {
      const idx = inlineCodes.length;
      inlineCodes.push(`<code>${code}</code>`);
      return `%%INLINECODE${idx}%%`;
    });

    // 3. Headers
    html = html.replace(/^##### (.*)$/gm, "<h5>$1</h5>");
    html = html.replace(/^#### (.*)$/gm, "<h4>$1</h4>");
    html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.*)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.*)$/gm, "<h1>$1</h1>");

    // 4. Horizontal rule
    html = html.replace(/^---$/gm, "<hr>");

    // 5. Blockquote
    html = html.replace(/^&gt;\s?(.*)$/gm, "<blockquote>$1</blockquote>");

    // 6. Bold + italic
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

    // 7. Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // 8. Unordered list
    html = html.replace(/^[\s]*[-*][\s](.*)$/gm, "<li>$1</li>");
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

    // 9. Ordered list
    html = html.replace(/^[\s]*\d+\.[\s](.*)$/gm, "<li>$1</li>");
    html = html.replace(/((?:<li>.*<\/li>\n?)+)(?=\s*(?:<ol|$))/g, (m) => {
      if (m.includes("<ol>")) return m;
      return "<ol>" + m + "</ol>";
    });

    // 10. Restore inline code
    inlineCodes.forEach((c, i) => { html = html.replace(`%%INLINECODE${i}%%`, c); });

    // 11. Restore code blocks
    codeBlocks.forEach((c, i) => { html = html.replace(`%%CODEBLOCK${i}%%`, c); });

    // 12. Paragraph-wrapping for bare text lines
    const blockTags = /^(<h[1-6]|<ul|<ol|<li|<pre|<blockquote|<hr|<table|<tr|<div)/;
    const lines = html.split("\n").filter(l => l.trim());
    if (!lines.length) return "";
    const result = [];
    let paraOpen = false;
    for (const line of lines) {
      if (blockTags.test(line) || line.startsWith("<li>") || line.startsWith("<tr>")) {
        if (paraOpen) { result.push("</p>"); paraOpen = false; }
        result.push(line);
        continue;
      }
      if (!paraOpen) { result.push("<p>"); paraOpen = true; }
      else result.push(" ");
      result.push(line);
    }
    if (paraOpen) result.push("</p>");
    html = result.join("");

    // Clean empty paragraphs
    html = html.replace(/<p>\s*<\/p>/g, "");
    html = html.replace(/<p><\/p>/g, "");

    return html;
  }

  /* ---------- Chat ---------- */
  let chatHistory = [];  // {who, text, tools, imgSrc, ts}

  /* ---------- Context Panel (right sidebar) ---------- */
  const ctxPanel = {
    tools: [],
    msgCount: 0,
    enabledPlugins: [],
    agentStatus: 'IDLE',

    addTool(name) {
      if (window.innerWidth <= 880) return;
      this.tools.push({ name, ts: Date.now() });
      if (this.tools.length > 20) this.tools.shift();
      this.render();
    },

    incrementMsg() {
      if (window.innerWidth <= 880) return;
      this.msgCount++;
      this.render();
    },

    async refresh() {
      if (window.innerWidth <= 880) return;
      try {
        const p = await (await api('/api/plugins')).json();
        this.enabledPlugins = (p.plugins || []).filter(p => p.enabled).map(p => p.name);
      } catch (_) {}
      try {
        const a = await (await api('/api/agent/status')).json();
        this.agentStatus = a.active ? 'ACTIVE' : 'IDLE';
      } catch (_) {}
      this.render();
    },

    render() {
      const msgEl = document.getElementById('ctxMsgCount');
      const toolEl = document.getElementById('ctxToolCount');
      const toolsContainer = document.getElementById('ctxTools');
      const pluginsContainer = document.getElementById('ctxPlugins');
      const agentEl = document.getElementById('ctxAgent');
      if (!msgEl || !toolsContainer) return;

      msgEl.textContent = this.msgCount;
      toolEl.textContent = this.tools.length;

      if (this.tools.length === 0) {
        toolsContainer.innerHTML = '<div class="ctx-empty">No tools used yet.</div>';
      } else {
        toolsContainer.innerHTML = this.tools.slice(-8).reverse().map(t =>
          `<div class="ctx-tool-item">${icon('settings')} ${escapeHtml(t.name)}</div>`
        ).join('');
      }

      if (pluginsContainer) {
        pluginsContainer.innerHTML = this.enabledPlugins.length
          ? this.enabledPlugins.map(p => `<div class="ctx-tool-item">${icon('package')} ${escapeHtml(p)}</div>`).join('')
          : '<div class="ctx-empty">None enabled</div>';
      }

      if (agentEl) agentEl.textContent = this.agentStatus;
    }
  };

  function addMsg(who, text, tools, imgSrc) {
    const div = document.createElement("div");
    div.className = "msg " + (who === "You" ? "user" : "jarvis");
    const label = document.createElement("span");
    label.className = "who"; label.textContent = who; div.appendChild(label);
    const body = document.createElement("span"); body.className = "body";
    if (who === "JARVIS") {
      body.innerHTML = renderMarkdown(text || "");
      // Apply highlight.js to any code blocks
      if (window.hljs) body.querySelectorAll("pre code").forEach(el => {
        try { hljs.highlightElement(el); } catch (_) {}
      });
    } else {
      body.textContent = text || "";
    }
    div.appendChild(body);
    // Timestamp
    const now = new Date();
    const ts = document.createElement("span");
    ts.className = "ts";
    ts.textContent = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    div.appendChild(ts);
    // Image
    if (imgSrc) {
      const im = document.createElement("img"); im.className = "thumb"; im.src = imgSrc;
      im.addEventListener("click", () => openGallery(imgSrc, text || ""));
      div.appendChild(im);
    }
    // Tool chips
    if (tools && tools.length) appendChips(div, tools);
    // Per-message actions
    const acts = document.createElement("div"); acts.className = "actions";
    acts.innerHTML = `
      <button class="act-copy" title="Copy">${icon("copy")}</button>
      <button class="act-edit" title="Edit">${icon("edit")}</button>
      <button class="act-del" title="Delete">${icon("trash")}</button>
    `;
    acts.querySelector(".act-copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(text || ""); } catch (_) {}
    });
    acts.querySelector(".act-edit").addEventListener("click", () => {
      div.classList.add("editing");
      const existing = div.querySelector(".edit-area");
      if (!existing) {
        const ea = document.createElement("div"); ea.className = "edit-area";
        ea.innerHTML = `<input type="text" value="${escapeHtml(text || "")}" />
          <button class="edit-save">${icon("check")}</button>
          <button class="edit-cancel">✕</button>`;
        div.appendChild(ea);
        ea.querySelector(".edit-save").addEventListener("click", () => {
          const val = ea.querySelector("input").value;
          if (who === "JARVIS") body.innerHTML = renderMarkdown(val);
          else body.textContent = val;
          div.classList.remove("editing");
          // Update chat history
          const idx = Array.from(els.log.children).indexOf(div);
          if (idx >= 0 && chatHistory[idx]) chatHistory[idx].text = val;
        });
        ea.querySelector(".edit-cancel").addEventListener("click", () => {
          div.classList.remove("editing");
        });
        ea.querySelector("input").addEventListener("keydown", (e) => {
          if (e.key === "Enter") ea.querySelector(".edit-save").click();
          if (e.key === "Escape") ea.querySelector(".edit-cancel").click();
        });
        ea.querySelector("input").focus();
        ea.querySelector("input").select();
      }
    });
    acts.querySelector(".act-del").addEventListener("click", () => {
      if (!confirm("Delete this message?")) return;
      // Get index BEFORE removing from DOM
      const idx = Array.from(els.log.children).indexOf(div);
      div.remove();
      if (idx >= 0 && idx < chatHistory.length) chatHistory.splice(idx, 1);
    });
    div.appendChild(acts);
    els.log.appendChild(div);
    scrollLog();
    chatHistory.push({ who, text, tools, imgSrc, ts: now.toISOString() });
    ctxPanel.incrementMsg();
    return { div, body };
  }

  function appendChips(div, tools) {
    let wrap = div.querySelector(".chips");
    if (!wrap) { wrap = document.createElement("div"); wrap.className = "chips"; div.appendChild(wrap); }
    tools.forEach((tl) => {
      const c = document.createElement("span"); c.className = "tool-chip";
      c.innerHTML = icon("settings") + " " + escapeHtml(tl.name); wrap.appendChild(c);
    });
  }
  function scrollLog() { els.log.scrollTop = els.log.scrollHeight; }

  /* ---------- Image gallery ---------- */
  function openGallery(src, caption) {
    if (!els.gallery || !els.galleryImg) return;
    els.galleryImg.src = src;
    els.galleryCaption.textContent = caption || "";
    els.gallery.classList.remove("hidden");
  }
  function closeGallery() { if (els.gallery) els.gallery.classList.add("hidden"); }
  if (els.galleryClose) els.galleryClose.addEventListener("click", closeGallery);
  if (els.gallery) els.gallery.addEventListener("click", (e) => { if (e.target === els.gallery) closeGallery(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeGallery(); });

  /* ---------- Voice out ---------- */
  function speak(text) {
    if (!voiceOn || !text || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const lang = els.language.value;
    u.lang = lang === "hi" ? "hi-IN" : lang === "te" ? "te-IN" : "en-GB";
    u.rate = 1.02; u.pitch = 0.9;
    const voices = window.speechSynthesis.getVoices();
    const pref = voices.find(v => v.lang && v.lang.startsWith(u.lang.slice(0, 2)))
      || voices.find(v => /male|david|daniel|rishi/i.test(v.name)) || voices[0];
    if (pref) u.voice = pref;
    u.onstart = () => { setState("SPEAKING", 0.9); setWave("speak"); };
    u.onend = () => { setWave(null); setState(busy ? "PROCESSING" : "ONLINE", busy ? 0.7 : 0.4); };
    window.speechSynthesis.speak(u);
  }
  function stopSpeaking() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    if (waveMode === "speak") setWave(null);
  }

  /* ---------- Voice in ---------- */
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recog = null, listening = false;
  if (SR) {
    recog = new SR(); recog.interimResults = false; recog.maxAlternatives = 1;
    recog.onresult = (e) => { els.input.value = e.results[0][0].transcript; send(); };
    recog.onend = () => { listening = false; els.micBtn.classList.remove("active"); setWave(null); };
    recog.onerror = () => { listening = false; els.micBtn.classList.remove("active"); setWave(null); };
  }
  function startListening() {
    if (!recog) return;
    stopSpeaking();
    const lang = els.language.value;
    recog.lang = lang === "hi" ? "hi-IN" : lang === "te" ? "te-IN" : "en-US";
    listening = true; els.micBtn.classList.add("active"); setState("LISTENING", 0.8); setWave("mic");
    try { recog.start(); } catch (_) {}
  }
  els.micBtn.addEventListener("click", () => listening ? recog.stop() : startListening());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") stopSpeaking(); });

  /* ---------- Streaming send ---------- */
  async function send() {
    const text = els.input.value.trim();
    if (!text || busy) return;
    els.input.value = ""; stopSpeaking(); mview("main");
    addMsg("You", text);
    soundSend();
    busy = true; setState("PROCESSING", 0.7);

    // Show typing indicator
    const typingEl = document.createElement("div");
    typingEl.className = "typing-indicator";
    typingEl.innerHTML = "<i></i><i></i><i></i>";
    els.log.appendChild(typingEl);
    scrollLog();

    const holder = addMsg("JARVIS", "");
    holder.body.classList.add("cursor");
    typingEl.remove();

    let full = "";
    let wordsRendered = 0;
    let revealTimer = null;

    function startReveal() {
      if (revealTimer) return;
      revealTimer = setInterval(() => {
        if (!full) return;
        const words = full.split(/(\s+)/);
        if (wordsRendered < words.length) {
          wordsRendered += 5;
          if (wordsRendered > words.length) wordsRendered = words.length;
          const partial = words.slice(0, wordsRendered).join('');
          holder.body.innerHTML = renderMarkdown(partial);
          if (window.hljs) holder.body.querySelectorAll("pre code").forEach(el => {
            try { hljs.highlightElement(el); } catch (_) {}
          });
          scrollLog();
          // Animate code blocks
          holder.body.querySelectorAll('pre[data-streaming]').forEach(el => {
            setTimeout(() => el.removeAttribute('data-streaming'), 350);
          });
        } else if (wordsRendered >= words.length) {
          clearInterval(revealTimer);
          revealTimer = null;
        }
      }, 40);
    }

    try {
      await consumeStream("/api/chat/stream", { message: text }, holder, (ev) => {
        if (ev.type === "token") {
          full += ev.text;
          holder.div.classList.add("streaming");
          if (!revealTimer) startReveal();
        }
        else if (ev.type === "tool") {
          appendChips(holder.div, [{ name: ev.name }]);
          ctxPanel.addTool(ev.name);
        }
        else if (ev.type === "done") {
          full = ev.text || full;
          if (revealTimer) { clearInterval(revealTimer); revealTimer = null; }
          wordsRendered = Infinity;
          holder.body.innerHTML = renderMarkdown(full);
          if (window.hljs) holder.body.querySelectorAll("pre code").forEach(el => {
            try { hljs.highlightElement(el); } catch (_) {}
          });
        }
        else if (ev.type === "error") {
          if (ev.error === "no_key") { openSettings(); }
          full = ev.text || "Error."; pulseFlash("err"); setState("ERROR", 0.4, "err");
        }
        else if (ev.type === "approval_required") {
          appendChips(holder.div, [{ name: ev.name }]);
          ctxPanel.addTool(ev.name);
          return "pause";
        }
      });
    } catch (err) { full = "Connection lost: " + err.message; pulseFlash("err"); }
    holder.body.classList.remove("cursor");
    holder.div.classList.remove("streaming");
    if (revealTimer) { clearInterval(revealTimer); revealTimer = null; }
    if (full) {
      holder.body.innerHTML = renderMarkdown(full);
      holder.body.querySelectorAll('pre code').forEach(el => {
        const pre = el.closest('pre');
        if (pre) pre.removeAttribute('data-streaming');
      });
    }
    if (window.hljs) holder.body.querySelectorAll("pre code").forEach(el => {
      try { hljs.highlightElement(el); } catch (_) {}
    });
    // Update chat history
    const idx = Array.from(els.log.children).indexOf(holder.div);
    if (idx >= 0 && chatHistory[idx]) chatHistory[idx].text = full;
    busy = false;
    soundReceive();
    if (!els.reactorState.classList.contains("err")) setState("ONLINE", 0.4, "ok");
    setTimeout(() => { if (!busy) setState("ONLINE", 0.4); }, 1200);
    speak(full);
  }
  els.composer.addEventListener("submit", (e) => { e.preventDefault(); send(); });

  /* ---------- Vision & File Upload ---------- */
  els.attachBtn.addEventListener("click", () => els.fileInput.click());
  els.fileInput.addEventListener("change", () => {
    const files = els.fileInput.files;
    if (files.length) {
      // First image: send as vision
      const imgFile = Array.from(files).find(f => f.type.startsWith("image/"));
      if (imgFile) { sendImage(imgFile); }
      else { uploadFile(files[0]); }
    }
    els.fileInput.value = "";
  });

  // Drag & drop overlay
  const dragOverlay = document.createElement("div");
  dragOverlay.className = "drag-overlay";
  dragOverlay.innerHTML = '<span>' + icon("attach") + ' Drop file to attach</span>';
  const mainPanel = document.querySelector(".main-panel");
  if (mainPanel) mainPanel.appendChild(dragOverlay);

  document.addEventListener("dragover", (e) => {
    e.preventDefault();
    dragOverlay.classList.add("visible");
  });
  document.addEventListener("dragleave", (e) => {
    if (!e.relatedTarget || e.relatedTarget.closest(".main-panel")) return;
    dragOverlay.classList.remove("visible");
  });
  document.addEventListener("drop", (e) => {
    e.preventDefault();
    dragOverlay.classList.remove("visible");
    const files = [...(e.dataTransfer?.files || [])];
    const img = files.find(x => x.type.startsWith("image/"));
    if (img) sendImage(img);
    else if (files.length) uploadFile(files[0]);
  });
  document.addEventListener("paste", (e) => {
    const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/"));
    if (item) sendImage(item.getAsFile());
  });

  async function uploadFile(file) {
    if (busy) return;
    const text = await file.text();
    const ext = file.name.split(".").pop() || "";
    const q = els.input.value.trim();
    // Insert file content into the chat input and send via the regular streaming pipeline
    const contextMessage = `I've uploaded a file named "${file.name}" (${file.type || ext}).\nContent:\n\`\`\`\n${text.slice(0, 8000)}\n\`\`\`\n${q ? "\nMy question: " + q : "\nPlease summarize this file."}`;
    els.input.value = contextMessage;
    send();
  }

  async function sendImage(file) {
    if (busy) return;
    const dataUrl = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(file); });
    const q = els.input.value.trim(); els.input.value = ""; mview("main");
    addMsg("You", q || "(image)", null, dataUrl);
    busy = true; setState("ANALYZING", 0.8);
    const holder = addMsg("JARVIS", "…"); holder.body.classList.add("cursor");
    try {
      const res = await api("/api/vision", { method: "POST", body: JSON.stringify({ message: q, image: dataUrl }) });
      const data = await res.json();
      holder.body.classList.remove("cursor");
      holder.body.innerHTML = renderMarkdown(data.reply || "…");
      if (data.error === "no_key") openSettings();
      speak(data.reply);
    } catch (err) {
      holder.body.classList.remove("cursor"); holder.body.textContent = "Vision failed: " + err.message; pulseFlash("err");
    }
    busy = false; setState("ONLINE", 0.4);
  }

  /* ---------- Reset / Export ---------- */
  els.resetBtn.addEventListener("click", async () => {
    await api("/api/reset", { method: "POST" });
    els.log.innerHTML = ""; chatHistory = [];
    addMsg("JARVIS", "Memory cleared. Fresh start, sir.");
  });
  els.exportBtn.addEventListener("click", () => {
    window.open("/api/export", "_blank");
  });

  /* ---------- Top Menu ---------- */
  function toggleMenu(force) {
    const open = force != null ? force : els.topMenu.classList.contains("hidden");
    els.topMenu.classList.toggle("hidden", !open);
  }
  els.menuBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleMenu(); });
  document.addEventListener("click", (e) => {
    if (!els.topMenu.contains(e.target) && e.target !== els.menuBtn) toggleMenu(false);
  });

  const actMap = {
    palette: openPalette,
    qr: () => openQrModal(),
    contacts: openContacts,
    sessions: openSessions,
    backup: async () => {
      try {
        const res = await api("/api/backup", { method: "POST" });
        const d = await res.json();
        toast(d.sent ? "Memory backed up to Telegram." : "Backup: " + (d.error || "local only"));
      } catch (_) { toast("Backup failed."); }
    },
    settings: openSettings,
    files: openFiles,
    email: openEmail,
    reminders: openReminders,
    plugins: openPlugins,
  };
  if (els.topMenu) {
    els.topMenu.querySelectorAll("button[data-act]").forEach((b) => {
      b.addEventListener("click", () => {
        toggleMenu(false);
        const fn = actMap[b.dataset.act];
        if (fn) fn();
      });
    });
  }

  /* ---------- Theme toggle (top bar) ---------- */
  const THEME_CYCLE = ["arc", "mark3", "ultron", "stealth", "midnight", "amoled", "light"];
  let themeIndex = 0;
  if (els.themeToggle) {
    els.themeToggle.addEventListener("click", async () => {
      themeIndex = (themeIndex + 1) % THEME_CYCLE.length;
      const name = THEME_CYCLE[themeIndex];
      applyTheme(name);
      els.theme.value = name;
      await api("/api/config", { method: "POST", body: JSON.stringify({ theme: name, persist: true }) });
      updateThemeGrid(name);
    });
  }

  /* ---------- Settings ---------- */
  function openSettings() { els.settings.classList.remove("hidden"); els.apiKey.focus(); }
  function closeSettings() { els.settings.classList.add("hidden"); }
  els.closeSettings.addEventListener("click", closeSettings);
  els.settings.addEventListener("click", (e) => { if (e.target === els.settings) closeSettings(); });
  els.toggleKey.addEventListener("click", () => { els.apiKey.type = els.apiKey.type === "password" ? "text" : "password"; });
  els.model.addEventListener("change", () => els.modelCustom.classList.toggle("hidden", els.model.value !== "__custom__"));
  els.voiceToggle.addEventListener("change", () => { voiceOn = els.voiceToggle.checked; });
  els.soundToggle.addEventListener("change", () => { soundFx = els.soundToggle.checked; });

  // Settings tabs
  document.querySelectorAll(".settings-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".settings-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".settings-panel").forEach(p => p.classList.add("hidden"));
      const panel = document.querySelector(`.settings-panel[data-stab="${tab.dataset.stab}"]`);
      if (panel) panel.classList.remove("hidden");
    });
  });

  function applyTheme(name) {
    document.documentElement.setAttribute("data-theme", name);
    if (els.themeToggle) {
      const ic = els.themeToggle.querySelector("use");
      if (name === "light") ic.setAttribute("href", "#ic-sun");
      else ic.setAttribute("href", "#ic-moon");
    }
  }

  // Theme grid
  function updateThemeGrid(active) {
    els.themeGrid.querySelectorAll(".theme-card").forEach(c => {
      c.classList.toggle("active", c.dataset.theme === active);
    });
  }
  if (els.themeGrid) {
    els.themeGrid.addEventListener("click", async (e) => {
      const card = e.target.closest(".theme-card");
      if (!card) return;
      const name = card.dataset.theme;
      applyTheme(name);
      els.theme.value = name;
      updateThemeGrid(name);
      await api("/api/config", { method: "POST", body: JSON.stringify({ theme: name, persist: true }) });
    });
  }

  els.saveSettings.addEventListener("click", async () => {
    let model = els.model.value; if (model === "__custom__") model = els.modelCustom.value.trim();
    els.settingsMsg.className = "form-msg"; els.settingsMsg.textContent = "Engaging…";
    try {
      const body = {
        api_key: els.apiKey.value.trim() || undefined,
        model: model,
        persona: els.persona.value,
        language: els.language.value,
        theme: els.theme.value,
        pin: els.pin.value.trim(),
        persist: true,
      };
      // Email config — sent separately to /api/email/config
      if (els.emailAddr.value.trim() && els.emailPass.value.trim()) {
        await api("/api/email/config", {
          method: "POST",
          body: JSON.stringify({
            email: els.emailAddr.value.trim(),
            password: els.emailPass.value,
            smtp_host: els.smtpHost.value || "smtp.gmail.com",
            smtp_port: parseInt(els.smtpPort.value, 10) || 587,
            imap_host: els.imapHost.value || "imap.gmail.com",
            imap_port: parseInt(els.imapPort.value, 10) || 993,
          })
        });
      }
      const res = await api("/api/config", { method: "POST", body: JSON.stringify(body) });
      const data = await res.json();
      voiceOn = els.voiceToggle.checked;
      soundFx = els.soundToggle.checked;
      accessPin = els.pin.value.trim(); localStorage.setItem(PIN_KEY, accessPin);
      await refreshStatus();
      els.settingsMsg.className = "form-msg ok";
      els.settingsMsg.innerHTML = data.has_key ? icon("check") + " Systems online." : "Saved — no valid key yet.";
      showLan(data.lan_url);
      if (data.has_key) {
        if (data.pin_set && data.lan_url) {
          setTimeout(() => openQrModal(data.lan_url), 700);
        } else {
          setTimeout(closeSettings, 700);
        }
      }
    } catch (err) { els.settingsMsg.className = "form-msg err"; els.settingsMsg.textContent = "Failed: " + err.message; }
  });

  function showLan(url) {
    if (url) {
      els.lanInfo.classList.remove("hidden");
      els.lanInfo.innerHTML = `${icon("phone")} Open <b>${escapeHtml(url)}</b> on your phone (same Wi-Fi).`;
    } else els.lanInfo.classList.add("hidden");
  }

  /* ---------- Status ---------- */
  async function refreshStatus() {
    try {
      const s = await (await api("/api/status")).json();
      els.modelLabel.textContent = s.model.split("/").pop();
      els.brandTitle.textContent = s.name || "JARVIS";
      els.persona.value = s.persona; els.language.value = s.language;
      els.theme.value = s.theme; applyTheme(s.theme);
      themeIndex = THEME_CYCLE.indexOf(s.theme);
      if (themeIndex < 0) themeIndex = 0;
      const opt = [...els.model.options].find(o => o.value === s.model); if (opt) els.model.value = s.model;
      // Update theme grid
      updateThemeGrid(s.theme);
      // Update settings email fields
      if (s.email_configured) {
        els.emailStatus.textContent = "✓ Email configured";
        els.emailStatus.className = "form-msg ok";
      }
      // Load email config if available
      loadEmailConfig();
      if (s.has_key) {
        els.statusDot.textContent = "ONLINE"; els.statusDot.className = "brand-badge online";
        setState("ONLINE", 0.4);
      } else {
        els.statusDot.textContent = "NO KEY"; els.statusDot.className = "brand-badge offline";
        setState("STANDBY", 0.35);
      }
      showLan(s.lan_url);
      return s;
    } catch (_) { return null; }
  }

  /* ---------- Watchdog ---------- */
  function toast(alertOrMsg) {
    const el = document.createElement("div");
    if (typeof alertOrMsg === "string") {
      el.className = "toast";
      el.innerHTML = icon("alert") + " " + alertOrMsg;
    } else {
      el.className = "toast" + (alertOrMsg.level === "crit" ? " crit" : "");
      el.innerHTML = icon("alert") + " " + escapeHtml(alertOrMsg.message);
      if (alertOrMsg.level === "crit") { pulseFlash("err"); soundAlert(); }
    }
    els.toasts.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 400); }, 8000);
  }
  async function pollWatchdog() {
    try {
      const d = await (await api("/api/watchdog")).json();
      (d.alerts || []).forEach(toast);
    } catch (_) {}
  }
  setInterval(pollWatchdog, 20000);

  /* ---------- System stats ---------- */
  function setText(id, v) { const e = $(id); if (e) e.textContent = v; }
  function setBar(id, pct) {
    const el = $(id); if (!el) return;
    pct = Math.max(0, Math.min(100, pct));
    el.style.width = pct + "%";
    el.style.background = pct >= 90 ? "var(--danger)" : pct >= 75 ? "var(--accent)" : "var(--primary)";
  }
  function fmtBytes(b) {
    if (b < 1024) return Math.round(b) + " B/s";
    if (b < 1048576) return (b / 1024).toFixed(0) + " KB/s";
    return (b / 1048576).toFixed(1) + " MB/s";
  }
  function fmtUptime(s) {
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
  }
  async function pollSystem() {
    try {
      const d = await (await api("/api/system")).json();
      if (!d || !d.available) return;
      setBar("barCpu", d.cpu);
      setBar("barRam", d.ram);
      setBar("barDisk", d.disk);
      setText("sCpu", Math.round(d.cpu) + "%");
      setText("sRam", Math.round(d.ram) + "%");
      setText("sDisk", Math.round(d.disk) + "%");
      setText("sDown", fmtBytes(d.net_down));
      setText("sUp", fmtBytes(d.net_up));
      setText("sProcs", d.procs);
      setText("sUptime", fmtUptime(d.uptime));
      setText("sHost", d.host);
      setText("sOs", d.os);
      updateIndicators(d);
      if (!busy) targetEnergy = 0.35 + (d.cpu / 100) * 0.35;
    } catch (_) {}
  }
  setInterval(pollSystem, 2500);

  /* ---------- Indicator pills ---------- */
  function updateIndicators(d) {
    if (els.indBatt) {
      const s = els.indBatt.querySelector("span:last-child");
      if (s) s.textContent = d.battery == null ? "AC" : d.battery + "%";
      els.indBatt.classList.toggle("charging", !!d.plugged);
      const low = d.battery != null && !d.plugged;
      els.indBatt.classList.toggle("crit", low && d.battery <= 15);
      els.indBatt.classList.toggle("warn", low && d.battery > 15 && d.battery <= 30);
    }
    if (els.indCpu) {
      const s = els.indCpu.querySelector("span:last-child");
      if (s) s.textContent = Math.round(d.cpu) + "%";
      els.indCpu.classList.toggle("warn", d.cpu >= 75 && d.cpu < 90);
      els.indCpu.classList.toggle("crit", d.cpu >= 90);
    }
    if (els.indRam) {
      const s = els.indRam.querySelector("span:last-child");
      if (s) s.textContent = Math.round(d.ram) + "%";
      els.indRam.classList.toggle("warn", d.ram >= 75 && d.ram < 90);
      els.indRam.classList.toggle("crit", d.ram >= 90);
    }
  }

  /* ---------- Clock ---------- */
  function tickClock() {
    const now = new Date();
    let h = now.getHours();
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12; if (h === 0) h = 12;
    const p = (n) => String(n).padStart(2, "0");
    if (els.clock) els.clock.textContent = `${h}:${p(now.getMinutes())} ${ampm}`;
    if (els.dateStr) els.dateStr.textContent = now.toLocaleDateString(undefined,
      { weekday: "short", day: "2-digit", month: "short" });
  }
  setInterval(tickClock, 1000); tickClock();

  /* ---------- Weather ---------- */
  async function pollWeather() {
    try {
      const d = await (await api("/api/weather")).json();
      if (!d || !d.available) { if (els.weatherVal) els.weatherVal.textContent = "--"; return; }
      if (els.weatherVal) {
        els.weatherVal.textContent =
          (d.temp_c != null ? d.temp_c + "°C" : "") + (d.city ? " · " + d.city : "");
      }
      const w = $("weather");
      if (w && d.desc) w.title = d.desc + (d.city ? " — " + d.city : "");
    } catch (_) {}
  }
  setInterval(pollWeather, 15 * 60 * 1000);

  /* ---------- Location ---------- */
  function sendLocation() {
    if (!("geolocation" in navigator)) { pollWeather(); return; }
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        const body = JSON.stringify({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        const d = await (await api("/api/location", { method: "POST", body })).json();
        if (d && d.available && d.weather && d.weather.available) {
          const w = d.weather;
          if (els.weatherVal) {
            els.weatherVal.textContent =
              (w.temp_c != null ? w.temp_c + "°C" : "") + (d.city ? " · " + d.city : "");
          }
          const pill = $("weather");
          if (pill) pill.title = (w.desc || "") + " — " + (d.city || "current location");
        } else { pollWeather(); }
      } catch (_) { pollWeather(); }
    }, () => { pollWeather(); },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 });
  }

  /* ---------- Mobile nav ---------- */
  document.querySelectorAll(".mnav-btn[data-view]").forEach(b =>
    b.addEventListener("click", () => mview(b.dataset.view)));
  $("mnavMic").addEventListener("click", startListening);
  $("mnavSettings").addEventListener("click", openSettings);

  /* ---------- Command palette ---------- */
  const COMMANDS = [
    { label: "Open settings", key: "settings", run: openSettings },
    { label: "File explorer", key: "folder", run: openFiles },
    { label: "Email", key: "mail", run: openEmail },
    { label: "Reminders", key: "bell", run: openReminders },
    { label: "Plugins", key: "package", run: openPlugins },
    { label: "Clear memory (reset)", key: "reset", run: () => els.resetBtn.click() },
    { label: "Export chat", key: "download", run: () => els.exportBtn.click() },
    { label: "Back up memory", key: "archive", run: async () => {
      const r = await api("/api/backup", { method: "POST" });
      const d = await r.json();
      toast(d.sent ? "Memory backed up!" : "Backup: " + (d.error || "done"));
    }},
    { label: "Start voice input", key: "mic", run: startListening },
    { label: "Stop speaking", key: "stop", run: stopSpeaking },
    { label: "Theme cycle", key: "sun", run: () => els.themeToggle.click() },
    { label: "Ask: what can you do?", key: "help", run: () => { els.input.value = "What can you do?"; send(); } },
  ];
  let paletteSel = 0, paletteFiltered = COMMANDS;

  function openPalette() {
    els.palette.classList.remove("hidden"); els.paletteInput.value = ""; paletteSel = 0;
    renderPalette(COMMANDS); els.paletteInput.focus();
  }
  function closePalette() { els.palette.classList.add("hidden"); }
  function renderPalette(list) {
    paletteFiltered = list; els.paletteList.innerHTML = "";
    list.forEach((c, i) => {
      const el = document.createElement("div");
      el.className = "palette-item" + (i === paletteSel ? " sel" : "");
      el.innerHTML = `<span>${escapeHtml(c.label)}</span><span class="k">${icon(c.key)}</span>`;
      el.addEventListener("click", () => { c.run(); closePalette(); });
      els.paletteList.appendChild(el);
    });
  }
  els.paletteInput.addEventListener("input", () => {
    const q = els.paletteInput.value.toLowerCase();
    paletteSel = 0; renderPalette(COMMANDS.filter(c => c.label.toLowerCase().includes(q)));
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
    if (els.palette.classList.contains("hidden")) return;
    if (e.key === "Escape") closePalette();
    else if (e.key === "ArrowDown") { paletteSel = Math.min(paletteSel + 1, paletteFiltered.length - 1); renderPalette(paletteFiltered); }
    else if (e.key === "ArrowUp") { paletteSel = Math.max(paletteSel - 1, 0); renderPalette(paletteFiltered); }
    else if (e.key === "Enter") { const c = paletteFiltered[paletteSel]; if (c) { c.run(); closePalette(); } }
  });

  /* ---------- Boot ---------- */
  const bootLines = [
    "> INITIALIZING J.A.R.V.I.S CORE …",
    "> loading neural interface … OK",
    "> mounting automation registry … OK",
    "> calibrating reactor core … OK",
    "> establishing Gemini uplink …",
    "> ready.",
  ];
  async function boot() {
    let booted = false;
    const forceHide = () => {
      if (booted) return; booted = true;
      try { els.boot.classList.add("done"); } catch (_) {}
      setTimeout(() => { try { els.boot.remove(); } catch (_) {} }, 500);
    };
    const safetyTimer = setTimeout(forceHide, 6000);
    try {
      for (const line of bootLines) {
        els.bootLog.textContent += line + "\n";
        await new Promise(r => setTimeout(r, 200));
      }
      await new Promise(r => setTimeout(r, 200));
      soundBoot();
      forceHide(); clearTimeout(safetyTimer);
    } catch (_) { forceHide(); clearTimeout(safetyTimer); }

    try { pollWatchdog(); } catch (_) {}
    try { pollSystem(); } catch (_) {}
    try { pollWeather(); } catch (_) {}
    try { sendLocation(); } catch (_) {}
    let s = null;
    try { s = await refreshStatus(); } catch (_) {}
    try { await ctxPanel.refresh(); } catch (_) {}
    const greet = (s && s.has_key)
      ? "Good day, Sampath. All systems are online. How can I help?"
      : "Systems on standby. Open settings and paste your Gemini API key to bring me online, sir.";
    try { addMsg("JARVIS", greet); } catch (_) {}
    try { if (s && s.has_key) speak(greet); else openSettings(); } catch (_) {}
  }

  /* ---------- SSE + Approval ---------- */
  async function consumeStream(path, body, holder, onEvent) {
    const res = await api(path, { method: "POST", body: JSON.stringify(body) });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n"); buf = parts.pop();
      for (const p of parts) {
        const line = p.split("\n").find(l => l.startsWith("data:"));
        if (!line) continue;
        let ev; try { ev = JSON.parse(line.slice(5).trim()); } catch (_) { continue; }
        const result = onEvent ? onEvent(ev) : undefined;
        if (ev.type === "approval_required" && result === "pause") {
          if (holder && holder.body) holder.body.classList.remove("cursor");
          const decision = await openApprovalModal(ev);
          if (holder && holder.body) holder.body.classList.add("cursor");
          setState("PROCESSING", 0.7);
          await consumeStream("/api/approve", { id: ev.id, approve: decision }, holder, onEvent);
          return;
        }
      }
    }
  }

  /* ---------- Approval modal ---------- */
  let approvalTimer = null, approvalSeconds = 60;
  function openApprovalModal(ev) {
    return new Promise((resolve) => {
      els.approvalPrompt.textContent = `JARVIS wants to run: ${ev.name}`;
      els.approvalArgs.textContent = JSON.stringify(ev.args, null, 2);
      els.approval.classList.remove("hidden");
      els.approvalTimeout.textContent = "60s";
      els.approvalTimeout.className = "approval-timer";
      approvalSeconds = 60;
      clearInterval(approvalTimer);
      approvalTimer = setInterval(() => {
        approvalSeconds--;
        els.approvalTimeout.textContent = `${approvalSeconds}s`;
        if (approvalSeconds <= 10) els.approvalTimeout.className = "approval-timer crit";
        else if (approvalSeconds <= 20) els.approvalTimeout.className = "approval-timer warn";
        if (approvalSeconds <= 0) {
          clearInterval(approvalTimer);
          els.approval.classList.add("hidden");
          resolve(false);
        }
      }, 1000);
      const finish = (decision) => {
        clearInterval(approvalTimer);
        els.approval.classList.add("hidden");
        resolve(decision);
      };
      els.approvalEngage.addEventListener("click", () => finish(true), { once: true });
      els.approvalDeny.addEventListener("click", () => finish(false), { once: true });
    });
  }

  /* ---------- Contacts ---------- */
  async function loadContacts() {
    try {
      const d = await (await api("/api/contacts")).json();
      renderContacts(d.contacts || []);
    } catch (_) { renderContacts([]); }
  }
  function renderContacts(items) {
    if (!items.length) {
      els.contactsList.innerHTML = '<div class="contact-empty">No contacts yet.</div>';
      return;
    }
    els.contactsList.innerHTML = "";
    items.forEach((c) => {
      const row = document.createElement("div");
      row.className = "contact-item";
      const aliases = (c.aliases || []).join(", ") || "(none)";
      row.innerHTML = `
        <div>
          <div class="c-name">${escapeHtml(c.name)}</div>
          <div class="c-phone">+${escapeHtml(c.phone_e164)}</div>
          <div class="c-aliases">${escapeHtml(aliases)}</div>
        </div>
        <button class="ghost-btn" style="border-color:var(--danger-dim);color:var(--danger)" data-name="${escapeHtml(c.name)}">DEL</button>
      `;
      row.querySelector("button").addEventListener("click", async () => {
        if (!confirm(`Delete ${c.name}?`)) return;
        await api(`/api/contacts/${encodeURIComponent(c.name)}`, { method: "DELETE" });
        loadContacts();
      });
      els.contactsList.appendChild(row);
    });
  }
  function openContacts() { els.contactsModal.classList.remove("hidden"); loadContacts(); }
  function closeContacts() { els.contactsModal.classList.add("hidden"); }
  if (els.contactsTopBtn) els.contactsTopBtn.addEventListener("click", openContacts);
  els.closeContacts.addEventListener("click", closeContacts);
  els.contactsModal.addEventListener("click", (e) => { if (e.target === els.contactsModal) closeContacts(); });
  els.contactAdd.addEventListener("click", async () => {
    const name = els.contactName.value.trim();
    const phone = els.contactPhone.value.trim();
    const aliases = els.contactAliases.value.split(",").map(s => s.trim()).filter(Boolean);
    if (!name || !phone) {
      els.contactMsg.className = "form-msg err"; els.contactMsg.textContent = "Name and phone required.";
      return;
    }
    try {
      const res = await api("/api/contacts", { method: "POST", body: JSON.stringify({ name, phone, aliases }) });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      els.contactMsg.className = "form-msg ok"; els.contactMsg.textContent = `Saved ${data.contact.name}.`;
      els.contactName.value = ""; els.contactPhone.value = ""; els.contactAliases.value = "";
      loadContacts();
    } catch (err) { els.contactMsg.className = "form-msg err"; els.contactMsg.textContent = "Failed: " + err.message; }
  });

  /* ---------- Sessions ---------- */
  async function loadSessions() {
    try {
      const d = await (await api("/api/sessions?limit=30")).json();
      renderSessions(d.sessions || []);
    } catch (_) { renderSessions([]); }
  }
  function renderSessions(items) {
    if (!items.length) {
      els.sessionsList.innerHTML = '<div class="session-empty">No sessions yet.</div>';
      return;
    }
    els.sessionsList.innerHTML = "";
    items.forEach((s) => {
      const row = document.createElement("div"); row.className = "session-item";
      row.innerHTML = `<div class="s-ts">${escapeHtml(s.ts || "?")}</div><div class="s-summary">${escapeHtml(s.summary || "")}</div>`;
      els.sessionsList.appendChild(row);
    });
  }
  function openSessions() { els.sessionsModal.classList.remove("hidden"); loadSessions(); }
  function closeSessions() { els.sessionsModal.classList.add("hidden"); }
  if (els.sessionsTopBtn) els.sessionsTopBtn.addEventListener("click", openSessions);
  els.closeSessions.addEventListener("click", closeSessions);
  els.sessionsModal.addEventListener("click", (e) => { if (e.target === els.sessionsModal) closeSessions(); });

  /* ---------- See screen ---------- */
  els.seeBtn.addEventListener("click", async () => {
    if (busy) return;
    const question = els.input.value.trim();
    els.input.value = ""; stopSpeaking(); mview("main");
    addMsg("You", question || "(look at my screen)");
    busy = true; setState("ANALYZING", 0.8);
    const holder = addMsg("JARVIS", "…"); holder.body.classList.add("cursor");
    try {
      const res = await api("/api/see", { method: "POST", body: JSON.stringify({ question }) });
      const data = await res.json();
      holder.body.classList.remove("cursor");
      holder.body.innerHTML = renderMarkdown(data.reply || "…");
      if (data.error === "no_key") openSettings();
      speak(data.reply);
    } catch (err) { holder.body.classList.remove("cursor"); holder.body.textContent = "Vision failed: " + err.message; pulseFlash("err"); }
    busy = false; setState("ONLINE", 0.4);
  });

  /* ════════════════════════════════════════════════════════════════
     FILE EXPLORER
     ════════════════════════════════════════════════════════════════ */

  let currentFilePath = "";
  async function openFiles(path) {
    els.filesModal.classList.remove("hidden");
    await loadFiles(path || "");
  }
  function closeFiles() { els.filesModal.classList.add("hidden"); }
  if (els.filesTopBtn) els.filesTopBtn.addEventListener("click", () => openFiles());
  els.closeFiles.addEventListener("click", closeFiles);
  els.filesModal.addEventListener("click", (e) => { if (e.target === els.filesModal) closeFiles(); });
  if (els.fileRefresh) els.fileRefresh.addEventListener("click", () => loadFiles(currentFilePath));

  if (els.fileSearch) {
    els.fileSearch.addEventListener("input", () => {
      const items = els.fileList.querySelectorAll(".file-item");
      const q = els.fileSearch.value.toLowerCase();
      items.forEach(el => {
        el.style.display = el.textContent.toLowerCase().includes(q) ? "flex" : "none";
      });
    });
  }

  if (els.filePreviewClose) {
    els.filePreviewClose.addEventListener("click", () => {
      els.filePreview.classList.add("hidden");
    });
  }

  async function loadFiles(path) {
    if (!path) path = "";
    els.fileList.innerHTML = Array.from({ length: 4 }, () =>
      '<div class="file-skeleton"></div>'
    ).join('');
    try {
      const res = await api(`/api/files?path=${encodeURIComponent(path || "~")}`);
      const d = await res.json();
      if (d.error) {
        els.fileList.innerHTML = `<div class="file-empty">Error: ${escapeHtml(d.message || d.error)}</div>`;
        return;
      }
      currentFilePath = d.path;
      els.filePath.textContent = d.path;
      if (d.type === "file") {
        // Show file content preview
        els.filePreview.classList.remove("hidden");
        els.filePreviewName.textContent = d.path.split(/[/\\]/).pop();
        els.filePreviewContent.textContent = d.content || "(empty file)";
        els.fileList.innerHTML = `<div class="file-empty">Showing file preview above.</div>`;
        return;
      }
      els.filePreview.classList.add("hidden");
      if (!d.entries || !d.entries.length) {
        els.fileList.innerHTML = '<div class="file-empty">Empty directory.</div>';
        return;
      }
      els.fileList.innerHTML = "";
      // Parent dir
      if (d.parent && d.parent !== d.path) {
        const parent = document.createElement("div");
        parent.className = "file-item dir";
        parent.innerHTML = `<span class="fi-icon">${icon("arrow-up")}</span><span class="fi-name">..</span>`;
        parent.addEventListener("click", () => loadFiles(d.parent));
        els.fileList.appendChild(parent);
      }
      d.entries.forEach(e => {
        const el = document.createElement("div");
        el.className = "file-item" + (e.is_dir ? " dir" : "");
        el.innerHTML = `
          <span class="fi-icon">${icon(e.is_dir ? "folder" : "file")}</span>
          <span class="fi-name">${escapeHtml(e.name)}</span>
          <span class="fi-size">${e.is_dir ? "" : fmtFileSize(e.size)}</span>
          <span class="fi-time">${fmtTime(e.modified)}</span>
        `;
        el.addEventListener("click", () => {
          if (e.is_dir) loadFiles(e.path);
          else openFilePreview(e.path);
        });
        els.fileList.appendChild(el);
      });
    } catch (_) {
      els.fileList.innerHTML = '<div class="file-empty">Failed to load files.</div>';
    }
  }

  async function openFilePreview(path) {
    try {
      const res = await api("/api/files", {
        method: "POST",
        body: JSON.stringify({ path, action: "read" })
      });
      const d = await res.json();
      els.filePreview.classList.remove("hidden");
      els.filePreviewName.textContent = path.split(/[/\\]/).pop();
      els.filePreviewContent.textContent = d.content || "(empty or binary file)";
    } catch (_) {
      toast("Could not open file preview.");
    }
  }

  function fmtFileSize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }
  function fmtTime(ts) {
    if (!ts) return "";
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  /* ════════════════════════════════════════════════════════════════
     BACKGROUND PARTICLES
     ════════════════════════════════════════════════════════════════ */

  (function initBgParticles() {
    const particleCanvas = document.getElementById('bgParticles');
    if (!particleCanvas) return;
    const pctx = particleCanvas.getContext('2d');
    let W, H;

    function resize() {
      W = particleCanvas.width = window.innerWidth;
      H = particleCanvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    function cssVar(v) {
      return getComputedStyle(document.documentElement).getPropertyValue(v).trim();
    }
    function getPrimaryRGB() {
      const hex = cssVar('--primary');
      const n = parseInt(hex.replace('#', ''), 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }

    const bgParts = Array.from({ length: 35 }, () => ({
      x: Math.random() * (window.innerWidth || 800),
      y: Math.random() * (window.innerHeight || 600),
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      r: 0.5 + Math.random() * 1.8,
    }));

    let mx = W / 2, my = H / 2;
    document.addEventListener('mousemove', (e) => { mx = e.clientX; my = e.clientY; });

    let bgAnimId = null;
    function drawBgParticles() {
      const [r, g, b] = getPrimaryRGB();
      pctx.clearRect(0, 0, W, H);

      for (const p of bgParts) {
        const dx = mx - p.x, dy = my - p.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 300) {
          p.vx += (dx / dist) * 0.001;
          p.vy += (dy / dist) * 0.001;
        }
        p.vx *= 0.99; p.vy *= 0.99;
        const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
        if (speed > 0.4) { p.vx *= 0.4 / speed; p.vy *= 0.4 / speed; }

        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;

        pctx.beginPath();
        pctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        pctx.fillStyle = `rgba(${r},${g},${b},${0.04 + p.r * 0.04})`;
        pctx.fill();
      }

      // Connection lines between close particles
      for (let i = 0; i < bgParts.length; i++) {
        for (let j = i + 1; j < bgParts.length; j++) {
          const dx = bgParts[i].x - bgParts[j].x;
          const dy = bgParts[i].y - bgParts[j].y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < 100) {
            pctx.beginPath();
            pctx.moveTo(bgParts[i].x, bgParts[i].y);
            pctx.lineTo(bgParts[j].x, bgParts[j].y);
            pctx.strokeStyle = `rgba(${r},${g},${b},${0.015 * (1 - d / 100)})`;
            pctx.lineWidth = 0.5;
            pctx.stroke();
          }
        }
      }

      bgAnimId = requestAnimationFrame(drawBgParticles);
    }

    // Pause when tab hidden
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && bgAnimId) {
        cancelAnimationFrame(bgAnimId); bgAnimId = null;
      } else if (!document.hidden && !bgAnimId) {
        drawBgParticles();
      }
    });

    drawBgParticles();
  })();

  /* ════════════════════════════════════════════════════════════════
     EMAIL
     ════════════════════════════════════════════════════════════════ */

  async function loadEmailConfig() {
    try {
      const res = await api("/api/email/config");
      const d = await res.json();
      if (d.configured) {
        if (els.emailAddr) els.emailAddr.value = d.email || "";
        if (els.smtpHost) els.smtpHost.value = d.smtp_host || "smtp.gmail.com";
        if (els.smtpPort) els.smtpPort.value = d.smtp_port || 587;
        if (els.imapHost) els.imapHost.value = d.imap_host || "imap.gmail.com";
        if (els.imapPort) els.imapPort.value = d.imap_port || 993;
        if (els.emailPass) els.emailPass.placeholder = "******** (saved)";
      }
    } catch (_) {}
  }

  function openEmail() {
    els.emailModal.classList.remove("hidden");
    loadEmailConfig();
  }
  function closeEmail() { els.emailModal.classList.add("hidden"); }
  if (els.emailTopBtn) els.emailTopBtn.addEventListener("click", openEmail);
  els.closeEmail.addEventListener("click", closeEmail);
  els.emailModal.addEventListener("click", (e) => { if (e.target === els.emailModal) closeEmail(); });

  // Email tabs
  document.querySelectorAll(".email-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".email-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".email-panel").forEach(p => p.classList.add("hidden"));
      const panel = document.querySelector(`.email-panel[data-etab="${tab.dataset.etab}"]`);
      if (panel) panel.classList.remove("hidden");
      if (tab.dataset.etab === "inbox") loadInbox();
    });
  });

  if (els.emailSend) {
    els.emailSend.addEventListener("click", async () => {
      const to = els.emailTo.value.trim();
      const subject = els.emailSubject.value.trim();
      const body = els.emailBody.value.trim();
      if (!to || !subject) {
        els.emailMsg.className = "form-msg err";
        els.emailMsg.textContent = "Recipient and subject required.";
        return;
      }
      els.emailMsg.textContent = "Sending…";
      try {
        const res = await api("/api/email/send", {
          method: "POST",
          body: JSON.stringify({ to, subject, body })
        });
        const d = await res.json();
        if (d.ok) {
          els.emailMsg.className = "form-msg ok";
          els.emailMsg.textContent = `Sent to ${to}`;
          els.emailTo.value = ""; els.emailSubject.value = ""; els.emailBody.value = "";
        } else {
          els.emailMsg.className = "form-msg err";
          els.emailMsg.textContent = d.message || "Failed to send.";
        }
      } catch (err) {
        els.emailMsg.className = "form-msg err";
        els.emailMsg.textContent = "Error: " + err.message;
      }
    });
  }

  async function loadInbox() {
    if (!els.emailInboxList) return;
    els.emailInboxList.innerHTML = '<div class="file-empty">Loading inbox…</div>';
    try {
      const res = await api("/api/email/inbox?limit=10");
      const d = await res.json();
      if (d.error) {
        els.emailInboxList.innerHTML = `<div class="file-empty">${escapeHtml(d.error)}</div>`;
        return;
      }
      if (!d.inbox || !d.inbox.length) {
        els.emailInboxList.innerHTML = '<div class="file-empty">No messages in inbox.</div>';
        return;
      }
      els.emailInboxList.innerHTML = "";
      d.inbox.forEach(msg => {
        const el = document.createElement("div");
        el.className = "email-item";
        el.innerHTML = `
          <div class="ei-from">${escapeHtml(msg.from)}</div>
          <div class="ei-subject">${escapeHtml(msg.subject)}</div>
          <div class="ei-date">${escapeHtml(msg.date)}</div>
        `;
        els.emailInboxList.appendChild(el);
      });
    } catch (_) {
      els.emailInboxList.innerHTML = '<div class="file-empty">Failed to load inbox.</div>';
    }
  }

  if (els.emailRefreshInbox) {
    els.emailRefreshInbox.addEventListener("click", loadInbox);
  }

  /* ════════════════════════════════════════════════════════════════
     REMINDERS
     ════════════════════════════════════════════════════════════════ */

  function openReminders() {
    els.remindersModal.classList.remove("hidden");
    loadReminders();
  }
  function closeReminders() { els.remindersModal.classList.add("hidden"); }
  if (els.remindersTopBtn) els.remindersTopBtn.addEventListener("click", openReminders);
  els.closeReminders.addEventListener("click", closeReminders);
  els.remindersModal.addEventListener("click", (e) => { if (e.target === els.remindersModal) closeReminders(); });

  if (els.reminderAdd) {
    els.reminderAdd.addEventListener("click", async () => {
      const text = els.reminderText.value.trim();
      if (!text) return;
      const when = els.reminderWhen.value || null;
      try {
        const res = await api("/api/reminders", {
          method: "POST",
          body: JSON.stringify({ text, when })
        });
        const d = await res.json();
        if (d.reminder) {
          els.reminderMsg.className = "form-msg ok";
          els.reminderMsg.textContent = "Reminder set!";
          els.reminderText.value = "";
          els.reminderWhen.value = "";
          loadReminders();
        }
      } catch (_) {
        els.reminderMsg.className = "form-msg err";
        els.reminderMsg.textContent = "Failed to create reminder.";
      }
    });
  }

  els.reminderText.addEventListener("keydown", (e) => {
    if (e.key === "Enter") els.reminderAdd.click();
  });

  async function loadReminders() {
    if (!els.remindersList) return;
    try {
      const res = await api("/api/reminders");
      const d = await res.json();
      renderReminders(d.reminders || []);
    } catch (_) {
      els.remindersList.innerHTML = '<div class="file-empty">Could not load reminders.</div>';
    }
  }

  function renderReminders(items) {
    if (!items.length) {
      els.remindersList.innerHTML = '<div class="file-empty">No reminders yet.</div>';
      return;
    }
    els.remindersList.innerHTML = "";
    items.forEach(r => {
      const el = document.createElement("div");
      el.className = "reminder-item" + (r.done ? " done" : "");
      const when = r.when ? new Date(r.when).toLocaleString() : "Anytime";
      el.innerHTML = `
        <span class="ri-icon">${r.done ? "✅" : "⏰"}</span>
        <span class="ri-text">${escapeHtml(r.text)}</span>
        <span class="ri-when">${escapeHtml(when)}</span>
        ${!r.done ? `<button class="ri-done" data-id="${escapeHtml(r.id)}">✓</button>` : ""}
        <button class="ri-del" data-id="${escapeHtml(r.id)}">✕</button>
      `;
      const doneBtn = el.querySelector(".ri-done");
      if (doneBtn) doneBtn.addEventListener("click", async () => {
        await api(`/api/reminders/${r.id}/done`, { method: "POST" });
        loadReminders();
      });
      el.querySelector(".ri-del").addEventListener("click", async () => {
        await api(`/api/reminders/${r.id}`, { method: "DELETE" });
        loadReminders();
      });
      els.remindersList.appendChild(el);
    });
  }

  /* ════════════════════════════════════════════════════════════════
     PLUGIN MARKETPLACE
     ════════════════════════════════════════════════════════════════ */

  function openPlugins() {
    els.pluginsModal.classList.remove("hidden");
    loadPlugins();
  }
  function closePlugins() { els.pluginsModal.classList.add("hidden"); }
  if (els.pluginsTopBtn) els.pluginsTopBtn.addEventListener("click", openPlugins);
  els.closePlugins.addEventListener("click", closePlugins);
  els.pluginsModal.addEventListener("click", (e) => { if (e.target === els.pluginsModal) closePlugins(); });

  async function loadPlugins() {
    if (!els.pluginsList) return;
    els.pluginsList.innerHTML = '<div class="file-empty">Loading plugins…</div>';
    try {
      const res = await api("/api/plugins");
      const d = await res.json();
      renderPlugins(d.plugins || []);
    } catch (_) {
      els.pluginsList.innerHTML = '<div class="file-empty">Could not load plugins.</div>';
    }
  }

  function renderPlugins(plugins) {
    if (!plugins.length) {
      els.pluginsList.innerHTML = '<div class="file-empty">No plugins available.</div>';
      return;
    }
    els.pluginsList.innerHTML = "";
    plugins.forEach(p => {
      const el = document.createElement("div");
      el.className = "plugin-item" + (p.dangerous ? " danger" : "");
      el.innerHTML = `
        <span class="pi-icon">${icon(p.dangerous ? "alert" : "package")}</span>
        <div class="pi-info">
          <span class="pi-name">${escapeHtml(p.name)}</span>
          ${p.dangerous ? '<span class="pi-danger">DANGER</span>' : ""}
          <div class="pi-desc">${escapeHtml(p.description || "No description")}</div>
        </div>
        <label class="pi-toggle">
          <input type="checkbox" ${p.enabled ? "checked" : ""} data-plugin="${escapeHtml(p.name)}" />
          <span class="slider"></span>
        </label>
      `;
      const toggle = el.querySelector("input");
      toggle.addEventListener("change", async () => {
        try {
          await api(`/api/plugins/${encodeURIComponent(p.name)}/toggle`, {
            method: "POST",
            body: JSON.stringify({ enable: toggle.checked })
          });
          els.pluginMsg.className = "form-msg ok";
          els.pluginMsg.textContent = `${p.name}: ${toggle.checked ? "enabled" : "disabled"}`;
        } catch (_) {
          toggle.checked = !toggle.checked;
          els.pluginMsg.className = "form-msg err";
          els.pluginMsg.textContent = "Toggle failed.";
        }
      });
      els.pluginsList.appendChild(el);
    });
  }

  /* ════════════════════════════════════════════════════════════════
     MULTI-CHAT TABS
     ════════════════════════════════════════════════════════════════ */

  let chatTabs = ["default"];
  let activeTab = "default";

  if (els.chatTabAdd) {
    els.chatTabAdd.addEventListener("click", () => {
      const name = prompt("New chat tab name:") || "";
      if (!name || chatTabs.includes(name)) return;
      chatTabs.push(name);
      switchTab(name);  // Auto-switch to the new tab
    });
  }

  function renderChatTabs() {
    if (!els.chatTabsScroll) return;
    els.chatTabsScroll.innerHTML = "";
    chatTabs.forEach(tab => {
      const el = document.createElement("div");
      el.className = "chat-tab" + (tab === activeTab ? " active" : "");
      el.textContent = tab === "default" ? "Main" : tab;
      if (tab !== "default") {
        const del = document.createElement("span");
        del.className = "tab-del"; del.textContent = "✕";
        del.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (!confirm(`Delete tab "${tab}"?`)) return;
          chatTabs = chatTabs.filter(t => t !== tab);
          if (activeTab === tab) switchTab("default");
          renderChatTabs();
        });
        el.appendChild(del);
      }
      el.addEventListener("click", () => switchTab(tab));
      els.chatTabsScroll.appendChild(el);
    });
  }

  async function switchTab(tabId) {
    // Save current tab messages
    if (activeTab) {
      await api(`/api/chat/tabs/${encodeURIComponent(activeTab)}/save`, {
        method: "POST",
        body: JSON.stringify({ messages: chatHistory })
      });
    }
    activeTab = tabId;
    renderChatTabs();
    // Load tab messages
    els.log.innerHTML = "";
    chatHistory = [];
    try {
      const res = await api(`/api/chat/tabs/${encodeURIComponent(tabId)}/messages`);
      const d = await res.json();
      const msgs = d.messages || [];
      msgs.forEach(m => {
        if (m.who === "JARVIS" || m.who === "You") {
          addMsg(m.who, m.text, m.tools, m.imgSrc);
        }
      });
    } catch (_) {}
    scrollLog();
  }

  /* ════════════════════════════════════════════════════════════════
     CONVERSATION SEARCH
     ════════════════════════════════════════════════════════════════ */

  if (els.chatSearchBtn) {
    els.chatSearchBtn.addEventListener("click", () => {
      const input = els.chatSearchInput;
      input.classList.toggle("open");
      if (input.classList.contains("open")) {
        input.focus();
        els.chatSearchClose.classList.remove("hidden");
      } else {
        input.value = "";
        els.chatSearchClose.classList.add("hidden");
      }
    });
  }

  if (els.chatSearchInput) {
    els.chatSearchInput.addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        const q = els.chatSearchInput.value.trim();
        if (q.length < 2) return;
        try {
          const res = await api(`/api/chat/search?q=${encodeURIComponent(q)}`);
          const d = await res.json();
          showSearchResults(d.results || [], q);
        } catch (_) {}
      }
      if (e.key === "Escape") {
        els.chatSearchInput.value = "";
        els.chatSearchInput.classList.remove("open");
        els.chatSearchClose.classList.add("hidden");
      }
    });
  }

  if (els.chatSearchClose) {
    els.chatSearchClose.addEventListener("click", () => {
      els.chatSearchInput.value = "";
      els.chatSearchInput.classList.remove("open");
      els.chatSearchClose.classList.add("hidden");
    });
  }

  function showSearchResults(results, query) {
    if (!els.searchResults || !els.searchResultsList) return;
    els.searchResultsList.innerHTML = "";
    if (!results.length) {
      if (els.searchResultsEmpty) {
        els.searchResultsEmpty.classList.remove("hidden");
        els.searchResultsEmpty.textContent = `No results for "${escapeHtml(query)}".`;
      }
    } else {
      if (els.searchResultsEmpty) els.searchResultsEmpty.classList.add("hidden");
      results.forEach(r => {
        const el = document.createElement("div");
        el.className = "search-result-item";
        el.innerHTML = `
          <div class="sri-role">${escapeHtml(r.role.toUpperCase())}</div>
          <div class="sri-content">${escapeHtml(r.content)}</div>
        `;
        el.addEventListener("click", () => {
          els.searchResults.classList.add("hidden");
          // Focus on the chat
          els.input.focus();
        });
        els.searchResultsList.appendChild(el);
      });
    }
    els.searchResults.classList.remove("hidden");
  }

  if (els.searchResultsClose) {
    els.searchResultsClose.addEventListener("click", () => {
      els.searchResults.classList.add("hidden");
    });
  }
  els.searchResults.addEventListener("click", (e) => {
    if (e.target === els.searchResults) els.searchResults.classList.add("hidden");
  });

  /* ---------- Boot! ---------- */
  boot();
})();
