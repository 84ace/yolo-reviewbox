#!/usr/bin/env python3
import os, glob, json, shutil, zipfile, io
from datetime import datetime
from typing import List, Dict, Any
from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image
import xml.etree.ElementTree as ET

APP_TITLE = "Yolo-ReviewBox"
PROJECTS_ROOT_DIR = os.environ.get("RB_PROJECTS_DIR", os.path.abspath("./projects"))
RAW_IMAGES_DIR = os.environ.get("RB_RAW_IMAGES_DIR", os.path.abspath("./raw_images"))
IMAGE_CATALOG_DIR = os.environ.get("RB_IMAGE_CATALOG_DIR", os.path.abspath("./image_catalog"))
ANNOTATION_CATALOG_DIR = os.environ.get("RB_ANNOTATION_CATALOG_DIR", os.path.abspath("./annotations"))
PAGE_SIZE_DEFAULT = int(os.environ.get("RB_PAGE_SIZE", "200"))
ALLOWED_EXTS = {".jpg", ".jpeg", ".png"}

ACTIVE_PROJECT_FILE = os.path.join(PROJECTS_ROOT_DIR, "active_project.txt")

def get_active_project() -> str:
    if os.path.exists(ACTIVE_PROJECT_FILE):
        with open(ACTIVE_PROJECT_FILE, "r") as f:
            return f.read().strip()
    return "default"

def set_active_project(name: str):
    os.makedirs(PROJECTS_ROOT_DIR, exist_ok=True)
    with open(ACTIVE_PROJECT_FILE, "w") as f:
        f.write(name)

def get_project_dirs(project_name: str) -> Dict[str, str]:
    base = os.path.join(PROJECTS_ROOT_DIR, project_name)
    return {
        "annotations": os.path.join(base, "annotations"),
        "exports": os.path.join(base, "exports"),
        "project_images": os.path.join(base, "project_images.txt"),
    }

def get_active_project_dirs() -> Dict[str, str]:
    return get_project_dirs(get_active_project())

def ensure_project_dirs_exist(project_name: str):
    dirs = get_project_dirs(project_name)
    os.makedirs(dirs["annotations"], exist_ok=True)
    os.makedirs(dirs["exports"], exist_ok=True)
    if not os.path.exists(dirs["project_images"]):
        with open(dirs["project_images"], "w") as f:
            pass  # Create an empty file

# Ensure default project exists on startup
ensure_project_dirs_exist(get_active_project())
os.makedirs(RAW_IMAGES_DIR, exist_ok=True)
os.makedirs(IMAGE_CATALOG_DIR, exist_ok=True)
os.makedirs(ANNOTATION_CATALOG_DIR, exist_ok=True)


app = Flask(__name__, static_url_path='/static', static_folder='static')
# Respect X-Forwarded-Proto/Host when behind a reverse proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def list_images_sorted() -> List[str]:
    dirs = get_active_project_dirs()
    images_file = dirs["project_images"]
    if not os.path.exists(images_file):
        return []
    with open(images_file, "r") as f:
        files = [line.strip() for line in f if line.strip()]

    # Sort by modification time of the actual files in the catalog
    def get_mtime(f):
        path = os.path.join(IMAGE_CATALOG_DIR, f)
        return os.path.getmtime(path) if os.path.exists(path) else 0

    files.sort(key=lambda p: (-get_mtime(p), p.lower()))
    return files

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
    ET.SubElement(ann, "folder").text = os.path.basename(IMAGE_CATALOG_DIR)
    ET.SubElement(ann, "filename").text = img_file
    ET.SubElement(ann, "path").text = os.path.join(IMAGE_CATALOG_DIR, img_file)
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

def project_voc_xml_path(img_name: str) -> str:
    dirs = get_active_project_dirs()
    annotation_dir = dirs["annotations"]
    base, _ = os.path.splitext(img_name)
    return os.path.join(annotation_dir, base + ".xml")

