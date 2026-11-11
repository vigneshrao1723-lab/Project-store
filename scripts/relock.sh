#!/bin/sh
# Regenerate requirements.lock and requirements-dev.lock (every package pinned, with hashes) from the direct pins.
# Run it under Python 3.12, the version the Docker image and CI use, so the markers resolve the same way:
#   docker run --rm -v "$PWD:/work" -w /work python:3.12-slim sh scripts/relock.sh
# pip-compile keeps the versions already in the lock; to upgrade one package, change its pin in requirements.txt
# (or add --upgrade-package NAME to the commands below).
set -eu
pip install -q pip-tools==7.6.2
for pair in "requirements.txt requirements.lock" "requirements-dev.txt requirements-dev.lock"; do
    set -- $pair
    pip-compile -q --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url -o "$2" "$1"
done
