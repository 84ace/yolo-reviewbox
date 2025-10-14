(() => {
  const grid = document.getElementById("grid");
  const btnDelete = document.getElementById("btnDelete");
  const btnExport = document.getElementById("btnExport");
  const btnImport = document.getElementById("btnImport");
  const importFile = document.getElementById("importFile");
  const btnImportImages = document.getElementById("btnImportImages");
  const importImagesFile = document.getElementById("importImagesFile");
  const btnPrev = document.getElementById("btnPrev");
  const btnNext = document.getElementById("btnNext");
  const pageInfo = document.getElementById("pageInfo");
  const pageSizeSel = document.getElementById("pageSize");
  const thumbSizeSel = document.getElementById("thumbSize");
  const filterText = document.getElementById("filterText");
  const classFilter = document.getElementById("classFilter");

  const exportModal = document.getElementById("exportModal");
  const exportClassList = document.getElementById("exportClassList");
  const exportRemap = document.getElementById("exportRemap");
  const addRemapRow = document.getElementById("addRemapRow");
  const nullHandling = document.getElementById("nullHandling");
  const runExport = document.getElementById("runExport");
  const cancelExport = document.getElementById("cancelExport");
  const exportSpinner = document.getElementById("exportSpinner");

  const projectSwitcher = document.getElementById("projectSwitcher");
  const btnNewProject = document.getElementById("btnNewProject");
  const newProjectModal = document.getElementById("newProjectModal");
  const newProjectName = document.getElementById("newProjectName");
  const moveCurrentProject = document.getElementById("moveCurrentProject");
  const runCreateProject = document.getElementById("runCreateProject");
  const cancelCreateProject = document.getElementById("cancelCreateProject");

  let state = { page: 1, pageSize: window.appConfig?.pageSize || 200, total: 0,
    images: [], selected: new Set(), lastClickedIndex: null, thumb: 112, filter: "", class: "All Classes", project: "default" };
  let pageBoxes = {}; // name -> boxes[]

  function applyThumbSize() {
    const s = parseInt(state.thumb, 10);
    grid.style.gridTemplateColumns = `repeat(auto-fill, minmax(${s}px, 1fr))`;
  }

  async function fetchImages() {
    let url = `/api/images?page=${state.page}&page_size=${state.pageSize}`;
    if (state.class && state.class !== "All Classes") {
      url += `&class=${encodeURIComponent(state.class)}`;
    }
    const res = await fetch(url);
    const data = await res.json();
    state.total = data.total; state.images = data.images;
    await render();
  }

  function drawOverlayForTile(tile, name){
    const img = tile.querySelector("img.thumb");
    if (!img) return;
    let overlay = tile.querySelector("canvas.overlay");
    if (!overlay){
      overlay = document.createElement("canvas");
      overlay.className = "overlay";
      tile.appendChild(overlay);
    }
    const w = img.clientWidth || img.width;
    const h = img.clientHeight || img.height;
    overlay.width = w; overlay.height = h;
    const ctx = overlay.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0,0,w,h);
    const boxes = (pageBoxes && pageBoxes[name]) ? pageBoxes[name] : [];
    if (!boxes.length) return;
    const f = (w / 224);
    ctx.save();
    ctx.lineWidth = Math.max(1, Math.round(1*f));
    ctx.font = `${Math.max(10, Math.round(10*f))}px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial`;
    const isNull = boxes.some(b => b.label === "__null__");
    if (isNull) {
      ctx.strokeStyle = "rgba(255, 50, 50, 0.8)";
      ctx.lineWidth = 2 * f;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(w, h);
      ctx.stroke();
      ctx.moveTo(w, 0);
      ctx.lineTo(0, h);
      ctx.stroke();
    }
    boxes.forEach(b => {
      if (b.label === "__null__") return;
      ctx.strokeStyle = colorFromString(b.label);
      const x = Math.min(b.x1,b.x2)*f, y = Math.min(b.y1,b.y2)*f;
      const bw = Math.abs(b.x2-b.x1)*f, bh = Math.abs(b.y2-b.y1)*f;
      ctx.strokeRect(x,y,bw,bh);
      if (b.label){
        const pad = 4*f;
        const tw = ctx.measureText(b.label).width + pad*2;
        const bhh = (14*f);
        ctx.fillStyle = "rgba(0,0,0,0.6)";
        ctx.fillRect(x, Math.max(0, y-bhh), tw, bhh);
        ctx.fillStyle = "#fff";
        ctx.fillText(b.label, x+pad, Math.max(10*f, y-4*f));
      }
    });
    ctx.restore();
  }

  async function fetchBoxesForPage(imgs){
    // Try bulk endpoint first
    try{
      const res = await fetch("/api/annotations_bulk", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ images: imgs })
      });
      if (!res.ok) throw new Error(`bulk ${res.status}`);
      const data = await res.json();
      const items = data.items || {};
      const normalized = {};
      Object.keys(items).forEach(k => { normalized[k] = (items[k] && items[k].boxes) ? items[k].boxes : []; });
      return normalized;
    } catch(e){
      // Fallback: per-image fetch with small concurrency
      const out = {};
      const queue = imgs.slice();
      const workers = Array.from({length: 8}).map(async ()=>{
        while(queue.length){
          const name = queue.shift();
          try{
            const r = await fetch(`/api/annotation?image=${encodeURIComponent(name)}&t=${Date.now()}`, { cache: "no-store" });
            const d = await r.json();
            out[name] = d.boxes || [];
          }catch{ out[name] = []; }
        }
      });
      await Promise.all(workers);
      return out;
    }
  }

  async function render() {
    pageInfo.textContent = `Page ${state.page} of ${Math.max(1, Math.ceil(state.total / state.pageSize))} — ${state.total} images`;
    grid.innerHTML = "";
    let imgs = state.images;
    if (state.filter.trim()) {
      const q = state.filter.toLowerCase();
      imgs = imgs.filter(n => n.toLowerCase().includes(q));
    }

    imgs.forEach((name, i) => {
      const idx = i;
      const tile = document.createElement("div"); tile.className = "tile"; tile.dataset.name = name;
      if (state.selected.has(name)) tile.classList.add("selected");

      const a = document.createElement("a"); a.className = "annotate"; a.href = `/annotate?image=${encodeURIComponent(name)}`;
      a.textContent = "✏️"; a.title = "Annotate"; a.addEventListener("click", (ev) => ev.stopPropagation());
      tile.appendChild(a);

      const badge = document.createElement("div"); badge.className = "badge";
      badge.textContent = `${(state.page - 1) * state.pageSize + i + 1}`; tile.appendChild(badge);

      const img = document.createElement("img"); img.src = `/image/${encodeURIComponent(name)}`; img.className = "thumb";
      img.loading = "lazy"; img.width = state.thumb; img.height = state.thumb; tile.appendChild(img);

      tile.addEventListener("click", (e) => {
        const sel = state.selected;
        if (e.shiftKey && state.lastClickedIndex !== null) {
          const start = Math.min(state.lastClickedIndex, idx);
          const end = Math.max(state.lastClickedIndex, idx);
          for (let j = start; j <= end; j++) {
            const name2 = imgs[j];
            const tile2 = grid.children[j];
            if (sel.has(name2)) {
              sel.delete(name2);
              if(tile2) tile2.classList.remove("selected");
            } else {
              sel.add(name2);
              if(tile2) tile2.classList.add("selected");
            }
          }
        } else {
          if (sel.has(name)) sel.delete(name); else sel.add(name);
          state.lastClickedIndex = idx;
        }
        tile.classList.toggle("selected", sel.has(name));
      });

      grid.appendChild(tile);
    });

    // Fetch page boxes and draw overlays
    try{
      pageBoxes = await fetchBoxesForPage(imgs);
    }catch(e){
      pageBoxes = {};
    }
    if (!pageBoxes || typeof pageBoxes !== 'object') pageBoxes = {};

    Array.from(grid.children).forEach(tile => {
      const name = tile.dataset.name;
      if (!name) return;
      drawOverlayForTile(tile, name);
    });
  }

  async function deleteSelected() {
    const files = Array.from(state.selected);
    if (!files.length) { alert("No images selected."); return; }
    if (!confirm(`Delete ${files.length} images? This cannot be undone.`)) return;
    const res = await fetch("/api/delete", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files })});
    const data = await res.json();
    const del = data.deleted || [];
    del.forEach(n => state.selected.delete(n));
    await fetchImages();
  }

  function addRemapRowLogic() {
    const from = document.createElement("input"); from.type = "text"; from.placeholder = "comma,separated,list";
    const to = document.createElement("input"); to.type = "text"; to.placeholder = "new_class";
    const arrow = document.createElement("span"); arrow.textContent = "→";
    exportRemap.appendChild(from);
    exportRemap.appendChild(arrow);
    exportRemap.appendChild(to);
  }

  async function exportVOC() {
    const res = await fetch("/api/export_options");
    const data = await res.json();
    const classes = data.classes || [];
    exportClassList.innerHTML = "";
    classes.forEach(c => {
      const label = document.createElement("label");
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.value = c; cb.checked = true;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(c));
      exportClassList.appendChild(label);
    });
    exportModal.style.display = "flex";
  }

  async function runExportLogic() {
    runExport.disabled = true;
    exportSpinner.style.display = "flex";

    try {
      const classes = Array.from(exportClassList.querySelectorAll("input:checked")).map(cb => cb.value);
      const remap = [];
      const remapRows = exportRemap.querySelectorAll("input[type=text]");
      for (let i = 0; i < remapRows.length; i += 2) {
        const from = remapRows[i].value.trim();
        const to = remapRows[i+1].value.trim();
        if (from && to) {
          remap.push({from: from.split(",").map(s => s.trim()), to});
        }
      }

      const payload = {
        classes,
        remap,
        null_handling: nullHandling.value,
      };

      const res = await fetch("/api/export_voc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.ok) {
        const a = document.createElement("a");
        a.href = data.zip_url;
        a.download = data.zip_name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        exportModal.style.display = "none";
      } else {
        alert("Export failed.");
      }
    } catch (e) {
      alert(`An error occurred: ${e.message}`);
    } finally {
      runExport.disabled = false;
      exportSpinner.style.display = "none";
    }
  }


  async function importVOC() {
    if (!importFile.files.length) { alert("Please select a zip file to import."); return; }
    const file = importFile.files[0];
    if (!confirm(`Import dataset from ${file.name}? This may overwrite existing images and annotations.`)) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch("/api/import_voc", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok && data.ok) {
        let alertMsg = data.message || "Import finished.";
        if (data.failed_files && data.failed_files.length > 0) {
          alertMsg += `\n\nCould not import:\n- ${data.failed_files.join("\n- ")}`;
        }
        alert(alertMsg);
        await fetchClasses();
        await fetchImages();
      } else {
        alert(`Import failed: ${data.error || 'Unknown error'}`);
      }
    } catch (e) {
      alert(`An error occurred: ${e.message}`);
    } finally {
      importFile.value = ""; // Reset file input
    }
  }

  async function importImages() {
    if (!importImagesFile.files.length) { alert("Please select a zip file to import."); return; }
    const file = importImagesFile.files[0];
    if (!confirm(`Import images from ${file.name}?`)) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch("/api/import_images", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok && data.ok) {
        let alertMsg = data.message || "Import finished.";
        if (data.failed_files && data.failed_files.length > 0) {
          alertMsg += `\n\nCould not import:\n- ${data.failed_files.join("\n- ")}`;
        }
        alert(alertMsg);
        await fetchImages();
      } else {
        alert(`Import failed: ${data.error || 'Unknown error'}`);
      }
    } catch (e) {
      alert(`An error occurred: ${e.message}`);
    } finally {
      importImagesFile.value = ""; // Reset file input
    }
  }

  btnPrev.addEventListener("click", () => { if (state.page > 1) { state.page -= 1; fetchImages(); }});
  btnNext.addEventListener("click", () => {
    const maxPage = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page < maxPage) { state.page += 1; fetchImages(); }
  });
  btnDelete.addEventListener("click", deleteSelected);
  btnExport.addEventListener("click", exportVOC);
  btnImport.addEventListener("click", () => importFile.click());
  importFile.addEventListener("change", importVOC);
  addRemapRow.addEventListener("click", addRemapRowLogic);
  runExport.addEventListener("click", runExportLogic);
  cancelExport.addEventListener("click", () => { exportModal.style.display = "none"; });
  btnImportImages.addEventListener("click", () => importImagesFile.click());
  importImagesFile.addEventListener("change", importImages);
  pageSizeSel.addEventListener("change", () => { state.pageSize = parseInt(pageSizeSel.value, 10); state.page = 1; fetchImages(); });
  thumbSizeSel.addEventListener("change", () => { state.thumb = parseInt(thumbSizeSel.value, 10); applyThumbSize(); render(); });
  filterText.addEventListener("input", (e) => { state.filter = e.target.value; render(); });
  classFilter.addEventListener("change", () => { state.class = classFilter.value; state.page = 1; fetchImages(); });

  async function fetchClasses() {
    const res = await fetch("/api/classes");
    const data = await res.json();
    const classes = data.classes || [];
    classFilter.innerHTML = `<option>All Classes</option>
<option value="__unannotated__">Unannotated</option>
<option value="__null__">Null</option>
<option disabled>---</option>`;
    classes.forEach(c => {
      if(c){
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        classFilter.appendChild(opt);
      }
    });
  }

  async function fetchProjects() {
    const res = await fetch("/api/projects");
    const data = await res.json();
    const projects = data.projects || [];
    state.project = data.active;
    projectSwitcher.innerHTML = "";
    projects.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      if (p === state.project) opt.selected = true;
      projectSwitcher.appendChild(opt);
    });
  }

  async function switchProject() {
    const newProject = projectSwitcher.value;
    if (newProject === state.project) return;
    try {
      const res = await fetch("/api/project/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newProject }),
      });
      if (res.ok) {
        state.project = newProject;
        state.page = 1;
        state.selected.clear();
        await fetchClasses();
        await fetchImages();
      } else {
        alert("Failed to switch project.");
        projectSwitcher.value = state.project; // Revert selection
      }
    } catch (e) {
      alert(`Error: ${e.message}`);
      projectSwitcher.value = state.project;
    }
  }

  function showNewProjectModal() {
    newProjectName.value = "";
    moveCurrentProject.checked = false;
    newProjectModal.style.display = "flex";
    newProjectName.focus();
  }

  async function createNewProject() {
    const name = newProjectName.value.trim();
    if (!name.match(/^[a-zA-Z0-9]+$/)) {
      alert("Project name must be alphanumeric with no spaces.");
      return;
    }

    runCreateProject.disabled = true;
    try {
      const res = await fetch("/api/project/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          move_from: moveCurrentProject.checked ? state.project : null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        newProjectModal.style.display = "none";
        state.project = data.name;
        await fetchProjects();
        state.page = 1;
        state.selected.clear();
        await fetchClasses();
        await fetchImages();
      } else {
        alert(`Failed to create project: ${data.error || 'Unknown error'}`);
      }
    } catch (e) {
      alert(`Error: ${e.message}`);
    } finally {
      runCreateProject.disabled = false;
    }
  }

  projectSwitcher.addEventListener("change", switchProject);
  btnNewProject.addEventListener("click", showNewProjectModal);
  runCreateProject.addEventListener("click", createNewProject);
  cancelCreateProject.addEventListener("click", () => { newProjectModal.style.display = "none"; });

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.key === "d" || e.key === "D") deleteSelected();
    if (e.key === "e" || e.key === "E") exportVOC();
    if (e.key === "a" || e.key === "A") {
      const imgs = state.images;
      let all = true; for (const n of imgs) if (!state.selected.has(n)) { all = false; break; }
      if (all) imgs.forEach(n => state.selected.delete(n)); else imgs.forEach(n => state.selected.add(n));
      render();
    }
    if (e.key === "ArrowLeft") btnPrev.click();
    if (e.key === "ArrowRight") btnNext.click();
  });

  pageSizeSel.value = String(state.pageSize);
  thumbSizeSel.value = String(state.thumb);
  applyThumbSize();
  (async () => {
    await fetchProjects();
    await fetchClasses();
    await fetchImages();
  })();
})();