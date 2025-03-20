#!/bin/bash

if [ "$(id -u)" -ne 0 ]; then
    exec sudo -- "$0" "$@"
fi

docker build -t code-runner -f docker/Dockerfile .
mkdir -p tmp
chown -R www-data:www-data tmp/
chmod 700 tmp/
usermod -aG docker www-data