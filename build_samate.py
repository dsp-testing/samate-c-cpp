#!/usr/bin/env python3
#
# This script builds SAMATE test cases for C/C++ or Java according to command line arguments.  Typical usage:
#   build_samate.py --language cpp --samate [path] --output [path]
#   build_samate.py -h
#
# You are likely to need the following dependendies:
#   Juliet Test Suite for C/C++ / Java (as appropriate) version 1.3
#	 download from:
#	   https://samate.nist.gov/SRD/testsuite.php
#   g++ / g++-mingw-w64 (the latter is useful on Linux because it includes some Windows stuff like `windows.h`)
#	 Ubuntu:
#	   sudo apt-get install g++-mingw-w64
#	 OSX:
#	   install g++-mingw-w64, e.g. using homebrew (using https://github.com/cosmo0920/homebrew-mingw_w64 ?)
#	   after installation, do:
#		 sudo ln -s /usr/local/Cellar/mingw-w64/<version>/bin/i686-w64-mingw32-g++ /usr/bin/
#	 Windows:
#	   install MinGW
#
# You can also build with 'cl' on Windows (specify `--cl cl`) and a few things will work slightly better
# (e.g. `SecureZeroMemory`, `__try`) *but* results may differ from the Linux build that we consider standard.
#
# See `buildutils-internal\security-extvalid\summarize_samate.py` in the `github/semmle-code` repo for more
# information on the overall structure of things.

# TODO: SAMATE build for Java should work now, but
#	(1) we don't have a way to make a separate good / bad build, so we need to sort results instead;
#		see however the original samate script sorted them for Java?
#   (2) the original script had some logic to 'keep the path smaller', do we need that?
#	(3) is not integrated into Jenkins / Actions

# TODO: SAMATE for C# exists as well, though I don't think we've ever used it.

import argparse
import multiprocessing
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time

def is_windows():
	'''Whether we appear to be running on Windows.'''
	if platform.system() == 'Windows':
		return True
	if platform.system().startswith('CYGWIN'):
		return True
	return False

def plural(num):
	if num == 1:
		return ""
	else:
		return "s"

class Jobs:
	'''A very simple thread pool.'''
	def __init__(self, threads):
		self.slots = threading.Semaphore(threads)
		self.outstanding_jobs = []
		self.errors = []
	
	def start_job(self, job):
		'''Start running a job (in a thread).'''
		def do_job():
			try:
				job.do()
			except Exception as e:
				self.errors.append(e)
				raise
			finally:
				self.slots.release()

		self.slots.acquire()
		thread = threading.Thread(target = do_job)
		thread.start()
		self.outstanding_jobs.append(thread)

	def has_errors(self):
		return bool(self.errors)

	def wait_jobs(self):
		'''Wait until all outstanding jobs are complete.'''
		for job in self.outstanding_jobs:
			job.join()
		self._outstanding_jobs = []
		if len(self.errors) > 0:
			print("*** exceptions occurred in " + str(len(self.errors)) + " threads:")
			print(str(self.errors))
			print("")
			raise Exception("Exception in thread(s).")

def find_all_testcases_rec(search_dir, dirs_regexp, files_regexp, cwes_include, cwes_exclude, for_gcc):
	'''Recursive part of find_all_testcases.'''
	results = list()

	# for each child of this directory...
	for child in os.listdir(search_dir):
		child_path = os.path.join(search_dir, child)

		if os.path.isdir(child_path):
			# a directory; check against dirs_regexp and `cwes_exclude`
			dir_match = dirs_regexp.match(child)
			if dir_match:
				recurse_in = False
				report = False

				if dir_match.group(1):
					# CWE-labelled directory
					if dir_match.group(1) in cwes_include or not cwes_include:
						recurse_in = True
						report = True
					if dir_match.group(1) in cwes_exclude:
						recurse_in = False
				else:
					# non-CWE labelled directory (i.e. subdivision directory)
					recurse_in = True

				if recurse_in:
					# recurse in
					new_results = find_all_testcases_rec(child_path, dirs_regexp, files_regexp, cwes_include, cwes_exclude, for_gcc)
					if report:
						print("    found CWE " + dir_match.group(1) + " with " + str(len(new_results)) + " test sources")
					results += new_results

		if os.path.isfile(child_path):
			# a file; check against `files_regexp`
			file_match = files_regexp.match(child)
			if file_match:
				if (child == "CWE397_Throw_Generic_Exception__declare_dotdotdot_w32_01.cpp" and for_gcc):
					# this test-case is "windows specific" according to it's own comments, and won't
					# build in gcc.
					print("  excluding '" + child + "' because that test case explicitly does not work in gcc.")
				else:
					# add to results
					results.append(child_path)

	return results

