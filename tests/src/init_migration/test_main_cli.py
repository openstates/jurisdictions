"""Tests for main.py CLI argument parsing."""
from src.init_migration.main import parse_args


def test_parse_args_defaults():
    """Default args should process all states with no force."""
    args = parse_args([])
    assert args.state is None
    assert args.force is False
    assert args.log_dir == "logs"


def test_parse_args_single_state():
    """--state wa should parse a single state."""
    args = parse_args(["--state", "wa"])
    assert args.state == "wa"


def test_parse_args_multiple_states():
    """--state wa,tx,oh should parse comma-separated states."""
    args = parse_args(["--state", "wa,tx,oh"])
    assert args.state == "wa,tx,oh"


def test_parse_args_force():
    """--force should set force=True."""
    args = parse_args(["--force"])
    assert args.force is True


def test_parse_args_log_dir():
    """--log-dir should override default."""
    args = parse_args(["--log-dir", "/tmp/my_logs"])
    assert args.log_dir == "/tmp/my_logs"
