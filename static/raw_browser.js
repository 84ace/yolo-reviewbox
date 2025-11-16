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
    items.forEach(item => {
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
        tile.dataset.path = path;
        if (state.selected.has(path)) tile.classList.add("selected");

        const img = document.createElement("img");
        img.src = `/raw_image/${encodeURIComponent(path)}`;
        img.className = "thumb";
        img.loading = "lazy";
        tile.appendChild(img);

        tile.addEventListener("click", () => {
          if (state.selected.has(path)) {
            state.selected.delete(path);
          } else {
            state.selected.add(path);
          }
          tile.classList.toggle("selected");
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

  fetchItems();
})();
