#!/usr/bin/env bash

#find ./ -mindepth 2 -maxdepth 2 -type f -name README |sort -V |xargs -i bash -c "echo {}; head -1q {}; echo ''" > README

subdirs=$(find ./ -mindepth 1 -maxdepth 1 -type d |sort -V)

for subdir in $subdirs; do
	manual=''

	if [ ! -d ${subdir}/testcase ]; then
		manual=' (manual test)'
	fi

	echo "${subdir}${manual}"

	if [ -f ${subdir}/README ]; then
		head -1q ${subdir}/README
	fi
	echo ''
done
