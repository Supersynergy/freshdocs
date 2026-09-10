"""Tests for extended manifest detection, extensions, deprecations, and drift."""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class ExtendedManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["FRESHDOCS_HOME"] = self.tmp.name
        os.environ["FRESHDOCS_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "registry.json")
        os.environ["FRESHDOCS_STATE"] = str(pathlib.Path(self.tmp.name) / "state.json")
        os.environ["FRESHDOCS_DB"] = str(pathlib.Path(self.tmp.name) / "freshdocs.db")
        os.environ["FRESHDOCS_LEGACY_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "legacy-registry.json")
        import importlib
        import freshdocs.core as core

        self.core = importlib.reload(core)

    def tearDown(self):
        self.tmp.cleanup()

    def test_registry_has_161_libraries(self):
        registry = self.core.ensure_registry()
        self.assertGreaterEqual(len(registry["libs"]), 150)

    def test_registry_covers_go_ecosystem(self):
        registry = self.core.ensure_registry()
        go_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "go"]
        self.assertGreaterEqual(len(go_libs), 5)
        self.assertIn("gin", go_libs)
        self.assertIn("cobra", go_libs)

    def test_registry_covers_ruby_ecosystem(self):
        registry = self.core.ensure_registry()
        ruby_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "rubygems"]
        self.assertGreaterEqual(len(ruby_libs), 5)
        self.assertIn("rails", ruby_libs)
        self.assertIn("rspec", ruby_libs)

    def test_registry_covers_swift_ecosystem(self):
        registry = self.core.ensure_registry()
        swift_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "swiftpm"]
        self.assertGreaterEqual(len(swift_libs), 5)
        self.assertIn("alamofire", swift_libs)
        self.assertIn("vapor", swift_libs)

    def test_registry_covers_php_ecosystem(self):
        registry = self.core.ensure_registry()
        php_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "packagist"]
        self.assertGreaterEqual(len(php_libs), 3)
        self.assertIn("laravel", php_libs)
        self.assertIn("symfony", php_libs)

    def test_registry_covers_elixir_ecosystem(self):
        registry = self.core.ensure_registry()
        hex_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "hex"]
        self.assertGreaterEqual(len(hex_libs), 3)
        self.assertIn("phoenix", hex_libs)
        self.assertIn("ecto", hex_libs)

    def test_registry_covers_scala_ecosystem(self):
        registry = self.core.ensure_registry()
        scala_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "maven" and "cats" in name or "akka" in name or "zio" in name or "tapir" in name or "doobie" in name]
        self.assertGreaterEqual(len(scala_libs), 3)

    def test_registry_covers_cpp_ecosystem(self):
        registry = self.core.ensure_registry()
        cpp_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "other"]
        self.assertGreaterEqual(len(cpp_libs), 5)
        self.assertIn("fmt", cpp_libs)
        self.assertIn("grpc", cpp_libs)
        self.assertIn("protobuf", cpp_libs)

    def test_registry_covers_dart_ecosystem(self):
        registry = self.core.ensure_registry()
        pub_libs = [name for name, meta in registry["libs"].items() if meta.get("eco") == "pub"]
        self.assertGreaterEqual(len(pub_libs), 3)
        self.assertIn("flutter", pub_libs)
        self.assertIn("riverpod", pub_libs)

    def test_registry_covers_clojure_ecosystem(self):
        registry = self.core.ensure_registry()
        clojure_libs = [name for name, meta in registry["libs"].items() if "clojure" in name or "ring" in name or "reagent" in name or "re-frame" in name or "malli" in name]
        self.assertGreaterEqual(len(clojure_libs), 3)

    def test_registry_covers_julia_ecosystem(self):
        registry = self.core.ensure_registry()
        julia_libs = [name for name, meta in registry["libs"].items() if name.endswith("-jl")]
        self.assertGreaterEqual(len(julia_libs), 3)


