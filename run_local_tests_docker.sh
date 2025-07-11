#!/usr/bin/env bash
export PATH=/usr/local/bin:$PATH

docker-compose run --rm django sh ./ci.sh