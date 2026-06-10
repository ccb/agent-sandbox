from setuptools import setup, find_packages

from text_adventure_games import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="text adventure games",
    version=__version__,
    author="Chris Callison-Burch, Jms Dnns",
    author_email="ccb@upenn.edu",
    description="A framework for building text based RPGs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://interactive-fiction-class.org/",
    # license='',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "jupyter",
        "graphviz",
        "flask",
        "rich",  # colored, turn-structured terminal output (see reporting.py).
        # Optional at runtime: the engine falls back to a plain renderer
        # if it's missing, so a no-rich install still works.
    ],
    extras_require={
        "dev": [
            "black",
            "nbformat",
            "pytest",
        ],
        "docs": [
            # Local documentation site under mkdocs/. Build/serve with
            # `cd mkdocs && mkdocs serve`; the rendered site is local-only (not
            # published anywhere — see mkdocs/docs/index.md).
            "mkdocs-material",  # theme + search + navigation
            "mkdocstrings[python]",  # API reference pulled from docstrings
            "black",  # lets mkdocstrings pretty-format rendered signatures
        ],
        "openai": [
            "openai>=1.0",
            "tiktoken",
        ],
        "anthropic": [
            "anthropic>=0.20",
        ],
        "llm": [
            "openai>=1.0",
            "tiktoken",
            "anthropic>=0.20",
        ],
    },
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
