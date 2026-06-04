from __future__ import annotations

from uuid import uuid4

from app.api.routes import events


def test_scrape_batch_fast_path_preserves_s1_stage() -> None:
    batch_id = uuid4()
    campaign_id = uuid4()

    payload = events._batch_event_payload(
        {
            "batch_id": str(batch_id),
            "campaign_id": str(campaign_id),
            "state": "running",
        },
        stage=events._STAGE_LABEL["scrape_batch"],
        event_type="scrape_batch",
    )

    assert payload["stage"] == "s1"
    assert payload["event_type"] == "scrape_batch"
    assert payload["batch_id"] == str(batch_id)