def catalog_voc_xml_path(img_name: str) -> str:
    base, _ = os.path.splitext(img_name)
    return os.path.join(ANNOTATION_CATALOG_DIR, base + ".xml")

def raw_voc_xml_path(img_name: str) -> str:
    base, _ = os.path.splitext(img_name)
    return os.path.join(RAW_IMAGES_DIR, ".tmp", base + ".xml")

@app.route("/")
def index():
    return render_template("catalog.html", app_title=APP_TITLE, page_size=PAGE_SIZE_DEFAULT)

@app.route("/project")
def project_view():
    return render_template("index.html", app_title=APP_TITLE, page_size=PAGE_SIZE_DEFAULT)

@app.route("/review")
def review_mode():
    return render_template("review.html", app_title=APP_TITLE)

@app.route("/raw_review")
def raw_review_page():
    return render_template("raw_review.html", app_title=APP_TITLE)

@app.route("/raw_review_classify")
def raw_review_classify_page():
    return render_template("raw_review_classify.html", app_title=APP_TITLE)

@app.route("/add_from_catalog")
def add_from_catalog_page():
    return render_template("add_from_catalog.html", app_title=APP_TITLE)

@app.route("/api/catalog/available")
def api_catalog_available():
    try: page = int(request.args.get("page", "1"))
    except: page = 1
    try: page_size = int(request.args.get("page_size", str(PAGE_SIZE_DEFAULT)))
    except: page_size = PAGE_SIZE_DEFAULT

    dirs = get_active_project_dirs()
    with open(dirs["project_images"], "r") as f:
        project_images = {line.strip() for line in f}

    catalog_images = {f for f in os.listdir(IMAGE_CATALOG_DIR) if os.path.isfile(os.path.join(IMAGE_CATALOG_DIR, f))}
    available_images = sorted(list(catalog_images - project_images))

    total = len(available_images)
    start = max(0, (page - 1) * page_size)
    end = min(total, start + page_size)

    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "images": available_images[start:end]
    })

@app.route("/api/catalog/images")
def api_catalog_images():
    try: page = int(request.args.get("page", "1"))
    except: page = 1
    try: page_size = int(request.args.get("page_size", str(PAGE_SIZE_DEFAULT)))
    except: page_size = PAGE_SIZE_DEFAULT

    all_files = sorted(
        [f for f in os.listdir(IMAGE_CATALOG_DIR) if os.path.isfile(os.path.join(IMAGE_CATALOG_DIR, f))],
        key=lambda f: (-os.path.getmtime(os.path.join(IMAGE_CATALOG_DIR, f)), f.lower())
    )

    total = len(all_files)
    start = max(0, (page - 1) * page_size)
    end = min(total, start + page_size)

    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "images": all_files[start:end]
    })

@app.route("/api/catalog/project_associations")
def api_catalog_project_associations():
    associations = {}
    projects = [d for d in os.listdir(PROJECTS_ROOT_DIR) if os.path.isdir(os.path.join(PROJECTS_ROOT_DIR, d))]
    for project in projects:
        project_images_file = os.path.join(PROJECTS_ROOT_DIR, project, "project_images.txt")
        if os.path.exists(project_images_file):
            with open(project_images_file, "r") as f:
                for line in f:
                    image = line.strip()
                    if image:
                        if image not in associations:
                            associations[image] = []
                        associations[image].append(project)
    return jsonify(associations)

@app.route("/api/catalog/add_to_project", methods=["POST"])
def api_catalog_add_to_project():
    data = request.get_json(force=True, silent=True) or {}
    files = data.get("files", [])
    errors = []
    dirs = get_active_project_dirs()

    try:
        with open(dirs["project_images"], "a") as f:
            for file in files:
                if is_safe_filename(file):
                    f.write(file + "\n")
                else:
                    errors.append({"file": file, "error": "Invalid filename"})
    except Exception as e:
        errors.append({"error": str(e)})

    return jsonify({"ok": True, "errors": errors})

