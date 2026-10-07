#!/usr/bin/env python3
"""
GAME language to C compiler.
Translates .gm source to file.c, then compiles it with gcc to produce a binary.
Usage: python3 beam.py input.gm

Semantics follow the miep.py interpreter:
  * several statements may be written without spaces ($=27"[H" ... "abc"/)
  * expressions are evaluated strictly left to right (no precedence)
  * unary + is abs(), ' is random (0..n-1), % is the last remainder
  * '/' keeps the remainder and the expression continues after it
  * FOR runs its body at least once and loops while var <= limit
    (the limit is evaluated once); *FM1 enables skipping when start > limit
  * *QU quits, *FM sets FOR mode, other * commands are ignored
"""
import sys
import re
import os
import subprocess

lines = []
cp = 0
loopstack = []
outfile = None
gosub_count = 0     # number of gosub call sites (return-point ids)
RETSTACK_SIZE = 256 # depth of the gosub return stack
FORSTACK_SIZE = 64  # max nesting depth of FOR loops


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
    p("#include <time.h>")
    p("static short A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z,reminder;")
    p("static unsigned char memory[65536]={0};")
    p("static int tmp;")
    p(f"static int retstack[{RETSTACK_SIZE}];")
    p("static int retsp=0;")
    p(f"static int forto[{FORSTACK_SIZE}];")
    p("static int formode=0;")
    p("static void gosub_errchk(void) {")
    p(f"    if (retsp>={RETSTACK_SIZE}) {{ fprintf(stderr,\"gosub stack overflow\\n\"); exit(1); }}")
    p("}")
    p("static short input_num(void) {")
    p("    int c;")
    p("    tmp=0;")
    p("    fflush(stdout);")
    p("    if (scanf(\"%d\",&tmp)==EOF) return 0;")
    p("    while ((c=getchar())!='\\n' && c!=EOF);")
    p("    return (short)tmp;")
    p("}")
    # read one character (output is flushed first, like the interpreter)
    p("static short game_getch(void) {")
    p("    int c;")
    p("    fflush(stdout);")
    p("    c=getchar();")
    p("    return (short)(c==EOF ? 0 : c);")
    p("}")
    # division with remainder, Python-style (same as the interpreter)
    p("static short gdiv(int a,int b) {")
    p("    int q,r;")
    p("    if (b==0) { printf(\"Division by zero\\n\"); return -1; }")
    p("    q=a/b; r=a%b;")
    p("    if (r!=0 && ((r<0)!=(b<0))) { r+=b; q--; }")
    p("    reminder=(short)r;")
    p("    return (short)q;")
    p("}")
    # random number 0..n-1 (0 when n<=0)
    p("static short grand(int n) {")
    p("    return (short)(n>0 ? rand()%n : 0);")
    p("}")
    p("int main() {")
    p("    srand((unsigned)time(NULL));")
    return


def out_tailer():
    p("    return 0;")
    # Return dispatcher: pop a return-point id and jump to its label.
    p("game_return:")
    p("    if (retsp<=0) exit(0);")
    p("    switch (retstack[--retsp]) {")
    for k in range(gosub_count):
        p(f"    case {k}: goto r{k};")
    p("    }")
    p("    exit(0);")
    p("}")
    return


def xdigit(c):
    """Return True if c is a hex digit."""
    return c.upper() in '0123456789ABCDEF'


def gethexstr(s, idx):
    d = "0x"
    while idx < len(s) and s[idx].upper() in '0123456789ABCDEF':
        d = d + s[idx]
        idx += 1
    return (d, idx)


def getdcmstr(s, idx):
    d = ""
    while idx < len(s) and s[idx] in "0123456789":
        d = d + s[idx]
        idx += 1
    return (d, idx)


def skip_alpha(s, idx):
    """Variable names may be longer than one letter; only the first counts."""
    while idx < len(s) and s[idx].isalpha():
        idx += 1
    return idx


