import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from freshdocs.identity import (
    detect_model,
    model_from_commands,
    model_from_environment,
    model_from_host_config,
    model_from_metadata,
)


class ModelIdentityTests(unittest.TestCase):
    def test_explicit_identity_wins(self):
        found = detect_model("openai/gpt-5.6-sol", {"model": "other"}, {"OPENAI_MODEL": "third"}, [])
        self.assertEqual((found.model, found.source), ("openai/gpt-5.6-sol", "explicit"))

    def test_hook_metadata_alias_is_automatic(self):
        for key in ("model", "model_id", "modelId", "model_name", "modelName"):
            with self.subTest(key=key):
                found = model_from_metadata({key: "claude-fable-5-1"})
                self.assertEqual(found.model, "claude-fable-5-1")
                self.assertTrue(found.source.startswith("metadata:"))

    def test_mcp_experimental_metadata_is_automatic(self):
        found = model_from_metadata({
            "capabilities": {"experimental": {"freshdocs": {"model": "openai/gpt-5.6-sol"}}}
        })
        self.assertEqual(found.model, "openai/gpt-5.6-sol")

    def test_provider_environment_is_automatic(self):
        found = model_from_environment({"OPENAI_MODEL": "gpt-5.6-sol"})
        self.assertEqual((found.model, found.source), ("gpt-5.6-sol", "env:OPENAI_MODEL"))

    def test_same_model_in_two_environment_variables_is_not_ambiguous(self):
        found = model_from_environment({"OPENAI_MODEL": "gpt-5.6-sol", "LLM_MODEL": "gpt-5.6-sol"})
        self.assertEqual(found.model, "gpt-5.6-sol")

    def test_conflicting_provider_environment_fails_safe(self):
        found = model_from_environment({"OPENAI_MODEL": "gpt-5", "ANTHROPIC_MODEL": "claude-5"})
        self.assertIsNone(found.model)
        self.assertEqual(found.source, "ambiguous-environment")

    def test_conflicting_metadata_and_environment_fail_safe(self):
        found = detect_model(None, {"model": "claude-5"}, {"OPENAI_MODEL": "gpt-5"}, [])
        self.assertIsNone(found.model)
        self.assertEqual(found.source, "ambiguous-runtime")

    def test_provider_qualified_and_bare_evidence_agree(self):
        found = detect_model(None, {"model": "openai/gpt-5.6-sol"}, {"OPENAI_MODEL": "gpt-5.6-sol"}, [])
        self.assertEqual(found.model, "openai/gpt-5.6-sol")

    def test_generic_model_environment_is_ignored(self):
        self.assertIsNone(model_from_environment({"MODEL": "/tmp/embedding.bin"}).model)

    def test_known_agent_model_argument_is_detected(self):
        found = model_from_commands(["node /opt/codex --model openai/gpt-5.6-sol run"])
        self.assertEqual((found.model, found.source), ("openai/gpt-5.6-sol", "process-argv:0"))

    def test_unrelated_process_model_argument_is_ignored(self):
        self.assertIsNone(model_from_commands(["python train.py --model embedding-v2"]).model)

    def test_codex_parent_uses_its_own_config_when_argv_omits_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / ".codex" / "config.toml"
            path.parent.mkdir()
            path.write_text('model = "gpt-5.6-sol"\n')
            found = model_from_host_config(["/usr/local/bin/codex exec"], pathlib.Path(tmp))
        self.assertEqual((found.model, found.source), ("gpt-5.6-sol", "host-config:codex"))

    def test_unrelated_parent_never_reads_available_agent_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / ".codex" / "config.toml"
            path.parent.mkdir()
            path.write_text('model = "gpt-5.6-sol"\n')
            found = model_from_host_config(["python app.py"], pathlib.Path(tmp))
        self.assertIsNone(found.model)

    def test_invalid_identity_fails_safe(self):
        self.assertIsNone(model_from_metadata({"model": "../../secret\nvalue"}).model)

    def test_hook_forwards_model_metadata_without_a_cli_flag(self):
        import freshdocs.cli as cli

        payload = {"prompt": "use current API", "cwd": "/tmp", "modelId": "openai/gpt-5.6-sol"}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            with mock.patch.object(cli, "routed_context", return_value="") as routed:
                self.assertEqual(cli.main(["hook", "--client", "raw"]), 0)
        self.assertEqual(routed.call_args.kwargs["metadata"]["modelId"], "openai/gpt-5.6-sol")

    def test_mcp_session_identity_is_reused_without_repeating_model(self):
        import freshdocs.mcp as mcp

        with mock.patch.object(
            mcp, "model_cutoff", return_value=("openai/gpt-5.6-sol", "measured:x", "2025-08-16")
        ):
            result = mcp.call_tool("freshdocs_identity", {}, session_model="openai/gpt-5.6-sol")
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["model"], "openai/gpt-5.6-sol")
        self.assertEqual(payload["detection_source"], "mcp-session")
        self.assertEqual(payload["mode"], "gap-aware")

    def test_mcp_conflict_override_forces_safe_full_even_with_tool_model(self):
        import freshdocs.mcp as mcp
        from freshdocs.identity import ModelIdentity

        forced = ModelIdentity(None, "ambiguous-mcp-session", "conflicting identity evidence")
        result = mcp.call_tool(
            "freshdocs_identity",
            {"model": "claude-fable-5-1"},
            session_model="openai/gpt-5.6-sol",
            identity_override=forced,
        )
        payload = json.loads(result["content"][0]["text"])
        self.assertIsNone(payload["model"])
        self.assertEqual(payload["mode"], "safe-full")

if __name__ == "__main__":
    unittest.main()
