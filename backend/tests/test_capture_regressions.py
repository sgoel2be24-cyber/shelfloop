"""Regression coverage for real capture failures and bounded local media paths."""
import io
import json

import pytest

from app import capture, capture_media, db
from conftest import auth_headers, login


@pytest.fixture
def conn(tmp_db):
    connection = db.connect(tmp_db)
    yield connection
    connection.close()


@pytest.mark.parametrize("text,quantity", [
    ("Parle-G 100g 20 packets", 20),
    ("₹10 wala Parle-G 100g 20 packets", 20),
    ("20 packets Parle-G 100g", 20),
    ("Maggi 70g ३ पैकेट", 3),
    ("मैगी पाँच पैकेट चाहिए", 5),
    ("maggi paanch packet chahiye", 5),
    ("Maggi 70g 2 dozen", 24),
])
def test_pack_count_is_not_pack_size_or_price(conn, text, quantity):
    parsed = capture.parse_text(conn, text)
    assert len(parsed["proposals"]) == 1, parsed
    assert parsed["proposals"][0]["qty"] == quantity, parsed


def test_each_product_keeps_its_own_count_and_intent(conn):
    parsed = capture.parse_text(conn, "Maggi 70g 2 packets, Tata Salt 1kg 4 packets chahiye")
    assert [p["qty"] for p in parsed["proposals"]] == [2, 4]
    assert [p["kind"] for p in parsed["proposals"]] == ["stock_update", "need"]


@pytest.mark.parametrize("text", ["Parle-G 100g", "10 wala biscuit", "१० वाला बिस्कुट", "Tata Salt 2kg"])
def test_price_and_weight_only_are_not_counts(conn, text):
    parsed = capture.parse_text(conn, text)
    assert parsed["status"] == "clarification_needed", parsed
    assert parsed["proposals"][0]["qty"] is None, parsed


def test_deduplicates_catalogue_aliases(conn):
    parsed = capture.parse_text(conn, "मैगी 5 पैकेट")
    ids = [p["product_id"] for p in parsed["proposals"][0]["ambiguity"]["candidates"]]
    assert len(ids) == len(set(ids)) == 3


def test_alias_must_be_a_complete_word(conn):
    assert capture.parse_text(conn, "maggiore 5 packets")["status"] == "failed"


def test_untrusted_oversized_number_does_not_escape_capture_limits(conn):
    parsed = capture.parse_text(conn, "Maggi 70g " + "9" * 5000 + " packets")
    assert parsed["status"] == "clarification_needed"
    assert parsed["proposals"][0]["qty"] is None


def _stored_capture(conn, text="Maggi 70g 5 packets"):
    result = capture.parse_text(conn, text)
    cur = conn.execute(
        "INSERT INTO captures(shop_id,modality,raw_text,extracted,status,created_at) VALUES (1,'text',?,?,?,?)",
        (text, json.dumps(result), result["status"], db.now_iso()))
    return cur.lastrowid, result["proposals"][0]["product_id"]


@pytest.mark.parametrize("patch", [
    {"index": -1}, {"index": 99}, {"index": True}, {"qty": -4}, {"qty": 0},
    {"qty": 1.5}, {"qty": True}, {"qty": "NaN"}, {"qty": 1_000_001},
    {"product_id": 999999}, {"kind": "payment"}, {"unit": "kg"},
])
def test_invalid_confirmation_is_atomic(conn, patch):
    cap_id, product = _stored_capture(conn)
    before = conn.execute("SELECT SUM(qty) FROM stock_lots").fetchone()[0]
    edit = {"index": 0, "product_id": product, "qty": 5, "unit": "pack", "kind": "stock_update", **patch}
    with pytest.raises(ValueError):
        capture.confirm_capture(conn, cap_id, [edit], "owner")
    assert conn.execute("SELECT SUM(qty) FROM stock_lots").fetchone()[0] == before
    assert conn.execute("SELECT status FROM captures WHERE id=?", (cap_id,)).fetchone()[0] != "confirmed"


def test_empty_and_duplicate_confirmation_do_not_commit(conn):
    cap_id, product = _stored_capture(conn)
    edit = {"index": 0, "product_id": product, "qty": 5}
    with pytest.raises(ValueError):
        capture.confirm_capture(conn, cap_id, [], "owner")
    with pytest.raises(ValueError):
        capture.confirm_capture(conn, cap_id, [edit, edit], "owner")


def test_new_stock_does_not_invent_cost_or_sharing_and_cannot_repeat(conn):
    cap_id, product = _stored_capture(conn)
    result = capture.confirm_capture(conn, cap_id, [{"index": 0, "product_id": product, "qty": 5}], "owner")
    lot = conn.execute("SELECT * FROM stock_lots WHERE id=?", (result["applied"][0]["lot_id"],)).fetchone()
    assert lot["qty"] == 5 and lot["cost_paise"] == 0 and lot["permit_share"] == 0
    assert lot["expiry_date"] is None
    with pytest.raises(ValueError, match="already confirmed"):
        capture.confirm_capture(conn, cap_id, [{"index": 0, "product_id": product, "qty": 5}], "owner")