def find_all_testcases(args):
	'''Find all testcase source files in a search directory'''

	# regexp for directories to explore
	#  - directories of the form `CWE000...`, where 000 is a CWE we are interested in
	#  - directories of the form `s00`, where 00 is any number (these subdivide some CWE directories)
	#  - no other directories (in particular not the "antbuild" directories in Juliet Test Suite v1.3 for Java)
	cwe_dirs_exp = "CWE([0-9]+)_.*"
	s_dirs_exp = "s[0-9]+"
	dirs_exp = "^" + cwe_dirs_exp + "|" + s_dirs_exp + "$"
	dirs_regexp = re.compile(dirs_exp)
	print("  dirs_exp = " + dirs_exp)

	# regexp for files to build
	if (args.language == "cpp"):
		files_exp = "^CWE[0-9]+_.*\.(c|cpp)$" # find source files
	elif (args.language == "java"):
		#files_exp = "^CWE[0-9]+_.*\.java$"
		files_exp = "build\.xml$" # find build files
	else:
		raise Exception("Unknown language (find_all_testcases).")
	files_regexp = re.compile(files_exp)
	print("  files_exp = " + files_exp)

	# include / excluded CWEs
	if args.cwes:
		cwes_include = set(args.cwes.split(","))
	else:
		cwes_include = set()
	if args.exclude:
		cwes_exclude = set(args.exclude.split(","))
	else:
		cwes_exclude = set()
	print("  include = " + str(cwes_include))
	print("  exclude = " + str(cwes_exclude))

	# recursively find testcases
	results = find_all_testcases_rec(args.test_cases_dir, dirs_regexp, files_regexp, cwes_include, cwes_exclude, not args.cl)
	return results

def build_source_files(args, source_paths):
	'''Build a specified source file.'''

	if args.cases == "good":
		cases_macro = "OMITBAD"
	elif args.cases == "bad":
		cases_macro = "OMITGOOD"
	elif args.cases == "both":
		cases_macro = None
	else:
		raise Exception("Unknown cases.")

	if (args.language == "cpp"):
		if args.cl:
			# construct command line (cl)
			cmd = [str(args.cl_path)]
			cmd.append('/I' + args.test_cases_support_dir)
			if cases_macro:
				cmd.append("/D" + cases_macro)
			cmd += ["/W3", "/MT", "/GS", "/RTC1", "/bigobj", "/EHsc", "/nologo"] # same as the .bat files in SAMATE dist
			cmd.append("/c") # do not link
			for source_path in source_paths:
				cmd.append(source_path)
			verbose = []
		else:
			# construct command line (gcc)
			cmd = [str(args.gcc_path)]
			cmd += ["-I", args.test_cases_support_dir]
			if cases_macro:
				cmd.append("-D" + cases_macro)
		
			# the following have been found missing in particular library versions; defining them here
			# increases reliability.
			cmd.append('-DCALG_RC5=(ALG_CLASS_DATA_ENCRYPT|ALG_TYPE_BLOCK|ALG_SID_RC5)') # CALG_RC5 is usually part of 'wincrypt.h'
			cmd.append("-DNO_ERROR=0L")
			cmd.append("-D__STDC_FORMAT_MACROS") # Instruct MinGW to include PRId64, SCNd64 etc
			cmd.append("-c") # do not link
			cmd += ["-wrapper", "true"] # redirect subcommands to do nothing (speeds things up)
			if args.use_pipe:
				cmd.append("-pipe") # use pipes rather than temporary files (may build 10-20% faster, but doesn't work on every system)
			for source_path in source_paths:
				cmd.append(source_path)
			verbose = ["-v", "-pass-exit-codes"] # -v = verbose, -pass-exit-codes = may give more detailed exit code
	elif (args.language == "java"):
		print("build " + str(source_paths))
		cmd = [args.ant_path]
		verbose = ["-v"]
		if len(source_paths) > 1:
			raise Exception("Can't build more than one file at a time with 'ant'.")	
		for source_path in source_paths:
			cmd += ["-buildfile", source_path]
	else:
		# raise exception
		raise Exception("Don't know how to build for this language (build_source_files).")	

	# execute command line (with as little overhead as we can)
	#print('  exec: "' + str(cmd) + '"') # --- report every compiler invocation (affects performance)
	with open(os.devnull, 'w') as devnull:
		rtn = subprocess.call(cmd, stdout = devnull, stderr = devnull)

	# if it fails, execute the command again but with maximum verbosity (for debugging); then fail
	if rtn != 0:
		args.output_mutex.acquire() # avoid getting errors from different threads garbled
		print("*** FAILED BUILD:")
		print('exec: "' + str(cmd + verbose) + '"')
		print("")
		sys.stdout.flush() # try to get output in the right order
		rtn2 = subprocess.call(cmd + verbose, stderr = subprocess.STDOUT)
		print("exit code: " + str(rtn) + " / " + str(rtn2))
		print("***")
		print("")
		sys.stdout.flush()
		args.output_mutex.release()

		# raise exception
		raise Exception("Build '" + source_path + "' failed.")

