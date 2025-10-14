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
        "images": os.path.join(base, "images"),
        "annotations": os.path.join(base, "annotations"),
        "exports": os.path.join(base, "exports"),
    }

def get_active_project_dirs() -> Dict[str, str]:
    return get_project_dirs(get_active_project())

def ensure_project_dirs_exist(project_name: str):
    dirs = get_project_dirs(project_name)
    os.makedirs(dirs["images"], exist_ok=True)
    os.makedirs(dirs["annotations"], exist_ok=True)
    os.makedirs(dirs["exports"], exist_ok=True)

# Ensure default project exists on startup
ensure_project_dirs_exist(get_active_project())

app = Flask(__name__, static_url_path='/static', static_folder='static')
# Respect X-Forwarded-Proto/Host when behind a reverse proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def list_images_sorted() -> List[str]:
    dirs = get_active_project_dirs()
    image_dir = dirs["images"]
    files = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        files.extend(glob.glob(os.path.join(image_dir, ext)))
    files.sort(key=lambda p: (-os.path.getmtime(p), os.path.basename(p).lower()))
    return [os.path.basename(p) for p in files]

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
    dirs = get_active_project_dirs()
    image_dir = dirs["images"]
    ann = ET.Element("annotation")
    ET.SubElement(ann, "folder").text = os.path.basename(image_dir)
    ET.SubElement(ann, "filename").text = img_file
    ET.SubElement(ann, "path").text = os.path.join(image_dir, img_file)
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
    dirs = get_active_project_dirs()
    annotation_dir = dirs["annotations"]
    base, _ = os.path.splitext(img_name)
    return os.path.join(annotation_dir, base + ".xml")

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
    dirs = get_active_project_dirs()
    image_dir = dirs["images"]
    path = os.path.join(image_dir, img)
    if not os.path.exists(path): abort(404, "Image not found.")
    w,h = img_size(path)
    return render_template("annotate.html", image_name=img, image_w=w, image_h=h, app_title=APP_TITLE)

def get_unannotated_images() -> List[str]:
    dirs = get_active_project_dirs()
    image_dir = dirs["images"]
    annotation_dir = dirs["annotations"]
    all_images = set(list_images_sorted())
    annotated_images = set()
    for ann_file in glob.glob(os.path.join(annotation_dir, "*.xml")):
        base, _ = os.path.splitext(os.path.basename(ann_file))
        # This is not robust, but works for now
        for ext in ALLOWED_EXTS:
            annotated_images.add(base + ext)
            annotated_images.add(base + ext.upper())

    unannotated = sorted(list(all_images - annotated_images), key=lambda p: (-os.path.getmtime(os.path.join(image_dir, p)), p.lower()))
    return unannotated

def get_images_by_class(class_name: str) -> List[str]:
    dirs = get_active_project_dirs()
    annotation_dir = dirs["annotations"]
    img_files = set()
    if class_name == "__unannotated__":
        return get_unannotated_images()

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
    dirs = get_active_project_dirs()
    image_dir = dirs["images"]
    return send_from_directory(image_dir, fname)

@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json(force=True, silent=True) or {}
    files = data.get("files", [])
    deleted, errors = [], []
    dirs = get_active_project_dirs()
    image_dir = dirs["images"]
    for f in files:
        if not is_safe_filename(f):
            errors.append({"file": f, "error": "invalid name"}); continue
        fpath = os.path.join(image_dir, f)
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
    dirs = get_active_project_dirs()
    image_dir = dirs["images"]
    path = os.path.join(image_dir, img)
    if not os.path.exists(path): abort(404, "Image not found.")
    w,h = img_size(path)
    with open(voc_xml_path(img), "wb") as f:
        f.write(boxes_to_voc_xml(img, w, h, boxes))
    return jsonify({"ok": True})

@app.route("/api/classes", methods=["GET", "POST"])
def api_classes():
    dirs = get_active_project_dirs()
    annotation_dir = dirs["annotations"]
    classes_file = os.path.join(annotation_dir, "classes.json")
    if request.method == "GET":
        if os.path.exists(classes_file):
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
        with open(classes_file, "w") as f: json.dump(classes, f, indent=2)
        return jsonify({"ok": True})

def update_classes_from_annotations():
    """Scan all XML files and update classes.json"""
    dirs = get_active_project_dirs()
    annotation_dir = dirs["annotations"]
    classes = set()
    for ann_file in glob.glob(os.path.join(annotation_dir, "*.xml")):
        try:
            tree = ET.parse(ann_file)
            for obj in tree.findall("object"):
                class_name = obj.findtext("name")
                if class_name and class_name != "__null__":
                    classes.add(class_name)
        except ET.ParseError:
            continue

    classes_file = os.path.join(annotation_dir, "classes.json")
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
        imported_count = 0
        failed_files = []
        dirs = get_active_project_dirs()
        image_dir = dirs["images"]
        annotation_dir = dirs["annotations"]
        with zipfile.ZipFile(file, 'r') as z:
            for item in z.infolist():
                try:
                    if item.is_dir() or '__MACOSX' in item.filename:
                        continue

                    base_filename = os.path.basename(item.filename)
                    if not base_filename: continue

                    if any(base_filename.lower().endswith(ext) for ext in ALLOWED_EXTS):
                        target_dir = image_dir
                        if not is_safe_filename(base_filename):
                            failed_files.append(f"{item.filename} (unsafe name)")
                            continue
                        target_path = os.path.join(target_dir, base_filename)
                        with z.open(item) as zf, open(target_path, 'wb') as f:
                            shutil.copyfileobj(zf, f)
                        imported_count += 1
                    elif base_filename.lower().endswith('.xml'):
                        target_dir = annotation_dir
                        target_path = os.path.join(target_dir, base_filename)
                        with z.open(item) as zf, open(target_path, 'wb') as f:
                            shutil.copyfileobj(zf, f)
                except Exception as e:
                    app.logger.error(f"Error importing {item.filename}: {str(e)}")
                    failed_files.append(item.filename)

        update_classes_from_annotations()

        message = f"Imported {imported_count} images."
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
        imported_count = 0
        failed_files = []
        dirs = get_active_project_dirs()
        image_dir = dirs["images"]
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
                        target_path = os.path.join(image_dir, base_filename)
                        with z.open(item) as zf, open(target_path, 'wb') as f:
                            shutil.copyfileobj(zf, f)
                        imported_count += 1
                except Exception as e:
                    app.logger.error(f"Error importing {item.filename}: {str(e)}")
                    failed_files.append(item.filename)

        message = f"Imported {imported_count} images."
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
    image_dir = dirs["images"]
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
        src_img = os.path.join(image_dir, name)
        axml_src = voc_xml_path(name)

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
    move_from = data.get("move_from")

    if not name or "/" in name or "\\" in name or not name.isalnum():
        abort(400, "Invalid project name. Must be alphanumeric.")

    new_project_path = os.path.join(PROJECTS_ROOT_DIR, name)
    if os.path.exists(new_project_path):
        abort(409, "Project already exists.")

    ensure_project_dirs_exist(name)

    if move_from:
        from_dirs = get_project_dirs(move_from)
        to_dirs = get_project_dirs(name)
        try:
            # Move images, annotations
            for d in ["images", "annotations"]:
                src_dir = from_dirs[d]
                dst_dir = to_dirs[d]
                for item in os.listdir(src_dir):
                    shutil.move(os.path.join(src_dir, item), os.path.join(dst_dir, item))
        except Exception as e:
            # Best-effort, log and continue
            app.logger.error(f"Error moving files from '{move_from}': {e}")


    set_active_project(name)
    return jsonify({"ok": True, "name": name})


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