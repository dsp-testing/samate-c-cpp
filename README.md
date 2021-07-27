# samate-c-cpp
Mirror of the Juliet Test Suite for C/C++ version 1.3 and script(s) to build it.

This README was created by concatenating the READMEs from the old codeql-mirror-juliet-c-cpp and codeql-samate repositories.

## codeql-mirror-juliet-c-cpp
This is a mirror of the Juliet Test Suite for C/C++ version 1.3, from the zip file available at https://samate.nist.gov/SRD/testsuite.php.  It is not maintained by GitHub but is provided here for convenience.

From the above link:
```
This software is not subject to copyright protection and is in the public domain. NIST assumes no responsibility whatsoever for its use by other parties, and makes no guaranties, expressed or implied, about its quality, reliability, or any other characteristic.

Pursuant to 17 USC 105, Juliet Test Suite for C/C++ version 1.3 is not subject to copyright protection in the United States. To the extent NIST may claim Foreign Rights in Juliet Test Suite for C/C++ version 1.3, the Test Suite is being made available to you under the CC0 1.0 Public Domain License.
```

## codeql-samate
Script(s) to build the SAMATE Juliet Test Suite.

Depends on:
 - https://github.com/github/codeql-mirror-juliet-c-cpp (for CPP)
 - https://github.com/github/codeql-mirror-juliet-java (for Java)

This is designed to 'just work' if you have access to the Build-Snapshots job (or CPP-Differences) and point it at this repo:
 - set `urlIdentifier` to "ssh/github/codeql-samate".
 - untick `use_docker` (required for the Makefile to access other repos that are private)
 - set `node` to `linux-8core-scalable` (this will run faster and should have the dependency `g++-mingw-w64` installed).
 - set `LGTMDists` to the build number of a recent successful ODASA build on main (this is optional, without it a new one will be built by the job, potentially adding an hour to your build time).

This repo is also used by the `CPP-Differences` and `SAMATE-cpp-detailed` Jenkins jobs.

----

We used to build this file inside Docker, with all repos public (in dsp-testing) and the following `.lgtm.yml`:
```
extraction:
  cpp:
    prepare:
      packages:
        - g++-mingw-w64
```
