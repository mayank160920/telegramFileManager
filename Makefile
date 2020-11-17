test_filesize = 3G
test_args = "noResume" # could also be "resume(1|2)", for testing resuming capability
install_path = /usr/local/bin
package_path = $(shell python -c "import pyrogram;import os;print(os.path.dirname(pyrogram.__file__))")

# this also needs to be modified inside tests.py
tmp_path = ~/.tmp

CFLAGS = -O2 -std=c99 -fPIC -shared

transferHandler_extern.so: src/backend/transferHandler_extern.c
	$(CC) $(CFLAGS) -o $@ $^

bundle: clean transferHandler_extern.so
	pyinstaller src/cli.py --add-data $(package_path)/mime.types:pyrogram \
		--add-data $(package_path)/storage/schema.sql:pyrogram/storage \
		--add-binary transferHandler_extern.so:. --onefile

clean:
	rm -rf src/__pycache__ src/backend/__pycache__ \
		transferHandler_extern.so cli.spec build dist

test: clean transferHandler_extern.so
	echo "Just a heads up this will take around an hour"
	echo "Also it is recommended but not required for any other file up/down"
	echo "progress to be finished before running this test"
	echo "Press enter to continue:"
	read a
	mkdir -p $(tmp_path)/tfilemgr
	mkdir -p downloads
	echo "Generating temp $(test_filesize) file out of random data"
	head -c $(test_filesize) </dev/urandom> $(tmp_path)/tfilemgr/rand
	echo "Starting python program"
	# The reason we start the test in the makefile is to not use
	# system specific commands in the python program so the tests can be
	# easily modified for other systems
	cd src && python tests.py $(test_args)
	echo "Checking if files are the same"
	diff $(tmp_path)/tfilemgr/rand downloads/tfilemk_rand
	echo "Finished test"
	echo "Deleting temporary files"
	rm $(tmp_path)/tfilemgr/rand downloads/tfilemk_rand

install: bundle
	cp dist/cli $(install_path)/tgFileManager

.SILENT: test
