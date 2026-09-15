#!/usr/bin/env python3
"""
GAME language to C compiler.
Translates .gm source to file.c, then compiles it with gcc to produce a binary.
Usage: python3 beam.py input.gm
"""
import sys
import re
import os
import subprocess

lines = []
cp = 0
loopstack = []
outfile = None

def p(s, end='\n'):
    """Write to outfile, mimicking print."""
    global outfile
    outfile.write(s)
    if end:
        outfile.write(end)

def out_header():
    p("#include <stdio.h>")
    p("#include <stdlib.h>")
    p("#include <string.h>")
    p("static short A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z,reminder;")
    p("static unsigned char memory[65536]={0};")
    p("static int tmp;")
    p("int main() {")
    return

def out_tailer():
    p("    return 0;")
    p("}")
    return

def xdigit(c):
    """Return True if c is a hex digit."""
    return c.upper() in '0123456789ABCDEF'

def gethexstr(s, idx):
    d = "0x"
    while idx < len(s) and s[idx] in '0123456789ABCDEF':
        d = d + s[idx]
        idx += 1
    return (d, idx)

def getdcmstr(s, idx):
    d = ""
    while idx < len(s) and s[idx] in "0123456789":
        d = d + s[idx]
        idx += 1
    return (d, idx)

def term(s, idx):
    u = ''
    if idx >= len(s):
        return s, len(s)

    if s[idx] == '(':
        (o, idx) = expression(s, idx + 1)

        if idx < len(s) and s[idx] == ')':
            idx += 1
        return ("(" + o + ")", idx)  # normal end.

    elif s[idx] == '$' and idx + 1 < len(s) and s[idx + 1].upper() in "0123456789ABCDEF":
        (o, idx) = gethexstr(s, idx + 1)
        return (o, idx)

    elif s[idx] in "0123456789":
        (o, idx) = getdcmstr(s, idx)
        return (o, idx)

    elif s[idx] == '-':
        (o, idx) = term(s, idx + 1)
        return "-" + o, idx

    elif s[idx] == '+':
        (o, idx) = term(s, idx + 1)
        return "(+(" + o + "))", idx

    elif s[idx] == '#':
        (o, idx) = term(s, idx + 1)
        return "!(" + o + ")", idx

    elif s[idx] == '\'':
        (o, idx) = term(s, idx + 1)
        u = "(rand()%(" + o + "))"
        return u, idx

    elif s[idx] == '%':
        (o, idx) = term(s, idx + 1)
        u = "(reminder)"
        return u, idx

    elif s[idx] == '$' and (idx + 1 >= len(s) or not xdigit(s[idx + 1])):
        return "getchar()", idx + 1

    elif s[idx] == '"':  # 文字定数
        if idx + 1 < len(s):
            return "'" + s[idx + 1] + "'", idx + 2
        return "''", idx + 1

    elif s[idx] == '?':
        u = "(scanf(\"%d\",&tmp),(short)tmp)"
        return u, idx + 1

    elif s[idx].upper() >= 'A' and s[idx].upper() <= 'Z':
        if (idx + 1) < len(s) and s[idx + 1] == ':':  # 8 bit array
            l = s[idx].upper()
            p_, idx = expression(s, idx + 2)
            o = "memory[" + l + "+" + p_ + "]"
            if idx < len(s) and s[idx] == ')':
                idx += 1
            return o, idx

        elif (idx + 1) < len(s) and s[idx + 1] == '(':  # 16 bit array
            l = s[idx].upper()
            p_, idx = expression(s, idx + 1)
            o = "*((short *)(&memory[" + l + "+(" + p_ + "*2)]))"
            return o, idx

        else:  # variable
            idx += 1
            return (s[idx - 1].upper()), idx
    return s, idx + 1

