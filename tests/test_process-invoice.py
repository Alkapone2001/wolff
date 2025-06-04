import io
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_process_invoice_endpoint():
    # Create dummy image data (you can use a real small image file if you prefer)
    file_content = io.BytesIO(b"fake image bytes here")

    response = client.post(
        "/process-invoice/",
        files={"file": ("test_invoice.png", file_content, "image/png")},
        headers={"X-Client-ID": "test-client"}
    )
    assert response.status_code == 200

    json_data = response.json()
    assert "extracted_text" in json_data
    assert "structured_data" in json_data
    assert "context" in json_data
    assert json_data["context"]["client_id"] == "test-client"
