"""Unit tests for CapyPunk Studio with a fake HarnessRouter (no network, no key)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("HR_API_KEY", "sk-hr-test")
os.environ["STUDIO_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")

from fastapi.testclient import TestClient  # noqa: E402

import app as studio  # noqa: E402

MANIFEST = {"title": "Haiku Espresso", "entry": "index.html", "pages": ["index.html"],
            "files": ["index.html", "story.json", "manifest.json"], "summary": "A barista capybara and a poet machine.",
            "verified": True}


class FakeHR:
    def __init__(self):
        self.started, self.polls = [], 0

    def start_task(self, **kw):
        self.started.append(kw)
        return {"id": f"resp_{len(self.started)}", "status": "in_progress", "metadata": {"session_id": "hsess1"}}

    def get_response(self, rid):
        self.polls += 1
        return {"id": rid, "status": "completed", "metadata": {"session_id": "hsess1"},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "Your skit is ready."}]}]}

    def session_files(self, sid):
        return [{"id": "f1", "path": "story/index.html", "bytes": 10}, {"id": "f2", "path": "story/manifest.json", "bytes": 10},
                {"id": "f3", "path": "story/story.json", "bytes": 10}, {"id": "f4", "path": "notes.txt", "bytes": 1}]

    def file_bytes(self, sid, fid):
        return {"f1": b"<h1>play</h1>", "f2": json.dumps(MANIFEST).encode(), "f3": b"{}"}[fid], "application/octet-stream"


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHR()
        studio._hr = self.fake
        self.a, self.b = TestClient(studio.app), TestClient(studio.app)
        self.a.get("/"); self.b.get("/")

    def test_task_flow_sends_server_side_harness_and_user(self):
        t = self.a.post("/api/tasks", json={"prompt": "A capybara barista and a haiku espresso machine."}).json()
        sent = self.fake.started[0]
        self.assertEqual(sent["harness_id"], studio.CONF["harness_id"])
        self.assertEqual(sent["user"], self.a.cookies.get("cp_uid"))
        d = self.a.get(f"/api/tasks/{t['id']}").json()
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["title"], "Haiku Espresso")
        self.assertEqual([f["path"] for f in d["files"]], ["index.html", "manifest.json", "story.json"])
        self.assertNotIn("harness", json.dumps(d).lower().replace("harnessrouter", ""))
        page = self.a.get(d["preview"])
        self.assertEqual(page.status_code, 200)
        self.assertIn("sandbox", page.headers["content-security-policy"])
        dl = self.a.get(f"/api/tasks/{t['id']}/files/story.json")
        self.assertEqual(dl.status_code, 200)
        self.assertIn("attachment", dl.headers["content-disposition"])

    def test_other_visitor_is_denied(self):
        t = self.a.post("/api/tasks", json={"prompt": "A capybara detective in the rain."}).json()
        self.assertEqual(self.b.get(f"/api/tasks/{t['id']}").status_code, 404)
        self.assertEqual(self.b.get(f"/api/tasks/{t['id']}/files/story.json").status_code, 404)
        self.assertEqual(self.b.post(f"/api/tasks/{t['id']}/followup", json={"prompt": "darker"}).status_code, 404)
        self.assertEqual(self.b.get("/api/tasks").json()["tasks"], [])

    def test_follow_up_continues_the_same_session(self):
        t = self.a.post("/api/tasks", json={"prompt": "A capybara astronaut."}).json()
        self.a.get(f"/api/tasks/{t['id']}")
        studio_row_reset = self.a.post(f"/api/tasks/{t['id']}/followup", json={"prompt": "Make it funnier."})
        self.assertEqual(studio_row_reset.status_code, 200)
        sent = self.fake.started[-1]
        self.assertEqual(sent["previous_response_id"], "resp_1")
        self.assertEqual(sent["session_id"], "hsess1")
        self.assertEqual(sent["harness_id"], studio.CONF["harness_id"])

    def test_preview_signature_and_paths(self):
        tok = studio.sign_preview("abc")
        self.assertEqual(studio.verify_preview(tok), "abc")
        self.assertIsNone(studio.verify_preview(tok[:-1] + ("0" if tok[-1] != "0" else "1")))
        self.assertIsNone(studio.verify_preview(studio.sign_preview("abc", ttl=-5)))
        for bad in ("../x", "/etc/passwd", "a/../../x", "a\\b", ""):
            self.assertIsNone(studio.safe_path(bad), bad)
        self.assertEqual(studio.safe_path("css/app.css"), "css/app.css")
        self.assertEqual(self.a.get("/preview/nope.1.2/index.html").status_code, 404)

    def test_role_mismatch_is_a_polite_state(self):
        self.fake.get_response = lambda rid: {"id": rid, "status": "completed", "metadata": {"session_id": "hsess1"},
                                              "output": [{"type": "message", "content": [{"type": "output_text",
                                                          "text": "role_mismatch\nI write skits."}]}]}
        t = self.a.post("/api/tasks", json={"prompt": "Build me a todo app."}).json()
        self.assertEqual(self.a.get(f"/api/tasks/{t['id']}").json()["status"], "role_mismatch")


if __name__ == "__main__":
    unittest.main()
