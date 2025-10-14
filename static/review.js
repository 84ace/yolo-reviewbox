(() => {
  const classFilter = document.getElementById("classFilter");
  const labelSelect = document.getElementById("labelSelect");
  const newLabel = document.getElementById("newLabel");
  const addLabelBtn = document.getElementById("addLabelBtn");
  const nullBtn = document.getElementById("nullBtn");
  const delBtn = document.getElementById("delBtn");
  const backBtn = document.getElementById("backBtn");
  const skipBtn = document.getElementById("skipBtn");

  const prevCanvas = document.getElementById("prevCanvas");
  const currCanvas = document.getElementById("currCanvas");
  const nextCanvas = document.getElementById("nextCanvas");

  const prevCtx = prevCanvas.getContext("2d");
  let currCtx = currCanvas.getContext("2d");
  const nextCtx = nextCanvas.getContext("2d");
  prevCtx.imageSmoothingEnabled = false;
  currCtx.imageSmoothingEnabled = false;
  nextCtx.imageSmoothingEnabled = false;

  const base = window.reviewConfig.baseSize || 224;
  const SIZES = { prev: window.reviewConfig.leftSize || base*2, curr: window.reviewConfig.centerSize || base*3, next: window.reviewConfig.rightSize || base*2 };

  let images = []; let idx = 0;
  const boxesCache = {}; // name -> boxes[]
  let isDragging = false; let dragStart = null; let lastPos = null;
  let activeMouseUpHandler = null;

  function factorFor(which){ return which === "curr" ? SIZES.curr / base : SIZES.prev / base; }
  function imgUrl(n){ return `/image/${encodeURIComponent(n)}`; }

  async function loadClasses(){
    const res = await fetch("/api/classes"); const data = await res.json();
    const classes = data.classes || [];
    renderClasses(classes);
    classFilter.innerHTML = `<option>All Classes</option>
<option value="__unannotated__">Unannotated</option>
<option value="__null__">Null</option>
<option disabled>---</option>`;
    classes.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      classFilter.appendChild(opt);
    });
  }
  function renderClasses(classes){
    labelSelect.innerHTML = "";
    classes.forEach((c,i)=>{ const o=document.createElement("option"); o.value=c; o.textContent=`${i+1}. ${c}`; labelSelect.appendChild(o); });
  }
  addLabelBtn.addEventListener("click", async ()=>{
    const val = (newLabel.value||"").trim(); if(!val) return;
    const existing = Array.from(labelSelect.options).map(o=>o.value);
    if(!existing.includes(val)) existing.push(val);
    renderClasses(existing); newLabel.value="";
    await fetch("/api/classes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({classes:existing})});
  });
  labelSelect.addEventListener("change", ()=>{ localStorage.setItem("rb-last-label", labelSelect.value || ""); });
  classFilter.addEventListener("change", () => {
    idx = 0;
    loadImages();
  });

  async function loadImages(){
    let url = `/api/images?page=1&page_size=2500`;
    if (classFilter.value && classFilter.value !== "All Classes") {
      url += `&class=${encodeURIComponent(classFilter.value)}`;
    }
    const res = await fetch(url); const data = await res.json();
    images = data.images || [];
    idx = 0;
    await renderTriplet();
  }

  async function renderTriplet(){
    localStorage.setItem("rb-review-idx", String(idx));
    const prevName = images[idx-1], currName = images[idx], nextName = images[idx+1];
    [prevCtx, currCtx, nextCtx].forEach(ctx=>{ ctx.clearRect(0,0,ctx.canvas.width,ctx.canvas.height); ctx.fillStyle="#0b0b0c"; ctx.fillRect(0,0,ctx.canvas.width,ctx.canvas.height); });
    if (prevName) { if (boxesCache[prevName]) { await drawImageWithBoxesKnown(prevCtx, prevName, "prev", boxesCache[prevName]); } else { await drawImageWithBoxes(prevCtx, prevName, "prev"); } }
    if (currName) { if (boxesCache[currName]) { await drawImageWithBoxesKnown(currCtx, currName, "curr", boxesCache[currName]); } else { await drawImageWithBoxes(currCtx, currName, "curr"); } }
    if (nextName) { if (boxesCache[nextName]) { await drawImageWithBoxesKnown(nextCtx, nextName, "next", boxesCache[nextName]); } else { await drawImageWithBoxes(nextCtx, nextName, "next"); } }
    attachDrawHandlers(currName);
  }

  function drawImageToCanvas(ctx, img, w, h){
    const cw = ctx.canvas.width;
    const ch = ctx.canvas.height;
    const scale = Math.min(cw/w, ch/h);
    const dw = w*scale;
    const dh = h*scale;
    const dx = (cw-dw)/2;
    const dy = (ch-dh)/2;
    ctx.drawImage(img, dx, dy, dw, dh);
    return {dx, dy, scale};
  }
  async function drawImageOnly(ctx, name, which){
    const img = new Image(); img.src = imgUrl(name);
    await img.decode().catch(()=>{});
    const {naturalWidth, naturalHeight} = img;
    return drawImageToCanvas(ctx, img, naturalWidth, naturalHeight);
  }
  async function drawImageWithBoxesKnown(ctx, name, which, boxes){
    const img = new Image(); img.src = imgUrl(name);
    await img.decode().catch(()=>{});
    const {naturalWidth, naturalHeight} = img;
    const {dx, dy, scale} = drawImageToCanvas(ctx, img, naturalWidth, naturalHeight);

    const isNull = boxes.some(b => b.label === "__null__");
    if (isNull) {
      ctx.save();
      ctx.strokeStyle = "rgba(255, 50, 50, 0.8)";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(dx, dy);
      ctx.lineTo(dx + naturalWidth*scale, dy + naturalHeight*scale);
      ctx.stroke();
      ctx.moveTo(dx + naturalWidth*scale, dy);
      ctx.lineTo(dx, dy + naturalHeight*scale);
      ctx.stroke();
      ctx.restore();
    }
    boxes.forEach(b=>{
      if (b.label === "__null__") return;
      const x = dx + Math.min(b.x1,b.x2)*scale, y= dy + Math.min(b.y1,b.y2)*scale;
      const w = Math.abs(b.x2-b.x1)*scale, h = Math.abs(b.y2-b.y1)*scale;
      ctx.save();
      ctx.strokeStyle = colorFromString(b.label);
      ctx.lineWidth=2;
      ctx.strokeRect(x,y,w,h);
      if (b.label){ ctx.fillStyle="rgba(0,0,0,0.6)"; const t=b.label, pad=6; const tw=ctx.measureText(t).width+pad*2; const bh=18;
        ctx.fillRect(x, Math.max(0,y-bh), tw, bh); ctx.fillStyle="#fff"; ctx.font="14px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial"; ctx.fillText(t, x+pad, Math.max(12,y-4)); }
      ctx.restore();
    });
  }
  async function drawImageWithBoxes(ctx, name, which){
    await drawImageOnly(ctx, name, which);
    try{
      const res = await fetch(`/api/annotation?image=${encodeURIComponent(name)}&t=${Date.now()}`, { cache: "no-store" }); const data = await res.json();
      const arr = (data.boxes||[]); boxesCache[name] = arr; await drawImageWithBoxesKnown(ctx, name, which, arr);
    }catch{}
  }

  function attachDrawHandlers(currName){
    const old = document.getElementById("currCanvas");
    const clone = old.cloneNode(true);
    old.parentNode.replaceChild(clone, old);
    currCtx = clone.getContext("2d");
    currCtx.imageSmoothingEnabled = false;
    drawImageWithBoxes(currCtx, currName, "curr"); // ensure visible immediately

    clone.addEventListener("click", skip);

    // Remove any previous global mouseup handler (prevents accumulation)
    if (activeMouseUpHandler) {
      window.removeEventListener("mouseup", activeMouseUpHandler);
      activeMouseUpHandler = null;
    }

    isDragging=false; dragStart=null; lastPos=null;

    clone.addEventListener("mousedown",(e)=>{
      isDragging=true; const r=clone.getBoundingClientRect();
      dragStart={x:Math.floor(e.clientX-r.left), y:Math.floor(e.clientY-r.top)};
      lastPos={...dragStart};
    });
    clone.addEventListener("mousemove",(e)=>{
      const r=clone.getBoundingClientRect();
      lastPos={x:Math.floor(e.clientX-r.left), y:Math.floor(e.clientY-r.top)};
      if(!isDragging) return;
      drawImageOnly(currCtx, currName, "curr").then(()=>{
        currCtx.save(); currCtx.setLineDash([4,3]);
        currCtx.strokeStyle = colorFromString(labelSelect.value || "");
        currCtx.lineWidth=2;
        currCtx.strokeRect(dragStart.x, dragStart.y, lastPos.x-dragStart.x, lastPos.y-dragStart.y);
        currCtx.restore();
      });
    });

    async function onMouseUpOnce(e){
      if(!isDragging) return;
      isDragging=false; window.removeEventListener("mouseup", onMouseUpOnce); activeMouseUpHandler = null;
      if(!dragStart || !lastPos) return;

      const img = new Image(); img.src = imgUrl(currName);
      await img.decode().catch(()=>{});
      const {naturalWidth, naturalHeight} = img;

      const canvas = currCtx.canvas;
      const {dx, dy, scale} = drawImageToCanvas(currCtx, img, naturalWidth, naturalHeight);

      const x1 = (dragStart.x - dx) / scale;
      const y1 = (dragStart.y - dy) / scale;
      const x2 = (lastPos.x - dx) / scale;
      const y2 = (lastPos.y - dy) / scale;

      const box = {
        x1: Math.round(Math.max(0, Math.min(naturalWidth, x1))),
        y1: Math.round(Math.max(0, Math.min(naturalHeight, y1))),
        x2: Math.round(Math.max(0, Math.min(naturalWidth, x2))),
        y2: Math.round(Math.max(0, Math.min(naturalHeight, y2))),
        label: labelSelect.value || ""
      };
      const updatedBoxes = await saveBox(currName, box);
      boxesCache[currName] = updatedBoxes;
      localStorage.setItem("rb-last-label", box.label);
      if (idx < images.length-1) idx += 1;
      await renderTriplet();
    }
    activeMouseUpHandler = onMouseUpOnce;
    window.addEventListener("mouseup", onMouseUpOnce);
  }

  async function saveBox(imageName, newBoxes){
    try{
      const res = await fetch(`/api/annotation?image=${encodeURIComponent(imageName)}&t=${Date.now()}`, { cache: "no-store" });
      const data = await res.json();
      const existingBoxes = (data.boxes||[]).slice();
      const finalBoxes = Array.isArray(newBoxes) ? newBoxes : [...existingBoxes, newBoxes];
      await fetch("/api/annotate", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ image:imageName, boxes: finalBoxes }) });
      return finalBoxes;
    }catch(e){ console.error("Save failed", e); return []; }
  }

  async function goBack(){ if(idx>0){ idx-=1; await renderTriplet(); } }
  async function skip(){ if(idx<images.length-1){ idx+=1; await renderTriplet(); } }
  async function deleteCurrent(){
    const name = images[idx]; if(!name) return;
    if(!confirm(`Delete ${name}? This cannot be undone.`)) return;
    const res = await fetch("/api/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({files:[name]})});
    const data = await res.json();
    if ((data.deleted||[]).includes(name)){
      images.splice(idx,1); if(idx>=images.length) idx=Math.max(0, images.length-1); await renderTriplet();
    } else { alert("Delete failed."); }
  }

  async function tagAsNull() {
    const name = images[idx]; if(!name) return;
    const boxes = [{label: "__null__", x1: 0, y1: 0, x2: 0, y2: 0}];
    await saveBox(name, boxes);
    boxesCache[name] = boxes;
    if (idx < images.length-1) idx += 1;
    await renderTriplet();
  }

  backBtn.addEventListener("click", goBack);
  skipBtn.addEventListener("click", skip);
  delBtn.addEventListener("click", deleteCurrent);
  nullBtn.addEventListener("click", tagAsNull);

  document.addEventListener("keydown",(e)=>{
    if (e.target.tagName==="INPUT" || e.target.tagName==="TEXTAREA") return;
    if (e.key==="ArrowLeft") goBack();
    if (e.key===" "){ e.preventDefault(); skip(); }
    if (e.key==="Delete") deleteCurrent();
    if (e.key === "n" || e.key === "N") tagAsNull();
    if (e.key>="1" && e.key<="9"){
      const n=parseInt(e.key,10)-1;
      if (n>=0 && n<labelSelect.options.length){
        labelSelect.selectedIndex=n;
        localStorage.setItem("rb-last-label", labelSelect.value || "");
      }
    }
  });

  loadClasses().then(loadImages);
})();