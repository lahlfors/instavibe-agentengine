import unittest
from unittest.mock import patch, call
import subprocess
import sys
import os

import deploy_all

class TestDeployAllScript(unittest.TestCase):

    @patch('deploy_all.build_and_deploy_cloud_run_service')
    def test_build_and_deploy_cloud_run_service(self, mock_build_and_deploy):
        deploy_all.build_and_deploy_cloud_run_service(
            'test-project', 'us-central1', 'instavibe-app', './instavibe',
            env_vars={'VAR1': 'val1'}
        )
        mock_build_and_deploy.assert_called_once_with(
            'test-project', 'us-central1', 'instavibe-app', './instavibe',
            env_vars={'VAR1': 'val1'}
        )

    @patch('deploy_all.deploy_agent', return_value="projects/test-p-env/locations/us-central1/reasoningEngines/test-agent-123")
    @patch('deploy_all.setup_environment', return_value={
        "project_id": "test-p-env", "region": "us-central1",
        "staging_bucket": "gs://test-bucket-env", "spanner_instance": "test-instance",
        "spanner_db": "test-db"
    })
    @patch('deploy_all.setup_spanner')
    @patch('deploy_all.build_and_deploy_cloud_run_service')
    def test_main_default_behavior(self, mock_build_and_deploy, mock_setup_spanner, mock_setup_env, mock_deploy_agent):
        # Set up mock return values for build_and_deploy_cloud_run_service
        def build_and_deploy_side_effect(project_id, region, service_name, source_path, env_vars=None, allow_unauthenticated=True, service_account=None):
            if service_name == "mcp-tool-server":
                return "https://mcp-tool-server-url.a.run.app"
            if service_name == "unified-agent-gateway":
                return "https://unified-gateway-url.a.run.app"
            return "https://some-other-url.a.run.app"
        mock_build_and_deploy.side_effect = build_and_deploy_side_effect

        with patch('sys.argv', ['deploy_all.py']):
             deploy_all.main()

        mock_setup_env.assert_called_once()
        mock_setup_spanner.assert_called_once_with("test-p-env", "test-instance", "test-db", "us-central1")

        # Check that deploy_agent was called for all agents
        self.assertEqual(mock_deploy_agent.call_count, 4)
        agent_names_called = [call.args[2] for call in mock_deploy_agent.call_args_list]
        self.assertIn("Planner Agent", agent_names_called)
        self.assertIn("Social Agent", agent_names_called)
        self.assertIn("Orchestrate Agent", agent_names_called)
        self.assertIn("Platform MCP Client Agent", agent_names_called)

        # Check that build_and_deploy_cloud_run_service was called for all services
        self.assertEqual(mock_build_and_deploy.call_count, 3)
        service_names_called = [call.args[2] for call in mock_build_and_deploy.call_args_list]
        self.assertIn("mcp-tool-server", service_names_called)
        self.assertIn("unified-agent-gateway", service_names_called)
        self.assertIn("instavibe-app", service_names_called)

    @patch.dict(os.environ, {}, clear=True)
    @patch('sys.exit')
    def test_main_missing_env_vars(self, mock_exit):
        with patch('sys.argv', ['deploy_all.py']):
            deploy_all.main()
        mock_exit.assert_called_once_with(1)

if __name__ == '__main__':
    unittest.main()
