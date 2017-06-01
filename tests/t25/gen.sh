#!/bin/bash

fileid=0
for animal in cat dog elephant; do
	for vegetable in tomato cucumber radish; do
		for mineral in granite diamond mercury; do
			echo "$animal $vegetable $mineral" > s1/file$fileid.txt
			fileid=$[ $fileid + 1 ]
			echo "$animal $mineral $vegetable" > s1/file$fileid.txt
			fileid=$[ $fileid + 1 ]
			echo "$vegetable $animal $mineral" > s1/file$fileid.txt
			fileid=$[ $fileid + 1 ]
			echo "$vegetable $mineral $animal" > s1/file$fileid.txt
			fileid=$[ $fileid + 1 ]
			echo "$mineral $animal $vegetable" > s1/file$fileid.txt
			fileid=$[ $fileid + 1 ]
			echo "$mineral $vegetable $animal" > s1/file$fileid.txt
			fileid=$[ $fileid + 1 ]
		done
	done
done
