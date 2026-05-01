from app.services.scrape_service import classify_scrape_outcome


def test_classify_scrape_outcome_full_success() -> None:
    outcome = classify_scrape_outcome([
        {"success": True, "page_kind": "home", "text_len": 1000},
        {"success": True, "page_kind": "about", "text_len": 900},
        {"success": True, "page_kind": "products", "text_len": 800},
    ])
    assert outcome == ("full_success", "")


def test_classify_scrape_outcome_partial_home_plus_one() -> None:
    outcome = classify_scrape_outcome([
        {"success": True, "page_kind": "home", "text_len": 1000},
        {"success": True, "page_kind": "contact", "text_len": 500},
        {"success": False, "page_kind": "products", "fetch_error_code": "not_found"},
    ])
    assert outcome == ("partial_success", "")


def test_classify_scrape_outcome_partial_two_non_home_pages() -> None:
    outcome = classify_scrape_outcome([
        {"success": True, "page_kind": "about", "text_len": 800},
        {"success": True, "page_kind": "services", "text_len": 700},
    ])
    assert outcome == ("partial_success", "")


def test_classify_scrape_outcome_no_pages_uses_dominant_failure() -> None:
    outcome = classify_scrape_outcome([
        {"success": False, "page_kind": "home", "fetch_error_code": "tls_error"},
        {"success": False, "page_kind": "about", "fetch_error_code": "tls_error"},
        {"success": False, "page_kind": "products", "fetch_error_code": "not_found"},
    ])
    assert outcome == ("failed_gracefully", "tls_error")
