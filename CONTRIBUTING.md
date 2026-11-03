# Contributing

Use a disposable profile and backup; never run tests against a personal collection. Please describe the Anki version, operating system, expected and actual behavior, and steps to reproduce when reporting a problem. Remove personal note contents and identifiers from logs or screenshots.

Install the dependencies described in the README in an isolated environment, then run `python -m pytest -q` and `python build.py`. Add meaningful tests for changes to archive, restore, or statistics scope. Check the compatibility notes before changing Anki integration points. A pull request should explain behavior changes and the tests actually run. Do not commit collection databases, profile data, media, credentials, or generated caches.
