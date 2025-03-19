#!/bin/bash

stdbuf -o0 gdb --batch -nx \
    -ex "source tracer.py" \
    -ex "runTrace program"