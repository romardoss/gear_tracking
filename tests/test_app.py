import io

import pytest
from PIL import Image

from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "ADMIN_PASSWORD": "pw"})
    return app.test_client()


def tok(c, url="/login"):
    c.get(url)
    with c.session_transaction() as s:
        return s["csrf"]


def login(c):
    c.post("/login", data={"csrf": tok(c), "password": "pw"})


def test_admin_requires_login(client):
    assert client.get("/admin").status_code == 302
    assert client.get("/admin/qr.pdf").status_code == 302


def test_full_flow(client):
    login(client)
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1000), "red").save(buf, "PNG")
    buf.seek(0)
    r = client.post("/admin/items/new", data={
        "csrf": tok(client, "/admin"), "name": "Намет", "holder": "Іван Петренко",
        "photo": (buf, "a.png")})
    assert r.status_code == 302
    page = client.get("/i/1").get_data(as_text=True)
    assert "Намет" in page and "Іван Петренко" in page and "/photos/" in page
    client.post("/admin/qr", data={"csrf": tok(client, "/admin/qr"), "qr_mm": "25",
                                   "id_pt": "12", "base_url": "https://x.test/"})
    assert "https://x.test/i/1" in client.get("/admin/qr").get_data(as_text=True)
    pdf = client.get("/admin/qr.pdf?ids=1-3")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_public_404_and_auto_base(client):
    assert client.get("/i/99").status_code == 404
    login(client)
    assert "http://localhost/i/1" in client.get("/admin/qr").get_data(as_text=True)


def test_csrf_enforced(client):
    assert client.post("/login", data={"password": "pw"}).status_code == 400