class build_source_files_job:
	'''Build a specified source file (as a job).'''
	def __init__(self, args, source_paths):
		self.args = args
		self.source_paths = source_paths

	def do(self):
		build_source_files(self.args, self.source_paths)

def main():
	time_start = time.time()
	print("--- build_samate.py ---")
	print("")
	sys.stdout.write("receiving from stdout\n")
	sys.stdout.flush()
	sys.stderr.write("receiving from stderr\n")
	sys.stderr.flush()
	print("")

	# parse arguments
	#  (`dest` is the member of `args` the argument is written to
	#   `choices` resticts the values it can take
	#   `default` is the value if it isn't specified, `required` forces the user to specify it
	#   `metavar` and `help` and only used in help messages)
	arg_parser = argparse.ArgumentParser(description='Builds the SAMATE Juliet test suite.')
	arg_parser.add_argument('--language', dest='language', choices=["cpp", "java"], required=True,
							metavar='LANG', help='which language to build ("cpp" or "java")')
	arg_parser.add_argument('--samate', dest='samate_dir', required=True,
							metavar='DIR', help='location of the unzipped Samate suite')
	arg_parser.add_argument('--output', dest='output_dir', required=True,
							metavar='DIR', help='location for the output directory')
	# ... optional args ...
	arg_parser.add_argument('--cwes', dest='cwes', required=False,
							metavar='NUM', help='CWEs to test, separated by \',\' (default: all CWEs)')
	arg_parser.add_argument('--exclude', dest='exclude', required=False,
							metavar='NUM', help='CWEs to exclude from tests, separated by \',\'')
	arg_parser.add_argument('--cases', dest='cases', choices=["good", "bad", "both"], required=False,
							metavar='WHICH', help='which test cases to build ("good" or "bad"; default: both)', default = "both")
	try:
		cpu_count = multiprocessing.cpu_count()
		default_threads = cpu_count + 1 # one per CPU + one ready
	except NotImplementedError:
		default_threads = 9 # high guess, as excessive threads don't seem to hurt performance much
	arg_parser.add_argument('--threads', dest='threads', type=int, required=False,
							metavar='NUM', help='number of threads, use 1 for better determinism and cleaner output (default: auto)', default = default_threads)
	if is_windows():
		default_gcc = "gcc"
	else:
		default_gcc = "/usr/bin/i686-w64-mingw32-gcc"
	arg_parser.add_argument('--gcc', dest='gcc', required=False,
							metavar='PATH', help='path to gcc (default: "' + default_gcc + '")', default = default_gcc)
	arg_parser.add_argument('--cl', dest='cl', required=False,
							metavar='PATH', help='path to cl (default: uses gcc unless --cl is specified)')
	args = arg_parser.parse_args()

	# normalize paths (absolute paths work better when we change directory later!)
	args.samate_dir = os.path.abspath(args.samate_dir)
	args.output_dir = os.path.abspath(args.output_dir)

	# compute SAMATE language root (and add to `args`, for convenience)
	if not os.path.isdir(args.samate_dir):
		raise Exception("Specified SAMATE path is not a directory.")
	if (args.language == "cpp"):
		args.language_root = os.path.join(args.samate_dir, 'C') # root for Samate 1.3
		if not os.path.isdir(args.language_root):
			args.language_root = args.samate_dir # in Samate 1.2 there was no C subdirectory
	elif (args.language == "java"):
		args.language_root = os.path.join(args.samate_dir, "Java", "src") # test case root for Samate 1.3
		if not os.path.isdir(args.language_root):
			args.language_root = os.path.join(args.samate_dir, "") # in Samate 1.2 there was no Java subdirectory
	else:
		raise Exception("Unknown language.")
	if not os.path.isdir(args.language_root):
		raise Exception("Cannot locate SAMATE language root directory.")

	# compute SAMATE test cases and support directories (and add to `args`, for convenience)
	args.test_cases_dir = os.path.join(args.language_root, "testcases")
	args.test_cases_support_dir = os.path.join(args.language_root, "testcasesupport")
	if not os.path.isdir(args.test_cases_dir):
		raise Exception("Cannot locate SAMATE test cases directory.")
	if not os.path.isdir(args.test_cases_support_dir):
		raise Exception("Cannot locate SAMATE test cases support directory.")

	# ensure temp. object directory exists
	args.object_dir = os.path.join(args.output_dir, "object")
	shutil.rmtree(args.object_dir, ignore_errors = True)
	if not os.path.isdir(args.object_dir):
		os.makedirs(args.object_dir)

	# find gcc / cl (note: if `args.cl` is set, we will use `cl`; otherwise we will use `gcc`)
	if (args.language == "cpp"):
		if args.gcc:
			args.gcc_path = shutil.which(args.gcc)
			if not args.gcc_path:
				raise Exception("Could not locate gcc.")
		if args.cl:
			args.cl_path = shutil.which(args.cl)
			if not args.cl_path:
				raise Exception("Could not locate cl.")
	if (args.language == "java"):
		args.ant_path = shutil.which("ant")
		if not args.ant_path:
			raise Exception("Could not locate ant.")

	# other initialization (the `args` structure is abused to store general configuration)
	args.output_mutex = threading.Semaphore(1)
	args.use_pipe = True
	if args.cl:
		args.use_pipe = False # no such setting

	# find testcases
	# (strictly speaking we're finding / building / reporting test case source files, not test cases; in
	#  some cases there is more than one source file corresponding to a particular test case, e.g. good
	#  and bad variants in separate files)
	time_find_start = time.time()
	print("scanning SAMATE test cases...")
	sys.stdout.flush()
	testcases = find_all_testcases(args)
	print("  found " + str(len(testcases)) + " test sources total")
	if len(testcases) > 0:
		print("    from " + str(testcases[0]))
		print("    to " + str(testcases[len(testcases) - 1]))
	print("")
	time_find_end = time.time()

	# find support files (any that need building)
	if (args.language == "cpp"):
		support_files = [os.path.join(args.test_cases_support_dir, "io.c")]
		if args.cl:
			# std_thread.c uses `__try`, which only builds in cl.
			support_files.append(os.path.join(args.test_cases_support_dir, "std_thread.c"))

	# start building
	original_dir = os.getcwd()
	os.chdir(args.object_dir) # build from the object dir, so that outputs are put there
	time_build_start = time.time()

	# build support files (in a loop, backing off settings each time it fails...)
	if (args.language == "cpp"):
		print("building support files...")
		print("")
		sys.stdout.flush()
		success = False
		while not success:
			try:
				build_source_files(args, support_files)
				success = True
			except:
				# build failed, can we use more conservative settings?
				if args.use_pipe:
					print("trying without `-pipe`...")
					print("")
					args.use_pipe = False
				else:
					# fail
					raise

	# build testcases (ideally in chunks and in parallel)
	print("building test cases (" + str(args.threads) + " thread" + plural(args.threads) + " / " + str(cpu_count) + " CPU" + plural(cpu_count) + ")...")	
	print("")
	sys.stdout.flush()
	if args.threads >= 1:
		jobs = Jobs(args.threads)
	else:
		raise Exception("'threads' argument is non-positive.")
	chunk = []
	chunk_size = 0
	if (args.language == "java"):
		chunk_max = 1 # build one file per call
	else:
		chunk_max = min(50, round(len(testcases) / args.threads)) # build multiple files per call
	for testcase in testcases:
		chunk.append(testcase)
		chunk_size += 1

		if chunk_size >= chunk_max:
			if args.threads == 1:
				# the simple way, for maximum determinism
				build_source_files(args, chunk)
			else:
				# the threaded way, for maximum performance
				jobs.start_job(build_source_files_job(args, chunk))

				if jobs.has_errors(): # stop submitting jobs if we hit an error
					break
			chunk = []
			chunk_size = 0
	if chunk_size >= 1:
		# run final 'remainder' chunk
		if args.threads == 1:
			build_source_files(args, chunk)
		else:
			jobs.start_job(build_source_files_job(args, chunk))
	jobs.wait_jobs()

	# done building
	print("all testcases built.")
	print("")
	time_build_end = time.time()
	os.chdir(original_dir)

	# note: we don't link.  We could, and the SAMATE.bat files provided with the tests do (on Windows),
	#       but we don't need to and it would slow things down.

	# report timings
	time_end = time.time()
	time_total = time_end - time_start
	time_find_total = time_find_end - time_find_start
	time_build_total = time_build_end - time_build_start
	time_accounted_total = time_find_total + time_build_total
	print("total time: " + "{0:.1f}".format(time_total) + "s")
	print("  finding testcases: " + "{0:.1f}".format(time_find_total) + "s")
	print("  building sources: " + "{0:.1f}".format(time_build_total) + "s")
	print("  unaccounted for: " + "{0:.1f}".format(time_total - time_accounted_total) + "s")
	print("")

	print("--- build_samate.py: success! ---")

if __name__ == '__main__':
	main()
