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
  * FOR runs its body at least once and loops while var <= limit, or while
    var >= limit when NEXT decreased the variable (the limit is evaluated once)
  * &n is 1 while the key with key code n is pressed (read from /dev/input/eventN;
    MIEP_KBD selects the device), like miep.c
  * *QU quits, *WT n waits n milliseconds, other * commands (including *FM) are ignored

Portability: when the program uses no *WT command and no & term, the generated
C is strictly conforming standard C (C89 or later) with no machine dependence:
values wrap to 16 bits explicitly, word memory is little endian byte by byte,
addresses wrap to 64KB, division does not depend on the C rounding rule, and
operands with side effects ($ ? ' / %) are evaluated left to right.
The POSIX/evdev key functions are added only when & is used, and the POSIX
wait function only when *WT is used.
"""
import sys
import re
import os
import subprocess
import io

lines = []
cp = 0
loopstack = []
outfile = None
gosub_count = 0     # number of gosub call sites (return-point ids)
RETSTACK_SIZE = 256 # depth of the gosub return stack
FORSTACK_SIZE = 64  # max nesting depth of FOR loops
FORTO_SIZE = 4096   # FOR limits of all active GOSUB levels
need_key = False    # True when & terms are used (POSIX/evdev key input)
need_wait = False   # True when *WT is used (POSIX nanosleep)
tmp_count = 0       # number of temporaries gt[] used for left-to-right order

# Key input device (& term); same behavior as miep.c
KBD_C = r"""
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <termios.h>
#include <unistd.h>
#include <sys/ioctl.h>
#ifdef __linux__
#include <linux/input.h>
#else
#include <dev/evdev/input.h>
#endif
#define KBD_MAX 16
static int kbdFd[KBD_MAX];
static int kbdCount=-1;
static unsigned char keyState[KEY_CNT];  /* bit0: held, bit1: pressed since last check */
static struct termios ttySaved;
static int ttyChanged=0;
static void ttyRestore(void) {
    if (ttyChanged) { tcflush(0,TCIFLUSH); tcsetattr(0,TCSANOW,&ttySaved); ttyChanged=0; }
}
static void kbdSignal(int sig) { ttyRestore(); signal(sig,SIG_DFL); raise(sig); }
static int isKeyboard(int fd) {
    unsigned long bits[KEY_CNT/(8*sizeof(long))+1];
    size_t w=8*sizeof(long);
    memset(bits,0,sizeof(bits));
    if (ioctl(fd,EVIOCGBIT(EV_KEY,sizeof(bits)),bits)<0) return 0;
    return ((bits[KEY_A/w]>>(KEY_A%w))&1) && ((bits[KEY_Z/w]>>(KEY_Z%w))&1) &&
           ((bits[KEY_ENTER/w]>>(KEY_ENTER%w))&1);
}
static void kbdOpen(void) {
    const char *dev=getenv("MIEP_KBD");
    char path[64];
    int i,fd,denied=0;
    kbdCount=0;
    if (dev!=NULL && *dev!='\0') {
        fd=open(dev,O_RDONLY|O_NONBLOCK);
        if (fd<0) { fprintf(stderr,"%s: %s\n",dev,strerror(errno)); exit(1); }
        kbdFd[kbdCount++]=fd;
    } else {
        for (i=0;i<64 && kbdCount<KBD_MAX;i++) {
            snprintf(path,sizeof(path),"/dev/input/event%d",i);
            fd=open(path,O_RDONLY|O_NONBLOCK);
            if (fd<0) { if (errno==EACCES) denied=1; continue; }
            if (isKeyboard(fd)) kbdFd[kbdCount++]=fd; else close(fd);
        }
        if (kbdCount==0) {
            fprintf(stderr,denied ? "/dev/input/event*: Permission denied\n"
                                  : "No keyboard found in /dev/input/event*\n");
            exit(1);
        }
    }
    if (isatty(0) && tcgetattr(0,&ttySaved)==0) {
        struct termios t=ttySaved;
        t.c_lflag&=~(ECHO|ICANON);
        tcsetattr(0,TCSANOW,&t);
        ttyChanged=1;
        atexit(ttyRestore);
        signal(SIGINT,kbdSignal); signal(SIGTERM,kbdSignal); signal(SIGHUP,kbdSignal);
    }
}
static int game_key(int code) {
    struct input_event ev;
    int i,v;
    if (kbdCount<0) kbdOpen();
    for (i=0;i<kbdCount;i++) {
        while (read(kbdFd[i],&ev,sizeof(ev))==(ssize_t)sizeof(ev)) {
            if (ev.type==EV_KEY && ev.code<KEY_CNT) {
                if (ev.value!=0) keyState[ev.code]|=3; else keyState[ev.code]&=~1;
            }
        }
    }
    if (code<0 || code>=KEY_CNT) return 0;
    v=(keyState[code]!=0);
    keyState[code]&=~2;
    return v;
}
"""

# *WT n: wait n milliseconds
WAIT_C = r"""
static void game_wait(int ms) {
    struct timespec ts;
    fflush(stdout);
    if (ms<=0) return;
    ts.tv_sec=ms/1000;
    ts.tv_nsec=(long)(ms%1000)*1000000L;
    nanosleep(&ts,NULL);
}
"""


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
    if need_key:
        p(KBD_C)
    if need_wait:
        p(WAIT_C)
    # all values are int in -32768..32767 (int has at least 16 bits)
    p("static int A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z,reminder;")
    p("static unsigned char memory[65536];")
    p("static int tmp,ga,gw,gp;")
    if tmp_count:
        p(f"static int gt[{tmp_count}];")
    p(f"static int retstack[{RETSTACK_SIZE}];")
    p("static int retsp=0;")
    # FOR limits: forto[fbase+depth]; a GOSUB moves fbase past the FOR loops
    # open at the call site so that loops in the subroutine do not overwrite them
    p(f"static int forto[{FORTO_SIZE}];")
    p("static int fbase=0;")
    p(f"static int fbstack[{RETSTACK_SIZE}];")
    p("static void gosub_push(int k,int d) {")
    p(f"    if (retsp>={RETSTACK_SIZE} || fbase+d>{FORTO_SIZE - FORSTACK_SIZE}) {{ fprintf(stderr,\"gosub stack overflow\\n\"); exit(1); }}")
    p("    fbstack[retsp]=fbase;")
    p("    retstack[retsp++]=k;")
    p("    fbase+=d;")
    p("}")
    # wrap to a 16 bit two's complement value without implementation-defined conversions
    p("static int w16(long v) {")
    p("    unsigned long u=(unsigned long)v&0xFFFFUL;")
    p("    return u>=0x8000UL ? (int)((long)u-65536L) : (int)u;")
    p("}")
    p("static unsigned gaddr(long a) {")
    p("    return (unsigned)((unsigned long)a&0xFFFFUL);")
    p("}")
    p("static int gneg(int a) {")
    p("    return w16(-(long)a);")
    p("}")
    p("static int gabs(int a) {")
    p("    return a<0 ? gneg(a) : a;")
    p("}")
    # 16 bit memory access, little endian (same as miep.c)
    p("static int peekw(long a) {")
    p("    unsigned ad=gaddr(a);")
    p("    return w16((long)memory[ad]|((long)memory[gaddr(ad+1L)]<<8));")
    p("}")
    p("static void pokeb(long a,int v) {")
    p("    memory[gaddr(a)]=(unsigned char)((unsigned)v&0xFFu);")
    p("}")
    p("static void pokew(long a,int v) {")
    p("    unsigned ad=gaddr(a);")
    p("    memory[ad]=(unsigned char)((unsigned)v&0xFFu);")
    p("    memory[gaddr(ad+1L)]=(unsigned char)(((unsigned)v>>8)&0xFFu);")
    p("}")
    p("static int input_num(void) {")
    p("    char buf[256];")
    p("    int c;")
    p("    fflush(stdout);")
    p("    if (fgets(buf,(int)sizeof(buf),stdin)==NULL) return 0;")
    p("    if (strchr(buf,'\\n')==NULL) while ((c=getchar())!='\\n' && c!=EOF);")
    p("    return w16(strtol(buf,NULL,10));")
    p("}")
    # read one character (output is flushed first, like the interpreter)
    p("static int game_getch(void) {")
    p("    int c;")
    p("    fflush(stdout);")
    p("    c=getchar();")
    p("    return c==EOF ? 0 : c;")
    p("}")
    # division with remainder, Python-style (same as the interpreter);
    # computed on non-negative operands so C's rounding rule does not matter
    p("static int gdiv(int a,int b) {")
    p("    long x=a,y=b,q,r;")
    p("    if (y==0) { printf(\"Division by zero\\n\"); return -1; }")
    p("    q=(x<0 ? -x : x)/(y<0 ? -y : y);")
    p("    if ((x<0)!=(y<0)) q=-q;")
    p("    r=x-q*y;")
    p("    if (r!=0 && ((r<0)!=(y<0))) { r+=y; q--; }")
    p("    reminder=w16(r);")
    p("    return w16(q);")
    p("}")
    # random number 0..n-1 (0 when n<=0)
    p("static int grand(int n) {")
    p("    return n>0 ? rand()%n : 0;")
    p("}")
    p("int main(void) {")
    p("    time_t now=time(NULL);")
    p("    unsigned seed=0;")
    p("    size_t i;")
    p("    for (i=0;i<sizeof(now);i++) seed=seed*31u+((unsigned char *)&now)[i];")
    p("    srand(seed);")
    return


def out_tailer():
    p("    return 0;")
    # Return dispatcher: pop a return-point id and jump to its label.
    p("game_return:")
    p("    if (retsp<=0) exit(0);")
    p("    fbase=fbstack[--retsp];")
    p("    switch (retstack[retsp]) {")
    for k in range(gosub_count):
        p(f"    case {k}: goto r{k};")
    p("    }")
    p("    exit(0);")
    p("}")
    return


def xdigit(c):
    """Return True if c is a hex digit."""
    return c.upper() in '0123456789ABCDEF'


def cint(v):
    """C literal for v wrapped to a signed 16 bit value."""
    v &= 0xFFFF
    if v >= 0x8000:
        v -= 0x10000
    if v == -32768:
        return "(-32767-1)"
    return f"({v})" if v < 0 else str(v)


def new_tmp():
    global tmp_count
    k = tmp_count
    tmp_count += 1
    return f"gt[{k}]"


def gethexstr(s, idx):
    d = ""
    while idx < len(s) and s[idx].upper() in '0123456789ABCDEF':
        d = d + s[idx]
        idx += 1
    return (cint(int(d, 16)), idx)


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
    """Returns (C code, next index, impure). impure: has side effects or reads %."""
    global need_key
    if idx >= len(s):
        return "0", len(s), False

    if s[idx] == '(':
        (o, idx, imp) = expr3(s, idx + 1)
        if idx < len(s) and s[idx] == ')':
            idx += 1
        return ("(" + o + ")", idx, imp)

    elif s[idx] == '$' and idx + 1 < len(s) and xdigit(s[idx + 1]):
        (o, idx) = gethexstr(s, idx + 1)
        return (o, idx, False)

    elif s[idx] in "0123456789":
        (o, idx) = getdcmstr(s, idx)
        return (cint(int(o)), idx, False)

    elif s[idx] == '-':
        (o, idx, imp) = term(s, idx + 1)
        return "gneg(" + o + ")", idx, imp

    elif s[idx] == '+':                       # abs
        (o, idx, imp) = term(s, idx + 1)
        return "gabs(" + o + ")", idx, imp

    elif s[idx] == '#':                       # not
        (o, idx, imp) = term(s, idx + 1)
        return "(!(" + o + "))", idx, imp

    elif s[idx] == '\'':                      # random
        (o, idx, imp) = term(s, idx + 1)
        return "grand(" + o + ")", idx, True

    elif s[idx] == '%':                       # remainder
        (o, idx, imp) = term(s, idx + 1)
        return "(reminder)", idx, True

    elif s[idx] == '&':                       # key state
        need_key = True
        (o, idx, imp) = term(s, idx + 1)
        return "game_key(" + o + ")", idx, True

    elif s[idx] == '$':                       # getch
        return "game_getch()", idx + 1, True

    elif s[idx] == '"':                       # character constant (1 or 2 chars)
        j = s.find('"', idx + 1)
        if j < 0:
            j = len(s)
        body = s[idx + 1:j]
        v = (ord(body[0]) if len(body) > 0 else 0) + ((ord(body[1]) * 256) if len(body) > 1 else 0)
        return cint(v), min(j + 1, len(s)), False

    elif s[idx] == '?':
        return "input_num()", idx + 1, True

    elif s[idx].isalpha():
        l = s[idx].upper()
        nidx = skip_alpha(s, idx)
        if nidx < len(s) and s[nidx] == ':':  # 8 bit array
            p_, idx, imp = expr3(s, nidx + 1)
            if idx < len(s) and s[idx] == ')':
                idx += 1
            return "memory[gaddr((long)" + l + "+(" + p_ + "))]", idx, imp

        elif nidx < len(s) and s[nidx] == '(':  # 16 bit array
            p_, idx, imp = expr3(s, nidx + 1)
            if idx < len(s) and s[idx] == ')':
                idx += 1
            return "peekw((long)" + l + "+2L*(" + p_ + "))", idx, imp

        else:  # variable
            return l, nidx, False
    return "0", idx + 1, False


def binop(op, w, v):
    if op == '/':
        return "gdiv(" + w + "," + v + ")"   # continue with the next operator
    if op in '+-*':
        return "w16((long)(" + w + ")" + op + "(" + v + "))"
    return "((" + w + ")" + op + "(" + v + "))"


def expression0(s, idx):
    (w, idx, wimp) = term(s, idx)
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
        (v, idx, vimp) = term(s, idx)
        if wimp and vimp:
            # C leaves the operand order unspecified: store the left side first
            t = new_tmp()
            w = "(" + t + "=" + w + "," + binop(op, t, v) + ")"
        else:
            w = binop(op, w, v)
        wimp = wimp or vimp or op == '/'
    return w, idx, wimp


def expr3(s, idx):
    sidx = idx
    (o, idx, imp) = expression0(s, idx)
    if sidx == idx:
        idx += 1
    return (o, idx, imp)


def expression(s, idx):
    (o, idx, imp) = expr3(s, idx)
    return (o, idx)


def c_string(body):
    """Make a C string literal from GAME string contents.
    Characters outside C's basic character set are written as octal escapes
    and ? is escaped so that no trigraph can appear."""
    out = []
    for b in body.encode('utf-8'):
        c = chr(b)
        if c in '\\"?':
            out.append('\\' + c)
        elif 0x20 <= b < 0x7f and c not in '$@`':
            out.append(c)
        else:
            out.append('\\%03o' % b)
    return '"' + ''.join(out) + '"'


def statement(s):
    """Compile one statement at the head of s. Returns the index after it."""
    global loopstack, need_wait

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
        p(f"printf(\"%04x\",(unsigned)({o})&0xFFFFu); ", end='')
        return idx

    if s[0:3] == '?$=':
        (o, idx) = expression(s, 3)
        p(f"printf(\"%02x\",(unsigned)({o})&0xFFu); ", end='')
        return idx

    if s[0:2] == '?(':
        w, idx, wimp = expr3(s, 2)
        if s[idx:idx + 2] == ')=':
            idx += 2
        elif s[idx:idx + 1] == '=':
            idx += 1
        v, idx, vimp = expr3(s, idx)
        if wimp and vimp:
            p(f"gw={w}; ", end='')
            w = "gw"
        p(f"printf(\"%*d\",({w}),({v})); ", end='')
        return idx

    if s[0:2] == '?=':
        (o, idx) = expression(s, 2)
        p(f"printf(\"%d\",({o})); ", end='')
        return idx

    if s[0:2] == '$=':
        (o, idx) = expression(s, 2)
        p(f"putchar((unsigned char)({o})); ", end='')
        return idx

    if s[0:2] == '.=':
        (o, idx) = expression(s, 2)
        p(f"gw={o}; for(tmp=0;tmp<gw;tmp++) putchar(' '); ", end='')
        return idx

    if s[0:2] == '\'=':
        (o, idx) = expression(s, 2)
        p(f"srand((unsigned)({o})); ", end='')
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
        elif cmd == 'WT':          # wait n milliseconds
            need_wait = True
            (o, idx) = expression(s, 3)
            p(f"game_wait({o}); ", end='')
        elif cmd == 'FM':          # FOR mode is not supported: ignored
            (o, idx) = expression(s, 3)
            p(f"(void)({o}); ", end='')
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
            v, idx, vimp = expr3(s, i + 1)
            if s[idx:idx + 2] == ')=':
                idx += 2
            w, idx, wimp = expr3(s, idx)
            if vimp and wimp:
                p(f"ga={v}; ", end='')
                v = "ga"
            p(f"pokeb((long){ch}+({v}),{w}); ", end='')
            return idx

        if s[i:i + 1] == '(':                             # 16 bit array
            v, idx, vimp = expr3(s, i + 1)
            if s[idx:idx + 2] == ')=':
                idx += 2
            w, idx, wimp = expr3(s, idx)
            if vimp and wimp:
                p(f"ga={v}; ", end='')
                v = "ga"
            p(f"pokew((long){ch}+2L*({v}),{w}); ", end='')
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
                p(f"forto[fbase+{d}]={to}; ", end='')
                p("do { ", end='')
                loopstack.append(("for", ch, d))
            return idx

    print(f"warning: line {cp}: cannot parse '{s}'")
    return len(s)


def close_for(kind, v):
    ch, d = kind[1], kind[2]
    p(f"gp={ch}; {ch}={v}; }} while({ch}<gp ? {ch}>=forto[fbase+{d}] : {ch}<=forto[fbase+{d}]); ", end='')


def parse(l):
    l = list(l)
    k = 0
    while k < len(l):
        s = l[k]
        k += 1
        # *WT n / *FM n: the argument is written after a space
        if len(s) == 3 and s[0] == '*' and s[1:].upper() in ('WT', 'FM') and k < len(l):
            s += l[k]
            k += 1
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
    d = sum(1 for e in loopstack if e[0] == "for")
    p(f"gosub_push({k},{d}); ", end='')
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
    global outfile, gosub_count, loopstack, need_key, need_wait, tmp_count
    gosub_count = 0
    loopstack = []
    need_key = False
    need_wait = False
    tmp_count = 0
    # compile the body first: the header depends on what the body uses
    outfile = io.StringIO()
    pass1(srcfile)
    pass2(srcfile)
    body = outfile.getvalue()
    outfile = open(cfile, "w", encoding="utf-8")
    try:
        out_header()
        p(body, end='')
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
