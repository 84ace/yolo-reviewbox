(() => {
  const browser = document.getElementById("browser");
  const btnDelete = document.getElementById("btnDelete");
  const btnClassify = document.getElementById("btnClassify");
  const networkFilter = document.getElementById("networkFilter");
  const deviceFilter = document.getElementById("deviceFilter");
  const recursiveToggle = document.getElementById("recursiveToggle");
  const btnGoBack = document.getElementById("btnGoBack");

  let state = {
    path: "",
    selected: new Set(),
    lastClickedIndex: null,
    visibleFiles: [],
  };

  async function fetchItems() {
    const url = new URL("/api/raw_browser", window.location.origin);
    url.searchParams.append("path", state.path);
    if (recursiveToggle.checked) {
      url.searchParams.append("recursive", "true");
    }
    if (networkFilter.value) {
      url.searchParams.append("network", networkFilter.value);
    }
    if (deviceFilter.value) {
      url.searchParams.append("device", deviceFilter.value);
    }

    const res = await fetch(url);
    const items = await res.json();
    render(items);
  }

  function render(items) {
    browser.innerHTML = "";
    state.visibleFiles = [];
    items.forEach((item, idx) => {
      const tile = document.createElement("div");
      tile.className = "tile";
      if (item.type === "dir") {
        tile.innerHTML = `<div class="dirname">${item.name}</div>`;
        tile.addEventListener("click", () => {
          state.path = state.path ? `${state.path}/${item.name}` : item.name;
          fetchItems();
        });
      } else {
        const path = item.path || item;
        state.visibleFiles.push(path);
        tile.dataset.path = path;
        if (state.selected.has(path)) tile.classList.add("selected");

        const img = document.createElement("img");
        img.src = `/raw_image/${encodeURIComponent(path)}`;
        img.className = "thumb";
        img.loading = "lazy";
        tile.appendChild(img);

        tile.addEventListener("click", (e) => {
          if (e.shiftKey && state.lastClickedIndex !== null) {
            const start = Math.min(state.lastClickedIndex, idx);
            const end = Math.max(state.lastClickedIndex, idx);
            for (let i = start; i <= end; i++) {
              const file = state.visibleFiles[i];
              if (file) {
                state.selected.add(file);
                const tileNode = browser.querySelector(`[data-path="${file}"]`);
                if (tileNode) tileNode.classList.add("selected");
              }
            }
          } else {
            if (state.selected.has(path)) {
              state.selected.delete(path);
              tile.classList.remove("selected");
            } else {
              state.selected.add(path);
              tile.classList.add("selected");
            }
          }
          state.lastClickedIndex = idx;
        });
      }
      browser.appendChild(tile);
    });
  }

  btnGoBack.addEventListener("click", () => {
    if (state.path) {
      state.path = state.path.substring(0, state.path.lastIndexOf('/'));
      fetchItems();
    }
  });

  [networkFilter, deviceFilter, recursiveToggle].forEach(el => {
    el.addEventListener("change", fetchItems);
  });

  btnDelete.addEventListener("click", async () => {
    const files = Array.from(state.selected);
    if (files.length === 0) return;
    await fetch("/api/raw/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    state.selected.clear();
    fetchItems();
  });

  btnClassify.addEventListener("click", () => {
    const files = Array.from(state.selected);
    if (files.length === 0) return;
    sessionStorage.setItem("classify_files", JSON.stringify(files));
    window.location.href = "/raw_review_classify";
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "a" || e.key === "A") {
      e.preventDefault();
      const allSelected = state.visibleFiles.every(f => state.selected.has(f));
      if (allSelected) {
        state.selected.clear();
        browser.querySelectorAll(".tile.selected").forEach(t => t.classList.remove("selected"));
      } else {
        state.visibleFiles.forEach(f => state.selected.add(f));
        browser.querySelectorAll(".tile").forEach(t => {
          if (t.dataset.path) t.classList.add("selected");
        });
      }
    } else if (e.key === "d" || e.key === "D") {
      e.preventDefault();
      btnDelete.click();
    }
  });

  fetchItems();
})();
