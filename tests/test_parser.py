"""Tests for the Tree-sitter parser module."""

import tempfile
from pathlib import Path

from code_review_graph.parser import CodeParser

FIXTURES = Path(__file__).parent / "fixtures"


class TestCodeParser:
    def setup_method(self):
        self.parser = CodeParser()

    def test_detect_language_python(self):
        assert self.parser.detect_language(Path("foo.py")) == "python"

    def test_detect_language_typescript(self):
        assert self.parser.detect_language(Path("foo.ts")) == "typescript"

    def test_detect_language_unknown(self):
        assert self.parser.detect_language(Path("foo.txt")) is None

    # --- Shebang detection for extension-less Unix scripts (#237) ---

    def _write_shebang_file(self, tmp_path: Path, name: str, content: str) -> Path:
        """Helper: write an extension-less file with ``content`` and return its path."""
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_detect_shebang_bin_bash(self, tmp_path):
        p = self._write_shebang_file(
            tmp_path, "deploy", "#!/bin/bash\nfoo() { echo hi; }\n",
        )
        assert self.parser.detect_language(p) == "bash"

    def test_detect_shebang_bin_sh_routed_to_bash(self, tmp_path):
        """/bin/sh scripts are parsed through the bash grammar."""
        p = self._write_shebang_file(
            tmp_path, "install-hook", "#!/bin/sh\necho hello\n",
        )
        assert self.parser.detect_language(p) == "bash"

    def test_detect_shebang_env_bash(self, tmp_path):
        p = self._write_shebang_file(
            tmp_path, "runner", "#!/usr/bin/env bash\nfoo() { echo hi; }\n",
        )
        assert self.parser.detect_language(p) == "bash"

    def test_detect_shebang_env_python3(self, tmp_path):
        p = self._write_shebang_file(
            tmp_path, "myapp",
            "#!/usr/bin/env python3\ndef main():\n    pass\n",
        )
        assert self.parser.detect_language(p) == "python"

    def test_detect_shebang_direct_python(self, tmp_path):
        p = self._write_shebang_file(
            tmp_path, "tool", "#!/usr/bin/python3\nprint('hi')\n",
        )
        assert self.parser.detect_language(p) == "python"

    def test_detect_shebang_node(self, tmp_path):
        p = self._write_shebang_file(
            tmp_path, "cli", "#!/usr/bin/env node\nconsole.log(1);\n",
        )
        assert self.parser.detect_language(p) == "javascript"

    def test_detect_shebang_env_dash_s_flag(self, tmp_path):
        """``#!/usr/bin/env -S node --flag`` (Linux -S) resolves to the interpreter."""
        p = self._write_shebang_file(
            tmp_path, "esm-tool",
            "#!/usr/bin/env -S node --experimental-vm-modules\n"
            "console.log('esm');\n",
        )
        assert self.parser.detect_language(p) == "javascript"

    def test_detect_shebang_ruby(self, tmp_path):
        p = self._write_shebang_file(
            tmp_path, "rake-task", "#!/usr/bin/env ruby\nputs 1\n",
        )
        assert self.parser.detect_language(p) == "ruby"

    def test_detect_shebang_perl(self, tmp_path):
        p = self._write_shebang_file(
            tmp_path, "cgi-script", "#!/usr/bin/env perl\nprint 1;\n",
        )
        assert self.parser.detect_language(p) == "perl"

    def test_detect_shebang_with_trailing_flags(self, tmp_path):
        """``#!/bin/bash -e`` still maps to bash (flags ignored)."""
        p = self._write_shebang_file(
            tmp_path, "strict", "#!/bin/bash -e\nfoo() { echo hi; }\n",
        )
        assert self.parser.detect_language(p) == "bash"

    def test_detect_shebang_missing_returns_none(self, tmp_path):
        """Extension-less text files without a shebang return None, not bash."""
        p = self._write_shebang_file(
            tmp_path, "README", "# just a readme, no shebang\nsome content\n",
        )
        assert self.parser.detect_language(p) is None

    def test_detect_shebang_empty_file_returns_none(self, tmp_path):
        p = tmp_path / "EMPTY"
        p.write_bytes(b"")
        assert self.parser.detect_language(p) is None

    def test_detect_shebang_binary_content_returns_none(self, tmp_path):
        """A garbage-byte first line that happens not to start with ``#!``
        must not raise and must return None."""
        p = tmp_path / "binary-blob"
        p.write_bytes(b"\x00\x01\x02\x03 garbage bytes not a shebang\n")
        assert self.parser.detect_language(p) is None

    def test_detect_shebang_unknown_interpreter_returns_none(self, tmp_path):
        """A valid shebang to an interpreter we don't route is treated as
        'unknown language' — same as an unmapped extension."""
        p = self._write_shebang_file(
            tmp_path, "ocaml-script", "#!/usr/bin/env ocaml\nlet x = 1\n",
        )
        assert self.parser.detect_language(p) is None

    def test_detect_shebang_does_not_override_extension(self, tmp_path):
        """A file with a known extension must still use extension-based
        detection, even if its first line is a misleading shebang."""
        p = tmp_path / "script.py"
        p.write_text("#!/bin/bash\nprint('hi')\n", encoding="utf-8")
        # .py wins over the bash shebang — non-intuitive-looking content
        # in a .py file must not fool the detector.
        assert self.parser.detect_language(p) == "python"

    def test_parse_shebang_script_produces_function_nodes(self, tmp_path):
        """End-to-end regression: an extension-less bash script is not only
        detected but also fully parsed into structural nodes via parse_file.
        """
        script = (
            "#!/usr/bin/env bash\n"
            "greet() {\n"
            '    echo "hi $1"\n'
            "}\n"
            "main() {\n"
            "    greet world\n"
            "}\n"
            "main\n"
        )
        p = self._write_shebang_file(tmp_path, "deploy", script)

        nodes, edges = self.parser.parse_file(p)

        # We at least got the File node plus both functions.
        assert len(nodes) >= 3
        funcs = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in funcs}
        assert "greet" in func_names
        assert "main" in func_names
        for n in nodes:
            assert n.language == "bash"

    def test_parse_python_file(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")

        # Should have File node
        file_nodes = [n for n in nodes if n.kind == "File"]
        assert len(file_nodes) == 1

        # Should find classes
        classes = [n for n in nodes if n.kind == "Class"]
        class_names = {c.name for c in classes}
        assert "BaseService" in class_names
        assert "AuthService" in class_names

        # Should find functions
        funcs = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in funcs}
        assert "__init__" in func_names
        assert "authenticate" in func_names
        assert "create_auth_service" in func_names
        assert "process_request" in func_names

    def test_parse_python_edges(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")

        edge_kinds = {e.kind for e in edges}
        assert "CONTAINS" in edge_kinds
        assert "IMPORTS_FROM" in edge_kinds
        assert "CALLS" in edge_kinds

        # Should detect inheritance
        inherits = [e for e in edges if e.kind == "INHERITS"]
        assert len(inherits) >= 1
        assert any("AuthService" in e.source and "BaseService" in e.target for e in inherits)

    def test_parse_python_imports(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        import_targets = {e.target for e in imports}
        assert "os" in import_targets
        assert "pathlib" in import_targets

    def test_parse_python_calls(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        calls = [e for e in edges if e.kind == "CALLS"]
        call_targets = {e.target for e in calls}
        # _resolve_call_targets qualifies same-file definitions
        assert any("_validate_token" in t for t in call_targets)
        assert any("authenticate" in t for t in call_targets)

    def test_parse_typescript_file(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_typescript.ts")

        classes = [n for n in nodes if n.kind == "Class"]
        class_names = {c.name for c in classes}
        assert "UserRepository" in class_names
        assert "UserService" in class_names

        funcs = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in funcs}
        assert "findById" in func_names or "handleGetUser" in func_names

    def test_parse_test_file(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "test_sample.py")

        # Test functions should be detected
        tests = [n for n in nodes if n.kind == "Test"]
        test_names = {t.name for t in tests}
        assert "test_authenticate_valid" in test_names
        assert "test_process_request_ok" in test_names

    def test_calls_edge_same_file_resolution(self):
        """Call targets defined in the same file should be qualified."""
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        calls = [e for e in edges if e.kind == "CALLS"]
        file_path = str(FIXTURES / "sample_python.py")

        # create_auth_service() calls AuthService() — a class defined in the same file
        auth_service_calls = [
            e for e in calls if e.target == f"{file_path}::AuthService"
        ]
        assert len(top_level) == 1


class TestModuleScopeCalls:
    """Module-scope calls (no enclosing function) must attribute to the File node.

    Previously these edges were silently dropped, causing ``find_dead_code`` to
    flag CLI entrypoints, notebook-helper functions, and top-level JSX renders
    as dead. The fix emits a CALLS edge with ``source = file_path`` (the File
    node's qualified name).
    """

    def setup_method(self):
        self.parser = CodeParser()

    def test_python_top_level_call_attributes_to_file(self):
        source = (
            b"def worker():\n"
            b"    return 1\n"
            b"\n"
            b"worker()\n"
        )
        path = FIXTURES / "module_scope_py.py"
        _, edges = self.parser.parse_bytes(path, source)

        calls = [e for e in edges if e.kind == "CALLS"]
        top_level = [
            e for e in calls
            if e.source == str(path) and e.target.endswith("worker")
        ]
        assert len(top_level) == 1
        # Edge originates at the call site (line 4), not the def (line 1).
        assert top_level[0].line == 4

    def test_python_if_main_block_call_attributes_to_file(self):
        source = (
            b"def run_job():\n"
            b"    return 1\n"
            b"\n"
            b"if __name__ == '__main__':\n"
            b"    run_job()\n"
        )
        path = FIXTURES / "module_scope_cli.py"
        _, edges = self.parser.parse_bytes(path, source)

        calls = [e for e in edges if e.kind == "CALLS"]
        top_level = [
            e for e in calls
            if e.source == str(path) and e.target.endswith("run_job")
        ]
        assert len(top_level) == 1
        # Edge originates inside the `if __name__` block (line 5).
        assert top_level[0].line == 5

    def test_tsx_top_level_jsx_render_attributes_to_file(self):
        # Bare top-level JSX expression statement exercises the
        # _extract_jsx_child path specifically (not a value-reference
        # fallback from the `const element = ...` assignment).
        source = (
            b"import App from './App';\n"
            b"\n"
            b"<App />;\n"
        )
        path = FIXTURES / "module_scope_entry.tsx"
        _, edges = self.parser.parse_bytes(path, source)

        calls = [e for e in edges if e.kind == "CALLS"]
        top_level = [
            e for e in calls
            if e.source == str(path) and e.target.endswith("App")
        ]
        assert len(top_level) == 1
        # Edge originates at the JSX site (line 3), not the import (line 1).
        assert top_level[0].line == 3

    def test_r_top_level_call_attributes_to_file(self):
        # R scripts are overwhelmingly module-scope by convention; this is
        # the highest-leverage language for the fix after Python.
        source = (
            b"worker <- function() {\n"
            b"  1\n"
            b"}\n"
            b"\n"
            b"worker()\n"
        )
        path = FIXTURES / "module_scope_sample.R"
        _, edges = self.parser.parse_bytes(path, source)

        top_level = [
            e for e in edges
            if e.kind == "CALLS"
            and e.source == str(path)
            and e.target.endswith("worker")
        ]
        assert len(top_level) == 1

    def test_elixir_top_level_dotted_call_attributes_to_file(self):
        # `.exs` scripts and mix tasks commonly have module-scope `IO.puts`,
        # which is what the parser comment explicitly calls out.
        source = b'IO.puts("hello")\n'
        path = FIXTURES / "module_scope_script.exs"
        _, edges = self.parser.parse_bytes(path, source)

        top_level = [
            e for e in edges
            if e.kind == "CALLS"
            and e.source == str(path)
            and e.target.endswith("puts")
        ]
        assert len(top_level) == 1


class TestTerraformHCLParser:
    """Tests for Terraform/HCL parser support."""

    def setup_method(self):
        self.parser = CodeParser()

    def test_terraform_resource_detection(self):
        """Parse sample.tf, assert aws_instance.main is a Class node."""
        nodes, edges = self.parser.parse_file(FIXTURES / "sample.tf")

        # Check File node exists
        file_nodes = [n for n in nodes if n.kind == "File"]
        assert len(file_nodes) == 1

        # Check resource block is detected as Class
        classes = [n for n in nodes if n.kind == "Class"]
        class_names = {c.name for c in classes}
        assert "resource.aws_instance.main" in class_names

    def test_terraform_module_detection(self):
        """Assert module.vpc is a Class node."""
        nodes, _ = self.parser.parse_file(FIXTURES / "sample.tf")

        classes = [n for n in nodes if n.kind == "Class"]
        class_names = {c.name for c in classes}
        assert "module.vpc" in class_names

    def test_terraform_variable_detection(self):
        """Assert variable.vpc_name is a Function node."""
        nodes, _ = self.parser.parse_file(FIXTURES / "sample.tf")

        functions = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in functions}
        assert "variable.vpc_name" in func_names

    def test_terraform_output_detection(self):
        """Assert output.instance_id is a Function node."""
        nodes, _ = self.parser.parse_file(FIXTURES / "sample.tf")

        functions = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in functions}
        assert "output.instance_id" in func_names

    def test_terraform_data_detection(self):
        """Assert data.aws_ami.latest is a Class node."""
        nodes, _ = self.parser.parse_file(FIXTURES / "sample.tf")

        classes = [n for n in nodes if n.kind == "Class"]
        class_names = {c.name for c in classes}
        assert "data.aws_ami.latest" in class_names

    def test_terraform_locals_detection(self):
        """Assert locals is a Function node."""
        nodes, _ = self.parser.parse_file(FIXTURES / "sample.tf")

        functions = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in functions}
        assert "locals" in func_names

    def test_terraform_module_source_import(self):
        """Assert IMPORTS_FROM edge exists for module source."""
        _, edges = self.parser.parse_file(FIXTURES / "sample.tf")

        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        import_targets = {e.target for e in imports}
        assert "terraform-aws-modules/vpc/aws" in import_targets

    def test_terraform_contains_edges(self):
        """Assert CONTAINS edges exist from file to blocks."""
        nodes, edges = self.parser.parse_file(FIXTURES / "sample.tf")

        contains = [e for e in edges if e.kind == "CONTAINS"]
        assert len(contains) > 0

    def test_terraform_language_detection(self):
        """Test that .tf extension is detected as terraform."""
        assert self.parser.detect_language(Path("main.tf")) == "terraform"
        assert self.parser.detect_language(Path("vars.tfvars")) == "terraform"
        assert self.parser.detect_language(Path("config.hcl")) == "hcl"


class TestYamlParser:
    """Tests for YAML parser support."""

    def setup_method(self):
        self.parser = CodeParser()

    def test_yaml_file_parsed(self):
        """Verify YAML files can be parsed without errors."""
        nodes, edges = self.parser.parse_file(FIXTURES / "sample.yaml")

        # YAML is a data format, so we mainly check it doesn't crash
        # Should at least have a File node
        file_nodes = [n for n in nodes if n.kind == "File"]
        assert len(file_nodes) == 1
        assert file_nodes[0].language == "yaml"

    def test_yaml_language_detection(self):
        """Test that .yaml and .yml extensions are detected as yaml."""
        assert self.parser.detect_language(Path("config.yaml")) == "yaml"
        assert self.parser.detect_language(Path("config.yml")) == "yaml"