@app.route("/annotate")
def annotate_page():
    img = request.args.get("image","")
    if not is_safe_filename(img): abort(400, "Invalid image name.")
    path = os.path.join(IMAGE_CATALOG_DIR, img)
    if not os.path.exists(path): abort(404, "Image not found.")
    w,h = img_size(path)
    return render_template("annotate.html", image_name=img, image_w=w, image_h=h, app_title=APP_TITLE)

def get_unannotated_images() -> List[str]:
    dirs = get_active_project_dirs()
    project_annotation_dir = dirs["annotations"]
    all_images = set(list_images_sorted())
    annotated_images = set()

    def scan_annotations(annotation_dir):
        for ann_file in glob.glob(os.path.join(annotation_dir, "*.xml")):
            try:
                tree = ET.parse(ann_file)
                if len(tree.findall("object")) > 0:
                    filename = tree.findtext("filename")
                    if filename and is_safe_filename(filename):
                        annotated_images.add(filename)
            except ET.ParseError:
                continue

    scan_annotations(project_annotation_dir)
    scan_annotations(ANNOTATION_CATALOG_DIR)

    unannotated = sorted(list(all_images - annotated_images), key=lambda p: p.lower())
    return unannotated

def get_images_by_class(class_name: str) -> List[str]:
    dirs = get_active_project_dirs()
    project_annotation_dir = dirs["annotations"]
    img_files = set()
    if class_name == "__unannotated__":
        return get_unannotated_images()

    def scan_for_class(annotation_dir):
        for ann_file in glob.glob(os.path.join(annotation_dir, "*.xml")):
            try:
                tree = ET.parse(ann_file)
                root = tree.getroot()

                if class_name == "__null__":
                    if any(o.findtext("name") == "__null__" for o in root.findall("object")):
                        filename = root.findtext("filename")
                        if filename:
                            img_files.add(filename)
                else:
                    for obj in root.findall("object"):
                        if obj.findtext("name") == class_name:
                            filename = root.findtext("filename")
                            if filename:
                                img_files.add(filename)
                            break
            except ET.ParseError:
                continue

    scan_for_class(project_annotation_dir)
    scan_for_class(ANNOTATION_CATALOG_DIR)

    all_images = list_images_sorted()
    return [img for img in all_images if img in img_files]

@app.route("/api/images")
def api_images():
    try: page = int(request.args.get("page","1"))
    except: page = 1
    try: page_size = int(request.args.get("page_size", str(PAGE_SIZE_DEFAULT)))
    except: page_size = PAGE_SIZE_DEFAULT

    class_filter = request.args.get("class", None)

    if class_filter and class_filter != "All Classes":
        imgs = get_images_by_class(class_filter)
    else:
        imgs = list_images_sorted()

    total = len(imgs)
    start = max(0, (page-1)*page_size)
    end = min(total, start+page_size)
    return jsonify({"total": total, "page": page, "page_size": page_size, "images": imgs[start:end]})

@app.route("/image/<path:fname>")
def serve_image(fname):
    if not is_safe_filename(fname): abort(400, "Invalid image name.")
    return send_from_directory(IMAGE_CATALOG_DIR, fname)

@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json(force=True, silent=True) or {}
    files_to_delete = set(data.get("files", []))
    deleted_count = 0
    errors = []

    dirs = get_active_project_dirs()
    images_file = dirs["project_images"]

    try:
        with open(images_file, "r") as f:
            all_images = [line.strip() for line in f if line.strip()]

        updated_images = [img for img in all_images if img not in files_to_delete]

        with open(images_file, "w") as f:
            for img in updated_images:
                f.write(img + "\n")

        deleted_count = len(all_images) - len(updated_images)

        # Also delete associated annotation files
        for f in files_to_delete:
            if not is_safe_filename(f): continue
            axml = project_voc_xml_path(f)
            if os.path.exists(axml):
                os.remove(axml)

    except Exception as e:
        errors.append({"error": str(e)})

    return jsonify({"deleted_count": deleted_count, "errors": errors})

