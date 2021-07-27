# This makefile fetches and builds the SAMATE Juliet Test Suite.

# default build, this is what CPP-Differences > Analyze-Snapshots > Build-Snapshots will do.
.PHONY: default
default: output-cpp-both

# build all CPP test cases
output-cpp-both: samate-cpp
	python3 build_samate.py --language cpp --cases both --samate samate-cpp --output output-cpp-both

# build all GOOD CPP test cases
output-cpp-good: samate-cpp
	python3 build_samate.py --language cpp --cases good --samate samate-cpp --output output-cpp-good

# build all BAD CPP test cases
output-cpp-bad: samate-cpp
	python3 build_samate.py --language cpp --cases bad --samate samate-cpp --output output-cpp-bad

# build all Java test cases
output-java-both: samate-java
	python3 build_samate.py --language java --cases both --samate samate-java --output output-java-both

# build all GOOD Java test cases
output-java-good: samate-java
	python3 build_samate.py --language java --cases good --samate samate-java --output output-java-good

# build all BAD Java test cases
output-java-bad: samate-java
	python3 build_samate.py --language java --cases bad --samate samate-java --output output-java-bad

# ensure that we have the SAMATE Juliet Test Suite for CPP
samate-cpp:
	rm -rf samate-cpp
	git clone --depth 1 git@github.com:github/codeql-mirror-juliet-c-cpp.git samate-cpp

# ensure that we have the SAMATE Juliet Test Suite for Java
samate-java:
	rm -rf samate-java
	git clone --depth 1 git@github.com:github/codeql-mirror-juliet-java.git samate-java

clean:
	rm -rf output-*
	# note: in principle the samate-* directories should be removed as well, but they are a bit slow to
	#       fetch and *very* rarely change.
