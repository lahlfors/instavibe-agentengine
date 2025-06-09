import unittest
from unittest.mock import patch, call
import subprocess # Import for CalledProcessError
import sys # Import for sys.argv manipulation if needed, though not for these tests

# Assuming deploy_all.py is in the same directory and functions can be imported
import deploy_all

class TestDeployAllScript(unittest.TestCase):

    @patch('subprocess.run')
    def test_deploy_planner_agent(self, mock_run):
        deploy_all.deploy_planner_agent('test-project', 'us-central1')
        expected_command = [
            'python',
            'deploy.py', # Changed
            '--project_id', 'test-project',
            '--region', 'us-central1'
        ]
        mock_run.assert_called_once_with(
            expected_command,
            check=True,
            capture_output=True,
            text=True,
            cwd='agents/planner' # Added
        )

    @patch('subprocess.run')
    def test_deploy_social_agent(self, mock_run):
        deploy_all.deploy_social_agent('test-project', 'us-central1')
        expected_command = [
            'python',
            'deploy.py', # Changed
            '--project_id', 'test-project',
            '--region', 'us-central1'
        ]
        mock_run.assert_called_once_with(
            expected_command,
            check=True,
            capture_output=True,
            text=True,
            cwd='agents/social' # Added
        )

    @patch('subprocess.run')
    def test_deploy_orchestrate_agent(self, mock_run):
        deploy_all.deploy_orchestrate_agent('test-project', 'us-central1')
        expected_command = [
            'python',
            'deploy.py', # Changed
            '--project_id', 'test-project',
            '--region', 'us-central1'
        ]
        mock_run.assert_called_once_with(
            expected_command,
            check=True,
            capture_output=True,
            text=True,
            cwd='agents/orchestrate' # Added
        )

    @patch('subprocess.run')
    def test_deploy_platform_mcp_client_agent(self, mock_run): # Test name kept for clarity on what it tests
        deploy_all.deploy_platform_mcp_client('test-project', 'us-central1')
        expected_command = [
            'python',
            'deploy.py', # Changed
            '--project_id', 'test-project',
            '--location', 'us-central1' # This specific deploy script uses --location
        ]
        mock_run.assert_called_once_with(
            expected_command,
            check=True,
            capture_output=True,
            text=True,
            cwd='agents/platform_mcp_client' # Added
        )

    @patch('subprocess.run')
    def test_deploy_instavibe_app(self, mock_run):
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

    @patch('subprocess.run')
    def test_deploy_mcp_tool_server(self, mock_run):
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

    @patch('subprocess.run')
    def test_deploy_planner_agent_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="test cmd", output="stdout", stderr="stderr"
        )
        with self.assertRaises(subprocess.CalledProcessError):
            deploy_all.deploy_planner_agent('test-project', 'us-central1')

    # Tests for main() function and argument parsing
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_default_behavior(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--project_id', 'test-p', '--region', 'test-r'])

        mock_planner.assert_called_once_with('test-p', 'test-r')
        mock_social.assert_called_once_with('test-p', 'test-r')
        mock_orchestrate.assert_called_once_with('test-p', 'test-r')
        mock_platform_mcp.assert_called_once_with('test-p', 'test-r')
        mock_instavibe.assert_called_once_with('test-p', 'test-r')
        mock_mcp_tool.assert_called_once_with('test-p', 'test-r')

    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_agents(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--project_id', 'test-p', '--region', 'test-r', '--skip_agents'])

        mock_planner.assert_not_called()
        mock_social.assert_not_called()
        mock_orchestrate.assert_not_called()
        # platform_mcp_client is also considered an agent in the skip_agents logic of deploy_all.py
        # The prompt for deploy_all.py main function update specified:
        # if not args.skip_agents:
        # deploy_planner_agent(args.project_id, args.region)
        # deploy_social_agent(args.project_id, args.region)
        # deploy_orchestrate_agent(args.project_id, args.region)
        # deploy_platform_mcp_client(args.project_id, args.region) <--- This line was missing in the prompt but present in my implementation of deploy_all.py
        # I need to confirm if platform_mcp_client is skipped by --skip_agents in deploy_all.py
        # Assuming it IS skipped by --skip_agents as per a reasonable interpretation.
        # If deploy_all.py was implemented to *not* skip platform_mcp_client with --skip_agents, this test would need adjustment.
        # Let's check deploy_all.py's main:
        # if not args.skip_agents:
        #     deploy_planner_agent(args.project_id, args.region)
        #     deploy_social_agent(args.project_id, args.region)
        #     deploy_orchestrate_agent(args.project_id, args.region)
        #     # My `deploy_all.py` did *not* include platform_mcp_client under --skip_agents initially.
        #     # It had a separate --skip_platform_mcp_client.
        #     # Let's adjust the test to reflect the actual implementation.
        #
        # The original `deploy_all.py` structure for main was:
        # if not args.skip_agents:
        #    deploy_planner_agent
        #    deploy_social_agent
        #    deploy_orchestrate_agent
        # if not args.skip_app: deploy_instavibe_app
        # if not args.skip_platform_mcp_client: deploy_platform_mcp_client
        # if not args.skip_mcp_tool_server: deploy_mcp_tool_server
        #
        # So, --skip_agents *only* skips planner, social, orchestrate.

        mock_platform_mcp.assert_called_once_with('test-p', 'test-r') # It's NOT skipped by --skip_agents
        mock_instavibe.assert_called_once_with('test-p', 'test-r')
        mock_mcp_tool.assert_called_once_with('test-p', 'test-r')

    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_app(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--project_id', 'test-p', '--region', 'test-r', '--skip_app'])

        mock_planner.assert_called_once_with('test-p', 'test-r')
        mock_social.assert_called_once_with('test-p', 'test-r')
        mock_orchestrate.assert_called_once_with('test-p', 'test-r')
        mock_platform_mcp.assert_called_once_with('test-p', 'test-r')
        mock_instavibe.assert_not_called()
        mock_mcp_tool.assert_called_once_with('test-p', 'test-r')

    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_platform_mcp_client(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--project_id', 'test-p', '--region', 'test-r', '--skip_platform_mcp_client'])

        mock_planner.assert_called_once_with('test-p', 'test-r')
        mock_social.assert_called_once_with('test-p', 'test-r')
        mock_orchestrate.assert_called_once_with('test-p', 'test-r')
        mock_platform_mcp.assert_not_called()
        mock_instavibe.assert_called_once_with('test-p', 'test-r')
        mock_mcp_tool.assert_called_once_with('test-p', 'test-r')

    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_mcp_tool_server(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        deploy_all.main(['--project_id', 'test-p', '--region', 'test-r', '--skip_mcp_tool_server'])

        mock_planner.assert_called_once_with('test-p', 'test-r')
        mock_social.assert_called_once_with('test-p', 'test-r')
        mock_orchestrate.assert_called_once_with('test-p', 'test-r')
        mock_platform_mcp.assert_called_once_with('test-p', 'test-r')
        mock_instavibe.assert_called_once_with('test-p', 'test-r')
        mock_mcp_tool.assert_not_called()

    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    def test_main_skip_app_and_skip_social_and_skip_platform_mcp(self, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool):
        # Testing a combination. Note: --skip_social_agent is not a flag in deploy_all.py
        # I will test skipping app and platform_mcp_client
        args = ['--project_id', 'test-p', '--region', 'test-r', '--skip_app', '--skip_platform_mcp_client']
        deploy_all.main(args)

        mock_planner.assert_called_once_with('test-p', 'test-r')
        mock_social.assert_called_once_with('test-p', 'test-r') # Social is part of general agents, not individually skippable by default
        mock_orchestrate.assert_called_once_with('test-p', 'test-r')
        mock_platform_mcp.assert_not_called()
        mock_instavibe.assert_not_called()
        mock_mcp_tool.assert_called_once_with('test-p', 'test-r')

    def test_main_missing_project_id(self):
        with self.assertRaises(SystemExit):
            # Suppress argparse error output to stderr during test
            with patch('sys.stderr'):
                deploy_all.main(['--region', 'test-r'])

    def test_main_missing_region(self):
        with self.assertRaises(SystemExit):
            with patch('sys.stderr'):
                deploy_all.main(['--project_id', 'test-p'])

if __name__ == '__main__':
    unittest.main()
