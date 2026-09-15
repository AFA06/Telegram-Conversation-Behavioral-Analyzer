from app.services.telegram_parser import detect_message_type, normalize_text, parse_export


def test_normalize_text_plain_string():
    assert normalize_text("Hello") == "Hello"


def test_normalize_text_nested_entities():
    text_field = ["Hello ", {"type": "bold", "text": "world"}, "!"]
    assert normalize_text(text_field) == "Hello world!"


def test_normalize_text_none_and_missing():
    assert normalize_text(None) == ""
    assert normalize_text([{"type": "bold"}]) == ""


def test_detect_message_type_variants():
    assert detect_message_type({"text": "hi"}) == "text"
    assert detect_message_type({"text": "", "media_type": "voice_message"}) == "voice_message"
    assert detect_message_type({"text": "", "photo": "photos/1.jpg"}) == "photo"
    assert detect_message_type({"text": ""}) == "empty"
    assert detect_message_type({"type": "service", "action": "pin_message"}) == "service"


def test_parse_export_basic():
    data = {
        "name": "Test Chat",
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2026-01-01T20:31:12",
                "date_unixtime": "1767299472",
                "from": "Alice",
                "from_id": "user1000",
                "text": "Hello",
            },
            {
                "id": 2,
                "type": "message",
                "date": "2026-01-01T20:32:00",
                "date_unixtime": "1767299520",
                "from": "Bob",
                "from_id": "user2000",
                "text": ["Hi ", {"type": "bold", "text": "there"}],
            },
        ],
    }
    parsed, report = parse_export(data, source_file="test.json")
    assert report.imported_count == 2
    assert report.valid_count == 2
    assert report.skipped_count == 0
    assert parsed[0].text == "Hello"
    assert parsed[1].text == "Hi there"


def test_parse_export_skips_service_messages():
    data = {"messages": [{"id": 1, "type": "service", "action": "phone_call", "date_unixtime": "1767299472"}]}
    parsed, report = parse_export(data)
    assert len(parsed) == 0
    assert report.skipped_reasons.get("service_message_ignored") == 1


def test_parse_export_skips_missing_sender():
    data = {
        "messages": [
            {"id": 1, "type": "message", "date_unixtime": "1767299472", "text": "hi"},
        ]
    }
    parsed, report = parse_export(data)
    assert len(parsed) == 0
    assert report.skipped_reasons.get("missing_sender") == 1


def test_parse_export_skips_duplicate_ids():
    msg = {"id": 1, "type": "message", "date_unixtime": "1767299472", "from_id": "user1", "text": "hi"}
    data = {"messages": [msg, dict(msg)]}
    parsed, report = parse_export(data)
    assert len(parsed) == 1
    assert report.skipped_reasons.get("duplicate_message_id") == 1


def test_parse_export_skips_invalid_timestamp():
    data = {
        "messages": [
            {"id": 1, "type": "message", "from_id": "user1", "text": "hi"},  # no date at all
        ]
    }
    parsed, report = parse_export(data)
    assert len(parsed) == 0
    assert report.skipped_reasons.get("invalid_timestamp") == 1


def test_parse_export_skips_malformed_record():
    data = {"messages": ["not a dict", 42]}
    parsed, report = parse_export(data)
    assert len(parsed) == 0
    assert report.skipped_reasons.get("malformed_record") == 2
