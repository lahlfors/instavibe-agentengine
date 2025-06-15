from setuptools import setup, find_packages

setup(
    name='a2a_common',
    version='0.1.1', # Incremented version
    packages=find_packages(),
    description='Common utilities for agent-to-agent communication for the Instavibe project.',
    author='Instavibe Development Team',
    author_email='dev@example.com', # Placeholder
    keywords='agents a2a instavibe common',
    install_requires=[
        # List any direct dependencies of the common code here if this package
        # is intended to be used by the refactored LangGraph agents.
        # Example: 'pydantic>=1.10.0,<3.0.0' if it defines Pydantic models.
        #
        # Ensure no ADK-specific dependencies are listed here.
        # The refactored agents primarily use dependencies from the main
        # requirements.txt (e.g., langchain, langgraph).
        #
        # This package (a2a_common) was previously referenced as a wheel in
        # requirements files but has been removed from them. If this package
        # is still necessary, its dependencies should be clearly defined here
        # and it should be installed as part of the agent's environment.
    ],
    python_requires='>=3.9', # Based on python:3.12-slim used in Dockerfiles
)