@app.route("/api/annotation", methods=["GET"])
def api_get_annotation():
    img = request.args.get("image","")
    if not is_safe_filename(img): abort(400, "Invalid image name.")

    # Project-specific annotation takes precedence
    axml = project_voc_xml_path(img)
    if not os.path.exists(axml):
        axml = catalog_voc_xml_path(img)

    boxes = []
    w, h = -1, -1
    if os.path.exists(axml):
        try:
            root = ET.parse(axml).getroot()
            size_el = root.find("size")
            if size_el:
                w = int(size_el.findtext("width", "-1"))
                h = int(size_el.findtext("height", "-1"))

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
            resp = jsonify({"boxes": boxes, "error": str(e), "w": w, "h": h})
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            return resp, 200

    if w < 0:
        w, h = img_size(os.path.join(IMAGE_CATALOG_DIR, img))

    resp = jsonify({"boxes": boxes, "w": w, "h": h})
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

@app.route("/api/catalog/annotations_bulk", methods=["POST"])
def api_catalog_annotations_bulk():
    data = request.get_json(force=True, silent=True) or {}
    images = data.get("images", [])
    out = {}

    for name in images:
        if not is_safe_filename(name):
            continue

        axml = catalog_voc_xml_path(name)

        boxes = []
        w,h = -1,-1
        if os.path.exists(axml):
            try:
                root = ET.parse(axml).getroot()
                size_el = root.find("size")
                if size_el:
                    w = int(size_el.findtext("width", "-1"))
                    h = int(size_el.findtext("height", "-1"))

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

        if w < 0:
            w, h = img_size(os.path.join(IMAGE_CATALOG_DIR, name))

        out[name] = {"boxes": boxes, "w": w, "h": h}

    resp = jsonify({"items": out})
    resp.headers["Cache-control"] = "no-store, max-age=0"
    return resp

@app.route("/api/annotations_bulk", methods=["POST"])
def api_annotations_bulk():
    data = request.get_json(force=True, silent=True) or {}
    images = data.get("images", [])
    out = {}

    for name in images:
        if not is_safe_filename(name):
            continue

        axml = project_voc_xml_path(name)
        if not os.path.exists(axml):
            axml = catalog_voc_xml_path(name)

        boxes = []
        w,h = -1,-1
        if os.path.exists(axml):
            try:
                root = ET.parse(axml).getroot()
                size_el = root.find("size")
                if size_el:
                    w = int(size_el.findtext("width", "-1"))
                    h = int(size_el.findtext("height", "-1"))

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

        if w < 0:
            w, h = img_size(os.path.join(IMAGE_CATALOG_DIR, name))

        out[name] = {"boxes": boxes, "w": w, "h": h}

    resp = jsonify({"items": out})
    resp.headers["Cache-control"] = "no-store, max-age=0"
    return resp

@app.route("/api/annotate", methods=["POST"])
def api_post_annotate():
    data = request.get_json(force=True, silent=True) or {}
    img = data.get("image"); boxes = data.get("boxes", [])
    if not (img and is_safe_filename(img)): abort(400, "Invalid image.")
    path = os.path.join(IMAGE_CATALOG_DIR, img)
    if not os.path.exists(path): abort(404, "Image not found.")
    w,h = img_size(path)
    with open(project_voc_xml_path(img), "wb") as f:
        f.write(boxes_to_voc_xml(img, w, h, boxes))
    return jsonify({"ok": True})

@app.route("/api/classes", methods=["GET", "POST"])
def api_classes():
    dirs = get_active_project_dirs()
    annotation_dir = dirs["annotations"]
    classes_file = os.path.join(annotation_dir, "classes.json")
    if request.method == "GET":
        if not os.path.exists(classes_file):
            update_classes_from_annotations()

        if os.path.exists(classes_file):
            try:
                with open(classes_file, "r") as f:
                    resp = jsonify({"classes": json.load(f)})
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
        with open(classes_file, "w") as f: json.dump(classes, f, indent=2)
        return jsonify({"ok": True})

