from pathlib import Path
import re


def test_run_worker_defaults_contact_fetch_to_single_worker() -> None:
    source = Path("scripts/run_worker.sh").read_text()

    assert "./scripts/run_worker.sh contact_fetch 1" in source
    assert "contact_fetch|validation) CONCURRENCY=\"1\" ;;" in source


def test_run_worker_defaults_validation_to_single_worker() -> None:
    source = Path("scripts/run_worker.sh").read_text()

    assert "./scripts/run_worker.sh validation 1" in source
    assert "contact_fetch|validation) CONCURRENCY=\"1\" ;;" in source


def test_compose_uses_single_contact_fetch_worker() -> None:
    source = Path("docker-compose.yml").read_text()
    provider = re.search(r"worker-provider:(?P<body>.*?)(?:\n    [a-zA-Z0-9_-]+:|\Z)", source, re.S)

    assert provider is not None
    assert 'PS_WORKER_CONCURRENCY: "1"' in provider.group("body")
    assert '- "contact_fetch"' in provider.group("body")
    assert '- "1"' in provider.group("body")
    assert '- "contact_fetch,email_reveal,validation"' not in source


def test_compose_has_single_validation_worker() -> None:
    source = Path("docker-compose.yml").read_text()
    worker = re.search(r"worker-validation:(?P<body>.*?)(?:\n    [a-zA-Z0-9_-]+:|\Z)", source, re.S)

    assert worker is not None
    assert 'PS_WORKER_CONCURRENCY: "1"' in worker.group("body")
    assert '- "validation"' in worker.group("body")
    assert '- "1"' in worker.group("body")
