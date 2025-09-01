import unittest
from unittest.mock import patch, call, MagicMock
import subprocess
import sys
import os
import argparse
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import deploy_all

class TestDeployAllScript(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir)

    @patch('deploy_all.run_command')
    @patch('deploy_all.os.path.isdir', return_value=True)
    def test_build_and_deploy_cloud_run_service_substitutions(self, mock_isdir, mock_run_command):
        """Test that build_and_deploy_cloud_run_service constructs the correct substitutions string."""
        # Mock for the build submission and URL fetch
        mock_run_command.return_value = MagicMock(stdout="https://my-service-url.a.run.app")

        deploy_all.build_and_deploy_cloud_run_service(
            project_id="test-proj",
            region="us-central1",
            service_name="test-service",
            source_path="./test/path",
            env_vars={"KEY": "VALUE", "ANOTHER_KEY": "ANOTHER_VALUE"},
            service_account="test-sa@test-proj.iam.gserviceaccount.com"
        )

        # Check the build command call
        build_call_args = mock_run_command.call_args_list[0].args[0]
        self.assertIn("gcloud", build_call_args)
        self.assertIn("builds", build_call_args)
        self.assertIn("submit", build_call_args)

        # Check substitutions are passed as a single comma-separated string
        substitutions_arg = next((arg for arg in build_call_args if arg.startswith('--substitutions=')), None)
        self.assertIsNotNone(substitutions_arg)

        # Verify all keys are present in the substitutions string
        self.assertIn("_IMAGE_PATH=us-central1-docker.pkg.dev/test-proj/instavibe-images/test-service:latest", substitutions_arg)
        self.assertIn("_SERVICE_NAME=test-service", substitutions_arg)
        self.assertIn("_SERVICE_DIR=./test/path", substitutions_arg)
        self.assertIn("_REGION=us-central1", substitutions_arg)
        self.assertIn("_SERVICE_ACCOUNT=test-sa@test-proj.iam.gserviceaccount.com", substitutions_arg)
        self.assertIn("_KEY=VALUE", substitutions_arg)
        self.assertIn("_ANOTHER_KEY=ANOTHER_VALUE", substitutions_arg)


    @patch('deploy_all.importlib.import_module')
    @patch('deploy_all.deploy_agent_engine_app')
    @patch('deploy_all.setup_environment', return_value={
        "project_id": "test-p-env", "region": "us-central1",
        "staging_bucket": "gs://test-bucket-env", "spanner_instance": "test-instance",
        "spanner_db": "test-db", "service_account": "test-sa@example.com"
    })
    @patch('deploy_all.setup_spanner')
    @patch('deploy_all.build_and_deploy_cloud_run_service')
    def test_main_deployment_calls(self, mock_build_and_deploy, mock_setup_spanner, mock_setup_env, mock_deploy_agent_engine_app, mock_import_module):
        """Test that main() calls deployment functions with the correct arguments."""
        # Set up mock return values for build_and_deploy_cloud_run_service
        def build_and_deploy_side_effect(project_id, region, service_name, source_path, env_vars=None, allow_unauthenticated=True, service_account=None):
            if service_name == "mcp-tool-server":
                return "https://mcp-tool-server-url.a.run.app"
            return "https://some-other-url.a.run.app"
        mock_build_and_deploy.side_effect = build_and_deploy_side_effect

        # Mock the return value of deploy_agent_engine_app
        mock_agent = MagicMock()
        mock_agent.name = "projects/test-p-env/locations/us-central1/reasoningEngines/test-agent-123"
        mock_deploy_agent_engine_app.return_value = mock_agent

        # Mock the dynamic import
        mock_module = MagicMock()
        mock_import_module.return_value = mock_module

        # Create a dummy requirements file
        req_path = os.path.join(self.test_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write("requirement1\nrequirement2")

        mock_args = argparse.Namespace(
            skip_agents=False,
            skip_gateway=False,
            skip_mcp_server=False,
            skip_app=False,
            skip_spanner=False,
            deploy_orchestrate_only=False,
        )
        with patch('builtins.open', unittest.mock.mock_open(read_data='requirement1\nrequirement2')):
            deploy_all.main(mock_args)

        # --- Assertions ---
        mock_setup_env.assert_called_once()
        mock_setup_spanner.assert_called_once_with("test-p-env", "test-instance", "test-db", "us-central1")
        self.assertEqual(mock_deploy_agent_engine_app.call_count, 4)
        self.assertEqual(mock_build_and_deploy.call_count, 2)

        # Assert correct arguments are passed for one of the agents
        orchestrate_call = next((c for c in mock_deploy_agent_engine_app.call_args_list if c.kwargs['display_name'] == 'Orchestrate Agent'), None)
        self.assertIsNotNone(orchestrate_call)
        self.assertEqual(orchestrate_call.kwargs['project'], 'test-p-env')
        self.assertEqual(orchestrate_call.kwargs['location'], 'us-central1')
        self.assertIsInstance(orchestrate_call.kwargs['requirements'], list)
        self.assertIsInstance(orchestrate_call.kwargs['requirements'][0], str)
        self.assertEqual(orchestrate_call.kwargs['labels'], {'agent_id': 'orchestrate_agent'})

        # Assert correct arguments are passed for the app
        app_call = next((c for c in mock_build_and_deploy.call_args_list if c.args[2] == 'instavibe-app'), None)
        self.assertIsNotNone(app_call)
        self.assertEqual(app_call.kwargs['service_account'], 'test-sa@example.com')
        self.assertIn("ORCHESTRATE_AGENT_URL", app_call.kwargs['env_vars'])
        self.assertEqual(app_call.kwargs['env_vars']["ORCHESTRATE_AGENT_URL"], "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/test-p-env/locations/us-central1/reasoningEngines/test-agent-123:predict")


    @patch.dict(os.environ, {}, clear=True)
    @patch('sys.exit')
    @patch('deploy_all.install_dependencies')
    def test_main_missing_env_vars(self, mock_install_deps, mock_exit):
        mock_args = argparse.Namespace(
            skip_agents=True,
            skip_gateway=True,
            skip_mcp_server=True,
            skip_app=True,
            skip_spanner=True,
            deploy_orchestrate_only=False,
        )
        deploy_all.main(mock_args)
        mock_exit.assert_called_once_with(1)

if __name__ == '__main__':
    unittest.main()