def update_classes_from_annotations():
    """Scan all XML files and update classes.json"""
    dirs = get_active_project_dirs()
    project_annotation_dir = dirs["annotations"]
    classes = set()

    def scan_for_classes(annotation_dir):
        for ann_file in glob.glob(os.path.join(annotation_dir, "*.xml")):
            try:
                tree = ET.parse(ann_file)
                for obj in tree.findall("object"):
                    class_name = obj.findtext("name")
                    if class_name and class_name != "__null__":
                        classes.add(class_name)
            except ET.ParseError:
                continue

    scan_for_classes(project_annotation_dir)
    scan_for_classes(ANNOTATION_CATALOG_DIR)

    classes_file = os.path.join(project_annotation_dir, "classes.json")
    all_classes = sorted(list(classes))

    with open(classes_file, "w") as f:
        json.dump(all_classes, f, indent=2)

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
        imported_images = []
        failed_files = []
        dirs = get_active_project_dirs()
        annotation_dir = dirs["annotations"]

        with zipfile.ZipFile(file, 'r') as z:
            for item in z.infolist():
                try:
                    if item.is_dir() or '__MACOSX' in item.filename:
                        continue

                    base_filename = os.path.basename(item.filename)
                    if not base_filename: continue

                    if any(base_filename.lower().endswith(ext) for ext in ALLOWED_EXTS):
                        if not is_safe_filename(base_filename):
                            failed_files.append(f"{item.filename} (unsafe name)")
                            continue
                        target_path = os.path.join(IMAGE_CATALOG_DIR, base_filename)
                        with z.open(item) as zf, open(target_path, 'wb') as f:
                            shutil.copyfileobj(zf, f)
                        imported_images.append(base_filename)
                    elif base_filename.lower().endswith('.xml'):
                        target_path = os.path.join(ANNOTATION_CATALOG_DIR, base_filename)
                        with z.open(item) as zf, open(target_path, 'wb') as f:
                            shutil.copyfileobj(zf, f)
                except Exception as e:
                    app.logger.error(f"Error importing {item.filename}: {str(e)}")
                    failed_files.append(item.filename)

        # Add imported images to the current project
        if imported_images:
            images_file = dirs["project_images"]
            with open(images_file, "a") as f:
                for img in imported_images:
                    f.write(img + "\n")

        update_classes_from_annotations()

        message = f"Imported {len(imported_images)} images."
        if failed_files:
            message += f" Failed to import {len(failed_files)} files."

        return jsonify({"ok": True, "message": message, "failed_files": failed_files})
    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid or corrupted zip file."}), 400
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route("/api/import_images", methods=["POST"])
def api_import_images():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if not file.filename.lower().endswith('.zip'):
        return jsonify({"error": "Invalid file type, must be a .zip file"}), 400

    try:
        imported_images = []
        failed_files = []
        dirs = get_active_project_dirs()
        with zipfile.ZipFile(file, 'r') as z:
            for item in z.infolist():
                try:
                    if item.is_dir() or '__MACOSX' in item.filename:
                        continue
                    base_filename = os.path.basename(item.filename)
                    if not base_filename: continue
                    if any(base_filename.lower().endswith(ext) for ext in ALLOWED_EXTS):
                        if not is_safe_filename(base_filename):
                            failed_files.append(f"{item.filename} (unsafe name)")
                            continue
                        target_path = os.path.join(IMAGE_CATALOG_DIR, base_filename)
                        with z.open(item) as zf, open(target_path, 'wb') as f:
                            shutil.copyfileobj(zf, f)
                        imported_images.append(base_filename)
                except Exception as e:
                    app.logger.error(f"Error importing {item.filename}: {str(e)}")
                    failed_files.append(item.filename)

        if imported_images:
            images_file = dirs["project_images"]
            with open(images_file, "a") as f:
                for img in imported_images:
                    f.write(img + "\n")

        message = f"Imported {len(imported_images)} images."
        if failed_files:
            message += f" Failed to import {len(failed_files)} files."

        return jsonify({"ok": True, "message": message, "failed_files": failed_files})
    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid or corrupted zip file."}), 400
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route("/api/export_options", methods=["GET"])
def api_export_options():
    dirs = get_active_project_dirs()
    annotation_dir = dirs["annotations"]
    classes_file = os.path.join(annotation_dir, "classes.json")
    if os.path.exists(classes_file):
        try:
            with open(classes_file) as f:
                classes = json.load(f)
            return jsonify({"classes": classes})
        except Exception:
            pass
    return jsonify({"classes": []})

