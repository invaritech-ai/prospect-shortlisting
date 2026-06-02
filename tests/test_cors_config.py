from app.main import cors_middleware_options


def test_cors_wildcard_uses_regex_for_credentialed_frontend_fetches() -> None:
    assert cors_middleware_options("*") == {
        "allow_origins": [],
        "allow_origin_regex": ".*",
    }


def test_cors_explicit_origins_stay_explicit() -> None:
    assert cors_middleware_options("http://localhost:5173, http://127.0.0.1:5173") == {
        "allow_origins": ["http://localhost:5173", "http://127.0.0.1:5173"]
    }
