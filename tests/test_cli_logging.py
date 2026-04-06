from autopoc.cli import app
from typer.testing import CliRunner

runner = CliRunner()

def test_verbose_exception():
    import autopoc.cli
    
    class MockGraph:
        async def ainvoke(self, state):
            raise ValueError("Test generic error")
            
    def mock_build_graph(*args):
        return MockGraph()
        
    autopoc.cli.build_graph = mock_build_graph
    
    import os
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    os.environ["GITLAB_URL"] = "https://gitlab"
    os.environ["GITLAB_TOKEN"] = "token"
    os.environ["GITLAB_GROUP"] = "group"
    os.environ["QUAY_ORG"] = "org"
    os.environ["QUAY_TOKEN"] = "token"
    os.environ["OPENSHIFT_API_URL"] = "https://api"
    os.environ["OPENSHIFT_TOKEN"] = "token"
    
    result = runner.invoke(app, ["--name", "test", "--repo", "https://github/test", "-v"])
    assert result.exit_code == 1
    assert "Test generic error" in result.stdout
    assert "Traceback" in result.stdout

test_verbose_exception()
