(() => {
  const grid = document.getElementById("grid");
  const btnAdd = document.getElementById("btnAdd");
  const filterText = document.getElementById("filterText");
  const pageInfo = document.getElementById("pageInfo");
  const pageSizeSel = document.getElementById("pageSize");
  const categoryFilter = document.getElementById("categoryFilter");
  const btnPrev = document.getElementById("btnPrev");
  const btnNext = document.getElementById("btnNext");

  let state = {
    images: [],
    total: 0,
    page: 1,
    pageSize: 50,
    selected: new Set(),
    lastClickedIndex: null,
    filter: "",
    category: "",
  };

  async function fetchImages() {
    let url = `/api/catalog/available?page=${state.page}&page_size=${state.pageSize}`;
    if (state.category) {
      url += `&category=${encodeURIComponent(state.category)}`;
    }
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
      img.src = `/image/${encodeURIComponent(name)}`;
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

  async function addSelected() {
    const files = Array.from(state.selected);
    if (!files.length) {
      alert("No images selected.");
      return;
    }
    if (!confirm(`Add ${files.length} images to the project?`)) return;

    btnAdd.disabled = true;
    const res = await fetch("/api/catalog/add_to_project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    const data = await res.json();
    btnAdd.disabled = false;

    if (data.errors && data.errors.length > 0) {
      alert(`Some files could not be added:\n${JSON.stringify(data.errors)}`);
    }

    state.selected.clear();
    await fetchImages();
  }

  btnAdd.addEventListener("click", addSelected);
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

  categoryFilter.addEventListener("change", () => {
    state.category = categoryFilter.value;
    state.page = 1;
    fetchImages();
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT") return;
    if (e.key === "Enter") addSelected();
  });

  fetchImages();
})();