@app.route("/api/export_voc", methods=["POST"])
def api_export_voc():
    data = request.get_json(force=True, silent=True) or {}
    export_classes = data.get("classes", [])
    remap = data.get("remap", [])
    null_handling = data.get("null_handling", "unclassified")

    remap_dict = {}
    for r in remap:
        for f in r.get("from", []):
            remap_dict[f] = r.get("to")

    dirs = get_active_project_dirs()
    exports_dir = dirs["exports"]

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_root = os.path.join(exports_dir, f"VOC_{ts}")
    pj = os.path.join(out_root, "JPEGImages")
    pa = os.path.join(out_root, "Annotations")
    pm = os.path.join(out_root, "ImageSets", "Main")
    os.makedirs(pj, exist_ok=True); os.makedirs(pa, exist_ok=True); os.makedirs(pm, exist_ok=True)

    imgs = list_images_sorted()
    kept = []

    for name in imgs:
        src_img = os.path.join(IMAGE_CATALOG_DIR, name)

        axml_src = project_voc_xml_path(name)
        if not os.path.exists(axml_src):
            axml_src = catalog_voc_xml_path(name)

        if not os.path.exists(axml_src):
            continue

        try:
            tree = ET.parse(axml_src)
            root = tree.getroot()
            objects = root.findall("object")

            is_null = any(o.findtext("name") == "__null__" for o in objects)

            if is_null:
                if null_handling == "exclude":
                    continue
                # For "unclassified", we just don't add an annotation
                shutil.copy2(src_img, os.path.join(pj, name))
                kept.append(name)
                continue

            filtered_objects = []
            for obj in objects:
                original_class = obj.findtext("name")
                if original_class in export_classes:
                    filtered_objects.append(obj)

            if not filtered_objects:
                continue

            # Remap classes
            for obj in filtered_objects:
                original_class = obj.findtext("name")
                if original_class in remap_dict:
                    obj.find("name").text = remap_dict[original_class]

            # Write the modified XML
            new_tree = ET.ElementTree(root)
            # Remove old objects and add new ones
            for obj in objects:
                root.remove(obj)
            for obj in filtered_objects:
                root.append(obj)

            with open(os.path.join(pa, os.path.basename(axml_src)), "wb") as f:
                new_tree.write(f, encoding="utf-8")

            shutil.copy2(src_img, os.path.join(pj, name))
            kept.append(name)

        except Exception as e:
            app.logger.error(f"Error processing {name} for export: {e}")
            pass

    with open(os.path.join(pm, "train.txt"), "w") as f:
        for k in kept: f.write(os.path.splitext(k)[0] + "\n")

    zip_path = os.path.join(exports_dir, f"VOC_{ts}.zip")
    shutil.make_archive(base_name=zip_path[:-4], format="zip", root_dir=out_root)
    return jsonify({"ok": True, "count": len(kept), "zip_name": os.path.basename(zip_path), "zip_url": f"/exports/{os.path.basename(zip_path)}"})

@app.route("/exports/<path:fname>")
def serve_export(fname):
    if "/" in fname or "\\" in fname or not fname.endswith(".zip"): abort(400)
    dirs = get_active_project_dirs()
    exports_dir = dirs["exports"]
    return send_from_directory(exports_dir, fname, as_attachment=True)

