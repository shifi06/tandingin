"""Tes end-to-end untuk US-01..US-06.  Jalankan: python -m unittest discover -s tests -v"""
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import utcnow_naive  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "AUTO_INIT_DB": False,
            "SECRET_KEY": "test-secret-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.tmp.name}/t.db",
            "UPLOAD_FOLDER": os.path.join(self.tmp.name, "up"),
            "STORAGE_BACKEND": "local",
            "ADMIN_EMAIL": "admin@t.id", "ADMIN_PASSWORD": "adminadmin",
        })
        from models import db
        from app import bootstrap_data
        os.makedirs(self.app.config["UPLOAD_FOLDER"], exist_ok=True)
        with self.app.app_context():
            db.create_all()
            bootstrap_data(self.app)

    def tearDown(self):
        with self.app.app_context():
            from models import db
            db.session.remove()
            db.engine.dispose()
        self.tmp.cleanup()

    def client(self, email=None, pw=None):
        c = self.app.test_client()
        if email:
            r = c.post("/api/auth/login", json={"email": email, "password": pw})
            self.assertEqual(r.status_code, 200, r.json)
        return c

    def test_full_flow(self):
        admin = self.client("admin@t.id", "adminadmin")

        # US-01: admin membuat panitia; kapten daftar mandiri
        r = admin.post("/api/auth/register", json={"nama": "Panitia", "email": "p@t.id",
                                                   "password": "password1", "role": "panitia"})
        self.assertEqual(r.status_code, 201)
        panitia2 = admin.post("/api/auth/register", json={"nama": "P2", "email": "p2@t.id",
                                                          "password": "password1", "role": "panitia"})
        self.assertEqual(panitia2.status_code, 201)
        anon = self.app.test_client()
        for i in (1, 2, 3):
            r = anon.post("/api/auth/register", json={"nama": f"K{i}", "email": f"k{i}@t.id",
                                                      "password": "password1", "role": "super_admin"})
            self.assertEqual(r.json["role"], "kapten")  # role dari publik diabaikan
        self.assertEqual(anon.get("/api/users").status_code, 401)

        p, p2 = self.client("p@t.id", "password1"), self.client("p2@t.id", "password1")
        k1, k2, k3 = (self.client(f"k{i}@t.id", "password1") for i in (1, 2, 3))

        # US-02: hanya panitia yang boleh membuat turnamen
        self.assertEqual(k1.post("/api/turnamen", json={"nama_turnamen": "X", "tanggal_mulai": "2026-12-01"}).status_code, 403)
        r = p.post("/api/turnamen", json={"nama_turnamen": "Cup", "tanggal_mulai": "2026-12-01"})
        self.assertEqual(r.status_code, 201)
        tid = r.json["id_turnamen"]
        # Public visitors may browse the tournament catalog and room details.
        self.assertEqual(anon.get("/api/turnamen").status_code, 200)
        self.assertEqual(anon.get(f"/api/turnamen/{tid}").status_code, 200)
        self.assertEqual(anon.get(f"/api/turnamen/{tid}/peserta").json, [])

        # US-03: kapten membuat tim + mendaftar turnamen
        tims = []
        for name, c in (("Alpha", k1), ("Beta", k2), ("Gamma", k3)):
            r = c.post("/api/tim", data={"nama_tim": name, "id_turnamen": str(tid)})
            self.assertEqual(r.status_code, 201, r.json)
            tims.append(r.json["id_tim"])
        self.assertEqual(k1.post("/api/tim", data={"nama_tim": "Lagi"}).status_code, 409)  # 1 kapten = 1 tim
        self.assertEqual(k1.post(f"/api/turnamen/{tid}/daftar").status_code, 409)  # daftar ganda
        self.assertEqual(len(k1.get(f"/api/tim?turnamen_id={tid}").json), 3)
        self.assertEqual(len(anon.get(f"/api/tim?turnamen_id={tid}").json), 3)
        self.assertEqual(len(anon.get(f"/api/turnamen/{tid}/peserta").json), 3)

        # US-04: jadwal; validasi aturan
        jd = {"id_turnamen": tid, "id_tim_a": tims[0], "id_tim_b": tims[1], "jadwal_main": "2026-12-01T10:00"}
        self.assertEqual(p2.post("/api/jadwal", json=jd).status_code, 403)  # bukan pemilik turnamen
        self.assertEqual(p.post("/api/jadwal", json={**jd, "id_tim_b": tims[0]}).status_code, 400)
        r = p.post("/api/jadwal", json=jd)
        self.assertEqual(r.status_code, 201)
        jid = r.json["id_jadwal"]
        self.assertEqual(r.json["status_match"], "Menunggu")
        self.assertEqual(anon.get("/api/jadwal").status_code, 200)
        self.assertEqual(len(anon.get(f"/api/jadwal?turnamen_id={tid}").json), 1)
        self.assertEqual(p.post("/api/jadwal", json={**jd, "id_tim_b": tims[2]}).status_code, 409)  # bentrok

        # US-05: hanya kapten yang bertanding yang boleh unggah; hanya gambar
        up = lambda: {"foto": (io.BytesIO(PNG), "bukti.png")}
        self.assertEqual(k3.post(f"/api/jadwal/{jid}/hasil", data=up()).status_code, 403)
        bad = {"foto": (io.BytesIO(b"bukan gambar"), "x.png")}
        self.assertEqual(k1.post(f"/api/jadwal/{jid}/hasil", data=bad).status_code, 400)
        r = k1.post(f"/api/jadwal/{jid}/hasil", data=up())
        self.assertEqual(r.status_code, 201, r.json)
        hid = r.json["id_hasil"]
        self.assertEqual(r.json["id_pemenang"], tims[0])
        pending_public = anon.get("/api/jadwal").json[0]
        self.assertIsNone(pending_public["hasil"])  # pending winner is not an official public result
        self.assertNotIn("foto_bukti_url", pending_public)
        self.assertEqual(k1.get("/api/jadwal").json[0]["status_match"], "Diproses")
        self.assertEqual(k2.post(f"/api/jadwal/{jid}/hasil", data=up()).status_code, 409)  # sedang diproses
        self.assertEqual(k1.get(r.json["foto_bukti_url"]).status_code, 200)
        self.assertEqual(k2.get(r.json["foto_bukti_url"]).status_code, 200)  # opposing captain may verify evidence
        self.assertEqual(k3.get(r.json["foto_bukti_url"]).status_code, 403)  # unrelated captain
        self.assertEqual(p.get(r.json["foto_bukti_url"]).status_code, 200)  # tournament owner
        self.assertEqual(p2.get(r.json["foto_bukti_url"]).status_code, 403)  # other organizer
        self.assertEqual(anon.get(r.json["foto_bukti_url"]).status_code, 403)  # evidence stays private

        # US-06: validasi; panitia lain tidak boleh; tolak -> unggah ulang -> setuju
        self.assertEqual(p2.patch(f"/api/hasil/{hid}/validasi", json={"keputusan": "setuju"}).status_code, 403)
        self.assertEqual(len(p.get("/api/hasil?status=Menunggu").json), 1)
        self.assertEqual(len(p2.get("/api/hasil").json), 0)  # isolasi data antar turnamen
        r = p.patch(f"/api/hasil/{hid}/validasi", json={"keputusan": "tolak", "catatan": "Buram"})
        self.assertEqual(r.json["status_validasi"], "Ditolak")
        self.assertEqual(k1.get("/api/jadwal").json[0]["status_match"], "Menunggu")
        self.assertTrue(k2.get("/api/jadwal").json[0]["bisa_unggah"])
        r = k2.post(f"/api/jadwal/{jid}/hasil", data=up())
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json["id_pemenang"], tims[1])
        r = p.patch(f"/api/hasil/{hid}/validasi", json={"keputusan": "setuju"})
        self.assertEqual(r.json["status_validasi"], "Disetujui")
        j = p.get("/api/jadwal").json[0]
        self.assertEqual(j["status_match"], "Selesai")
        public_result = anon.get(f"/api/jadwal?turnamen_id={tid}").json[0]["hasil"]
        self.assertEqual(public_result["nama_pemenang"], "Beta")
        self.assertEqual(public_result["status_validasi"], "Disetujui")
        self.assertNotIn("foto_bukti_url", public_result)
        self.assertEqual(anon.get(r.json["foto_bukti_url"]).status_code, 403)
        self.assertEqual(p.patch(f"/api/hasil/{hid}/validasi", json={"keputusan": "tolak"}).status_code, 409)


    def test_upload_size_and_extension_validation(self):
        admin = self.client("admin@t.id", "adminadmin")
        admin.post("/api/auth/register", json={"nama": "Organizer", "email": "o@t.id", "password": "password1", "role": "panitia"})
        organizer = self.client("o@t.id", "password1")
        turnamen = organizer.post("/api/turnamen", json={"nama_turnamen": "Limit Cup", "tanggal_mulai": "2026-12-01"}).json
        captain = self.app.test_client()
        captain.post("/api/auth/register", json={"nama": "Captain", "email": "captain@t.id", "password": "password1"})
        captain.post("/api/auth/login", json={"email": "captain@t.id", "password": "password1"})
        self.assertEqual(captain.post("/api/tim", data={"nama_tim": "Limit Team", "id_turnamen": str(turnamen["id_turnamen"])}).status_code, 201)

        # Unsupported extension is rejected before storage is called.
        bad_ext = {"logo": (io.BytesIO(PNG), "logo.gif")}
        self.assertEqual(captain.put("/api/tim/saya", data=bad_ext).status_code, 400)

        # 4 MB + 1 byte is rejected by the app-level limit when it reaches Flask.
        too_large = {"logo": (io.BytesIO(PNG[:8] + b"x" * (4 * 1024 * 1024)), "large.png")}
        self.assertEqual(captain.put("/api/tim/saya", data=too_large).status_code, 413)

    def test_timestamp_factory_returns_utc_naive_value(self):
        before = datetime.now(timezone.utc)
        value = utcnow_naive()
        after = datetime.now(timezone.utc)
        self.assertIsNone(value.tzinfo)
        self.assertLessEqual(before, value.replace(tzinfo=timezone.utc))
        self.assertLessEqual(value.replace(tzinfo=timezone.utc), after)

    def test_security_headers(self):
        response = self.app.test_client().get("/")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
            self.assertIn("frame-ancestors 'none'", response.headers.get("Content-Security-Policy", ""))
            self.assertIn("connect-src 'self'", response.headers.get("Content-Security-Policy", ""))
            # The index route returns a file-backed response. Consume and close it
            # explicitly so Werkzeug's underlying file descriptor is not leaked.
            response.get_data()
        finally:
            response.close()

    def test_auth_rules(self):
        c = self.app.test_client()
        self.assertEqual(c.post("/api/auth/login", json={"email": "admin@t.id", "password": "salah"}).status_code, 401)
        r = c.post("/api/auth/register", json={"nama": "A", "email": "a@t.id", "password": "pendek"})
        self.assertEqual(r.status_code, 400)
        admin = self.client("admin@t.id", "adminadmin")
        self.assertEqual(admin.patch("/api/users/1/role", json={"role": "kapten"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
