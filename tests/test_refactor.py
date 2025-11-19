# tests/test_refactor.py

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch, MagicMock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider

from agents.common.observability import setup_observability

class TestObservabilityRefactor(unittest.TestCase):
    def tearDown(self):
        """Reset the global tracer provider after each test."""
        trace.set_tracer_provider(trace.ProxyTracerProvider())

    @patch.dict(os.environ, {"OTEL_COLLECTOR_ENDPOINT": "localhost:4317"})
    @patch("common.observability.trace.set_tracer_provider")
    @patch("common.observability.trace.get_tracer_provider")
    def test_setup_replaces_non_sdk_provider(
        self, mock_get_provider, mock_set_provider
    ):
        """
        Verify that setup_observability replaces a non-standard TracerProvider.
        This is the primary goal of the refactoring.
        """
        # 1. Arrange: Simulate the problematic state where a non-SDK provider
        # (represented by a simple MagicMock) is already set.
        mock_get_provider.return_value = MagicMock()

        # 2. Act: Run the function we are testing.
        setup_observability()

        # 3. Assert: Verify that set_tracer_provider was called exactly once
        # with an instance of the standard SdkTracerProvider.
        mock_set_provider.assert_called_once()
        args, _ = mock_set_provider.call_args
        self.assertIsInstance(args[0], SdkTracerProvider)

    @patch.dict(os.environ, {"OTEL_COLLECTOR_ENDPOINT": "localhost:4317"})
    @patch("common.observability.trace.set_tracer_provider")
    @patch("common.observability.trace.get_tracer_provider")
    def test_setup_does_not_replace_sdk_provider(
        self, mock_get_provider, mock_set_provider
    ):
        """
        Verify that setup_observability is idempotent and does not replace an
        already-configured standard SdkTracerProvider.
        """
        # 1. Arrange: Simulate the state where a standard provider is already set.
        mock_get_provider.return_value = SdkTracerProvider()

        # 2. Act: Run the function.
        setup_observability()

        # 3. Assert: Verify that set_tracer_provider was NOT called, because
        # no replacement was necessary.
        mock_set_provider.assert_not_called()
