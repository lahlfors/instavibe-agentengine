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
        # List any direct dependencies of the common code here
        # e.g., 'requests', if it uses requests for HTTP communication directly
        # For now, assuming it has no external deps not already covered by agents
    ],
    python_requires='>=3.9', # Based on python:3.12-slim used in Dockerfiles
)