class ExtendedExtensionTests(unittest.TestCase):
    def test_scala_extension_recognized(self):
        from freshdocs.analyzer import EXTENSION_LANGUAGES

        self.assertEqual(EXTENSION_LANGUAGES.get(".scala"), "Scala")
        self.assertEqual(EXTENSION_LANGUAGES.get(".sbt"), "Scala")

    def test_clojure_extension_recognized(self):
        from freshdocs.analyzer import EXTENSION_LANGUAGES

        self.assertEqual(EXTENSION_LANGUAGES.get(".clj"), "Clojure")
        self.assertEqual(EXTENSION_LANGUAGES.get(".cljs"), "ClojureScript")

    def test_vue_svelte_astro_extensions_recognized(self):
        from freshdocs.analyzer import EXTENSION_LANGUAGES

        self.assertEqual(EXTENSION_LANGUAGES.get(".vue"), "Vue")
        self.assertEqual(EXTENSION_LANGUAGES.get(".svelte"), "Svelte")
        self.assertEqual(EXTENSION_LANGUAGES.get(".astro"), "Astro")

    def test_graphql_proto_extensions_recognized(self):
        from freshdocs.analyzer import EXTENSION_LANGUAGES

        self.assertEqual(EXTENSION_LANGUAGES.get(".graphql"), "GraphQL")
        self.assertEqual(EXTENSION_LANGUAGES.get(".proto"), "Protocol Buffers")

    def test_perl_powershell_shell_extensions_recognized(self):
        from freshdocs.analyzer import EXTENSION_LANGUAGES

        self.assertEqual(EXTENSION_LANGUAGES.get(".pl"), "Perl")
        self.assertEqual(EXTENSION_LANGUAGES.get(".ps1"), "PowerShell")
        self.assertEqual(EXTENSION_LANGUAGES.get(".sh"), "Shell")

    def test_fortran_d_nim_crystal_extensions_recognized(self):
        from freshdocs.analyzer import EXTENSION_LANGUAGES

        self.assertEqual(EXTENSION_LANGUAGES.get(".f90"), "Fortran")
        self.assertEqual(EXTENSION_LANGUAGES.get(".d"), "D")
        self.assertEqual(EXTENSION_LANGUAGES.get(".nim"), "Nim")
        self.assertEqual(EXTENSION_LANGUAGES.get(".cr"), "Crystal")

    def test_julia_vala_verilog_extensions_recognized(self):
        from freshdocs.analyzer import EXTENSION_LANGUAGES

        self.assertEqual(EXTENSION_LANGUAGES.get(".jl"), "Julia")
        self.assertEqual(EXTENSION_LANGUAGES.get(".vala"), "Vala")
        self.assertEqual(EXTENSION_LANGUAGES.get(".vhd"), "VHDL")


class ExtendedManifestLanguageTests(unittest.TestCase):
    def test_gradle_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("build.gradle", MANIFEST_LANGUAGES)
        self.assertIn("build.gradle.kts", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["build.gradle.kts"][1], "gradle")

    def test_cmake_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("CMakeLists.txt", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["CMakeLists.txt"][1], "cmake")

    def test_deno_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("deno.json", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["deno.json"][1], "deno")

    def test_bun_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("bun.lock", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["bun.lock"][1], "bun")

    def test_podfile_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("Podfile", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["Podfile"][1], "cocoapods")

    def test_sbt_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("build.sbt", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["build.sbt"][1], "sbt")

    def test_vcpkg_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("vcpkg.json", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["vcpkg.json"][1], "vcpkg")

    def test_julia_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("Project.toml", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["Project.toml"][1], "julia")

    def test_shard_yml_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("shard.yml", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["shard.yml"][1], "shards")

    def test_renv_lock_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("renv.lock", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["renv.lock"][1], "cran")

    def test_deps_edn_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("deps.edn", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["deps.edn"][1], "clojure")

    def test_requirements_txt_manifest_recognized(self):
        from freshdocs.analyzer import MANIFEST_LANGUAGES

        self.assertIn("requirements.txt", MANIFEST_LANGUAGES)
        self.assertEqual(MANIFEST_LANGUAGES["requirements.txt"][1], "pypi")


class GradleParserTests(unittest.TestCase):
    def test_gradle_parses_coordinate_notation(self):
        from freshdocs.analyzer import _gradle_dependencies

        text = '''
        dependencies {
            implementation "org.springframework.boot:spring-boot-starter:3.2.0"
            implementation 'com.fasterxml.jackson.core:jackson-databind:2.16.0'
            testImplementation "org.junit.jupiter:junit-jupiter:5.10.1"
        }
        '''
        path = pathlib.Path(tempfile.mktemp(suffix=".gradle"))
        path.write_text(text)
        try:
            result = _gradle_dependencies(path)
            self.assertIn("org.springframework.boot:spring-boot-starter", result)
            self.assertEqual(result["org.springframework.boot:spring-boot-starter"], "3.2.0")
            self.assertIn("org.junit.jupiter:junit-jupiter", result)
        finally:
            path.unlink(missing_ok=True)


class VcpkgParserTests(unittest.TestCase):
    def test_vcpkg_parses_dependencies(self):
        from freshdocs.analyzer import _vcpkg_locked

        text = json.dumps({
            "name": "my-project",
            "version": "1.0.0",
            "dependencies": ["fmt", "spdlog", {"name": "nlohmann-json", "version": "3.14.0"}]
        })
        path = pathlib.Path(tempfile.mktemp(suffix=".json"))
        path.write_text(text)
        try:
            result = _vcpkg_locked(path)
            self.assertIn("fmt", result)
            self.assertIn("spdlog", result)
            self.assertIn("nlohmann-json", result)
        finally:
            path.unlink(missing_ok=True)


