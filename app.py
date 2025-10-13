#!/usr/bin/env python3
import os, glob, json, shutil, zipfile, io
from datetime import datetime
from typing import List, Dict, Any
from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image
import xml.etree.ElementTree as ET

APP_TITLE = "Yolo-ReviewBox"
IMAGE_DIR = os.environ.get("RB_IMAGE_DIR", os.path.abspath("./images"))
ANNOTATION_DIR = os.environ.get("RB_ANNOTATION_DIR", os.path.abspath("./annotations"))
EXPORTS_DIR = os.environ.get("RB_EXPORTS_DIR", os.path.abspath("./exports"))
PAGE_SIZE_DEFAULT = int(os.environ.get("RB_PAGE_SIZE", "200"))
ALLOWED_EXTS = {".jpg", ".jpeg", ".png"}
MAX_IMAGES = 2500

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(ANNOTATION_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

app = Flask(__name__)
# Respect X-Forwarded-Proto/Host when behind a reverse proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def list_images_sorted() -> List[str]:
    files = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        files.extend(glob.glob(os.path.join(IMAGE_DIR, ext)))
    files.sort(key=lambda p: (-os.path.getmtime(p), os.path.basename(p).lower()))
    return [os.path.basename(p) for p in files[:MAX_IMAGES]]

def is_safe_filename(name: str) -> bool:
    if "/" in name or "\\" in name: return False
    _, ext = os.path.splitext(name)
    return ext.lower() in ALLOWED_EXTS

def img_size(path: str):
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (224, 224)

def clamp(v, lo, hi): return max(lo, min(hi, v))

def boxes_to_voc_xml(img_file: str, w: int, h: int, boxes: List[Dict[str, Any]]) -> bytes:
    ann = ET.Element("annotation")
    ET.SubElement(ann, "folder").text = os.path.basename(IMAGE_DIR)
    ET.SubElement(ann, "filename").text = img_file
    ET.SubElement(ann, "path").text = os.path.join(IMAGE_DIR, img_file)
    src = ET.SubElement(ann, "source"); ET.SubElement(src, "database").text = "Unknown"
    size = ET.SubElement(ann, "size")
    ET.SubElement(size, "width").text = str(w)
    ET.SubElement(size, "height").text = str(h)
    ET.SubElement(size, "depth").text = "3"
    ET.SubElement(ann, "segmented").text = "0"
    for b in boxes:
        x1, y1, x2, y2 = int(b.get("x1",0)), int(b.get("y1",0)), int(b.get("x2",0)), int(b.get("y2",0))
        x1, y1 = clamp(x1,0,w-1), clamp(y1,0,h-1)
        x2, y2 = clamp(x2,0,w-1), clamp(y2,0,h-1)
        xmin, ymin, xmax, ymax = min(x1,x2), min(y1,y2), max(x1,x2), max(y1,y2)
        obj = ET.SubElement(ann, "object")
        ET.SubElement(obj, "name").text = str(b.get("label","object"))
        ET.SubElement(obj, "pose").text = "Unspecified"
        ET.SubElement(obj, "truncated").text = "0"
        ET.SubElement(obj, "difficult").text = "0"
        bb = ET.SubElement(obj, "bndbox")
        ET.SubElement(bb, "xmin").text = str(xmin)
        ET.SubElement(bb, "ymin").text = str(ymin)
        ET.SubElement(bb, "xmax").text = str(xmax)
        ET.SubElement(bb, "ymax").text = str(ymax)
    return ET.tostring(ann, encoding="utf-8")

def voc_xml_path(img_name: str) -> str:
    base, _ = os.path.splitext(img_name)
    return os.path.join(ANNOTATION_DIR, base + ".xml")

@app.route("/")
def index():
    return render_template("index.html", app_title=APP_TITLE, page_size=PAGE_SIZE_DEFAULT)

@app.route("/review")
def review_mode():
    return render_template("review.html", app_title=APP_TITLE)

@app.route("/annotate")
def annotate_page():
    img = request.args.get("image","")
    if not is_safe_filename(img): abort(400, "Invalid image name.")
    path = os.path.join(IMAGE_DIR, img)
    if not os.path.exists(path): abort(404, "Image not found.")
    w,h = img_size(path)
    return render_template("annotate.html", image_name=img, image_w=w, image_h=h, app_title=APP_TITLE)

@app.route("/api/images")
def api_images():
    try: page = int(request.args.get("page","1"))
    except: page = 1
    try: page_size = int(request.args.get("page_size", str(PAGE_SIZE_DEFAULT)))
    except: page_size = PAGE_SIZE_DEFAULT
    imgs = list_images_sorted()
    total = len(imgs)
    start = max(0, (page-1)*page_size)
    end = min(total, start+page_size)
    return jsonify({"total": total, "page": page, "page_size": page_size, "images": imgs[start:end]})

@app.route("/image/<path:fname>")
def serve_image(fname):
    if not is_safe_filename(fname): abort(400, "Invalid image name.")
    return send_from_directory(IMAGE_DIR, fname)

@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json(force=True, silent=True) or {}
    files = data.get("files", [])
    deleted, errors = [], []
    for f in files:
        if not is_safe_filename(f):
            errors.append({"file": f, "error": "invalid name"}); continue
        fpath = os.path.join(IMAGE_DIR, f)
        try:
            if os.path.exists(fpath): os.remove(fpath)
            axml = voc_xml_path(f)
            if os.path.exists(axml): os.remove(axml)
            deleted.append(f)
        except Exception as e:
            errors.append({"file": f, "error": str(e)})
    return jsonify({"deleted": deleted, "errors": errors})

@app.route("/api/annotation", methods=["GET"])
def api_get_annotation():
    img = request.args.get("image","")
    if not is_safe_filename(img): abort(400, "Invalid image name.")
    axml = voc_xml_path(img)
    boxes = []
    if os.path.exists(axml):
        try:
            root = ET.parse(axml).getroot()
            for obj in root.findall("object"):
                bnd = obj.find("bndbox")
                if bnd is None: continue
                boxes.append({
                    "label": obj.findtext("name","object"),
                    "x1": int(bnd.findtext("xmin","0")),
                    "y1": int(bnd.findtext("ymin","0")),
                    "x2": int(bnd.findtext("xmax","0")),
                    "y2": int(bnd.findtext("ymax","0")),
                })
        except Exception as e:
            resp = jsonify({"boxes": boxes, "error": str(e)})
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            return resp, 200
    resp = jsonify({"boxes": boxes})
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

@app.route("/api/annotations_bulk", methods=["POST"])
def api_annotations_bulk():
    data = request.get_json(force=True, silent=True) or {}
    images = data.get("images", [])
    out = {}
    for name in images:
        if not is_safe_filename(name):
            continue
        axml = voc_xml_path(name)
        boxes = []
        if os.path.exists(axml):
            try:
                root = ET.parse(axml).getroot()
                for obj in root.findall("object"):
                    bnd = obj.find("bndbox")
                    if bnd is None: continue
                    boxes.append({
                        "label": obj.findtext("name", "object"),
                        "x1": int(bnd.findtext("xmin", "0")),
                        "y1": int(bnd.findtext("ymin", "0")),
                        "x2": int(bnd.findtext("xmax", "0")),
                        "y2": int(bnd.findtext("ymax", "0")),
                    })
            except Exception:
                boxes = []
        out[name] = {"boxes": boxes}
    resp = jsonify({"items": out})
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

@app.route("/api/annotate", methods=["POST"])
def api_post_annotate():
    data = request.get_json(force=True, silent=True) or {}
    img = data.get("image"); boxes = data.get("boxes", [])
    if not (img and is_safe_filename(img)): abort(400, "Invalid image.")
    path = os.path.join(IMAGE_DIR, img)
    if not os.path.exists(path): abort(404, "Image not found.")
    w,h = img_size(path)
    with open(voc_xml_path(img), "wb") as f:
        f.write(boxes_to_voc_xml(img, w, h, boxes))
    return jsonify({"ok": True})

@app.route("/api/classes", methods=["GET", "POST"])
def api_classes():
    CLASSES_FILE = os.path.join(ANNOTATION_DIR, "classes.json")
    if request.method == "GET":
        if os.path.exists(CLASSES_FILE):
            try:
                resp = jsonify({"classes": json.load(open(CLASSES_FILE))})
                resp.headers["Cache-Control"] = "no-store, max-age=0"
                return resp
            except Exception:
                pass
        resp = jsonify({"classes": []})
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp
    else:
        data = request.get_json(force=True, silent=True) or {}
        classes = data.get("classes", [])
        with open(CLASSES_FILE, "w") as f: json.dump(classes, f, indent=2)
        return jsonify({"ok": True})

@app.route("/api/import_voc", methods=["POST"])
def api_import_voc():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if not file.filename.lower().endswith('.zip'):
        return jsonify({"error": "Invalid file type, must be a .zip file"}), 400

    try:
        imported_count = 0
        with zipfile.ZipFile(io.BytesIO(file.read()), 'r') as z:
            for item in z.infolist():
                if item.is_dir() or '__MACOSX' in item.filename:
                    continue

                # Sanitize filename to prevent directory traversal
                base_filename = os.path.basename(item.filename)
                if not base_filename: continue

                # Determine if it's an image or annotation and set the correct directory
                if any(base_filename.lower().endswith(ext) for ext in ALLOWED_EXTS):
                    target_dir = IMAGE_DIR
                    if not is_safe_filename(base_filename): continue
                    target_path = os.path.join(target_dir, base_filename)
                    with open(target_path, 'wb') as f:
                        f.write(z.read(item.filename))
                    imported_count += 1
                elif base_filename.lower().endswith('.xml'):
                    target_dir = ANNOTATION_DIR
                    target_path = os.path.join(target_dir, base_filename)
                    with open(target_path, 'wb') as f:
                        f.write(z.read(item.filename))

        return jsonify({"ok": True, "message": f"Imported {imported_count} images."})
    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid or corrupted zip file."}), 400
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route("/api/export_voc", methods=["POST"])
def api_export_voc():
    data = request.get_json(force=True, silent=True) or {}
    annotated_only = bool(data.get("annotated_only", True))
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_root = os.path.join(EXPORTS_DIR, f"VOC_{ts}")
    pj = os.path.join(out_root, "JPEGImages")
    pa = os.path.join(out_root, "Annotations")
    pm = os.path.join(out_root, "ImageSets", "Main")
    os.makedirs(pj, exist_ok=True); os.makedirs(pa, exist_ok=True); os.makedirs(pm, exist_ok=True)
    imgs = list_images_sorted(); kept = []
    for name in imgs:
        src_img = os.path.join(IMAGE_DIR, name)
        axml_src = voc_xml_path(name)
        if annotated_only and not os.path.exists(axml_src): continue
        try:
            shutil.copy2(src_img, os.path.join(pj, name))
            if os.path.exists(axml_src):
                shutil.copy2(axml_src, os.path.join(pa, os.path.basename(axml_src)))
            kept.append(name)
        except Exception: pass
    with open(os.path.join(pm, "train.txt"), "w") as f:
        for k in kept: f.write(os.path.splitext(k)[0] + "\n")
    zip_path = os.path.join(EXPORTS_DIR, f"VOC_{ts}.zip")
    shutil.make_archive(base_name=zip_path[:-4], format="zip", root_dir=out_root)
    return jsonify({"ok": True, "count": len(kept), "zip_name": os.path.basename(zip_path), "zip_url": f"/exports/{os.path.basename(zip_path)}"})

@app.route("/exports/<path:fname>")
def serve_export(fname):
    if "/" in fname or "\\" in fname or not fname.endswith(".zip"): abort(400)
    return send_from_directory(EXPORTS_DIR, fname, as_attachment=True)

if __name__ == "__main__":
    use_https = os.environ.get("RB_USE_HTTPS", "").lower() in ("1","true","yes")
    cert = os.environ.get("RB_SSL_CERT_FILE")
    key = os.environ.get("RB_SSL_KEY_FILE")
    ssl_context = None
    if cert and key:
        ssl_context = (cert, key)
        use_https = True
    elif use_https:
        ssl_context = "adhoc"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8000")), debug=True, threaded=True, ssl_context=ssl_context)
