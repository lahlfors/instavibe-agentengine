import unittest
import os
from unittest.mock import patch
from agents.app.common.tracing import get_tracer

class TestTracing(unittest.TestCase):

    @patch('agents.app.common.tracing.CloudTraceSpanExporter')
    @patch.dict(os.environ, {"COMMON_GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_get_tracer_with_project_id(self, mock_exporter):
        tracer = get_tracer("test-service")
        self.assertIsNotNone(tracer)
        mock_exporter.assert_called_once_with(project_id="test-project")

    def test_get_tracer_without_project_id(self):
        if "COMMON_GOOGLE_CLOUD_PROJECT" in os.environ:
            del os.environ["COMMON_GOOGLE_CLOUD_PROJECT"]
        tracer = get_tracer("test-service")
        self.assertIsNone(tracer)

if __name__ == "__main__":
    unittest.main()
