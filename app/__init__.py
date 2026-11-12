"""Мінімальна система обліку спорядження: QR = {BASE_URL}/i/{ID}."""
import io
import os
import secrets
import sqlite3
import uuid
from pathlib import Path

import segno
from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)
from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

DEFAULTS = {"base_url": "", "qr_mm": "30", "id_pt": "14", "cut_lines": "1"}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "admin"),
        BASE_URL=os.environ.get("BASE_URL", ""),
        DATA_DIR=os.environ.get("DATA_DIR", app.instance_path),
        MAX_CONTENT_LENGTH=15 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    data_dir = Path(app.config["DATA_DIR"])
    (data_dir / "photos").mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "gear.db"

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(db_path)
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_):
        d = g.pop("db", None)
        if d:
            d.close()

    with sqlite3.connect(db_path) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            holder TEXT NOT NULL DEFAULT '',
            photo TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)

    # ---------- допоміжне ----------
    def get_settings():
        s = dict(DEFAULTS)
        s.update({r["key"]: r["value"] for r in db().execute("SELECT * FROM settings")})
        return s

    def base_url():
        """Пріоритет: поле в адмінці → змінна BASE_URL → хост запиту."""
        s = get_settings()["base_url"].strip() or app.config["BASE_URL"].strip()
        return (s or request.host_url).rstrip("/")

    def item_url(item_id):
        return f"{base_url()}/i/{item_id}"

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def guard():
        if request.method == "POST":
            if not secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "x")):
                abort(400, "Невірний CSRF-токен")
        if request.path.startswith("/admin") and not session.get("admin"):
            return redirect(url_for("login", next=request.path))

    def save_photo(file):
        if not file or not file.filename:
            return None
        try:
            img = ImageOps.exif_transpose(Image.open(file.stream)).convert("RGB")
        except Exception:
            flash("Не вдалося прочитати зображення")
            return None
        img.thumbnail((1200, 1200))
        name = uuid.uuid4().hex + ".jpg"
        img.save(data_dir / "photos" / name, "JPEG", quality=82)
        return name

    def delete_photo(name):
        if name:
            (data_dir / "photos" / name).unlink(missing_ok=True)

    # ---------- публічне ----------
    @app.get("/")
    def index():
        return redirect(url_for("admin_items") if session.get("admin") else url_for("login"))

    @app.get("/i/<int:item_id>")
    def view_item(item_id):
        item = db().execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not item:
            abort(404)
        return render_template("view.html", item=item)

    @app.get("/photos/<name>")
    def photo(name):
        return send_from_directory(data_dir / "photos", name)

    # ---------- адмінка ----------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if secrets.compare_digest(request.form.get("password", ""), app.config["ADMIN_PASSWORD"]):
                session["admin"] = True
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/admin") else url_for("admin_items"))
            flash("Невірний пароль")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/admin")
    def admin_items():
        items = db().execute("SELECT * FROM items ORDER BY id").fetchall()
        return render_template("items.html", items=items)

    @app.route("/admin/items/new", methods=["GET", "POST"])
    @app.route("/admin/items/<int:item_id>", methods=["GET", "POST"])
    def edit_item(item_id=None):
        item = None
        if item_id:
            item = db().execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if not item:
                abort(404)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            holder = request.form.get("holder", "").strip()
            if not name:
                flash("Назва обов'язкова")
                return render_template("edit.html", item=item, form=request.form)
            new_photo = save_photo(request.files.get("photo"))
            if item:
                photo_name = item["photo"]
                if new_photo or request.form.get("remove_photo"):
                    delete_photo(photo_name)
                    photo_name = new_photo or ""
                db().execute("UPDATE items SET name=?, holder=?, photo=? WHERE id=?",
                             (name, holder, photo_name, item_id))
            else:
                db().execute("INSERT INTO items(name, holder, photo) VALUES (?,?,?)",
                             (name, holder, new_photo or ""))
            db().commit()
            return redirect(url_for("admin_items"))
        return render_template("edit.html", item=item, form=item or {})

    @app.post("/admin/items/<int:item_id>/delete")
    def delete_item(item_id):
        row = db().execute("SELECT photo FROM items WHERE id=?", (item_id,)).fetchone()
        if row:
            delete_photo(row["photo"])
            db().execute("DELETE FROM items WHERE id=?", (item_id,))
            db().commit()
        return redirect(url_for("admin_items"))

    @app.route("/admin/qr", methods=["GET", "POST"])
    def admin_qr():
        if request.method == "POST":
            try:
                qr_mm = float(request.form["qr_mm"].replace(",", "."))
                id_pt = float(request.form["id_pt"].replace(",", "."))
                assert 10 <= qr_mm <= 100 and 6 <= id_pt <= 60
            except Exception:
                flash("Розмір QR: 10–100 мм, шрифт ID: 6–60 pt")
                return redirect(url_for("admin_qr"))
            vals = {"base_url": request.form.get("base_url", "").strip(),
                    "qr_mm": str(qr_mm), "id_pt": str(id_pt),
                    "cut_lines": "1" if request.form.get("cut_lines") else "0"}
            for k, v in vals.items():
                db().execute("INSERT INTO settings VALUES (?,?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
            db().commit()
            flash("Збережено")
            return redirect(url_for("admin_qr"))
        items = db().execute("SELECT id FROM items ORDER BY id").fetchall()
        return render_template("qr.html", s=get_settings(), base=base_url(),
                               example=item_url(items[0]["id"] if items else 1),
                               count=len(items))

    def parse_ids(text, all_ids):
        """'1-5, 8, 12' → [1,2,3,4,5,8,12]; порожньо → всі."""
        text = text.strip()
        if not text:
            return all_ids
        out = set()
        for part in text.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                out.update(range(int(a), int(b) + 1))
            else:
                out.add(int(part))
        known = set(all_ids)
        return sorted(i for i in out if i in known)

    @app.get("/admin/qr.pdf")
    def qr_pdf():
        all_ids = [r["id"] for r in db().execute("SELECT id FROM items ORDER BY id")]
        try:
            ids = parse_ids(request.args.get("ids", ""), all_ids)
        except ValueError:
            abort(400, "Невірний формат ID (приклад: 1-5, 8, 12)")
        if not ids:
            abort(404, "Немає предметів для друку")
        s = get_settings()
        return Response(build_pdf(ids, float(s["qr_mm"]), float(s["id_pt"]),
                                  s["cut_lines"] == "1"),
                        mimetype="application/pdf",
                        headers={"Content-Disposition": "inline; filename=qr-labels.pdf"})

    def build_pdf(ids, qr_mm, id_pt, cut):
        W, H = A4
        margin = 10 * mm
        qr_sz = qr_mm * mm
        gap = 2 * mm
        font = "Helvetica-Bold"
        text_w = max(stringWidth(f"ID {i:04d}", font, id_pt) for i in ids)
        cell_w = qr_sz + gap + text_w + 3 * mm
        cell_h = qr_sz + 2 * mm
        cols = max(1, int((W - 2 * margin) // cell_w))
        rows = max(1, int((H - 2 * margin) // cell_h))
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setTitle("QR labels")
        for n, item_id in enumerate(ids):
            pos = n % (cols * rows)
            if n and pos == 0:
                c.showPage()
            col, row = pos % cols, pos // cols
            x = margin + col * cell_w
            y = H - margin - (row + 1) * cell_h
            if cut:
                c.setStrokeGray(0.6)
                c.setLineWidth(0.3)
                c.setDash(2, 2)
                c.rect(x, y, cell_w, cell_h)
                c.setDash()
            matrix = [list(r) for r in segno.make(item_url(item_id), error="h", micro=False).matrix]
            mod = qr_sz / (len(matrix) + 8)  # тиха зона 4 модулі з кожного боку
            qx, qy = x + 1 * mm, y + 1 * mm
            c.setFillGray(0)
            for r_i, r in enumerate(matrix):
                for c_i, bit in enumerate(r):
                    if bit:
                        c.rect(qx + (c_i + 4) * mod, qy + qr_sz - (r_i + 5) * mod,
                               mod + 0.05, mod + 0.05, stroke=0, fill=1)
            c.setFont(font, id_pt)
            c.drawString(qx + qr_sz + gap, qy + qr_sz / 2 - id_pt * 0.35, f"ID {item_id:04d}")
        c.save()
        return buf.getvalue()

    return app
