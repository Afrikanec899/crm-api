#!/bin/sh

if [[ $# -eq 0 ]] ; then
    echo 'Manage command not set!'
    exit 0
fi

docker-compose run --rm django python manage.py $1