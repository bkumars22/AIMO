"""Unit tests for alerting/dispatcher.py — network calls (httpx, smtplib) are mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from alerting import dispatcher


def _incident(**overrides) -> dict:
    base = {
        "id": "inc-1", "severity": "P0", "incident_type": "HALLUCINATION",
        "title": "Hallucination detected", "pipeline_id": "aria-prod", "root_cause": "Prompt v8 regression",
    }
    return {**base, **overrides}


class TestSendWebhook:
    def test_returns_false_when_webhook_not_configured(self):
        with patch.object(dispatcher, "WEBHOOK_URL", ""):
            assert dispatcher.send_webhook(_incident()) is False

    def test_posts_slack_payload_and_returns_true_on_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch.object(dispatcher, "WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X"), \
             patch("alerting.dispatcher.httpx.post", return_value=mock_resp) as mock_post:
            result = dispatcher.send_webhook(_incident())
        assert result is True
        sent_json = mock_post.call_args.kwargs["json"]
        assert sent_json["attachments"][0]["title"].startswith("[P0]")

    def test_returns_false_on_http_error(self):
        with patch.object(dispatcher, "WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X"), \
             patch("alerting.dispatcher.httpx.post", side_effect=httpx.ConnectError("down")):
            assert dispatcher.send_webhook(_incident()) is False


class TestSendEmail:
    def test_returns_false_when_smtp_not_configured(self):
        with patch.object(dispatcher, "SMTP_HOST", ""):
            assert dispatcher.send_email(_incident()) is False

    def test_sends_via_smtp_and_returns_true_on_success(self):
        mock_server = MagicMock()
        with patch.object(dispatcher, "SMTP_HOST", "smtp.example.com"), \
             patch.object(dispatcher, "SMTP_USER", "user@example.com"), \
             patch.object(dispatcher, "SMTP_PASS", "secret"), \
             patch.object(dispatcher, "ALERT_EMAIL_TO", "oncall@example.com"), \
             patch("alerting.dispatcher.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__.return_value = mock_server
            result = dispatcher.send_email(_incident())
        assert result is True
        mock_server.login.assert_called_once_with("user@example.com", "secret")
        mock_server.send_message.assert_called_once()

    def test_returns_false_on_smtp_error(self):
        with patch.object(dispatcher, "SMTP_HOST", "smtp.example.com"), \
             patch.object(dispatcher, "SMTP_USER", "user@example.com"), \
             patch.object(dispatcher, "SMTP_PASS", "secret"), \
             patch.object(dispatcher, "ALERT_EMAIL_TO", "oncall@example.com"), \
             patch("alerting.dispatcher.smtplib.SMTP", side_effect=OSError("connection refused")):
            assert dispatcher.send_email(_incident()) is False


class TestDispatch:
    def test_routes_slack_channel_to_send_webhook(self):
        with patch("alerting.dispatcher.send_webhook", return_value=True) as mock_webhook:
            result = dispatcher.dispatch(_incident(), channel="slack")
        mock_webhook.assert_called_once()
        assert result == {"ok": True, "channel": "slack"}

    def test_routes_email_channel_to_send_email(self):
        with patch("alerting.dispatcher.send_email", return_value=True) as mock_email:
            result = dispatcher.dispatch(_incident(), channel="email")
        mock_email.assert_called_once()
        assert result == {"ok": True, "channel": "email"}

    def test_unknown_channel_returns_not_ok_without_raising(self):
        result = dispatcher.dispatch(_incident(), channel="carrier-pigeon")
        assert result == {"ok": False, "channel": "carrier-pigeon"}
