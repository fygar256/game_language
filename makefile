miep: miep.c beam.py
	gcc -o miep miep.c
	sudo cp miep /usr/local/bin/
	chmod +x beam.py
	sudo cp beam.py /usr/local/bin/beam
