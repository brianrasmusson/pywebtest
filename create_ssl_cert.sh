#!/usr/bin/env bash

openssl req -new -x509 -key ${1}.key -out ${1}.cert -days 3650 -subj "/CN=${1}"
