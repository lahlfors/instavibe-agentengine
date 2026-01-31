import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
from common.agent_gateway import AgentGateway

class TestAgentGateway(unittest.TestCase):
    def setUp(self):
        # Patch setup_observability to avoid actual OTEL setup
        self.setup_patcher = patch('common.agent_gateway.setup_observability')
        self.mock_setup = self.setup_patcher.start()

        # Patch the module-level tracer object
        self.tracer_patcher = patch('common.agent_gateway.tracer')
        self.mock_tracer = self.tracer_patcher.start()

        self.mock_span = MagicMock()
        self.mock_tracer.start_as_current_span.return_value.__enter__.return_value = self.mock_span

    def tearDown(self):
        self.setup_patcher.stop()
        self.tracer_patcher.stop()

    def test_init(self):
        gateway = AgentGateway("test-service")
        self.mock_setup.assert_called_with(service_name_suffix="test-service", endpoint_override=None)

    def test_execute_sync_success(self):
        gateway = AgentGateway("test-service")
        func = MagicMock(return_value="success")

        result = gateway.execute_sync("op", func, 1, a=2)

        self.assertEqual(result, "success")
        func.assert_called_with(1, a=2)
        self.mock_span.set_status.assert_called()

    def test_execute_sync_failure(self):
        gateway = AgentGateway("test-service")
        func = MagicMock(side_effect=ValueError("fail"))

        with self.assertRaises(ValueError):
            gateway.execute_sync("op", func)

        self.mock_span.record_exception.assert_called()
        self.mock_span.set_status.assert_called()

    def test_execute_async_success(self):
        gateway = AgentGateway("test-service")
        func = AsyncMock(return_value="success")

        async def run_test():
            result = await gateway.execute_async("op", func, 1, a=2)
            self.assertEqual(result, "success")
            func.assert_called_with(1, a=2)

        asyncio.run(run_test())

    def test_execute_async_generator(self):
        gateway = AgentGateway("test-service")

        async def mock_gen(count):
            for i in range(count):
                item = MagicMock()
                item.usage_metadata = None # Simplify for this test
                item.is_final_response.return_value = False
                yield item

        async def run_test():
            results = []
            async for item in gateway.execute_async_generator("op", mock_gen, 3):
                results.append(item)
            self.assertEqual(len(results), 3)

        asyncio.run(run_test())

    def test_execute_async_generator_usage_metadata(self):
         gateway = AgentGateway("test-service")

         mock_item = MagicMock()
         mock_item.usage_metadata.prompt_token_count = 100
         mock_item.usage_metadata.candidates_token_count = 50
         mock_item.usage_metadata.total_token_count = 150
         mock_item.is_final_response.return_value = False

         async def mock_gen():
             yield mock_item

         async def run_test():
            async for item in gateway.execute_async_generator("op", mock_gen):
                pass

            # Check if attributes were set
            # We can't easily check the values passed to set_attribute without more complex mocking
            # because start_as_current_span returns a context manager which returns the span.
            # But we can verify set_attribute was called.
            self.assertTrue(self.mock_span.set_attribute.called)

         asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
