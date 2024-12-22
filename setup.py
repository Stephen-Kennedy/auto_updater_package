# setup
from setuptools import setup, find_packages

setup(
    name="auto_updater_email_notifications",
    version="1.0",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "postfix-setup=postfix_manager.postfix_setup:main",
            "auto-update=postfix_manager.auto_update:main",
        ],
    },
    description="AutoUpdater with Email Notifications",
    author="Stephen J Kennedy",
)
