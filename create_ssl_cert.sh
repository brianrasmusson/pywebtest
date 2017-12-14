#!/usr/bin/env bash

if [ "$#" -eq 0 ]; then
	host=privacore.test
else
	host=${1}
fi

openssl req -new -x509 -key ${host}.key -out ${host}.cert -days 3650 -subj "/CN=${host}"
