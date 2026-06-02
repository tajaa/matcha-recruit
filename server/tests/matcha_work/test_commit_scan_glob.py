"""Pure-function tests for the commit-scan glob matcher + element matching.

No DB, no Gemini — safe to run anywhere:
    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_commit_scan_glob.py -q
"""

from app.matcha.services.commit_scan_service import (
    path_matches_glob,
    element_matches_commit,
    match_changed_files_to_elements,
)


class TestPathMatchesGlob:
    def test_recursive_dir(self):
        assert path_matches_glob("server/app/x.py", "server/**")
        assert path_matches_glob("server", "server/**")          # dir itself
        assert not path_matches_glob("serverfoo/x.py", "server/**")  # no false prefix

    def test_single_level(self):
        assert path_matches_glob("server/x.py", "server/*")
        assert not path_matches_glob("server/app/x.py", "server/*")  # too deep

    def test_ext_anywhere(self):
        assert path_matches_glob("client/src/a.ts", "**/*.ts")
        assert not path_matches_glob("client/src/a.tsx", "**/*.ts")

    def test_bare_basename(self):
        assert path_matches_glob("a/b/c.py", "*.py")
        assert path_matches_glob("Makefile", "Makefile")

    def test_normalization(self):
        assert path_matches_glob("./server/app/x.py", "server/**")
        assert path_matches_glob("server\\app\\x.py", "server/**")  # backslashes

    def test_empty(self):
        assert not path_matches_glob("", "server/**")
        assert not path_matches_glob("server/x.py", "")


class TestElementMatching:
    def test_branch_pin_excludes(self):
        el = {"id": "E", "repo_paths": ["desktop/Werk/**"], "repo_branch": "main"}
        assert element_matches_commit(el, ["desktop/Werk/A.swift"], "main")
        assert not element_matches_commit(el, ["desktop/Werk/A.swift"], "dev")

    def test_no_branch_pin_matches_any(self):
        el = {"id": "E", "repo_paths": ["server/**"], "repo_branch": None}
        assert element_matches_commit(el, ["server/app/x.py"], "anything")

    def test_empty_repo_paths_never_matches(self):
        el = {"id": "E", "repo_paths": [], "repo_branch": None}
        assert not element_matches_commit(el, ["server/app/x.py"], None)

    def test_match_set(self):
        els = [
            {"id": "E1", "repo_paths": ["server/**"], "repo_branch": None},
            {"id": "E2", "repo_paths": ["desktop/Werk/**"], "repo_branch": "main"},
        ]
        assert match_changed_files_to_elements(
            ["server/app/x.py", "desktop/Werk/A.swift"], els, "main"
        ) == {"E1", "E2"}
        assert match_changed_files_to_elements(
            ["desktop/Werk/A.swift"], els, "dev"
        ) == set()
