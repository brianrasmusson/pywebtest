#!/usr/bin/env bash

find ./ -mindepth 2 -maxdepth 2 -type f -name README |sort -V |xargs -i bash -c "echo {}; head -1q {}; echo ''" > README
