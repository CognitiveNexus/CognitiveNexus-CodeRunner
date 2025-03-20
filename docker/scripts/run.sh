#!/bin/sh

stdbuf -o0 gdb --batch -nx \
    -ex "source /scripts/tracer.py" \
    -ex "runTrace" \
    > /sandbox/run.log 2>&1
