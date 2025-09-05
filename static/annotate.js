(() => {
  const img = document.getElementById("img");
  const canvas = document.getElementById("canvas");
  const ctx = canvas.getContext("2d");
  const boxesUL = document.getElementById("boxes");
  const labelSelect = document.getElementById("labelSelect");
  const newLabel = document.getElementById("newLabel");
  const addLabelBtn = document.getElementById("addLabelBtn");
  const saveBtn = document.getElementById("saveBtn");

  const W = window.annConfig.w, H = window.annConfig.h;
  canvas.width = W; canvas.height = H;

  let boxes = []; let current = null; let activeIdx = -1;

  function drawAll() {
    ctx.clearRect(0,0, W, H);
    boxes.forEach((b, i) => drawBox(b, i === activeIdx));
    if (current) drawBox(current, true, true);
  }

  function drawBox(b, active=false, dashed=false) {
    const x = Math.min(b.x1, b.x2), y = Math.min(b.y1, b.y2);
    const w = Math.abs(b.x2 - b.x1), h = Math.abs(b.y2 - b.y1);
    ctx.save();
    if (dashed) ctx.setLineDash([4,3]); else ctx.setLineDash([]);
    ctx.lineWidth = active ? 2 : 1;
    ctx.strokeStyle = active ? "#ff6a00" : "#00d7ff";
    ctx.strokeRect(x, y, w, h);
    const label = b.label || "";
    if (label) {
      ctx.fillStyle = "rgba(0,0,0,0.5)";
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

  let dragging = false; let startX = 0, startY = 0;
  canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    startX = Math.floor(e.clientX - rect.left); startY = Math.floor(e.clientY - rect.top);
    current = { x1: startX, y1: startY, x2: startX, y2: startY, label: labelSelect.value || "" };
    dragging = true; activeIdx = -1; drawAll(); refreshList();
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const rect = canvas.getBoundingClientRect();
    current.x2 = Math.floor(e.clientX - rect.left); current.y2 = Math.floor(e.clientY - rect.top);
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
    boxes = (data.boxes || []).map(b => ({...b})); activeIdx = boxes.length ? 0 : -1;
    drawAll(); refreshList();
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
  loadClasses(); loadBoxes();
})();