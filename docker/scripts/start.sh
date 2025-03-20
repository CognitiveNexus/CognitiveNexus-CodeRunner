#!/bin/sh

timeout -k 1s 2s /scripts/compile.sh && timeout -k 1s 10s /scripts/run.sh