def test_resolved_rules_skip_optional_model(conn, monkeypatch):
    def forbidden_call(_text):
        pytest.fail("a resolved capture must not wait for optional inference")
    monkeypatch.setattr(capture, "_ollama_hint", forbidden_call)
    assert capture.parse_capture(conn, "Maggi 70g 5 packets")["model_status"] == "not_needed"


def test_confirmation_and_retry_response_commit_together(conn):
    cap_id, product = _stored_capture(conn)
    edits = [{"index": 0, "product_id": product, "qty": 5}]
    body = {"edits": edits}
    first = capture.confirm_capture(conn, cap_id, edits, "owner", idempotency_key="owner:1:test:key", request_body=body)
    count = conn.execute("SELECT COUNT(*) FROM stock_lots").fetchone()[0]
    repeated = capture.confirm_capture(conn, cap_id, edits, "owner", idempotency_key="owner:1:test:key", request_body=body)
    assert repeated == first
    assert conn.execute("SELECT COUNT(*) FROM stock_lots").fetchone()[0] == count
    with pytest.raises(ValueError, match="different input"):
        capture.confirm_capture(conn, cap_id, edits, "owner", idempotency_key="owner:1:test:key", request_body={"edits": []})


def test_missing_optional_model_uses_short_circuit(monkeypatch):
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise OSError("optional local server is not installed")
    monkeypatch.setattr(capture, "_ollama_unavailable_until", 0.0)
    monkeypatch.setattr(capture.urllib.request, "urlopen", unavailable)
    assert capture._ollama_hint("unknown product") is None
    assert capture._ollama_hint("unknown product again") is None
    assert len(calls) == 1


def test_concurrent_identical_capture_retry_has_one_effect(conn, tmp_db):
    from concurrent.futures import ThreadPoolExecutor
    cap_id, product = _stored_capture(conn)
    edits = [{"index": 0, "product_id": product, "qty": 5}]
    before = conn.execute("SELECT SUM(qty) FROM stock_lots").fetchone()[0]
    def confirm_once(_):
        connection = db.connect(tmp_db)
        try:
            return capture.confirm_capture(connection, cap_id, edits, "owner",
                                           idempotency_key="owner:1:concurrent:key", request_body={"edits": edits})
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm_once, range(2)))
    assert results[0] == results[1]
    assert conn.execute("SELECT SUM(qty) FROM stock_lots").fetchone()[0] == before + 5


def test_real_csv_invoice_uses_quantity_column_not_rate(conn):
    document = b"product,quantity,rate\nMaggi 70g,4,14\nTata Salt 1kg,2,28\n"
    result = capture_media.extract_invoice(document, "invoice.csv")
    assert result["engine"] == "csv-invoice"
    parsed = capture.parse_text(conn, result["text"])
    assert [p["qty"] for p in parsed["proposals"]] == [4, 2]


def _text_pdf(text="Maggi 70g 5 packets"):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 120 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_real_pdf_invoice_extracts_into_proposals(conn):
    result = capture_media.extract_invoice(_text_pdf(), "invoice.pdf", "application/pdf")
    assert result["engine"] == "pypdf"
    parsed = capture.parse_text(conn, result["text"])
    assert parsed["status"] == "proposed" and parsed["proposals"][0]["qty"] == 5


@pytest.mark.parametrize("name,data,mime", [
    ("invoice.csv", b"product,quantity,rate\nMaggi 70g,4,14\n", "text/csv"),
    ("invoice.pdf", None, "application/pdf"),
])
def test_real_upload_route_preserves_review_gate(client, name, data, mime):
    token = login(client, "owner", "1234", 1)
    headers = auth_headers(token)
    before = sum(lot["qty"] for lot in client.get("/api/shops/1/stock", headers=headers).json())
    result = client.post("/api/captures/invoice", data={"shop_id": "1"},
                         files={"file": (name, data or _text_pdf(), mime)}, headers=headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["capture_id"] and body["status"] == "proposed", body
    assert body["proposals"][0]["qty"] == (4 if data else 5)
    assert sum(lot["qty"] for lot in client.get("/api/shops/1/stock", headers=headers).json()) == before


@pytest.mark.parametrize("data,name", [(b"%PDF-garbage", "bad.pdf"), (b"<svg/>", "invoice.svg"),
                                      (b"not-an-image", "invoice.png"), (b"\xff\xfe", "invoice.txt")])
def test_invalid_invoice_fails_without_writing(data, name):
    with pytest.raises(capture_media.CaptureMediaError):
        capture_media.extract_invoice(data, name)


def test_media_limits_and_missing_engines_are_honest(monkeypatch):
    with pytest.raises(capture_media.CaptureMediaError) as oversized:
        capture_media.extract_invoice(b"x" * (capture_media.MAX_UPLOAD_BYTES + 1), "invoice.txt")
    assert oversized.value.code == "too_large"
    monkeypatch.setattr(capture_media, "_tesseract_path", lambda: None)
    with pytest.raises(capture_media.CaptureMediaError) as unavailable:
        capture_media.extract_invoice(b"\x89PNG\r\n\x1a\nabc", "invoice.png")
    assert unavailable.value.code == "unavailable"
    monkeypatch.setattr(capture_media, "_whisper_model_path", lambda: None)
    with pytest.raises(capture_media.CaptureMediaError) as speech:
        capture_media.transcribe_audio(b"RIFF0000WAVEdata", "recording.wav")
    assert speech.value.code == "unavailable"