@app.route("/api/projects", methods=["GET"])
def api_get_projects():
    projects = [d for d in os.listdir(PROJECTS_ROOT_DIR) if os.path.isdir(os.path.join(PROJECTS_ROOT_DIR, d))]
    return jsonify({
        "projects": sorted(projects),
        "active": get_active_project(),
    })

@app.route("/api/project/switch", methods=["POST"])
def api_switch_project():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name")
    if not name or "/" in name or "\\" in name:
        abort(400, "Invalid project name.")

    if not os.path.isdir(os.path.join(PROJECTS_ROOT_DIR, name)):
        abort(404, "Project not found.")

    set_active_project(name)
    return jsonify({"ok": True, "active": name})

@app.route("/api/project/create", methods=["POST"])
def api_create_project():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name")

    if not name or "/" in name or "\\" in name or not name.isalnum():
        abort(400, "Invalid project name. Must be alphanumeric.")

    new_project_path = os.path.join(PROJECTS_ROOT_DIR, name)
    if os.path.exists(new_project_path):
        abort(409, "Project already exists.")

    ensure_project_dirs_exist(name)

    set_active_project(name)
    return jsonify({"ok": True, "name": name})

@app.route("/api/raw_browser")
def api_raw_browser():
    # Security: Ensure path is within RAW_IMAGES_DIR
    path_param = request.args.get("path", "")
    abs_path = os.path.abspath(os.path.join(RAW_IMAGES_DIR, path_param))
    if not abs_path.startswith(RAW_IMAGES_DIR):
        abort(400, "Invalid path.")

    recursive = request.args.get("recursive", "false").lower() == "true"
    network_filter = request.args.get("network", "")
    device_filter = request.args.get("device", "")

    items = []
    if recursive:
        for root, dirs, files in os.walk(abs_path):
            # Filtering logic for recursive view
            if network_filter and not any(f.startswith(network_filter) for f in root.split(os.sep)):
                continue

            for name in files:
                if device_filter and device_filter not in name:
                    continue
                if any(name.lower().endswith(ext) for ext in ALLOWED_EXTS):
                    path = os.path.relpath(os.path.join(root, name), RAW_IMAGES_DIR)
                    items.append({"name": name, "type": "file", "path": path})
    else:
        for item in os.listdir(abs_path):
            item_abs_path = os.path.join(abs_path, item)
            if os.path.isdir(item_abs_path):
                items.append({"name": item, "type": "dir"})
            elif any(item.lower().endswith(ext) for ext in ALLOWED_EXTS):
                items.append({"name": item, "type": "file", "path": os.path.relpath(item_abs_path, RAW_IMAGES_DIR)})

    # Sort directories first, then files
    items.sort(key=lambda x: (x.get("type", "file") != "dir", x.get("name").lower()))

    return jsonify(items)

@app.route("/raw_image/<path:fname>")
def serve_raw_image(fname):
    # Basic security check
    if ".." in fname or os.path.isabs(fname):
        abort(400, "Invalid path.")

    _, ext = os.path.splitext(fname)
    if ext.lower() not in ALLOWED_EXTS:
        abort(400, "Invalid file type.")

    return send_from_directory(RAW_IMAGES_DIR, fname)

