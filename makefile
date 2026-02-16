miep: miep.c gamecomp.py
	gcc -o miep miep.c
	sudo cp miep /usr/local/bin/
	chmod +x gamecomp.py
	sudo cp gamecomp.py /usr/local/bin/gamecomp
