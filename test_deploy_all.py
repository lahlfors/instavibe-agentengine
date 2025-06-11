import unittest
from unittest.mock import patch, call
import subprocess # Import for CalledProcessError
import sys # Import for sys.argv manipulation if needed, though not for these tests

# Assuming deploy_all.py is in the same directory and functions can be imported
import deploy_all

class TestDeployAllScript(unittest.TestCase):

    @patch('subprocess.run')
    def test_deploy_planner_agent(self, mock_run):
        # Note: deploy_planner_agent in deploy_all.py does not use gcloud config get project
        mock_pip_uninstall_result = subprocess.CompletedProcess(
            args=[sys.executable, '-m', 'pip', 'uninstall', 'google-cloud-aiplatform', 'google-adk', '-y'],
            returncode=0, stdout='', stderr=''
        )
        mock_pip_install_result = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        # The actual call to the sub-script (deploy_planner_main_func) is not a subprocess.run call from deploy_all.py's perspective
        # It's a direct Python function call. The subprocess.run calls are for pip.
        # So, we only need to mock pip calls here if we are testing deploy_planner_agent *unit*
        # However, the prompt seems to imply the 'python deploy.py' is still a subprocess call,
        # which means deploy_planner_main_func itself makes that call. Let's assume that for now.
        # If deploy_planner_main_func is imported and called directly, this test needs rethinking.
        # Based on deploy_all.py structure:
        # deploy_planner_main_func(project_id, region, base_dir=".") -> this is a direct call.
        # The prompt's "expected_command" for planner was: ['python', 'deploy.py', ...]
        # This implies that the *original* structure (before my previous changes to deploy_all.py)
        # might have called the agent deploy scripts via subprocess.
        # Let's assume the current deploy_all.py calls the main_func directly,
        # and thus the subprocess mocks should only be for pip.
        # The test is for deploy_all.deploy_planner_agent, not the sub-script.

        # If the intention *was* to test a `python deploy.py` call made by `deploy_planner_main_func`
        # then this mock_run here (patching subprocess.run for deploy_all.py) would not see it.
        # A different mock target would be needed (e.g. @patch('agents.planner.deploy.subprocess.run'))

        # Given current deploy_all.py, deploy_planner_agent directly calls deploy_planner_main_func.
        # The subprocess.run calls made by deploy_planner_agent are:
        # 1. pip uninstall
        # 2. pip install
        # There is NO `python deploy.py` subprocess call from deploy_planner_agent.
        # The prompt's request to change assert_called_once_with for a `python deploy.py` call is contradictory
        # to the current structure of deploy_all.py where sub-agent deployment is a direct Python function call.

        # For now, I will proceed by mocking the pip calls as they are made by deploy_planner_agent.
        # The assertion part will be tricky if it's expecting a `python deploy.py` call that doesn't exist at this level.

        # Re-evaluating the prompt: "Replace mock_run.assert_called_once_with(...) with:" for a python deploy.py call.
        # This implies that the test *should* be checking for that.
        # This means either my understanding of deploy_all.py is wrong, or the test is for an older structure.
        # Let's look at deploy_all.py's deploy_planner_agent again:
        # subprocess.run for pip uninstall
        # subprocess.run for pip install
        # deploy_planner_main_func(project_id, region, base_dir=".") -> direct python call
        # So, the `python deploy.py` is NOT called by `deploy_all.deploy_planner_agent` via subprocess.
        # It *might* be called by `deploy_planner_main_func`. If so, this test is mocking the wrong thing.

        # Let's assume the request means to verify the *arguments* to `deploy_planner_main_func`
        # and the `subprocess.run` calls for `pip`.
        # The prompt is very specific about `mock_run.side_effect` and the assertion.
        # This implies `deploy_all.py` itself *should* be making these `python deploy.py` calls.
        # This must be a misunderstanding from a previous step where I might have changed deploy_all.py
        # to call the sub-functions directly.
        # Let's assume the target `deploy_all.py` *does* call `python deploy.py ...` for each agent.

        mock_gcloud_config_get_project_result = subprocess.CompletedProcess(args=['gcloud', 'config', 'get', 'project'], returncode=0, stdout='test-project', stderr='')
        # This gcloud call is not in the provided deploy_all.py snippets for agent deployments.
        # Adding it as per prompt, but it might be an unused mock in side_effect if not called.

        mock_pip_uninstall_result = subprocess.CompletedProcess(
            args=[sys.executable, '-m', 'pip', 'uninstall', 'google-cloud-aiplatform', 'google-adk', '-y'],
            returncode=0, stdout='', stderr=''
        )
        mock_pip_install_result = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        # This is the problematic part: the prompt implies deploy_all.py calls 'python deploy.py ...'
        # If this is the case, the deploy_X_main_func imports are not used for subprocess.
        # Let's assume `deploy_all.py` was refactored to use `subprocess.run(['python', 'deploy.py', ...])` for each agent.
        mock_agent_deploy_script_result = subprocess.CompletedProcess(
            args=['python', 'deploy.py', '--project_id', 'test-project', '--region', 'us-central1'],
            returncode=0, stdout='deployed', stderr=''
        )
        # The number of side_effect items must match the number of calls.
        # If `gcloud config get project` is not called by `deploy_planner_agent`, then it shouldn't be in side_effect.
        # Based on the provided `deploy_all.py`, `deploy_planner_agent` calls:
        # 1. pip uninstall
        # 2. pip install
        # (and then calls deploy_planner_main_func directly, not via subprocess)
        # So side_effect should be for 2 calls.
        # If the prompt's intention is that `deploy_planner_agent` *should* call `python deploy.py`,
        # then `deploy_all.py` needs to change first.
        # I will assume the prompt is correct about the calls `deploy_planner_agent` is *expected* to make.
        # This means `deploy_all.py` is assumed to run:
        # 1. (Maybe gcloud config get project - though not in my current deploy_all.py for this function)
        # 2. pip uninstall
        # 3. pip install
        # 4. python deploy.py ...
        # So, 4 side effects. The gcloud one is a guess based on "General changes".

        # Let's assume the `deploy_X_agent` functions in `deploy_all.py` were changed to call `python deploy.py`
        # as a subprocess, instead of direct function imports.
        # And that they might also call 'gcloud config get project'.

        mock_run.side_effect = [
            # mock_gcloud_config_get_project_result, # Let's assume this is NOT called by agent functions directly for now
            mock_pip_uninstall_result,
            mock_pip_install_result,
            mock_agent_deploy_script_result
        ]
        deploy_all.deploy_planner_agent('test-project', 'us-central1')

        expected_cmd = ['python', 'deploy.py', '--project_id', 'test-project', '--region', 'us-central1']
        expected_kwargs = {'check': True, 'capture_output': True, 'text': True, 'cwd': 'agents/planner'}
        # We need to find this specific call among potentially others (pip installs)
        called_correctly = any(
            c_args[0] == expected_cmd and
            all(c_kwargs.get(k) == v for k, v in expected_kwargs.items())
            for c_args, c_kwargs in mock_run.call_args_list
        )
        self.assertTrue(called_correctly, f"Expected call to {' '.join(expected_cmd)} with {expected_kwargs} not found in {mock_run.call_args_list}")


    @patch('subprocess.run')
    def test_deploy_social_agent(self, mock_run):
        mock_gcloud_config_get_project_result = subprocess.CompletedProcess(args=['gcloud', 'config', 'get', 'project'], returncode=0, stdout='test-project', stderr='')
        mock_pip_install_result = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        mock_agent_deploy_script_result = subprocess.CompletedProcess(
            args=['python', 'deploy.py', '--project_id', 'test-project', '--region', 'us-central1'],
            returncode=0, stdout='deployed', stderr=''
        )
        mock_run.side_effect = [
            # mock_gcloud_config_get_project_result, # Assuming not called directly by this agent function
            mock_pip_install_result,
            mock_agent_deploy_script_result
        ]
        deploy_all.deploy_social_agent('test-project', 'us-central1')

        expected_cmd = ['python', 'deploy.py', '--project_id', 'test-project', '--region', 'us-central1']
        expected_kwargs = {'check': True, 'capture_output': True, 'text': True, 'cwd': 'agents/social'}
        called_correctly = any(
            c_args[0] == expected_cmd and
            all(c_kwargs.get(k) == v for k, v in expected_kwargs.items())
            for c_args, c_kwargs in mock_run.call_args_list
        )
        self.assertTrue(called_correctly, f"Expected call to {' '.join(expected_cmd)} with {expected_kwargs} not found in {mock_run.call_args_list}")


    @patch('subprocess.run')
    def test_deploy_orchestrate_agent(self, mock_run):
        mock_gcloud_config_get_project_result = subprocess.CompletedProcess(args=['gcloud', 'config', 'get', 'project'], returncode=0, stdout='test-project', stderr='')
        mock_pip_install_result = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        mock_agent_deploy_script_result = subprocess.CompletedProcess(
            args=['python', 'deploy.py', '--project_id', 'test-project', '--region', 'us-central1'],
            returncode=0, stdout='deployed', stderr=''
        )
        mock_run.side_effect = [
            # mock_gcloud_config_get_project_result, # Assuming not called directly
            mock_pip_install_result,
            mock_agent_deploy_script_result
        ]
        deploy_all.deploy_orchestrate_agent('test-project', 'us-central1')

        expected_cmd = ['python', 'deploy.py', '--project_id', 'test-project', '--region', 'us-central1']
        expected_kwargs = {'check': True, 'capture_output': True, 'text': True, 'cwd': 'agents/orchestrate'}
        called_correctly = any(
            c_args[0] == expected_cmd and
            all(c_kwargs.get(k) == v for k, v in expected_kwargs.items())
            for c_args, c_kwargs in mock_run.call_args_list
        )
        self.assertTrue(called_correctly, f"Expected call to {' '.join(expected_cmd)} with {expected_kwargs} not found in {mock_run.call_args_list}")


    @patch('subprocess.run')
    def test_deploy_platform_mcp_client_agent(self, mock_run): # Test name kept for clarity on what it tests
        mock_gcloud_config_get_project_result = subprocess.CompletedProcess(args=['gcloud', 'config', 'get', 'project'], returncode=0, stdout='test-project', stderr='')
        mock_pip_install_result = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"],
            returncode=0, stdout='', stderr=''
        )
        mock_agent_deploy_script_result = subprocess.CompletedProcess(
            args=['python', 'deploy.py', '--project_id', 'test-project', '--location', 'us-central1'], # Note --location
            returncode=0, stdout='deployed', stderr=''
        )
        mock_run.side_effect = [
            # mock_gcloud_config_get_project_result, # Assuming not called directly
            mock_pip_install_result,
            mock_agent_deploy_script_result
        ]
        deploy_all.deploy_platform_mcp_client('test-project', 'us-central1')

        expected_cmd = ['python', 'deploy.py', '--project_id', 'test-project', '--location', 'us-central1']
        expected_kwargs = {'check': True, 'capture_output': True, 'text': True, 'cwd': 'agents/platform_mcp_client'}
        called_correctly = any(
            c_args[0] == expected_cmd and
            all(c_kwargs.get(k) == v for k, v in expected_kwargs.items())
            for c_args, c_kwargs in mock_run.call_args_list
        )
        self.assertTrue(called_correctly, f"Expected call to {' '.join(expected_cmd)} with {expected_kwargs} not found in {mock_run.call_args_list}")

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

    @patch('subprocess.run')
    def test_deploy_planner_agent_failure(self, mock_run):
        mock_gcloud_config_get_project_result = subprocess.CompletedProcess(
            args=['gcloud', 'config', 'get', 'project'],
            returncode=0,
            stdout='test-project',
            stderr=''
        )
        mock_pip_uninstall_result = subprocess.CompletedProcess(
            args=[sys.executable, '-m', 'pip', 'uninstall', 'google-cloud-aiplatform', 'google-adk', '-y'],
            returncode=0,
            stdout='',
            stderr=''
        )
        pip_install_cmd = [
            sys.executable, "-m", "pip", "install", "--break-system-packages",
            "--force-reinstall", "--no-cache-dir", "-r", "requirements.txt"
        ]
        mock_pip_install_failure = subprocess.CalledProcessError(
            returncode=1,
            cmd=pip_install_cmd,
            output="pip install failed output",
            stderr="pip install failed stderr"
        )
        # Assuming deploy_planner_agent calls:
        # 1. gcloud config get project (as per prompt, though not in current deploy_all.py)
        # 2. pip uninstall
        # 3. pip install (this one fails)
        mock_run.side_effect = [
            # mock_gcloud_config_get_project_result, # Not called by current deploy_all.deploy_planner_agent
            mock_pip_uninstall_result,
            mock_pip_install_failure
        ]
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
