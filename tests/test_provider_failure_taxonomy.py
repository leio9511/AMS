import pytest

from etl.cb_provider_base import (
    DataProviderAuthError,
    DataProviderError,
    DataProviderFailureStatus,
    DataProviderNetworkUnavailableError,
    DataProviderQuotaError,
    DataProviderRuntimeBugError,
)


def test_failure_classes_expose_required_status_strings():
    expected = {
        DataProviderNetworkUnavailableError: "NETWORK_UNAVAILABLE",
        DataProviderAuthError: "AUTH_FAILED",
        DataProviderQuotaError: "QUOTA_EXCEEDED",
        DataProviderRuntimeBugError: "RUNTIME_BUG",
    }

    assert {status.value for status in DataProviderFailureStatus} == set(expected.values())
    for error_class, status in expected.items():
        error = error_class("provider failed")
        assert error.status == status
        assert error.status == error.failure_status.value
        assert isinstance(error, DataProviderError)


def test_concrete_failure_can_override_message_without_changing_status():
    error = DataProviderNetworkUnavailableError("timeout while fetching cb_call")

    assert str(error) == "timeout while fetching cb_call"
    assert error.status == "NETWORK_UNAVAILABLE"
    assert error.failure_status is DataProviderFailureStatus.NETWORK_UNAVAILABLE


def test_generic_provider_error_is_not_fallback_eligible_by_default():
    error = DataProviderError("generic provider failure")

    assert error.status == "RUNTIME_BUG"
    assert error.failure_status is DataProviderFailureStatus.RUNTIME_BUG
    assert not isinstance(error, DataProviderNetworkUnavailableError)