def term(s, idx):
    if idx >= len(s):
        return "0", len(s)

    if s[idx] == '(':
        (o, idx) = expression(s, idx + 1)
        if idx < len(s) and s[idx] == ')':
            idx += 1
        return ("(" + o + ")", idx)

    elif s[idx] == '$' and idx + 1 < len(s) and xdigit(s[idx + 1]):
        (o, idx) = gethexstr(s, idx + 1)
        return (o, idx)

    elif s[idx] in "0123456789":
        (o, idx) = getdcmstr(s, idx)
        return (o, idx)

    elif s[idx] == '-':
        (o, idx) = term(s, idx + 1)
        return "(-(" + o + "))", idx

    elif s[idx] == '+':                       # abs
        (o, idx) = term(s, idx + 1)
        return "abs(" + o + ")", idx

    elif s[idx] == '#':                       # not
        (o, idx) = term(s, idx + 1)
        return "(!(" + o + "))", idx

    elif s[idx] == '\'':                      # random
        (o, idx) = term(s, idx + 1)
        return "grand(" + o + ")", idx

    elif s[idx] == '%':                       # remainder
        (o, idx) = term(s, idx + 1)
        return "(reminder)", idx

    elif s[idx] == '$':                       # getch
        return "game_getch()", idx + 1

    elif s[idx] == '"':                       # character constant (1 or 2 chars)
        j = s.find('"', idx + 1)
        if j < 0:
            j = len(s)
        body = s[idx + 1:j]
        v = (ord(body[0]) if len(body) > 0 else 0) + ((ord(body[1]) * 256) if len(body) > 1 else 0)
        return str(v & 0xFFFF), min(j + 1, len(s))

    elif s[idx] == '?':
        return "input_num()", idx + 1

    elif s[idx].isalpha():
        l = s[idx].upper()
        nidx = skip_alpha(s, idx)
        if nidx < len(s) and s[nidx] == ':':  # 8 bit array
            p_, idx = expression(s, nidx + 1)
            if idx < len(s) and s[idx] == ')':
                idx += 1
            return "memory[" + l + "+(" + p_ + ")]", idx

        elif nidx < len(s) and s[nidx] == '(':  # 16 bit array
            p_, idx = expression(s, nidx + 1)
            if idx < len(s) and s[idx] == ')':
                idx += 1
            return "*((short *)(&memory[" + l + "+(" + p_ + ")*2]))", idx

        else:  # variable
            return l, nidx
    return "0", idx + 1


def expression0(s, idx):
    (w, idx) = term(s, idx)
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
            w = "gdiv(" + w + "," + v + ")"   # continue with the next operator
        else:
            w = "(" + w + op + v + ")"
    return w, idx


def expression(s, idx):
    sidx = idx
    (o, idx) = expression0(s, idx)
    if sidx == idx:
        idx += 1
    return (o, idx)


def c_string(body):
    """Make a C string literal from GAME string contents."""
    return '"' + body.replace('\\', '\\\\').replace('"', '\\"') + '"'


def statement(s):
    """Compile one statement at the head of s. Returns the index after it."""
    global loopstack

    if s[0:2] == '#=':                                    # GOTO
        if s[2:3] == '-':
            o, idx = getdcmstr(s, 3)
            goto(-1)
        else:
            o, idx = getdcmstr(s, 2)
            goto(int(o) if o else 0)
        return idx

    if s[0:2] == '!=':                                    # GOSUB
        o, idx = getdcmstr(s, 2)
        gosub(int(o) if o else 0)
        return idx

    if s[0:2] == ';=':                                    # IF
        (o, idx) = expression(s, 2)
        if__(o)
        return idx

    if s[0:3] == '??=':
        (o, idx) = expression(s, 3)
        p(f"printf(\"%04x\",(unsigned short)({o})); ", end='')
        return idx

    if s[0:3] == '?$=':
        (o, idx) = expression(s, 3)
        p(f"printf(\"%02x\",(unsigned char)({o})); ", end='')
        return idx

    if s[0:2] == '?(':
        w, idx = expression(s, 2)
        if s[idx:idx + 2] == ')=':
            idx += 2
        elif s[idx:idx + 1] == '=':
            idx += 1
        v, idx = expression(s, idx)
        p(f"printf(\"%*d\",(int)({w}),(short)({v})); ", end='')
        return idx

    if s[0:2] == '?=':
        (o, idx) = expression(s, 2)
        p(f"printf(\"%d\",(short)({o})); ", end='')
        return idx

    if s[0:2] == '$=':
        (o, idx) = expression(s, 2)
        p(f"putchar((unsigned char)({o})); ", end='')
        return idx

    if s[0:2] == '.=':
        (o, idx) = expression(s, 2)
        p(f"for(tmp=0;tmp<({o});tmp++) putchar(' '); ", end='')
        return idx

    if s[0:2] == '\'=':
        (o, idx) = expression(s, 2)
        p(f"srand({o}); ", end='')
        return idx

    if s[0] == ']':                                       # RETURN
        ret()
        return 1

    if s[0] == '"':                                       # print string
        j = s.find('"', 1)
        if j < 0:
            j = len(s)
        p(f"fputs({c_string(s[1:j])},stdout); ", end='')
        return min(j + 1, len(s))

    if s[0] == '/':                                       # newline
        p("putchar('\\n'); ", end='')
        return 1

    if s[0] == '*':                                       # optional commands
        cmd = s[1:3].upper()
        idx = 3
        if cmd == 'QU':
            p("fflush(stdout); exit(0); ", end='')
        elif cmd == 'FM':
            (o, idx) = expression(s, 3)
            p(f"formode={o}; ", end='')
        else:
            idx = len(s)   # TN/TF/LD/SH: not supported when compiled
        return idx

    if s[0:3] == '@=(':                                   # UNTIL
        kind = loopstack.pop(-1) if loopstack else ("do", None)
        v, idx = expression(s, 2)
        if kind[0] == "do":
            p(f"}} while(!({v})); ", end='')
        else:
            close_for(kind, v)
        return idx

    if s[0:2] == '@=':                                    # NEXT
        kind = loopstack.pop(-1) if loopstack else ("for", s[2:3].upper() or 'A')
        v, idx = expression(s, 2)
        if kind[0] == "for":
            close_for(kind, v)
        else:
            p(f"}} while(!({v})); ", end='')
        return idx

    if s[0] == '@':                                       # DO
        p("do { ", end='')
        loopstack.append(("do", None))
        return 1

    if s[0].isalpha():
        ch = s[0].upper()
        i = skip_alpha(s, 0)
        if s[i:i + 1] == ':':                             # 8 bit array
            v, idx = expression(s, i + 1)
            if s[idx:idx + 2] == ')=':
                idx += 2
            w, idx = expression(s, idx)
            p(f"memory[{ch}+({v})]=({w}); ", end='')
            return idx

        if s[i:i + 1] == '(':                             # 16 bit array
            v, idx = expression(s, i + 1)
            if s[idx:idx + 2] == ')=':
                idx += 2
            w, idx = expression(s, idx)
            p(f"*((short *)(&memory[{ch}+({v})*2]))=({w}); ", end='')
            return idx

        if s[i:i + 1] == '=':                             # assignment
            (o, idx) = expression(s, i + 1)
            p(f"{ch}={o}; ", end='')
            if idx < len(s) and s[idx] == ',':            # FOR
                (to, idx) = expression(s, idx + 1)
                d = sum(1 for k in loopstack if k[0] == "for")
                if d >= FORSTACK_SIZE:
                    print("FOR nesting too deep")
                    sys.exit(1)
                p(f"forto[{d}]={to}; ", end='')
                p(f"if (!(formode && {ch}>forto[{d}])) do {{ ", end='')
                loopstack.append(("for", ch, d))
            return idx

    print(f"warning: line {cp}: cannot parse '{s}'")
    return len(s)


