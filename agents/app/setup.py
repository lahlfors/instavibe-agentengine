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
        "python-dotenv>=1.0.0",
        "google-cloud-logging>=3.8.0", # For logging_setup.py
        "google-cloud-storage>=2.0.0", # For tracing.py (GCS client)
        "opentelemetry-api>=1.22.0",
        "opentelemetry-sdk>=1.22.0",
        "opentelemetry-exporter-gcp-trace==1.9.0", # Pinned to exact version
        "opentelemetry-propagator-gcp==1.9.0", # Pinned to exact version
        "opentelemetry-instrumentation>=0.43b0", # Namespace package
        "opentelemetry-instrumentation-logging>=0.43b0", # For LoggingInstrumentor
        # Add any other direct dependencies of the app/common or app/utils modules
    ],
    python_requires='>=3.9', # Based on python:3.12-slim used in Dockerfiles
)
