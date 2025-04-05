#!/bin/sh

stdbuf -o0 gdb --batch -nx \
    -ex "source /scripts/commands.py" \
    -ex $1 \
    > /sandbox/run.log 2>&1
