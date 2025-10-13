# Yolo-ReviewBox

Ultra-fast, web-based image reviewer & annotator built with Flask + vanilla JS.  
Optimized for reviewing and annotating large image datasets for object detection tasks.

- **Grid review**: A lightning-fast thumbnail grid with multi-select and bulk delete capabilities.
- **Review Mode (carousel)**: A high-speed annotation view with the current image at 3x resolution, and the previous/next images at 2x. Draw a box, and it auto-saves with the last used label and advances to the next image.
- **Color-Coded Overlays**: Bounding boxes are colored by class name, providing a clear visual distinction between different object types in all views.
- **Pascal VOC Annotations**: Annotations are saved as one XML file per image, compatible with Roboflow, YOLO, and other popular computer vision frameworks.
- **Robust ZIP Import**: Import Pascal VOC datasets in a `.zip` file. The importer is designed to handle large datasets and is resilient to errors with individual files.
- **One-Click Export**: Export your annotated dataset as a VOC-compliant `.zip` file, ready for training.
- **HTTPS-Ready**: Run with mkcert or behind a reverse proxy like Nginx or Caddy.

---

## 1) Quick start

```bash
# 1) Create & activate a venv
python3 -m venv .venv
source .venv/bin/activate

# 2) Install deps
pip install -r requirements.txt

# 3) Put your images in ./images
#    Or use env vars (see below) to point to a different folder.

# 4) Run
python app.py

# Open your browser
#   http://localhost:8000
# or http://<your-LAN-ip>:8000
```

### Optional: HTTPS (recommended on LAN)
- **With mkcert (trusted locally)**
  ```bash
  mkcert -install
  mkcert 192.168.68.128   # replace with your host/IP

  export RB_SSL_CERT_FILE=/path/to/192.168.128.pem
  export RB_SSL_KEY_FILE=/path/to/192.168.128-key.pem
  python app.py   # now on https://<ip>:8000
  ```
- **Ad-hoc self-signed**
  ```bash
  export RB_USE_HTTPS=1
  python app.py
  ```
  (Chrome will warn once about the cert, but downloads then happen over HTTPS.)

- **Behind a reverse proxy (Nginx/Caddy)**  
  App includes `ProxyFix` so `X-Forwarded-Proto/Host` are respected. Terminate TLS at the proxy and forward to Flask.

---

## 2) Project structure

```
.
├── app.py
├── requirements.txt
├── images/            # your input frames (PNG/JPEG)
├── annotations/       # VOC XML is saved here (one per image)
├── exports/           # VOC zip exports appear here
├── templates/
│   ├── index.html     # grid
│   ├── review.html    # review mode (carousel)
│   └── annotate.html  # single-image editor
└── static/
    ├── styles.css
    ├── main.js        # grid logic + overlays
    ├── review.js      # carousel + draw-to-advance
    ├── annotate.js    # single-image editor
    └── utils.js       # color generation utility
```

---

## 3) Environment variables

| Var | Default | What it does |
|---|---|---|
| `RB_IMAGE_DIR` | `./images` | Where images are read from. |
| `RB_ANNOTATION_DIR` | `./annotations` | Where Pascal VOC XML is stored. |
| `RB_EXPORTS_DIR` | `./exports` | Where VOC zips are written. |
| `RB_PAGE_SIZE` | `200` | Default grid page size. |
| `PORT` | `8000` | Listen port. |
| `RB_USE_HTTPS` | (unset) | If set to 1/true, enables HTTPS (adhoc) unless certs provided. |
| `RB_SSL_CERT_FILE` | (unset) | Path to TLS cert (PEM). |
| `RB_SSL_KEY_FILE` | (unset) | Path to TLS key (PEM). |

---

## 4) Using the app

### Grid view
- **Fast thumbnails**; choose page size & thumb size.
- **Select**: click to toggle; **Shift-click** a range.
- **Bulk delete**: removes images *and* their matching XML from the filesystem.

**Overlays on thumbnails**  
After you annotate, the grid draws scaled, color-coded boxes over each thumbnail. It bulk-fetches annotations with a single call, and falls back to per-image fetch if needed.

### Review Mode (carousel)
- Open “Review Mode ⚡” from the top bar.
- **Layout**: Previous (2×, shows saved boxes/labels) • Current (3×, draw here) • Next (2×).
- **Draw-to-advance**: Drag a box on **Current** → auto-saves with **last used label** → auto-moves to Next.
- **Change label quickly**: press **1–9** to pick from label dropdown.
- **Back/Skip/Delete**: buttons or shortcuts (see below).
- **Persistence**: Boxes save to `annotations/<basename>.xml` immediately. If the page reloads, your work is intact.

