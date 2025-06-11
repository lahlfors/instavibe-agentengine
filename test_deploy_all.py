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
    def test_deploy_planner_agent(self, mock_run, mock_planner_main_func):
        mock_pip_uninstall_planner_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "uninstall", "google-cloud-aiplatform", "google-adk", "-y"],
            returncode=0, stdout='', stderr=''
        )
        mock_pip_install_planner_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        # gcloud config get project is not called by deploy_planner_agent in deploy_all.py
        mock_run.side_effect = [mock_pip_uninstall_planner_success, mock_pip_install_planner_success]

        deploy_all.deploy_planner_agent('test-project', 'us-central1')

        mock_planner_main_func.assert_called_once_with('test-project', 'us-central1', base_dir='.')
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "uninstall", "google-cloud-aiplatform", "google-adk", "-y"],
            cwd='agents/planner', check=True, capture_output=True, text=True
        )
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"],
            cwd='agents/planner', check=True, capture_output=True, text=True
        )

    @patch('deploy_all.deploy_social_main_func')
    @patch('subprocess.run')
    def test_deploy_social_agent(self, mock_run, mock_social_main_func):
        mock_pip_install_generic_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        # gcloud config get project is not called by deploy_social_agent in deploy_all.py
        mock_run.side_effect = [mock_pip_install_generic_success]

        deploy_all.deploy_social_agent('test-project', 'us-central1')

        mock_social_main_func.assert_called_once_with('test-project', 'us-central1', base_dir='.')
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            cwd='agents/social', check=True, capture_output=True, text=True
        )

    @patch('deploy_all.deploy_orchestrate_main_func')
    @patch('subprocess.run')
    def test_deploy_orchestrate_agent(self, mock_run, mock_orchestrate_main_func):
        mock_pip_install_generic_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        # gcloud config get project is not called by deploy_orchestrate_agent in deploy_all.py
        mock_run.side_effect = [mock_pip_install_generic_success]

        deploy_all.deploy_orchestrate_agent('test-project', 'us-central1')

        mock_orchestrate_main_func.assert_called_once_with('test-project', 'us-central1', base_dir='.')
        mock_run.assert_any_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            cwd='agents/orchestrate', check=True, capture_output=True, text=True
        )

    @patch('deploy_all.deploy_platform_mcp_client_main_func')
    @patch('subprocess.run')
    def test_deploy_platform_mcp_client_agent(self, mock_run, mock_platform_main_func): # Test name kept for clarity on what it tests
        mock_pip_install_generic_success = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        # gcloud config get project is not called by deploy_platform_mcp_client in deploy_all.py
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
    def test_deploy_planner_agent_failure(self, mock_run, mock_planner_main_func): # mock_run is last due to decorator order
        mock_gcloud_config_result = subprocess.CompletedProcess(
            args=('gcloud', 'config', 'get', 'project'), # Command as tuple
            returncode=0,
            stdout='test-project',
            stderr=''
        )
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
        # deploy_planner_agent in deploy_all.py calls:
        # 1. pip uninstall
        # 2. pip install (this one fails)
        # It does NOT call 'gcloud config get project'.
        mock_run.side_effect = [
            # mock_gcloud_config_result, # Not called by deploy_planner_agent
            mock_pip_uninstall_success,
            mock_pip_install_failure
        ]
        with self.assertRaises(subprocess.CalledProcessError):
            deploy_all.deploy_planner_agent('test-project', 'us-central1')

        mock_planner_main_func.assert_not_called()

    # Tests for main() function and argument parsing
    @patch.dict(os.environ, {'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env', 'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env', 'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env'}, clear=True)
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_default_behavior(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        # The arguments to deploy_all.main are now ignored as project_id and region come from env vars
        deploy_all.main([]) # Pass empty list as args are parsed but values from env are used first

        # Assertions should now use the env var values
        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env')
        mock_platform_mcp.assert_called_once_with('test-p-env', 'test-r-env')
        mock_instavibe.assert_called_once_with('test-p-env', 'test-r-env') # deploy_instavibe_app also uses project_id, region from env
        mock_mcp_tool.assert_called_once_with('test-p-env', 'test-r-env') # deploy_mcp_tool_server also uses project_id, region from env

    @patch.dict(os.environ, {'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env', 'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env', 'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env'}, clear=True)
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_agents(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--skip_agents']) # project_id and region from env

        mock_planner.assert_not_called()
        mock_social.assert_not_called()
        mock_orchestrate.assert_not_called()
        # As per deploy_all.py logic, if --skip_agents is true,
        # deploy_planner_agent, deploy_social_agent, deploy_orchestrate_agent are skipped.
        # deploy_platform_mcp_client is skipped by its own flag --skip_platform_mcp_client.
        # So, platform_mcp, instavibe, mcp_tool should still be called if their flags are not set.
        mock_platform_mcp.assert_called_once_with('test-p-env', 'test-r-env')
        mock_instavibe.assert_called_once_with('test-p-env', 'test-r-env')
        mock_mcp_tool.assert_called_once_with('test-p-env', 'test-r-env')

    @patch.dict(os.environ, {'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env', 'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env', 'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env'}, clear=True)
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_app(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--skip_app']) # project_id and region from env

        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env')
        mock_platform_mcp.assert_called_once_with('test-p-env', 'test-r-env')
        mock_instavibe.assert_not_called()
        mock_mcp_tool.assert_called_once_with('test-p-env', 'test-r-env')

    @patch.dict(os.environ, {'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env', 'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env', 'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env'}, clear=True)
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_platform_mcp_client(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--skip_platform_mcp_client']) # project_id and region from env

        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env')
        mock_platform_mcp.assert_not_called()
        mock_instavibe.assert_called_once_with('test-p-env', 'test-r-env')
        mock_mcp_tool.assert_called_once_with('test-p-env', 'test-r-env')

    @patch.dict(os.environ, {'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env', 'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env', 'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env'}, clear=True)
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_mcp_tool_server(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--skip_mcp_tool_server']) # project_id and region from env

        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env')
        mock_platform_mcp.assert_called_once_with('test-p-env', 'test-r-env')
        mock_instavibe.assert_called_once_with('test-p-env', 'test-r-env')
        mock_mcp_tool.assert_not_called()

    @patch.dict(os.environ, {'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env', 'COMMON_GOOGLE_CLOUD_LOCATION': 'test-r-env', 'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env'}, clear=True)
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_app_and_skip_social_and_skip_platform_mcp(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        # Testing a combination.
        # --skip_social_agent is not an existing flag. --skip_agents will skip social.
        # This test will skip app and platform_mcp_client. Social agent should still run.
        args = ['--skip_app', '--skip_platform_mcp_client'] # project_id and region from env
        deploy_all.main(args)

        mock_planner.assert_called_once_with('test-p-env', 'test-r-env')
        mock_social.assert_called_once_with('test-p-env', 'test-r-env')
        mock_orchestrate.assert_called_once_with('test-p-env', 'test-r-env')
        mock_platform_mcp.assert_not_called()
        mock_instavibe.assert_not_called()
        mock_mcp_tool.assert_called_once_with('test-p-env', 'test-r-env')

    @patch.dict(os.environ, {}, clear=True) # Test with NO env vars set
    def test_main_missing_project_id(self):
        with self.assertRaises(ValueError) as context: # Expect ValueError from os.environ.get checks
            deploy_all.main([]) # Args don't matter, will fail on env var check
        self.assertIn("COMMON_GOOGLE_CLOUD_PROJECT not set", str(context.exception))

    @patch.dict(os.environ, {'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env'}, clear=True) # Test with only project set
    def test_main_missing_region(self):
        with self.assertRaises(ValueError) as context:
            deploy_all.main([])
        self.assertIn("COMMON_GOOGLE_CLOUD_LOCATION (used as common deploy region) not set", str(context.exception))

if __name__ == '__main__':
    unittest.main()
