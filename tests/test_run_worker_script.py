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


def test_compose_runs_queue_workers_through_wrapper() -> None:
    source = Path("docker-compose.yml").read_text()

    expected_workers = {
        "worker-scrape": ("scrape", "2"),
        "worker-ai": ("ai_decision", "2"),
        "worker-provider": ("contact_fetch", "1"),
        "worker-validation": ("validation", "1"),
    }
    for service, (queue, concurrency) in expected_workers.items():
        worker = re.search(rf"{service}:(?P<body>.*?)(?:\n    [a-zA-Z0-9_-]+:|\Z)", source, re.S)
        assert worker is not None
        body = worker.group("body")
        assert '- "./scripts/run_worker.sh"' in body
        assert f'- "{queue}"' in body
        assert f'- "{concurrency}"' in body

    assert '- "contact_fetch,email_reveal,validation"' not in source