### Single-image editor
If you need to refine a box: click the ✏️ on a tile. You can add/remove boxes and change classes; hit **Save**.

---

## 5) Keyboard shortcuts

**Grid**
- `A` — toggle select-all on page
- `D` — delete selected
- `E` — export VOC ZIP (annotated only)
- `← / →` — page navigation

**Review Mode**
- `Drag` — draw & save box on current image (auto-advance)
- `1–9` — switch current label
- `Space` — Skip to next (no change)
- `←` — Go back one image
- `Delete` — Delete current image (and its XML)

**Annotate page**
- `S` — Save
- `Backspace` — Delete selected box

---

## 6) Annotation format (Pascal VOC)

Annotations are stored per-image in `annotations/<image_basename>.xml`.  

Example:
```xml
<annotation>
  <folder>images</folder>
  <filename>frame_001.png</filename>
  <size><width>224</width><height>224</height><depth>3</depth></size>
  <object>
    <name>my_class</name>
    <bndbox>
      <xmin>32</xmin><ymin>45</ymin>
      <xmax>90</xmax><ymax>120</ymax>
    </bndbox>
  </object>
</annotation>
```

**Classes** are managed via `/api/classes` and saved in `annotations/classes.json`.

---

## 7) Exporting a dataset (for Roboflow / YOLO)

Click **Export VOC** from the grid. You’ll get `VOC_YYYYMMDD_HHMMSS.zip`, containing:

```
VOC_XXXX/
  ├── Annotations/      # Pascal VOC XMLs
  ├── JPEGImages/       # Original images (PNG or JPEG are kept as-is)
  └── ImageSets/
      └── Main/
          └── train.txt # One basename per line
```

Upload this ZIP to Roboflow as a Pascal VOC dataset (compatible with YOLO training pipelines).

---

## 8) API endpoints

- `GET /api/images?page=1&page_size=200`  
  Returns sorted filenames (most recent first).
  ```json
  {"total": 1234, "page": 1, "page_size": 200, "images": ["a.png","b.jpg", "..."]}
  ```

- `GET /image/<filename>`  
  Serves the raw image.

- `POST /api/delete`  
  Deletes images **and** corresponding XML.
  ```json
  { "files": ["a.png","b.jpg"] }
  ```

- `GET /api/annotation?image=<filename>`  
  Returns boxes for one image.
  ```json
  {"boxes":[{"label":"class","x1":10,"y1":20,"x2":60,"y2":80}]}
  ```

- `POST /api/annotations_bulk`  
  Boxes for many images at once (fast path for grid overlays).
  ```json
  { "images": ["a.png","b.jpg"] }
  =>
  { "items": { "a.png": {"boxes":[...]}, "b.jpg": {"boxes":[...]}} }
  ```

- `POST /api/annotate`  
  Save/replace all boxes for an image (writes VOC XML).
  ```json
  { "image": "a.png",
    "boxes": [ {"label":"class","x1":10,"y1":20,"x2":60,"y2":80}, ... ] }
  ```

- `GET /api/classes` / `POST /api/classes`  
  Get/set class list (persisted to `annotations/classes.json`).
  ```json
  { "classes": ["cat","dog"] }
  ```

- `POST /api/export_voc`  
  Build a VOC ZIP (annotated-only by default).
  ```json
  { "annotated_only": true }
  =>
  { "ok": true, "zip_name": "VOC_YYYYMMDD_HHMMSS.zip", "zip_url": "/exports/..." }
  ```
- `POST /api/import_voc`
  Import a VOC dataset from a `.zip` file.
  ```json
  { "ok": true, "message": "Imported 2 images.", "failed_files": [] }
  ```

> **Caching**: annotation responses use `Cache-Control: no-store` and the client appends `?t=<Date.now()>` to avoid stale reads.

---

## 9) Troubleshooting

- **Boxes not saving**  
  Ensure the process can write to `annotations/`. Check server logs for exceptions.

- **“Insecure download” warning**
  Run over HTTPS (see above). Either mkcert or a reverse proxy works.

- **Import fails silently**
  The importer is designed to be robust and skip problematic files. If an import fails, the UI will display a list of the files that could not be processed.

---

## 10) License

MIT (feel free to adapt to your workflow).