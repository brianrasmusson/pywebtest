#!/bin/bash

fileno=0
for aaa in "" "aaa"; do
	for bbb in "" "bbb"; do
		for ccc in "" "ccc"; do
			for ddd in "" "ddd"; do
				for eee in "" "eee"; do
					filename="s1/boolean-logic-test-$fileno".html
					fileno=$[ $fileno + 1 ]
					cat - >$filename <<EOF
<html lang="da">
<head>
<title>Test for boolean logic</title>
</head>
<body>
<p>$aaa $bbb $ccc $ddd $eee</p>
</body>
</html>
EOF
				done
			done
		done
	done
done
