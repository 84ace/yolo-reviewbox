(() => {
  const grid = document.getElementById("grid");
  const btnDelete = document.getElementById("btnDelete");
  const btnAccept = document.getElementById("btnAccept");
  const filterText = document.getElementById("filterText");
  const imageCounter = document.getElementById("imageCounter");

  let state = {
    images: [],
    selected: new Set(),
    lastClickedIndex: null,
    filter: "",
  };

  async function fetchImages() {
    const res = await fetch("/api/raw_images");
    const data = await res.json();
    state.images = data.images || [];
    await render();
  }

  async function render() {
    grid.innerHTML = "";
    let imgs = state.images;
    if (state.filter.trim()) {
      const q = state.filter.toLowerCase();
      imgs = imgs.filter(n => n.toLowerCase().includes(q));
    }

    imageCounter.textContent = `${imgs.length} of ${state.images.length} images`;

    imgs.forEach((name, i) => {
      const idx = i;
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.dataset.name = name;
      if (state.selected.has(name)) tile.classList.add("selected");

      const badge = document.createElement("div");
      badge.className = "badge";
      badge.textContent = name;
      tile.appendChild(badge);

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

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT") return;
    if (e.key === "d" || e.key === "D") deleteSelected();
    if (e.key === "a" || e.key === "A") acceptSelected();
  });

  fetchImages();
})();