def close_for(kind, v):
    ch, d = kind[1], kind[2]
    p(f"{ch}={v}; }} while({ch}<=forto[{d}]); ", end='')


def parse(l):
    for s in l:
        while s:
            idx = statement(s)
            if idx <= 0:
                idx = 1
            s = s[idx:]
    return


def adjust_go(n):
    for i in lines:
        if i >= n:
            return i
    return -1


def ret():
    p("goto game_return; ", end='')


def if__(o):
    p(f"if (!({o})) ", end='')
    goto(cp + 1)
    return


def gosub(n):
    global gosub_count
    k = gosub_count
    gosub_count += 1
    p("gosub_errchk(); ", end='')
    p(f"retstack[retsp++]={k}; ", end='')
    goto(n)
    p(f"r{k}: ; ", end='')
    return


def goto(n):
    if n == -1 or adjust_go(n) == -1:
        p("{ fflush(stdout); exit(0); } ", end='')
        return
    p(f"goto l{adjust_go(n)}; ", end='')
    return


def getl(line):
    ln = line.replace('\n', '').replace('\r', '')
    split_s = re.split(r'\s+(?=(?:[^"]*"[^"]*")*[^"]*$)', ln)
    s = [i for i in split_s if i]
    try:
        n = int(s[0])
    except Exception:
        return (-1, [""])
    else:
        return (n, s[1:])


def pass1(file):
    global lines
    lines = []
    with open(file, "rt", encoding="utf-8") as f:
        for l in f:
            (n, s) = getl(l)
            if n != -1:
                lines += [n]
    return


def pass2(file):
    global cp
    with open(file, "rt", encoding="utf-8") as f:
        for l in f:
            (n, s) = getl(l)
            if n != -1:
                p(f"l{n}: ; ", end='')
                cp = n
                if s:
                    parse(s)
                p("")
    return


def compile_to_c(srcfile, cfile="file.c"):
    global outfile, gosub_count, loopstack
    gosub_count = 0
    loopstack = []
    outfile = open(cfile, "w", encoding="utf-8")
    try:
        out_header()
        pass1(srcfile)
        pass2(srcfile)
        out_tailer()
    finally:
        outfile.close()
        outfile = None
    if loopstack:
        print(f"warning: {len(loopstack)} loop(s) not closed")
    print(f"Generated C code: {cfile}")
    return cfile


def compile_to_binary(cfile="file.c", binary=None):
    if binary is None:
        binary = "a.out"
    cmd = ["gcc", "-o", binary, cfile, "-O0"]
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("GCC error:")
            print(result.stderr)
            return False
        print(f"Binary created: {binary}")
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
