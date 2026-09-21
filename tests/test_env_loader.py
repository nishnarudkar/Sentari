import os

import sentari_env


def _write(tmp_path, body):
    p = tmp_path / ".env"
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_values_but_never_overrides_real_env(tmp_path, monkeypatch):
    p = _write(tmp_path, "SENTARI_T_NEW=from_file\nSENTARI_T_KEEP=from_file\n")
    monkeypatch.setenv("SENTARI_ENV_FILE", str(p))
    monkeypatch.delenv("SENTARI_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("SENTARI_T_NEW", raising=False)
    monkeypatch.setenv("SENTARI_T_KEEP", "from_shell")
    try:
        applied = sentari_env.load_env(force=True)
        assert applied == ["SENTARI_T_NEW"]
        assert os.environ["SENTARI_T_NEW"] == "from_file"
        assert os.environ["SENTARI_T_KEEP"] == "from_shell"
    finally:
        os.environ.pop("SENTARI_T_NEW", None)


def test_empty_values_are_ignored(tmp_path, monkeypatch):
    p = _write(tmp_path, "SENTARI_T_EMPTY=\nSENTARI_T_SET=1\n")
    monkeypatch.setenv("SENTARI_ENV_FILE", str(p))
    monkeypatch.delenv("SENTARI_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("SENTARI_T_EMPTY", raising=False)
    monkeypatch.delenv("SENTARI_T_SET", raising=False)
    try:
        applied = sentari_env.load_env(force=True)
        assert "SENTARI_T_EMPTY" not in applied and "SENTARI_T_EMPTY" not in os.environ
        assert os.environ["SENTARI_T_SET"] == "1"
    finally:
        os.environ.pop("SENTARI_T_SET", None)


def test_missing_file_and_skip_flag_are_noops(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTARI_ENV_FILE", str(tmp_path / "nope.env"))
    monkeypatch.delenv("SENTARI_SKIP_DOTENV", raising=False)
    assert sentari_env.load_env(force=True) == []
    p = _write(tmp_path, "SENTARI_T_SKIPPED=1\n")
    monkeypatch.setenv("SENTARI_ENV_FILE", str(p))
    monkeypatch.setenv("SENTARI_SKIP_DOTENV", "1")
    assert sentari_env.load_env(force=True) == []
    assert "SENTARI_T_SKIPPED" not in os.environ


def test_fallback_parser_handles_quotes_comments_export():
    parsed = sentari_env._parse('# c\nexport A="x y"\nB=\'q\'\nC=plain # trailing\n\nBAD\n')
    assert parsed == {"A": "x y", "B": "q", "C": "plain"}


def test_env_example_lists_every_variable_the_code_reads():
    """Guards against undocumented settings: every SENTARI_*/known var read in code appears in .env.example."""
    import re
    from pathlib import Path
    root = Path(sentari_env.ROOT)
    example = (root / ".env.example").read_text(encoding="utf-8")
    used = set()
    for py in list(root.glob("*/*.py")) + list(root.glob("*/*/*.py")):
        if "tests" in py.parts or "node_modules" in py.parts:
            continue
        used |= set(re.findall(r"environ(?:\.get)?\(?\[?[\"']([A-Z][A-Z_]{3,})[\"']", py.read_text(encoding="utf-8")))
    internal = {"SENTARI_ENV_FILE", "SENTARI_SKIP_DOTENV"}
    missing = sorted(v for v in used - internal if v not in example)
    assert not missing, f"add to .env.example: {missing}"
