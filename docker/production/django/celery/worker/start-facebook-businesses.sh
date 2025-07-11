#!/bin/sh

set -o errexit
set -o pipefail
set -o nounset

export DJANGO_SETTINGS_MODULE=project.settings.production
celery -A project worker -l ERROR --concurrency=8 -Q facebook_businesses -O fair  --without-gossip --without-mingle