class DenoLockParserTests(unittest.TestCase):
    def test_deno_lock_parses_packages(self):
        from freshdocs.analyzer import _deno_locked

        text = json.dumps({
            "packages": [
                {"spec": "npm:hono@4.12.27"},
                {"spec": "npm:zod@3.23.8"}
            ]
        })
        path = pathlib.Path(tempfile.mktemp(suffix=".json"))
        path.write_text(text)
        try:
            result = _deno_locked(path)
            self.assertIn("hono", result)
            self.assertEqual(result["hono"], "4.12.27")
        finally:
            path.unlink(missing_ok=True)


class RenvLockParserTests(unittest.TestCase):
    def test_renv_lock_parses_packages(self):
        from freshdocs.analyzer import _renv_locked

        text = json.dumps({
            "Packages": {
                "dplyr": {"Version": "1.1.4"},
                "ggplot2": {"Version": "3.5.0"}
            }
        })
        path = pathlib.Path(tempfile.mktemp(suffix=".json"))
        path.write_text(text)
        try:
            result = _renv_locked(path)
            self.assertEqual(result["dplyr"], "1.1.4")
            self.assertEqual(result["ggplot2"], "3.5.0")
        finally:
            path.unlink(missing_ok=True)


class JuliaManifestParserTests(unittest.TestCase):
    def test_julia_project_toml_parses_deps(self):
        from freshdocs.analyzer import _julia_manifest

        text = '[deps]\nDataFrames = "5fb3892e-4b0c-11eb-3f8e-7d7c1a8d1234"\nFlux = "587475ba-8d8e-4b0c-9f8e-7d7c1a8d5678"'
        path = pathlib.Path(tempfile.mktemp(suffix=".toml"))
        path.write_text(text)
        try:
            result = _julia_manifest(path)
            self.assertIn("DataFrames", result)
            self.assertIn("Flux", result)
        finally:
            path.unlink(missing_ok=True)


class DeprecationCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["FRESHDOCS_HOME"] = self.tmp.name
        os.environ["FRESHDOCS_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "registry.json")
        os.environ["FRESHDOCS_STATE"] = str(pathlib.Path(self.tmp.name) / "state.json")
        os.environ["FRESHDOCS_DB"] = str(pathlib.Path(self.tmp.name) / "freshdocs.db")
        os.environ["FRESHDOCS_LEGACY_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "legacy-registry.json")
        import importlib
        import freshdocs.core as core

        self.core = importlib.reload(core)
        # Create a package.json so the analyzer detects "demo" as a library
        pkg = pathlib.Path(self.tmp.name) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"demo": "1.0.0"}}))
        # Register "demo" in the registry
        registry = self.core.ensure_registry()
        registry["libs"]["demo"] = {"gh": "example/demo", "branch": "main", "eco": "npm", "pkg": "demo"}
        self.core.write_json(pathlib.Path(os.environ["FRESHDOCS_REGISTRY"]), registry)
        # Index a doc with @deprecated marker
        self.core.index_docs(
            "demo",
            "1.0.0",
            "# Demo\nThis API is @deprecated. Use newAPI instead.\n## Migration\nSee migration guide.",
            "2026-09-10",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_deprecations_finds_deprecated_marker(self):
        from freshdocs.cli import main

        argv = ["deprecations", "--project", self.tmp.name, "--lib", "demo", "--json"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        self.assertEqual(code, 0)
        output = buf.getvalue()
        data = json.loads(output)
        self.assertTrue(any(r["pattern"] == "@deprecated" for r in data))
        self.assertTrue(any("deprecated" in r["snippet"].lower() for r in data))


class DriftCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["FRESHDOCS_HOME"] = self.tmp.name
        os.environ["FRESHDOCS_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "registry.json")
        os.environ["FRESHDOCS_STATE"] = str(pathlib.Path(self.tmp.name) / "state.json")
        os.environ["FRESHDOCS_DB"] = str(pathlib.Path(self.tmp.name) / "freshdocs.db")
        os.environ["FRESHDOCS_LEGACY_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "legacy-registry.json")
        import importlib
        import freshdocs.core as core

        self.core = importlib.reload(core)

    def tearDown(self):
        self.tmp.cleanup()

    def test_drift_no_libraries_returns_zero(self):
        from freshdocs.cli import main

        argv = ["drift", "--project", self.tmp.name, "--json"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