@app.route("/api/raw/annotation", methods=["GET", "POST"])
def api_raw_annotation():
    if request.method == "GET":
        img = request.args.get("image","")
        if ".." in img or os.path.isabs(img): abort(400, "Invalid image name.")
        axml = raw_voc_xml_path(img)
        boxes = []
        w, h = -1, -1
        if os.path.exists(axml):
            try:
                root = ET.parse(axml).getroot()
                size_el = root.find("size")
                if size_el:
                    w = int(size_el.findtext("width", "-1"))
                    h = int(size_el.findtext("height", "-1"))

                for obj in root.findall("object"):
                    bnd = obj.find("bndbox")
                    if bnd is None: continue
                    boxes.append({
                        "label": obj.findtext("name","object"),
                        "x1": int(bnd.findtext("xmin","0")), "y1": int(bnd.findtext("ymin","0")),
                        "x2": int(bnd.findtext("xmax","0")), "y2": int(bnd.findtext("ymax","0")),
                    })
            except Exception as e:
                return jsonify({"boxes": boxes, "error": str(e), "w": w, "h": h}), 200

        if w < 0:
            w, h = img_size(os.path.join(RAW_IMAGES_DIR, img))

        resp = jsonify({"boxes": boxes, "w": w, "h": h})
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp
    else: # POST
        data = request.get_json(force=True, silent=True) or {}
        img = data.get("image"); boxes = data.get("boxes", [])
        if not img or ".." in img or os.path.isabs(img): abort(400, "Invalid image.")
        path = os.path.join(RAW_IMAGES_DIR, img)
        if not os.path.exists(path): abort(404, "Image not found.")

        xml_path = raw_voc_xml_path(img)
        xml_dir = os.path.dirname(xml_path)
        os.makedirs(xml_dir, exist_ok=True)

        w,h = img_size(path)
        with open(xml_path, "wb") as f:
            f.write(boxes_to_voc_xml(img, w, h, boxes))
        return jsonify({"ok": True})

@app.route("/api/raw/accept", methods=["POST"])
def api_raw_accept():
    data = request.get_json(force=True, silent=True) or {}
    files = data.get("files", [])
    label = data.get("label")
    accepted_files = []
    errors = []

    for f in files:
        src_path = os.path.join(RAW_IMAGES_DIR, f)
        raw_axml_path = raw_voc_xml_path(f)

        if not os.path.abspath(src_path).startswith(os.path.abspath(RAW_IMAGES_DIR)):
            errors.append({"file": f, "error": "Invalid path"})
            continue
        if not os.path.exists(src_path):
            errors.append({"file": f, "error": "Not found"})
            continue

        new_name = f.replace(os.sep, "_")
        dest_path = os.path.join(IMAGE_CATALOG_DIR, new_name)
        dest_axml_path = catalog_voc_xml_path(new_name)

        try:
            # Move image
            if not os.path.exists(dest_path):
                shutil.move(src_path, dest_path)

            # Move annotation if it exists, otherwise create a basic one
            if os.path.exists(raw_axml_path):
                shutil.move(raw_axml_path, dest_axml_path)
            else:
                if not label:
                    errors.append({"file": f, "error": "No label provided for un-annotated image"})
                    continue
                w, h = img_size(dest_path)
                box = {"label": label, "x1": 0, "y1": 0, "x2": w, "y2": h}
                with open(dest_axml_path, "wb") as axml:
                    axml.write(boxes_to_voc_xml(new_name, w, h, [box]))

            accepted_files.append({"original": f, "new": new_name})
        except Exception as e:
            errors.append({"file": f, "error": str(e)})

    for root, dirs, files in os.walk(RAW_IMAGES_DIR, topdown=False):
        if not dirs and not files:
            try:
                os.rmdir(root)
            except OSError:
                pass

    return jsonify({"accepted": accepted_files, "errors": errors})

@app.route("/api/raw/delete", methods=["POST"])
def api_raw_delete():
    data = request.get_json(force=True, silent=True) or {}
    files = data.get("files", [])
    deleted = []
    errors = []

    for f in files:
        path = os.path.join(RAW_IMAGES_DIR, f)

        if not os.path.abspath(path).startswith(os.path.abspath(RAW_IMAGES_DIR)):
            errors.append({"file": f, "error": "Invalid path"})
            continue

        if not os.path.exists(path):
            errors.append({"file": f, "error": "Not found"})
            continue

        try:
            os.remove(path)
            deleted.append(f)
        except Exception as e:
            errors.append({"file": f, "error": str(e)})

    for root, dirs, files in os.walk(RAW_IMAGES_DIR, topdown=False):
        if not dirs and not files:
            try:
                os.rmdir(root)
            except OSError:
                pass

    return jsonify({"deleted": deleted, "errors": errors})

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