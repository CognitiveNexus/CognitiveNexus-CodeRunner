#!/bin/sh

gcc -g -O0 /sandbox/code.c -o /sandbox/program > /sandbox/compile.log 2>&1 && echo "Compiled successfully" >> /sandbox/compile.log
