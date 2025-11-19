from setuptools import find_packages, setup

setup(
    name="a2a_common",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        # List any third-party dependencies that your agents share here.
        # e.g., 'google-cloud-spanner'
    ],
    description="A shared package for the InstaVibe A2A agents.",
)