def expression0(s, idx):
    (o, idx) = term(s, idx)
    w = o
    while True:
        if idx >= len(s):
            break
        if s[idx] == '+':
            op = '+'
            idx += 1
        elif s[idx] == '-':
            op = '-'
            idx += 1
        elif s[idx] == '/':
            op = '/'
            idx += 1
        elif s[idx] == '*':
            op = '*'
            idx += 1
        elif s[idx] == '=':
            op = '=='
            idx += 1
        elif s[idx:idx + 2] == '<>':
            op = '!='
            idx += 2
        elif s[idx:idx + 2] == '<=':
            op = '<='
            idx += 2
        elif s[idx:idx + 2] == '>=':
            op = '>='
            idx += 2
        elif s[idx] == '<':
            op = '<'
            idx += 1
        elif s[idx] == '>':
            op = '>'
            idx += 1
        else:
            break
        (v, idx) = term(s, idx)
        if op == '/':
            return ("((reminder=" + w + "%" + v + "),(short)(" + w + "/" + v + "))", idx)
        w = "(" + w + op + v + ")"
    return w, idx

def expression(s, idx):
    sidx = idx
    (o, idx) = expression0(s, idx)
    if (sidx == idx):
        idx += 1
    return (o, idx)

def value(s, idx):
    return (int(s[idx:]))

def parse(l):
    global loopstack
    index = 0
    while index < len(l):
        s = l[index]
        index += 1

        # Statements

        if s[0:2] == '#=':
            goto(value(s, 2))

        elif s[0:2] == '!=':
            gosub(value(s, 2))

        elif s[0:2] == ';=':
            (o, idx) = expression(s, 2)
            if__(o)

        elif s[0:2] == '?=':
            (o, idx) = expression(s, 2)
            p(f"printf(\"%d\",{o}); ", end='')
        elif s[0:3] == '??=':
            (o, idx) = expression(s, 3)
            p(f"printf(\"%04x\",{o}); ", end='')

        elif s[0:3] == '?$=':
            (o, idx) = expression(s, 3)
            p(f"printf(\"%02x\",{o}); ", end='')

        elif s[0:2] == '$=':
            (o, idx) = expression(s, 2)
            p(f"printf(\"%c\",{o}); ", end='')

        elif s[0:2] == '.=':
            (o, idx) = expression(s, 2)
            p(f"for(int i=0;i<{o};i++) printf(\" \"); ", end='')

        elif s[0:2] == '\'=':
            (o, idx) = expression(s, 2)
            p(f"srand({o}); ", end='')

        elif s[0:2] == '?(':
            o, idx = getdcmstr(s, 2)
            o = int(o)
            if s[idx:idx + 2] == ')=':
                idx += 2
                p_, idx = expression(s, idx)
                p(f"printf(\"%*d\",(short){o},(short){p_}); ", end='')
            else:
                pass
            pass

        elif s[0] == ']':
            ret()

        elif s[0] == '"':
            p(f"printf({s}); ", end='')

        elif s[0] == '/':
            idx = 0
            while idx < len(s) and s[idx] == '/':
                p("printf(\"\\n\"); ", end='')
                idx += 1

        elif s[0].upper() >= 'A' and s[0].upper() <= 'Z':
            if len(s) > 1 and s[1] == ':':  # 8bit array
                ch = s[0].upper()
                v, idx = expression(s, 2)
                if s[idx:idx + 2] == ')=':
                    idx += 2
                    w, idx = expression(s, idx)
                    p("memory[" + ch + "+" + v + "]=", end='')
                    p(f"{w}; ", end='')

            elif len(s) > 1 and s[1] == '(':  # 16 bit array
                ch = s[0].upper()
                v, idx = expression(s, 2)
                if s[idx:idx + 2] == ')=':
                    idx += 2
                    w, idx = expression(s, idx)
                    p("*((short *)(&memory[" + ch + "+" + v + "*2]))=", end='')
                    p(f"{w}; ", end='')

            elif len(s) > 1 and s[1] == '=':  # assignment
                ch = s[0].upper()
                (o, idx) = expression(s, 2)
                p(f"{ch}={o};", end='')
                if idx < len(s) and s[idx] == ',':  # for
                    (p_, idx) = expression(s, idx + 1)
                    p("while(1) { if (!(", end='')

                    try:
                        a, b = eval(o), eval(p_)
                    except:
                        ies = '<'
                    else:
                        ies = '<' if a < b else '>'

                    p(f"{ch}{ies}={p_})) break; ", end='')
                    loopstack += ["for"]
            else:
                pass

        elif s[0:3] == '@=(':
            i = loopstack.pop(-1) if loopstack else None

            if i == "do":  # until
                v, idx = expression(s, 2)
                p("} ", end='')
                p(f"while(!{v}); ", end='')

            elif i == "for":  # next
                ch = s[3].upper() if len(s) > 3 else 'A'
                v, idx = expression(s, 2)
                p(f"{ch}={v}; ", end='')
                p("} ", end='')

        elif s[0:2] == '@=':  # next
            i = loopstack.pop(-1) if loopstack else None
            ch = s[2].upper() if len(s) > 2 else 'A'

            if i == "for":
                v, idx = expression(s, 2)
                p(f"{ch}={v}; ", end='')
                p("} ", end='')

        elif s[0] == '@':  # do
            p("do { ", end='')
            loopstack += ["do"]

        elif s[0:2] == '?=':
            v, idx = expression(s, 2)
            p(f"printf(\"%d\",{v}); ", end='')

        else:
            pass
    return

