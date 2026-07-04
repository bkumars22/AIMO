"""
Unit tests for AIMOClient SDK.

Run:
    pip install pytest pytest-asyncio httpx
    pytest ai-engine/sdk/tests/test_aimo_client.py -v

Tests:
    test_report_run_success              — happy path, correct payload sent
    test_report_run_silent_fail_on_network_error — network error never propagates
    test_retry_logic                     — exactly 3 attempts before giving up
"""
from __future__ import annotations

import asyncio
import sys
import os

import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, call, patch

# Allow importing from the sdk package directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aimo_client import AIMOClient, _MAX_RETRIES


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ok_response(status_code: int = 202, body: dict | None = None) -> MagicMock:
    """Create a mock httpx.Response that returns status_code and JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body or {"accepted": True}
    resp.raise_for_status = MagicMock()   # does nothing (2xx)
    return resp


def _make_client(**kwargs) -> AIMOClient:
    return AIMOClient(
        api_key="test-api-key",
        pipeline_id="test-pipeline-uuid",
        base_url="http://fake-aimo.local",
        **kwargs,
    )


async def _drain(client: AIMOClient) -> None:
    """Wait for all background tasks to complete."""
    if client._tasks:
        await asyncio.gather(*client._tasks, return_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. test_report_run_success
# ─────────────────────────────────────────────────────────────────────────────

class TestReportRunSuccess:
    """report_run sends the correct payload and returns immediately."""

    @pytest.mark.asyncio
    async def test_returns_immediately_without_waiting_for_http(self):
        """Return value arrives before the HTTP call completes."""
        client = _make_client()

        delay_happened = False

        async def slow_post(*args, **kwargs):
            nonlocal delay_happened
            await asyncio.sleep(0.05)   # simulate latency
            delay_happened = True
            return _ok_response()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = slow_post

            result = await client.report_run(
                nodes=[{"name": "fetch", "duration_ms": 500, "tokens": 100, "cost_rupees": 1.0}],
                total_cost_rupees=1.0,
                faithfulness_score=0.92,
            )

            # Returns before the HTTP sleep finishes
            assert result["accepted"] is True
            assert result["scheduled"] is True
            assert "run_id" in result

            await _drain(client)
            assert delay_happened  # HTTP did eventually run in background
        await client.close()

    @pytest.mark.asyncio
    async def test_correct_payload_sent_to_runs_ingest(self):
        """Payload has all expected fields, node aliases correctly mapped."""
        client = _make_client()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _ok_response()

            await client.report_run(
                nodes=[
                    {
                        "name":        "generate_tests",
                        "duration_ms": 3000,
                        "tokens":      450,
                        "cost_rupees": 2.5,
                        "model_used":  "claude-haiku-4-5",
                    }
                ],
                total_cost_rupees=2.5,
                faithfulness_score=0.88,
                outputs={"report": "12 test cases"},
                run_id="run-abc",
            )
            await _drain(client)

        mock_post.assert_called_once()
        url, = mock_post.call_args[0]
        assert url.endswith("/runs/ingest")

        payload = mock_post.call_args[1]["json"]
        assert payload["pipeline_id"]        == "test-pipeline-uuid"
        assert payload["run_id"]             == "run-abc"
        assert payload["faithfulness_score"] == 0.88

        node = payload["nodes"][0]
        assert node["name"]         == "generate_tests"
        assert node["latency_ms"]   == 3000           # duration_ms → latency_ms
        assert node["prompt_tokens"] == 450            # tokens → prompt_tokens
        assert abs(node["cost_usd"] - 2.5 / 83.0) < 1e-5  # rupees → USD
        assert node["model_id"]     == "claude-haiku-4-5"

        await client.close()

    @pytest.mark.asyncio
    async def test_authorization_header_is_bearer(self):
        """Bearer token is included in the Authorization header."""
        client = _make_client()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _ok_response()
            await client.report_run(nodes=[])
            await _drain(client)

        headers = mock_post.call_args[1]["headers"]
        assert headers.get("Authorization") == "Bearer test-api-key"

        await client.close()

    @pytest.mark.asyncio
    async def test_contexts_attached_to_last_node(self):
        """RAG contexts land on the final node in the nodes list."""
        client = _make_client()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _ok_response()

            await client.report_run(
                nodes=[
                    {"name": "retrieve"},
                    {"name": "generate"},
                ],
                contexts=["chunk1", "chunk2"],
            )
            await _drain(client)

        payload = mock_post.call_args[1]["json"]
        assert payload["nodes"][1]["context"] == ["chunk1", "chunk2"]
        assert "context" not in payload["nodes"][0]

        await client.close()

    @pytest.mark.asyncio
    async def test_skips_when_no_pipeline_id(self):
        """If pipeline_id is empty, report_run skips without making any HTTP call."""
        client = AIMOClient(api_key="key", pipeline_id="", base_url="http://fake")

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            result = await client.report_run(nodes=[])
            await _drain(client)

        mock_post.assert_not_called()
        assert result["accepted"] is False

        await client.close()


# ─────────────────────────────────────────────────────────────────────────────
# 2. test_report_run_silent_fail_on_network_error
# ─────────────────────────────────────────────────────────────────────────────

class TestReportRunSilentFailOnNetworkError:
    """Network errors must never propagate to the calling pipeline."""

    @pytest.mark.asyncio
    async def test_connect_error_does_not_raise(self):
        """httpx.ConnectError is swallowed silently."""
        client = _make_client()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")
            with patch("asyncio.sleep", new_callable=AsyncMock):  # fast retries
                result = await client.report_run(nodes=[{"name": "n"}])
                await _drain(client)

        # report_run itself must not raise
        assert result["accepted"] is True
        assert result["scheduled"] is True

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_does_not_raise(self):
        """ReadTimeout is swallowed silently."""
        client = _make_client()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ReadTimeout("timed out")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await client.report_run(nodes=[])
                await _drain(client)

        # No exception propagated — if we reach this line, the test passes
        await client.close()

    @pytest.mark.asyncio
    async def test_http_500_does_not_raise(self):
        """5xx responses are swallowed after retries."""
        client = _make_client()

        error_resp = MagicMock(spec=httpx.Response)
        error_resp.status_code = 500
        error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=error_resp
        )

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = error_resp
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await client.report_run(nodes=[])
                await _drain(client)

        await client.close()

    @pytest.mark.asyncio
    async def test_pipeline_continues_after_aimo_failure(self):
        """Main pipeline work completes normally even when AIMO is down."""
        client = _make_client()
        pipeline_result = None

        async def simulate_pipeline():
            nonlocal pipeline_result
            with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.side_effect = httpx.ConnectError("AIMO is down")
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await client.report_run(nodes=[{"name": "step1"}])
                    # Pipeline continues without waiting for AIMO
                    pipeline_result = "pipeline completed"
                    await _drain(client)

        await simulate_pipeline()
        assert pipeline_result == "pipeline completed"
        await client.close()


# ─────────────────────────────────────────────────────────────────────────────
# 3. test_retry_logic
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryLogic:
    """_ship_with_retry retries exactly MAX_RETRIES times with backoff."""

    @pytest.mark.asyncio
    async def test_retries_exactly_max_retries_times(self):
        """On persistent failure, exactly _MAX_RETRIES POST calls are made."""
        client = _make_client()
        call_count = 0

        async def always_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("Network error")

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = always_fail
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await client._ship_with_retry("/runs/ingest", {"test": True})

        assert call_count == _MAX_RETRIES   # 3

        await client.close()

    @pytest.mark.asyncio
    async def test_succeeds_on_second_attempt(self):
        """If 1st attempt fails but 2nd succeeds, only 2 calls are made."""
        client = _make_client()
        attempt = 0

        async def fail_once(*args, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise httpx.ConnectError("first fail")
            return _ok_response()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = fail_once
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await client._ship_with_retry("/runs/ingest", {})

        assert attempt == 2

        await client.close()

    @pytest.mark.asyncio
    async def test_backoff_durations_are_correct(self):
        """Sleep is called with 1 s, 2 s between attempts (exponential base-2)."""
        client = _make_client()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("error")
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await client._ship_with_retry("/runs/ingest", {})

        # For _MAX_RETRIES=3: attempts 0 and 1 sleep; attempt 2 is last (no sleep)
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [1.0, 2.0]   # 1s then 2s

        await client.close()

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self):
        """Single successful response means exactly one POST call."""
        client = _make_client()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _ok_response()
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await client._ship_with_retry("/runs/ingest", {})

        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()

        await client.close()

    @pytest.mark.asyncio
    async def test_report_run_fires_background_task(self):
        """Background task is tracked in _tasks set during execution."""
        client = _make_client()

        # Use an event to catch the in-flight state
        running_event = asyncio.Event()
        done_event    = asyncio.Event()

        async def slow_post(*args, **kwargs):
            running_event.set()
            await done_event.wait()
            return _ok_response()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = slow_post

            result = await client.report_run(nodes=[])
            assert result["scheduled"] is True

            # Task is in-flight — should be tracked
            await running_event.wait()
            assert len(client._tasks) == 1

            done_event.set()
            await _drain(client)
            # After completion, task is removed from set
            assert len(client._tasks) == 0

        await client.close()


# ─────────────────────────────────────────────────────────────────────────────
# Context manager tests
# ─────────────────────────────────────────────────────────────────────────────

class TestContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        """async with AIMOClient() closes the httpx session on exit."""
        async with _make_client() as client:
            assert not client._client.is_closed

        assert client._client.is_closed

    @pytest.mark.asyncio
    async def test_context_manager_drains_background_tasks(self):
        """__aexit__ awaits all in-flight background tasks before closing."""
        completed: list[bool] = []

        async def tracked_ship(self_ref: AIMOClient, path: str, payload: dict) -> None:
            await asyncio.sleep(0)   # one yield so the task is visibly async
            completed.append(True)

        async with _make_client() as client:
            # Patch at class level so the scheduled coroutine keeps the reference
            with patch.object(AIMOClient, "_ship_with_retry", tracked_ship):
                await client.report_run(nodes=[])
            # Patch exits here; async with exits next — close() drains the task

        assert completed == [True]
