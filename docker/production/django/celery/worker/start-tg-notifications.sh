#!/bin/sh

set -o errexit
set -o pipefail
set -o nounset

export DJANGO_SETTINGS_MODULE=project.settings.production
celery -A project worker -l ERROR --concurrency=50  -P gevent -Q tg_notifications -O fair  --without-gossip --without-mingle

