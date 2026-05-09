from src.models import AIConfig, AIProvider, EmailConfig, WebhookConfig
from src.ai.client import OpenAIClient, AzureOpenAIClient
from src.services.email import EmailManager
from src.services.webhook import WebhookNotifier


def test_ai_client_uses_inline_api_key_without_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = OpenAIClient(
        AIConfig(
            provider=AIProvider.OPENAI,
            model="gpt-4",
            api_key="inline-key",
        )
    )

    assert client.client.api_key == "inline-key"


def test_azure_client_uses_inline_api_key_and_endpoint_without_env(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)

    client = AzureOpenAIClient(
        AIConfig(
            provider=AIProvider.AZURE,
            model="gpt-4o-production",
            api_key="inline-key",
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-10-21",
        )
    )

    assert client.client.api_key == "inline-key"


def test_webhook_notifier_uses_inline_url_without_env(monkeypatch):
    monkeypatch.delenv("HORIZON_WEBHOOK_URL", raising=False)

    notifier = WebhookNotifier(WebhookConfig(enabled=True, url="https://example.com/webhook"))

    assert notifier.url == "https://example.com/webhook"


def test_email_manager_uses_inline_password_without_env(monkeypatch):
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

    manager = EmailManager(
        EmailConfig(
            enabled=True,
            smtp_server="smtp.example.com",
            imap_server="imap.example.com",
            email_address="user@example.com",
            password="inline-password",
        )
    )

    assert manager.pwd == "inline-password"