def adjust_go(n):
    for i in lines:
        if i >= n:
            return i
    return -1

def ret():
    p("__asm__(\"ret\"); ", end='')

def if__(o):
    p(f"if (!({o})) ", end='')
    goto(cp + 1)
    return

def gosub(n):
    p("__asm__ (\"push %rax\"); ", end='')
    p(f"__asm__ goto(\"call %l[l{adjust_go(n)}]\" ::: : l{adjust_go(n)}); ", end="")
    p("__asm__ (\"pop %rax\"); ", end='')
    return

def goto(n):
    if n == -1:
        p("exit(0); ", end='')
        return
    p(f"goto l{adjust_go(n)}; ", end='')
    return

def getl(line):
    ln = line.replace('\n', '')
    split_s = re.split(r'\s+(?=(?:[^"]*"[^"]*")*[^"]*$)', ln)
    s = [i for i in split_s if i]
    try:
        n = int(s[0])
    except:
        return (-1, [""])
    else:
        return (n, s[1:])

def pass1(file):
    global lines
    lines = []
    with open(file, "rt") as f:
        while True:
            l = f.readline()
            if not l:
                break
            (n, s) = getl(l)
            if n == -1:
                pass
            else:
                lines += [n]
    return

def pass2(file):
    global lines, cp
    with open(file, "rt") as f:
        while True:
            l = f.readline()
            if not l:
                break
            (n, s) = getl(l)
            if n == -1:
                pass
            else:
                p(f"l{n}: ", end='')
                cp = n
                if s:
                    parse(s)
                p("")
    return

def compile_to_c(srcfile, cfile="file.c"):
    global outfile
    outfile = open(cfile, "w")
    try:
        out_header()
        pass1(srcfile)
        pass2(srcfile)
        out_tailer()
    finally:
        outfile.close()
        outfile = None
    print(f"Generated C code: {cfile}")
    return cfile

def compile_to_binary(cfile="file.c", binary=None):
    if binary is None:
        binary = "a.out"
    # Use gcc. Need -fgnu-tm or just standard for asm goto? asm goto is supported in gcc.
    # Also may need -no-pie or specific flags if labels issue, but try basic.
    cmd = ["gcc", "-o", binary, cfile, "-O0"]
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("GCC error:")
            print(result.stderr)
            return False
        print(f"Binary created: {binary}")
        # Make executable just in case
        os.chmod(binary, 0o755)
        return True
    except Exception as e:
        print(f"Failed to run gcc: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: beam.py file.gm")
        print("  Translates file.gm -> file.c -> file (executable)")
        sys.exit(1)

    src = sys.argv[1]

    if not os.path.exists(src):
        print(f"Error: source file '{src}' not found")
        sys.exit(1)

    # Generate output filenames based on input filename
    # e.g., fibonacci.gm -> fibonacci.c and fibonacci (binary)
    base_name = os.path.splitext(src)[0]
    cfile = base_name + ".c"
    binary = base_name

    compile_to_c(src, cfile)
    success = compile_to_binary(cfile, binary)
    if success:
        print(f"Success! Run with: ./{binary}")
    else:
        print("Compilation to binary failed.")
        sys.exit(1)

if __name__ == '__main__':
    main()
