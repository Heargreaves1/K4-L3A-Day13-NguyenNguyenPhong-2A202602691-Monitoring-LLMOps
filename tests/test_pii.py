from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD của tôi là 001099012345")
    assert "001099012345" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    for card in ("4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111"):
        out = scrub_text(f"Card: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out
        assert "REDACTED_PHONE_VN" not in out


def test_scrub_passport() -> None:
    out = scrub_text("Passport B1234567 expires 2030")
    assert "B1234567" not in out
    assert "REDACTED_PASSPORT" in out


def test_scrub_event_redacts_nested_values_before_render() -> None:
    from app.logging_config import scrub_event

    event = {
        "event": "request_failed",
        "payload": {"detail": "user a@b.com", "nested": {"phone": "0901234567"}},
        "items": ["001099012345"],
        "latency_ms": 12,
    }
    out = scrub_event(None, "info", event)
    rendered = str(out)
    for raw in ("a@b.com", "0901234567", "001099012345"):
        assert raw not in rendered
    assert out["latency_ms"] == 12
