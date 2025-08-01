import unittest
from unittest.mock import patch, call
import subprocess
import sys
import os

import deploy_all

class TestDeployAllScript(unittest.TestCase):

    @patch('deploy_all.deploy_planner_main_func')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_planner_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_planner_main_func):
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False
        deploy_all.deploy_planner_agent('test-project', 'us-central1')
        mock_planner_main_func.assert_called_once_with(project_id='test-project', region='us-central1', base_dir='.')

    @patch('deploy_all.deploy_social_main_func')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_social_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_social_main_func):
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False
        deploy_all.deploy_social_agent('test-project', 'us-central1')
        mock_social_main_func.assert_called_once_with(project_id='test-project', region='us-central1', base_dir='.')

    @patch('deploy_all.deploy_orchestrate_main_func')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_orchestrate_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_orchestrate_main_func):
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False
        deploy_all.deploy_orchestrate_agent('test-project', 'us-central1')
        mock_orchestrate_main_func.assert_called_once_with(project_id='test-project', region='us-central1', base_dir='.')

    @patch('deploy_all.deploy_platform_mcp_client_main_func')
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_platform_mcp_client_agent(self, mock_gapic_client_constructor, mock_check_exists, mock_platform_main_func):
        mock_gapic_client_constructor.return_value
        mock_check_exists.return_value = False
        deploy_all.deploy_platform_mcp_client('test-project', 'us-central1')
        mock_platform_main_func.assert_called_once_with(project_id='test-project', region='us-central1', base_dir='.')

    @patch('subprocess.run')
    def test_deploy_instavibe_app(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr='')
        deploy_all.deploy_instavibe_app('test-project', 'us-central1')
        expected_calls = [
            call(['gcloud', 'config', 'set', 'builds/use_kaniko', 'True', '--project', 'test-project'], check=True, capture_output=True, text=True),
            call(['gcloud', 'builds', 'submit', 'instavibe', '--tag', 'us-central1-docker.pkg.dev/test-project/instavibe-images/instavibe-app', '--project', 'test-project', '--no-cache'], check=True, capture_output=True, text=True),
            call(['gcloud', 'run', 'deploy', 'instavibe-app', '--image', 'us-central1-docker.pkg.dev/test-project/instavibe-images/instavibe-app', '--platform', 'managed', '--region', 'us-central1', '--project', 'test-project', '--allow-unauthenticated'], check=True, capture_output=True, text=True)
        ]
        mock_run.assert_has_calls(expected_calls, any_order=False)

    @patch('subprocess.run')
    def test_deploy_mcp_tool_server(self, mock_run):
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr=''),
            subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr=''),
            subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr=''),
            subprocess.CompletedProcess(args=[], returncode=0, stdout='https://mcp-tool-server-url.a.run.app', stderr='')
        ]
        url = deploy_all.deploy_mcp_tool_server('test-project', 'us-central1')
        self.assertEqual(url, 'https://mcp-tool-server-url.a.run.app')

    @patch('subprocess.run')
    def test_deploy_unified_agent_gateway(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='https://unified-agent-gateway-url', stderr=''
        )
        gateway_url = deploy_all.deploy_unified_agent_gateway(
            'test-project', 'us-central1', env_vars_string='VAR1=val1'
        )
        self.assertEqual(gateway_url, 'https://unified-agent-gateway-url')
        expected_deploy_call = call([
            "gcloud", "run", "deploy", "unified-agent-gateway",
            "--source", "./cloud_run_gateway", "--platform", "managed",
            "--region", "us-central1", "--project", "test-project",
            "--allow-unauthenticated", "--set-env-vars", "VAR1=val1"
        ], check=True, capture_output=True, text=True)
        mock_run.assert_any_call(*expected_deploy_call.args, **expected_deploy_call.kwargs)

    @patch('deploy_all.deploy_planner_main_func', side_effect=subprocess.CalledProcessError(1, "cmd"))
    @patch('deploy_all.check_reasoning_engine_exists')
    @patch('deploy_all.reasoning_engine_service.ReasoningEngineServiceClient')
    def test_deploy_planner_agent_failure(self, mock_gapic, mock_check_exists, mock_deploy_func):
        mock_check_exists.return_value = False
        with self.assertRaises(subprocess.CalledProcessError):
            deploy_all.deploy_planner_agent('test-project', 'us-central1')

    @patch.dict(os.environ, {
        'COMMON_GOOGLE_CLOUD_PROJECT': 'test-p-env', 'COMMON_GOOGLE_CLOUD_LOCATION': 'us-central1',
        'COMMON_VERTEX_STAGING_BUCKET': 'gs://test-bucket-env', 'COMMON_SPANNER_INSTANCE_ID': 'test-instance',
        'COMMON_SPANNER_DATABASE_ID': 'test-db'
    }, clear=True)
    @patch('deploy_all.vertexai.init')
    @patch('deploy_all.deploy_unified_agent_gateway')
    @patch('deploy_all.deploy_mcp_tool_server')
    @patch('deploy_all.deploy_instavibe_app')
    @patch('deploy_all.deploy_platform_mcp_client')
    @patch('deploy_all.deploy_orchestrate_agent')
    @patch('deploy_all.deploy_social_agent')
    @patch('deploy_all.deploy_planner_agent')
    @patch('subprocess.run')
    def test_main_default_behavior(self, mock_subprocess, mock_planner, mock_social, mock_orchestrate, mock_platform_mcp, mock_instavibe, mock_mcp_tool, mock_gateway, mock_vertex_init):
        mock_planner.return_value = "projects/test-p-env/locations/us-central1/reasoningEngines/planner-123"
        mock_social.return_value = "projects/test-p-env/locations/us-central1/reasoningEngines/social-456"
        mock_platform_mcp.return_value = "projects/test-p-env/locations/us-central1/reasoningEngines/mcp-789"
        mock_gateway.return_value = "https://unified-gateway-url.a.run.app"
        mock_mcp_tool.return_value = "https://mcp-tool-server-url.a.run.app"  # Set return value for the mock
        mock_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr='')

        deploy_all.main([])

        mock_vertex_init.assert_called_once_with(project='test-p-env', location='us-central1', staging_bucket='gs://test-bucket-env')
        mock_gateway.assert_called_once()
        self.assertTrue(mock_instavibe.called)
        _, kwargs = mock_instavibe.call_args
        self.assertIn("UNIFIED_AGENT_GATEWAY_URL=https://unified-gateway-url.a.run.app", kwargs.get("env_vars_string", ""))

    @patch.dict(os.environ, {}, clear=True)
    def test_main_missing_env_vars(self):
        with self.assertRaises(ValueError) as context:
            deploy_all.main([])
        self.assertIn("Missing critical environment variables", str(context.exception))

if __name__ == '__main__':
    unittest.main()
