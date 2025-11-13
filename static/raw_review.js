(() => {
  const grid = document.getElementById("grid");
  const btnDelete = document.getElementById("btnDelete");
  const btnAccept = document.getElementById("btnAccept");
  const filterText = document.getElementById("filterText");
  const pageInfo = document.getElementById("pageInfo");
  const pageSizeSel = document.getElementById("pageSize");
  const btnPrev = document.getElementById("btnPrev");
  const btnNext = document.getElementById("btnNext");

  let state = {
    images: [],
    total: 0,
    page: 1,
    pageSize: 100,
    selected: new Set(),
    lastClickedIndex: null,
    filter: "",
  };

  async function fetchImages() {
    const url = `/api/raw_images?page=${state.page}&page_size=${state.pageSize}`;
    const res = await fetch(url);
    const data = await res.json();
    state.images = data.images || [];
    state.total = data.total || 0;
    await render();
  }

  async function render() {
    grid.innerHTML = "";
    let imgs = state.images;
    if (state.filter.trim()) {
      const q = state.filter.toLowerCase();
      imgs = imgs.filter(n => n.toLowerCase().includes(q));
    }

    pageInfo.textContent = `Page ${state.page} of ${Math.max(1, Math.ceil(state.total / state.pageSize))} — ${state.total} images`;

    imgs.forEach((name, i) => {
      const idx = i;
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.dataset.name = name;
      if (state.selected.has(name)) tile.classList.add("selected");

      const img = document.createElement("img");
      img.src = `/raw_image/${encodeURIComponent(name)}`;
      img.className = "thumb";
      img.loading = "lazy";
      img.width = 224;
      img.height = 224;
      tile.appendChild(img);

      tile.addEventListener("click", (e) => {
        const sel = state.selected;
        if (e.shiftKey && state.lastClickedIndex !== null) {
          const start = Math.min(state.lastClickedIndex, idx);
          const end = Math.max(state.lastClickedIndex, idx);
          for (let j = start; j <= end; j++) {
            const name2 = imgs[j];
            const tile2 = Array.from(grid.children).find(c => c.dataset.name === name2);
            if (sel.has(name2)) {
              sel.delete(name2);
              if (tile2) tile2.classList.remove("selected");
            } else {
              sel.add(name2);
              if (tile2) tile2.classList.add("selected");
            }
          }
        } else {
          if (sel.has(name)) sel.delete(name);
          else sel.add(name);
          state.lastClickedIndex = idx;
        }
        tile.classList.toggle("selected", sel.has(name));
      });
      grid.appendChild(tile);
    });
  }

  async function acceptSelected() {
    const files = Array.from(state.selected);
    if (!files.length) {
      alert("No images selected.");
      return;
    }
    if (!confirm(`Accept ${files.length} images into the catalog? They will be moved from the raw folder.`)) return;

    btnAccept.disabled = true;
    const res = await fetch("/api/raw/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    const data = await res.json();
    btnAccept.disabled = false;

    if (data.errors && data.errors.length > 0) {
      alert(`Some files could not be accepted:\n${JSON.stringify(data.errors)}`);
    }

    state.selected.clear();
    await fetchImages();
  }

  async function deleteSelected() {
    const files = Array.from(state.selected);
    if (!files.length) {
      alert("No images selected.");
      return;
    }
    if (!confirm(`Permanently delete ${files.length} images? This cannot be undone.`)) return;

    btnDelete.disabled = true;
    const res = await fetch("/api/raw/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    const data = await res.json();
    btnDelete.disabled = false;

    if (data.errors && data.errors.length > 0) {
      alert(`Some files could not be deleted:\n${JSON.stringify(data.errors)}`);
    }

    state.selected.clear();
    await fetchImages();
  }

  btnAccept.addEventListener("click", acceptSelected);
  btnDelete.addEventListener("click", deleteSelected);
  filterText.addEventListener("input", (e) => {
    state.filter = e.target.value;
    render();
  });

  btnPrev.addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      fetchImages();
    }
  });

  btnNext.addEventListener("click", () => {
    const maxPage = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page < maxPage) {
      state.page += 1;
      fetchImages();
    }
  });

  pageSizeSel.addEventListener("change", () => {
    state.pageSize = parseInt(pageSizeSel.value, 10);
    state.page = 1;
    fetchImages();
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT") return;
    if (e.key === "d" || e.key === "D") deleteSelected();
    if (e.key === "a" || e.key === "A") acceptSelected();
  });

  fetchImages();
})();
