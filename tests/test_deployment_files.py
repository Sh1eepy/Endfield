# -*- coding: utf-8 -*-
"""部署配置的安全与完整性静态测试。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeploymentFileTests(unittest.TestCase):
    def test_dockerignore_excludes_secrets_and_local_chroma(self):
        text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn(".env\n", text)
        self.assertIn("output/rag/chroma", text)

    def test_dockerfile_builds_index_offline_and_uses_port(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        starter = (ROOT / "scripts" / "start_server.py").read_text(encoding="utf-8")
        self.assertIn("HF_HUB_OFFLINE=1", text)
        self.assertIn("build_rag.py", text)
        self.assertIn("download.pytorch.org/whl/cpu", text)
        self.assertIn("torch==2.13.0+cpu", text)
        self.assertIn("python scripts/start_server.py", text)
        self.assertIn('os.environ.get("PORT")', starter)
        self.assertIn('os.environ.get("WEB_CONCURRENCY")', starter)
        self.assertIn('os.environ.get("WEB_CONCURRENCY") or "1"', starter)
        self.assertNotIn("LLM_API_KEY=", text)

    def test_railway_healthcheck_matches_api(self):
        import json

        config = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        self.assertEqual(config["deploy"]["healthcheckPath"], "/api/health")

    def test_compose_keeps_app_private_and_bounded(self):
        text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:8000:8000"', text)
        self.assertIn("WEB_CONCURRENCY: ${WEB_CONCURRENCY:-1}", text)
        self.assertIn("ASK_MAX_CONCURRENCY: ${ASK_MAX_CONCURRENCY:-2}", text)
        self.assertIn("restart: unless-stopped", text)
        self.assertIn("max-size: \"10m\"", text)
        self.assertNotIn('"0.0.0.0:8000:8000"', text)

    def test_nginx_limits_paid_ask_route(self):
        text = (ROOT / "deploy" / "nginx" / "endfield.conf").read_text(encoding="utf-8")
        self.assertIn("location = /api/ask", text)
        self.assertIn("limit_req zone=endfield_ask_rate", text)
        self.assertIn("limit_conn endfield_ask_conn 1", text)
        self.assertIn("limit_req_status 429", text)
        self.assertIn('return 429 \'{"ok":false', text)
        self.assertIn("health/deep|metrics", text)
        self.assertIn("allow 127.0.0.1", text)
        self.assertIn("proxy_pass http://127.0.0.1:8000", text)

    def test_public_env_template_uses_safe_concurrency_defaults(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("WEB_CONCURRENCY=1", text)
        self.assertIn("ASK_MAX_CONCURRENCY=2", text)


if __name__ == "__main__":
    unittest.main()
