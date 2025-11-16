(() => {
  const labelSelect = document.getElementById("labelSelect");
  const newLabel = document.getElementById("newLabel");
  const addLabelBtn = document.getElementById("addLabelBtn");
  const delBtn = document.getElementById("delBtn");
  const backBtn = document.getElementById("backBtn");
  const skipBtn = document.getElementById("skipBtn");
  const acceptBtn = document.getElementById("acceptBtn");

  const prevCanvas = document.getElementById("prevCanvas");
  const currCanvas = document.getElementById("currCanvas");
  const nextCanvas = document.getElementById("nextCanvas");

  const prevCtx = prevCanvas.getContext("2d");
  let currCtx = currCanvas.getContext("2d");
  const nextCtx = nextCanvas.getContext("2d");
  prevCtx.imageSmoothingEnabled = false;
  currCtx.imageSmoothingEnabled = false;
  nextCtx.imageSmoothingEnabled = false;

  let images = []; let idx = 0;
  const annsCache = {};
  let isDragging = false; let dragStart = null; let lastPos = null;
  let activeMouseUpHandler = null;
  let isSaving = false;
  function imgUrl(n){ return `/raw_image/${encodeURIComponent(n)}`; }

  async function loadClasses(){
    const res = await fetch("/api/classes"); const data = await res.json();
    const classes = data.classes || [];
    renderClasses(classes);
  }
  function renderClasses(classes){
    labelSelect.innerHTML = "";
    classes.forEach((c,i)=>{ const o=document.createElement("option"); o.value=c; o.textContent=`${i+1}. ${c}`; labelSelect.appendChild(o); });
    const lastLabel = localStorage.getItem("rb-last-label");
    if(lastLabel && classes.includes(lastLabel)){ labelSelect.value = lastLabel; }
  }
  addLabelBtn.addEventListener("click", async ()=>{
    const val = (newLabel.value||"").trim(); if(!val) return;
    const existing = Array.from(labelSelect.options).map(o=>o.value);
    if(!existing.includes(val)) existing.push(val);
    await fetch("/api/classes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({classes:existing})});
    newLabel.value="";
    await loadClasses();
    labelSelect.value = val;
  });
  labelSelect.addEventListener("change", ()=>{ localStorage.setItem("rb-last-label", labelSelect.value || ""); });

  async function loadImages(){
    const files = JSON.parse(sessionStorage.getItem("classify_files") || "[]");
    if (files.length === 0) {
      alert("No files selected for classification.");
      window.location.href = "/raw_review";
      return;
    }
    images = files;
    idx = 0;
    await renderTriplet();
  }

  async function renderTriplet(){
    localStorage.setItem("rb-raw-review-idx", String(idx));
    const prevName = images[idx-1], currName = images[idx], nextName = images[idx+1];
    [prevCtx, currCtx, nextCtx].forEach(ctx=>{
      const canvas = ctx.canvas;
      ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.fillStyle="#0b0b0c";
      ctx.fillRect(0,0,canvas.width,canvas.height);
    });
    if(prevName) await drawImageWithBoxes(prevCtx, prevName);
    if(currName) await drawImageWithBoxes(currCtx, currName);
    if(nextName) await drawImageWithBoxes(nextCtx, nextName);
    attachDrawHandlers(currName);
  }
  async function drawImageWithBoxes(ctx, name){
    const img = new Image();
    img.src = imgUrl(name);
    try { await img.decode(); } catch(e){ console.error("img decode error",e); return; }

    const { naturalWidth: w, naturalHeight: h } = img;
    const canvas = ctx.canvas;
    const maxH = 450;
    const scale = maxH / h;
    const dw = w * scale;
    const dh = h * scale;
    canvas.width = dw; canvas.height = dh;

    ctx.drawImage(img, 0, 0, dw, dh);

    let anns = annsCache[name];
    if(!anns){
      try{
        const res = await fetch(`/api/raw/annotation?image=${encodeURIComponent(name)}&t=${Date.now()}`, {cache: "no-store"});
        anns = await res.json();
        annsCache[name] = anns;
      }catch(e){
        console.error("failed to fetch annotations", e);
        anns = {boxes:[], w, h};
      }
    }

    (anns.boxes || []).forEach(b => {
      if (b.label === "__null__") return;
      const x = Math.min(b.x1, b.x2) * scale;
      const y = Math.min(b.y1, b.y2) * scale;
      const bw = Math.abs(b.x2 - b.x1) * scale;
      const bh = Math.abs(b.y2 - b.y1) * scale;
      ctx.save();
      ctx.strokeStyle = colorFromString(b.label);
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, bw, bh);
      if(b.label){
        ctx.fillStyle = "rgba(0,0,0,0.6)";
        const t=b.label, pad=6;
        const tw = ctx.measureText(t).width+pad*2;
        const boxH = 18;
        ctx.fillRect(x, Math.max(0, y - boxH), tw, boxH);
        ctx.fillStyle="#fff"; ctx.font="14px system-ui";
        ctx.fillText(t, x+pad, Math.max(12, y-4));
      }
      ctx.restore();
    });
  }

  function attachDrawHandlers(currName){
    const old = document.getElementById("currCanvas");
    const clone = old.cloneNode(true);
    old.parentNode.replaceChild(clone, old);
    currCtx = clone.getContext("2d");
    currCtx.imageSmoothingEnabled = false;
    drawImageWithBoxes(currCtx, currName);

    if (activeMouseUpHandler) window.removeEventListener("mouseup", activeMouseUpHandler);
    isDragging=false; dragStart=null; lastPos=null;

    clone.addEventListener("mousedown",(e)=>{
      if (!labelSelect.value) {
        alert("Please select a class label before annotating.");
        isDragging = false;
        return;
      }
      isDragging=true; const r=clone.getBoundingClientRect();
      dragStart={x:Math.floor(e.clientX-r.left), y:Math.floor(e.clientY-r.top)};
      lastPos={...dragStart};
    });
    clone.addEventListener("mousemove",(e)=>{
      const r=clone.getBoundingClientRect();
      lastPos={x:Math.floor(e.clientX-r.left), y:Math.floor(e.clientY-r.top)};
      if(!isDragging) return;
      drawImageWithBoxes(currCtx, currName).then(()=>{
        currCtx.save(); currCtx.setLineDash([4,3]);
        currCtx.strokeStyle = colorFromString(labelSelect.value || "");
        currCtx.lineWidth=2;
        currCtx.strokeRect(dragStart.x, dragStart.y, lastPos.x-dragStart.x, lastPos.y-dragStart.y);
        currCtx.restore();
      });
    });

    async function onMouseUpOnce(e){
      if(!isDragging || isSaving) return;
      isDragging=false; window.removeEventListener("mouseup", onMouseUpOnce); activeMouseUpHandler = null;
      if(!dragStart || !lastPos) return;

      const canvas = currCtx.canvas;
      const { width: dw, height: dh } = canvas;
      const { w, h } = annsCache[currName] || {w:dw,h:dh};
      const scale = dh / h;

      const x1 = dragStart.x/scale, y1 = dragStart.y/scale;
      const x2 = lastPos.x/scale, y2 = lastPos.y/scale;

      const box = {
        x1:Math.round(Math.max(0, Math.min(w,x1))), y1:Math.round(Math.max(0, Math.min(h,y1))),
        x2:Math.round(Math.max(0, Math.min(w,x2))), y2:Math.round(Math.max(0, Math.min(h,y2))),
        label: labelSelect.value||""
      };
      if (Math.abs(x2-x1) < 5 || Math.abs(y2-y1) < 5) {
        console.log("Box too small, ignoring.");
        return;
      }

      isSaving = true;
      const updatedBoxes = await saveBox(currName, box);
      annsCache[currName] = {...(annsCache[currName]||{}), boxes: updatedBoxes};

      // Immediately accept after drawing.
      await acceptCurrent();
      isSaving = false;
    }
    activeMouseUpHandler = onMouseUpOnce;
    window.addEventListener("mouseup", onMouseUpOnce);
  }

  async function saveBox(imageName, newBoxOrBoxes, overwrite = false){
    try{
      const existing = (annsCache[imageName]||{}).boxes||[];
      const newBoxes = Array.isArray(newBoxOrBoxes) ? newBoxOrBoxes : [newBoxOrBoxes];
      const finalBoxes = overwrite ? newBoxes : [...existing, ...newBoxes];
      await fetch("/api/raw/annotation", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ image:imageName, boxes: finalBoxes })
      });
      return finalBoxes;
    }catch(e){ console.error("Save failed", e); return []; }
  }

  async function goBack(){ if(idx>0){ idx-=1; await renderTriplet(); } }
  async function skip(){ if(idx<images.length-1){ idx+=1; await renderTriplet(); } }
  async function deleteCurrent(){
    const name = images[idx]; if(!name) return;
    const res = await fetch("/api/raw/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({files:[name]})});
    const data = await res.json();
    if(data.errors && data.errors.length > 0){ alert("Delete failed."); }
    else{ images.splice(idx,1); if(idx>=images.length)idx=Math.max(0,images.length-1); await renderTriplet(); }
  }

  async function acceptCurrent() {
    const name = images[idx]; if(!name) return;

    acceptBtn.disabled = true;
    const res = await fetch("/api/raw/accept", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ files:[name], label: labelSelect.value||"" })
    });
    const data = await res.json();
    acceptBtn.disabled = false;

    if(data.errors && data.errors.length > 0){
      alert("Accept failed: " + JSON.stringify(data.errors));
    } else {
      delete annsCache[name];
      images.splice(idx,1);
      if(idx>=images.length)idx=Math.max(0,images.length-1);
      await renderTriplet();
    }
  }

  backBtn.addEventListener("click", goBack);
  skipBtn.addEventListener("click", skip);
  delBtn.addEventListener("click", deleteCurrent);

  const acceptCurrentWrapper = async () => {
    if (isSaving) return;
    isSaving = true;
    await acceptCurrent();
    isSaving = false;
  };

  acceptBtn.addEventListener("click", acceptCurrentWrapper);

  document.addEventListener("keydown",(e)=>{
    if (e.target.tagName==="INPUT" || e.target.tagName==="TEXTAREA") return;
    if (e.key==="ArrowLeft") goBack();
    if (e.key===" "){ e.preventDefault(); skip(); }
    if (e.key==="Delete") deleteCurrent();
    if (e.key==="Enter") acceptCurrentWrapper();
    if (e.key>="1" && e.key<="9"){
      const n=parseInt(e.key,10)-1;
      if(n>=0 && n<labelSelect.options.length){ labelSelect.selectedIndex=n; localStorage.setItem("rb-last-label", labelSelect.value || ""); }
    }
  });

  loadClasses().then(loadImages);
})();
