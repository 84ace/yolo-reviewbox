(() => {
  const img = document.getElementById("img");
  const canvas = document.getElementById("canvas");
  const ctx = canvas.getContext("2d");
  const boxesUL = document.getElementById("boxes");
  const labelSelect = document.getElementById("labelSelect");
  const newLabel = document.getElementById("newLabel");
  const addLabelBtn = document.getElementById("addLabelBtn");
  const nullBtn = document.getElementById("nullBtn");
  const saveBtn = document.getElementById("saveBtn");
  const goBack = document.getElementById("goBack");

  let W = window.annConfig.w, H = window.annConfig.h;
  let scaleX = 1, scaleY = 1;
  let boxes = []; let current = null; let activeIdx = -1;

  function initCanvas() {
    const displayW = img.clientWidth;
    const displayH = img.clientHeight;
    canvas.width = displayW;
    canvas.height = displayH;
    scaleX = W / displayW;
    scaleY = H / displayH;
    drawAll();
  }

  function drawAll() {
    if (!canvas.width || !canvas.height) return;
    ctx.clearRect(0,0, canvas.width, canvas.height);
    boxes.forEach((b, i) => drawBox(b, i === activeIdx));
    if (current) drawBox(current, true, true);
  }

  function drawBox(b, active=false, dashed=false) {
    const x = Math.min(b.x1, b.x2) / scaleX, y = Math.min(b.y1, b.y2) / scaleY;
    const w = Math.abs(b.x2 - b.x1) / scaleX, h = Math.abs(b.y2 - b.y1) / scaleY;
    ctx.save();
    if (dashed) ctx.setLineDash([4,3]); else ctx.setLineDash([]);
    ctx.lineWidth = active ? 3 : 1;
    ctx.strokeStyle = colorFromString(b.label);
    ctx.strokeRect(x, y, w, h);
    const label = b.label || "";
    if (label) {
      ctx.fillStyle = "rgba(0,0,0,0.6)";
      const textW = ctx.measureText(label).width + 8; const boxH = 16;
      ctx.fillRect(x, Math.max(0, y - boxH), textW, boxH);
      ctx.fillStyle = "#fff"; ctx.font = "12px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial";
      ctx.fillText(label, x + 4, Math.max(12, y - 4));
    }
    ctx.restore();
  }

  function refreshList() {
    boxesUL.innerHTML = "";
    boxes.forEach((b, i) => {
      const li = document.createElement("li");
      li.className = (i === activeIdx) ? "active" : "";
      li.textContent = `${b.label || "(unlabeled)"}  [${b.x1},${b.y1}]→[${b.x2},${b.y2}]`;
      const del = document.createElement("button"); del.textContent = "✖"; del.style.marginLeft = "8px";
      del.addEventListener("click", () => { boxes.splice(i, 1); if (activeIdx >= boxes.length) activeIdx = boxes.length - 1; drawAll(); refreshList(); });
      li.addEventListener("click", () => { activeIdx = i; drawAll(); refreshList(); });
      li.appendChild(del); boxesUL.appendChild(li);
    });
  }

  function setActiveLabelOnSelection() {
    if (activeIdx < 0 || activeIdx >= boxes.length) return;
    boxes[activeIdx].label = labelSelect.value || ""; drawAll(); refreshList();
  }

  let dragging = false;
  canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    const startX = Math.floor(e.clientX - rect.left);
    const startY = Math.floor(e.clientY - rect.top);
    current = { x1: startX * scaleX, y1: startY * scaleY, x2: startX * scaleX, y2: startY * scaleY, label: labelSelect.value || "" };
    dragging = true; activeIdx = -1; drawAll(); refreshList();
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const rect = canvas.getBoundingClientRect();
    current.x2 = Math.floor(e.clientX - rect.left) * scaleX;
    current.y2 = Math.floor(e.clientY - rect.top) * scaleY;
    drawAll();
  });
  window.addEventListener("mouseup", () => {
    if (dragging && current) {
      boxes.push(current); activeIdx = boxes.length - 1; current = null; dragging = false;
      drawAll(); refreshList();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Backspace") {
      if (activeIdx >= 0) { boxes.splice(activeIdx, 1); activeIdx = Math.max(-1, activeIdx - 1); drawAll(); refreshList(); e.preventDefault(); }
    }
    if (e.key === "s" || e.key === "S") { e.preventDefault(); saveAnnotations(); }
    if (e.key >= "1" && e.key <= "9") {
      const idx = parseInt(e.key, 10) - 1;
      if (idx >= 0 && idx < labelSelect.options.length) { labelSelect.selectedIndex = idx; setActiveLabelOnSelection(); }
    }
  });

  async function loadBoxes() {
    const res = await fetch(`/api/annotation?image=${encodeURIComponent(window.annConfig.image)}&t=${Date.now()}`, { cache: "no-store" });
    const data = await res.json();
    boxes = (data.boxes || []).map(b => ({...b}));
    W = data.w > 0 ? data.w : W;
    H = data.h > 0 ? data.h : H;
    activeIdx = boxes.length ? 0 : -1;
    initCanvas();
    refreshList();
  }

  async function loadClasses() {
    const res = await fetch("/api/classes"); const data = await res.json();
    renderClasses(data.classes || []);
  }

  function renderClasses(classes) {
    labelSelect.innerHTML = "";
    classes.forEach((c, i) => { const opt = document.createElement("option"); opt.value = c; opt.textContent = `${i+1}. ${c}`; labelSelect.appendChild(opt); });
  }

  addLabelBtn.addEventListener("click", async () => {
    const val = (newLabel.value || "").trim(); if (!val) return;
    const opts = Array.from(labelSelect.options).map(o => o.value); if (!opts.includes(val)) opts.push(val);
    renderClasses(opts); newLabel.value = "";
    await fetch("/api/classes", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ classes: Array.from(labelSelect.options).map(o => o.value) })});
  });

  labelSelect.addEventListener("change", setActiveLabelOnSelection);

  async function saveAnnotations() {
    const payload = { image: window.annConfig.image, boxes };
    const res = await fetch("/api/annotate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await res.json();
    if (data.ok) { saveBtn.textContent = "Saved ✓"; setTimeout(() => saveBtn.textContent = "Save (S)", 800); } else { alert("Save failed."); }
  }

  saveBtn.addEventListener("click", saveAnnotations);

  nullBtn.addEventListener("click", () => {
    boxes = [{label: "__null__", x1: 0, y1: 0, x2: 0, y2: 0}];
    saveAnnotations();
  });

  goBack.addEventListener("click", (e) => {
    e.preventDefault();
    if (document.referrer) {
      window.location.href = document.referrer;
    } else {
      history.back();
    }
  });

  window.addEventListener("resize", initCanvas);
  img.addEventListener("load", () => {
    loadClasses();
    loadBoxes();
  });
})();