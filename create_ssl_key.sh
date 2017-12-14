#!/usr/bin/env bash

if [ "$#" -eq 0 ]; then
	host=privacore.test
else
	host=${1}
fi

openssl genrsa -out ${host}.key 2048
