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


    @patch('deploy_all.get_project_number', return_value="123456789")
    @patch.dict(os.environ, {'COMMON_GEMINI_MODEL': 'gemini-1.5-flash'})
    @patch('deploy_all.deploy_phase_1_parallel')
    @patch('deploy_all.deploy_phase_2_orchestrate')
    @patch('deploy_all.deploy_phase_3_app')
    @patch('deploy_all.setup_environment', return_value={
        "project_id": "test-p-env", "region": "us-central1",
        "staging_bucket": "gs://test-bucket-env", "spanner_instance": "test-instance",
        "spanner_db": "test-db", "service_account": "test-sa@example.com"
    })
    @patch('deploy_all.setup_spanner')
    @patch('deploy_all.install_dependencies')
    @patch('deploy_all.setup_observability')
    def test_main_deployment_calls(self, mock_setup_obs, mock_install_deps, mock_setup_spanner, 
                                   mock_setup_env, mock_deploy_phase3, mock_deploy_phase2, 
                                   mock_deploy_phase1, mock_get_project_number):
        """Test that main() calls deployment functions with the correct arguments."""
        # Set up mock return values for deployment phases
        mock_deploy_phase1.return_value = {
            "planner_agent": "projects/test-p-env/locations/us-central1/reasoningEngines/planner-123",
            "social_agent": "projects/test-p-env/locations/us-central1/reasoningEngines/social-123",
            "platform_mcp_client_agent": "projects/test-p-env/locations/us-central1/reasoningEngines/platform-123"
        }
        mock_deploy_phase2.return_value = {
            "orchestrate_agent": "projects/test-p-env/locations/us-central1/reasoningEngines/orchestrate-123"
        }

        mock_args = argparse.Namespace(
            skip_agents=False,
            skip_gateway=False,
            skip_mcp_server=False,
            skip_app=False,
            skip_spanner=True,
            skip_collector=True,
            deploy_orchestrate_only=False,
            deploy_planner_only=False,
            force_update=False
        )
        
        deploy_all.main(mock_args)

        # --- Assertions ---
        mock_setup_env.assert_called_once()
        mock_setup_spanner.assert_not_called()  # We skip spanner in this test
        mock_deploy_phase1.assert_called_once()
        mock_deploy_phase2.assert_called_once()
        mock_deploy_phase3.assert_called_once()


    @patch('deploy_all.setup_environment', side_effect=ValueError("Missing critical environment variables"))
    @patch('deploy_all.install_dependencies')
    @patch('deploy_all.setup_observability')
    def test_main_missing_env_vars(self, mock_setup_obs, mock_install_deps, mock_setup_env):
        """Test main() exits when required environment variables are missing."""
        mock_args = argparse.Namespace(
            skip_agents=True,
            skip_gateway=True,
            skip_mcp_server=True,
            skip_app=True,
            skip_spanner=True,
            skip_collector=True,
            deploy_orchestrate_only=False,
            deploy_planner_only=False,
            force_update=False
        )
        # The function should exit with code 1 when env vars are missing
        with self.assertRaises(SystemExit) as cm:
            deploy_all.main(mock_args)
        self.assertEqual(cm.exception.code, 1)

    def test_get_agent_configurations(self):
        """Test that get_agent_configurations returns the expected agent list."""
        agents = deploy_all.get_agent_configurations()
        self.assertEqual(len(agents), 4)
        agent_names = [a["name"] for a in agents]
        self.assertIn("planner_agent", agent_names)
        self.assertIn("orchestrate_agent", agent_names)
        self.assertIn("social_agent", agent_names)
        self.assertIn("platform_mcp_client_agent", agent_names)

    def test_filter_agents_by_args_deploy_orchestrate_only(self):
        """Test that filter_agents_by_args correctly filters for orchestrate-only deployment."""
        agents = deploy_all.get_agent_configurations()
        mock_args = argparse.Namespace(deploy_orchestrate_only=True, deploy_planner_only=False)
        filtered = deploy_all.filter_agents_by_args(agents, mock_args)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "orchestrate_agent")

    def test_filter_agents_by_args_deploy_planner_only(self):
        """Test that filter_agents_by_args correctly filters for planner-only deployment."""
        agents = deploy_all.get_agent_configurations()
        mock_args = argparse.Namespace(deploy_orchestrate_only=False, deploy_planner_only=True)
        filtered = deploy_all.filter_agents_by_args(agents, mock_args)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "planner_agent")

    def test_filter_agents_by_args_all_agents(self):
        """Test that filter_agents_by_args returns all agents when no filter is applied."""
        agents = deploy_all.get_agent_configurations()
        mock_args = argparse.Namespace(deploy_orchestrate_only=False, deploy_planner_only=False)
        filtered = deploy_all.filter_agents_by_args(agents, mock_args)
        self.assertEqual(len(filtered), 4)

    @patch.dict(os.environ, {'COMMON_GEMINI_MODEL': 'gemini-1.5-flash'})
    def test_get_gemini_model_exists(self):
        """Test that get_gemini_model returns the model when set."""
        model = deploy_all.get_gemini_model()
        self.assertEqual(model, 'gemini-1.5-flash')

    @patch.dict(os.environ, {}, clear=True)
    def test_get_gemini_model_missing(self):
        """Test that get_gemini_model exits when model is not set."""
        with self.assertRaises(SystemExit) as cm:
            deploy_all.get_gemini_model()
        self.assertEqual(cm.exception.code, 1)

if __name__ == '__main__':
    unittest.main()
