from setuptools import setup
import logging
import plugin_registry


if __name__ == "__main__":
    setup(
        name="Archi Power Tools. Inspector", version="0.1.0", install_requires=["GitPython"]
    )
    plugin_registry.Registry(
        plugin_directory="plugins", logger=logging.getLogger("setup")
    ).setupPlugins()
