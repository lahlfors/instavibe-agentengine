import unittest
from unittest.mock import patch, call
import subprocess # Import for CalledProcessError
import sys # Import for sys.argv manipulation if needed, though not for these tests
import os # Ensure os is imported

# Assuming deploy_all.py is in the same directory and functions can be imported
import deploy_all

class TestDeployAllScript(unittest.TestCase):

    @patch('deploy_all.deploy_planner_main_func')
    @patch('subprocess.run')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_planner_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_run, mock_planner_main_func):
        mock_gapic_client_constructor.return_value # mock_gapic_instance
        mock_check_exists.return_value = False

        mock_gcloud_config_result = subprocess.CompletedProcess(
            args=('gcloud', 'config', 'get', 'project'),
            returncode=0,
            stdout='test-project',
            stderr=''
        )
        mock_pip_uninstall_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "uninstall", "google-cloud-aiplatform", "google-adk", "-y"],
            returncode=0, stdout='', stderr=''
        )
        mock_pip_install_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        # This assumes deploy_planner_agent makes three subprocess.run calls in this order:
        # 1. gcloud config get project (NOTE: current deploy_all.py does NOT do this for this function)
        # 2. pip uninstall
        # 3. pip install
        mock_run.side_effect = [mock_gcloud_config_result, mock_pip_uninstall_success, mock_pip_install_success]

        deploy_all.deploy_planner_agent('test-project', 'us-central1')

        mock_planner_main_func.assert_called_once_with('test-project', 'us-central1', base_dir='.')
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "uninstall", "google-cloud-aiplatform", "google-adk", "-y"],
            cwd='agents/planner',
            capture_output=True,
            text=True
        )
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"],
            cwd='agents/planner', check=True, capture_output=True, text=True
        )

    @patch('deploy_all.deploy_social_main_func')
    @patch('subprocess.run')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_social_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_run, mock_social_main_func):
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False

        mock_pip_install_generic_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        mock_run.side_effect = [mock_pip_install_generic_success]

        deploy_all.deploy_social_agent('test-project', 'us-central1')

        mock_social_main_func.assert_called_once_with('test-project', 'us-central1', base_dir='.')
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            cwd='agents/social', check=True, capture_output=True, text=True
        )

    @patch('deploy_all.deploy_orchestrate_main_func')
    @patch('subprocess.run')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_orchestrate_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_run, mock_orchestrate_main_func):
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False

        mock_pip_install_generic_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        mock_run.side_effect = [mock_pip_install_generic_success]

        deploy_all.deploy_orchestrate_agent('test-project', 'us-central1')

        mock_orchestrate_main_func.assert_called_once_with('test-project', 'us-central1', base_dir='.')
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            cwd='agents/orchestrate', check=True, capture_output=True, text=True
        )

    @patch('deploy_all.deploy_platform_mcp_client_main_func')
    @patch('subprocess.run')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_platform_mcp_client_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_run, mock_platform_main_func): # Test name kept for clarity
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False

        mock_pip_install_generic_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        mock_run.side_effect = [mock_pip_install_generic_success]

        deploy_all.deploy_platform_mcp_client('test-project', 'us-central1')

        mock_platform_main_func.assert_called_once_with('test-project', 'us-central1', base_dir='.')
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            cwd='agents/platform_mcp_client', check=True, capture_output=True, text=True
        )

    @patch('deploy_all.check_cloud_run_service_exists')
    @patch('subprocess.run')
    def test_deploy_instavibe_app(self, mock_run, mock_check_exists):
        mock_check_exists.return_value = False
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        mock_run.return_value.returncode = 0
        deploy_all.deploy_instavibe_app('test-project', 'us-central1')
        expected_calls = [
            call([
                'gcloud', 'builds', 'submit', '--tag', 'gcr.io/test-project/instavibe-app', '.', '--project', 'test-project'
            ], check=True, capture_output=True, text=True, cwd='instavibe/'),
            call([
                'gcloud', 'run', 'deploy', 'instavibe-app',
                '--image', 'gcr.io/test-project/instavibe-app',
                '--platform', 'managed',
                '--region', 'us-central1',
                '--project', 'test-project',
                '--allow-unauthenticated'
            ], check=True, capture_output=True, text=True)
        ]
        mock_run.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(mock_run.call_count, 2)

    @patch('deploy_all.check_cloud_run_service_exists')
    @patch('subprocess.run')
    def test_deploy_mcp_tool_server(self, mock_run, mock_check_exists):
        mock_check_exists.return_value = False
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        mock_run.return_value.returncode = 0
        deploy_all.deploy_mcp_tool_server('test-project', 'us-central1')
        expected_calls = [
            call([
                'gcloud', 'builds', 'submit', '--tag', 'gcr.io/test-project/mcp-tool-server', '.', '--project', 'test-project'
            ], check=True, capture_output=True, text=True, cwd='tools/instavibe/'),
            call([
                'gcloud', 'run', 'deploy', 'mcp-tool-server',
                '--image', 'gcr.io/test-project/mcp-tool-server',
                '--platform', 'managed',
                '--region', 'us-central1',
                '--project', 'test-project',
                '--allow-unauthenticated'
            ], check=True, capture_output=True, text=True)
        ]
        mock_run.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(mock_run.call_count, 2)

    @patch('deploy_all.deploy_planner_main_func')
    @patch('subprocess.run')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_planner_agent_failure(self, mock_gapic_client_constructor, mock_check_exists, mock_run, mock_planner_main_func):
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False

        mock_pip_uninstall_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "uninstall", "google-cloud-aiplatform", "google-adk", "-y"],
            returncode=0,
            stdout='uninstall_stdout',
            stderr='uninstall_stderr'
        )
        pip_install_cmd_for_planner = [
            sys.executable, "-m", "pip", "install", "--break-system-packages",
            "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"
        ]
        mock_pip_install_failure = subprocess.CalledProcessError(
            returncode=1,
            cmd=pip_install_cmd_for_planner,
            output="pip install failed output",
            stderr="pip install failed stderr"
        )
        mock_run.side_effect = [
            mock_pip_uninstall_success,
            mock_pip_install_failure
        ]
        with self.assertRaises(subprocess.CalledProcessError):
            deploy_all.deploy_planner_agent('test-project', 'us-central1')

        mock_planner_main_func.assert_not_called()

    # Tests for main() function and argument parsing
    @patch('deploy_all.vertexai.init')
    @patch('deploy_all.build_a2a_common_wheel')
    @patch('deploy_all.load_dotenv')
    @patch.dict(os.environ, {
        'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env',
        'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env',
        'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env',
        'COMMON_SPANNER_INSTANCE_ID': 'test-spanner-instance',
        'COMMON_SPANNER_DATABASE_ID': 'test-spanner-db',
        'INSTAVIBE_FLASK_SECRET_KEY': 'test-secret',
        # Add other necessary env vars for the functions being called if they rely on them directly
    }, clear=True)
    @patch('deploy_all.subprocess.run') # Mock subprocess globally for Spanner setup etc.
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_default_behavior_deploys_all(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool, mock_spanner_subprocess, mock_load_dotenv, mock_build_wheel, mock_vertex_init):
        # Ensure subprocess.run for spanner doesn't fail tests
        mock_spanner_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        mock_planner.return_value = "planner-id"
        mock_social.return_value = "social-id"
        mock_platform_mcp.return_value = "platform-mcp-id"
        mock_orchestrate.return_value = "orchestrate-id"

        deploy_all.main([]) # No args means deploy all

        mock_vertex_init.assert_called_once_with(project='test-p-env', location='test-r-env', staging_bucket='gs://test-bucket-env')
        mock_build_wheel.assert_called_once()
        mock_load_dotenv.assert_called_once()

        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env', remote_addresses_str="planner-id,social-id,platform-mcp-id")
        mock_platform_mcp.assert_called_once_with('test-p-env', 'test-r-env')

        expected_instavibe_env_vars = [
            "COMMON_GOOGLE_CLOUD_PROJECT=test-p-env",
            "COMMON_SPANNER_INSTANCE_ID=test-spanner-instance",
            "COMMON_SPANNER_DATABASE_ID=test-spanner-db",
            "INSTAVIBE_FLASK_SECRET_KEY=test-secret", # from env
            "INSTAVIBE_APP_HOST=0.0.0.0", # default
            "INSTAVIBE_APP_PORT=8080", # default
            # INSTAVIBE_GOOGLE_MAPS_API_KEY and MAP_ID might be empty if not in env
            "COMMON_GOOGLE_CLOUD_LOCATION=test-r-env",
            "AGENTS_PLANNER_RESOURCE_NAME=planner-id",
            "AGENTS_SOCIAL_RESOURCE_NAME=social-id",
            "AGENTS_PLATFORM_MCP_CLIENT_RESOURCE_NAME=platform-mcp-id",
            "AGENTS_ORCHESTRATE_RESOURCE_NAME=orchestrate-id"
        ]
        # Filter out vars with empty values as deploy_all.py does
        expected_instavibe_env_string = ",".join(var for var in expected_instavibe_env_vars if var.split('=',1)[1])

        mock_instavibe.assert_called_once_with('test-p-env', 'test-r-env', env_vars_string=expected_instavibe_env_string)

        expected_mcp_tool_env_vars = [
            "COMMON_GOOGLE_CLOUD_PROJECT=test-p-env",
            # TOOLS_INSTAVIBE_BASE_URL might be empty
            "TOOLS_GOOGLE_GENAI_USE_VERTEXAI=True", # default
            "TOOLS_GOOGLE_CLOUD_LOCATION=test-r-env"
            # TOOLS_GOOGLE_API_KEY might be empty
        ]
        expected_mcp_tool_env_string = ",".join(var for var in expected_mcp_tool_env_vars if var.split('=',1)[1])
        mock_mcp_tool.assert_called_once_with('test-p-env', 'test-r-env', env_vars_string=expected_mcp_tool_env_string)


    @patch('deploy_all.vertexai.init')
    @patch('deploy_all.build_a2a_common_wheel')
    @patch('deploy_all.load_dotenv')
    @patch.dict(os.environ, {
        'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env',
        'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env',
        'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env',
        'COMMON_SPANNER_INSTANCE_ID': 'test-spanner-instance',
        'COMMON_SPANNER_DATABASE_ID': 'test-spanner-db',
        'INSTAVIBE_FLASK_SECRET_KEY': 'test-secret',
    }, clear=True)
    @patch('deploy_all.subprocess.run')
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_deploy_agents_only(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool, mock_spanner_subprocess, mock_load_dotenv, mock_build_wheel, mock_vertex_init):
        mock_spanner_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        mock_planner.return_value = "p"
        mock_social.return_value = "s"
        mock_platform_mcp.return_value = "pmcp"

        deploy_all.main(['--deploy_agents'])

        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env', remote_addresses_str="p,s,pmcp")
        mock_platform_mcp.assert_called_once_with('test-p-env', 'test-r-env')

        mock_instavibe.assert_not_called()
        mock_mcp_tool.assert_not_called()

    @patch('deploy_all.vertexai.init')
    @patch('deploy_all.build_a2a_common_wheel')
    @patch('deploy_all.load_dotenv')
    @patch.dict(os.environ, {
        'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env',
        'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env',
        'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env',
        'COMMON_SPANNER_INSTANCE_ID': 'test-spanner-instance',
        'COMMON_SPANNER_DATABASE_ID': 'test-spanner-db',
        'INSTAVIBE_FLASK_SECRET_KEY': 'test-secret',
    }, clear=True)
    @patch('deploy_all.subprocess.run')
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_deploy_instavibe_only(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool, mock_spanner_subprocess, mock_load_dotenv, mock_build_wheel, mock_vertex_init):
        mock_spanner_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        deploy_all.main(['--deploy_instavibe'])

        mock_planner.assert_not_called()
        mock_social.assert_not_called()
        mock_orchestrate.assert_not_called()
        mock_platform_mcp.assert_not_called()

        expected_instavibe_env_vars = [
            "COMMON_GOOGLE_CLOUD_PROJECT=test-p-env",
            "COMMON_SPANNER_INSTANCE_ID=test-spanner-instance",
            "COMMON_SPANNER_DATABASE_ID=test-spanner-db",
            "INSTAVIBE_FLASK_SECRET_KEY=test-secret",
            "INSTAVIBE_APP_HOST=0.0.0.0",
            "INSTAVIBE_APP_PORT=8080",
            "COMMON_GOOGLE_CLOUD_LOCATION=test-r-env",
            # Agent names will be missing as they are not deployed
        ]
        expected_instavibe_env_string = ",".join(var for var in expected_instavibe_env_vars if var.split('=',1)[1])
        mock_instavibe.assert_called_once_with('test-p-env', 'test-r-env', env_vars_string=expected_instavibe_env_string)
        mock_mcp_tool.assert_not_called()

    @patch('deploy_all.vertexai.init')
    @patch('deploy_all.build_a2a_common_wheel')
    @patch('deploy_all.load_dotenv')
    @patch.dict(os.environ, {
        'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env',
        'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env',
        'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env',
        'COMMON_SPANNER_INSTANCE_ID': 'test-spanner-instance',
        'COMMON_SPANNER_DATABASE_ID': 'test-spanner-db',
    }, clear=True)
    @patch('deploy_all.subprocess.run')
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_deploy_mcp_tool_server_only(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool, mock_spanner_subprocess, mock_load_dotenv, mock_build_wheel, mock_vertex_init):
        mock_spanner_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        deploy_all.main(['--deploy_mcp_tool_server'])

        mock_planner.assert_not_called()
        mock_social.assert_not_called()
        mock_orchestrate.assert_not_called()
        mock_platform_mcp.assert_not_called()
        mock_instavibe.assert_not_called()

        expected_mcp_tool_env_vars = [
            "COMMON_GOOGLE_CLOUD_PROJECT=test-p-env",
            "TOOLS_GOOGLE_GENAI_USE_VERTEXAI=True",
            "TOOLS_GOOGLE_CLOUD_LOCATION=test-r-env"
        ]
        expected_mcp_tool_env_string = ",".join(var for var in expected_mcp_tool_env_vars if var.split('=',1)[1])
        mock_mcp_tool.assert_called_once_with('test-p-env', 'test-r-env', env_vars_string=expected_mcp_tool_env_string)

    @patch('deploy_all.vertexai.init')
    @patch('deploy_all.build_a2a_common_wheel')
    @patch('deploy_all.load_dotenv')
    @patch.dict(os.environ, {
        'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env',
        'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env',
        'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env',
        'COMMON_SPANNER_INSTANCE_ID': 'test-spanner-instance',
        'COMMON_SPANNER_DATABASE_ID': 'test-spanner-db',
        'INSTAVIBE_FLASK_SECRET_KEY': 'test-secret',
    }, clear=True)
    @patch('deploy_all.subprocess.run')
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_deploy_instavibe_and_agents(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool, mock_spanner_subprocess, mock_load_dotenv, mock_build_wheel, mock_vertex_init):
        mock_spanner_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        mock_planner.return_value = "p-id"
        mock_social.return_value = "s-id"
        mock_platform_mcp.return_value = "pmcp-id"
        mock_orchestrate.return_value = "o-id"

        deploy_all.main(['--deploy_instavibe', '--deploy_agents'])

        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env', remote_addresses_str="p-id,s-id,pmcp-id")
        mock_platform_mcp.assert_called_once_with('test-p-env', 'test-r-env')

        expected_instavibe_env_vars = [
            "COMMON_GOOGLE_CLOUD_PROJECT=test-p-env",
            "COMMON_SPANNER_INSTANCE_ID=test-spanner-instance",
            "COMMON_SPANNER_DATABASE_ID=test-spanner-db",
            "INSTAVIBE_FLASK_SECRET_KEY=test-secret",
            "INSTAVIBE_APP_HOST=0.0.0.0",
            "INSTAVIBE_APP_PORT=8080",
            "COMMON_GOOGLE_CLOUD_LOCATION=test-r-env",
            "AGENTS_PLANNER_RESOURCE_NAME=p-id",
            "AGENTS_SOCIAL_RESOURCE_NAME=s-id",
            "AGENTS_PLATFORM_MCP_CLIENT_RESOURCE_NAME=pmcp-id",
            "AGENTS_ORCHESTRATE_RESOURCE_NAME=o-id"
        ]
        expected_instavibe_env_string = ",".join(var for var in expected_instavibe_env_vars if var.split('=',1)[1])
        mock_instavibe.assert_called_once_with('test-p-env', 'test-r-env', env_vars_string=expected_instavibe_env_string)

        mock_mcp_tool.assert_not_called()


    @patch.dict(os.environ, {}, clear=True) # Test with NO env vars set
    @patch('deploy_all.load_dotenv') # Mock load_dotenv as it's called early
    @patch('deploy_all.build_a2a_common_wheel') # Mock build_a2a_common_wheel
    def test_main_missing_env_vars_raises_value_error(self, mock_build_wheel, mock_load_dotenv):
        mock_load_dotenv.return_value = None # Simulate .env not loading anything critical for this check
        mock_build_wheel.return_value = None # Simulate successful wheel build

        with self.assertRaises(ValueError) as context:
            deploy_all.main([])
        self.assertIn("Missing critical environment variables", str(context.exception))
        self.assertIn("COMMON_GOOGLE_CLOUD_PROJECT", str(context.exception))
        self.assertIn("COMMON_GOOGLE_CLOUD_LOCATION", str(context.exception))
        self.assertIn("COMMON_VERTEX_STAGING_BUCKET", str(context.exception))
        self.assertIn("COMMON_SPANNER_INSTANCE_ID", str(context.exception))
        self.assertIn("COMMON_SPANNER_DATABASE_ID", str(context.exception))


if __name__ == '__main__':
    unittest.main()
