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
        self.assertNotIn("LLM_API_KEY=", text)

    def test_railway_healthcheck_matches_api(self):
        import json

        config = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        self.assertEqual(config["deploy"]["healthcheckPath"], "/api/health")


if __name__ == "__main__":
    unittest.main()
