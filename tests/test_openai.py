import io
from http import client
from unittest.mock import patch

@patch("main.client.chat.completions.create")
def test_process_invoice_with_mock(mock_openai):
    mock_openai.return_value.choices = [
        type("obj", (object,), {"message": type("msg", (object,), {"content": '{"invoice_number": "12345"}'})()})()
    ]

    file_content = io.BytesIO(b"fake image bytes")
    response = client.post(
        "/process-invoice/",
        files={"file": ("invoice.png", file_content, "image/png")},
        headers={"X-Client-ID": "test-client"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["structured_data"]["invoice_number"] == "12345"
