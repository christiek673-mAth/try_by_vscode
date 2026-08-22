from app.config import Settings


def test_settings_accept_csv_and_json_lists():
    assert Settings(sensitive_columns="email, phone").sensitive_columns == ["email", "phone"]
    assert Settings(sensitive_columns=["email", "phone"]).sensitive_columns == ["email", "phone"]