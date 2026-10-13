#!/usr/bin/env python3
"""
miep.py - MIEP interpreter (Python port of miep.c)
"""

import random
import sys
import time

STACK_MAX = 65536

LONG_MAX = (1 << 63) - 1
LONG_MIN = -(1 << 63)


# ---- 整数ヘルパ ----

def i16(x):
    """int16_t へのキャスト"""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def c_div(a, b):
    """C の整数除算（0 方向への切り捨て）"""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def c_mod(a, b):
    """C の剰余（被除数の符号に従う）"""
    return a - b * c_div(a, b)


def is_alpha(c):
    return 97 <= c <= 122 or 65 <= c <= 90


def is_digit(c):
    return 48 <= c <= 57


def is_xdigit(c):
    return 48 <= c <= 57 or 97 <= c <= 102 or 65 <= c <= 70


def to_upper(c):
    if 97 <= c <= 122:
        return c - 32
    return c


def strtol(b, base):
    """C の strtol 相当（先頭空白・符号・0x 接頭辞・オーバーフロー時の飽和）"""
    n = len(b)
    i = 0
    while i < n and b[i] in b" \t\n\v\f\r":
        i += 1
    neg = False
    if i < n and b[i] in b"+-":
        neg = b[i] == 45
        i += 1
    if (base == 16 and i + 2 < n and b[i] == 48 and b[i + 1] in b"xX"
            and is_xdigit(b[i + 2])):
        i += 2
    val = 0
    while i < n:
        c = b[i]
        if is_digit(c):
            d = c - 48
        elif base == 16 and is_xdigit(c):
            d = to_upper(c) - 65 + 10
        else:
            break
        if d >= base:
            break
        val = val * base + d
        i += 1
    if neg:
        val = -val
    if val > LONG_MAX:
        val = LONG_MAX
    elif val < LONG_MIN:
        val = LONG_MIN
    return val


# ---- インタプリタ状態 ----

class Miep:
    def __init__(self):
        self.variables = [0] * 26        # A-Z 変数
        self.memory = bytearray(65536)   # 64KB メモリ
        self.pbuff = b""                 # プログラムバッファ
        self.psize = 0                   # プログラムサイズ
        self.s = b""                     # 現在の解析対象文字列
        self.slen = 0                    # s の長さ
        self.pos = 0                     # s 内の現在位置
        self.ln = 0                      # 現在行番号
        self.stack = [None] * STACK_MAX  # ランタイムスタック
        self.sp = 0                      # スタックポインタ（要素数）
        self.tron = 0                    # トレースモード
        self.mod = 0                     # 剰余結果
        self.forMode = 0                 # FOR ループモード
        self.out = sys.stdout.buffer
        self.inp = sys.stdin.buffer

    # ---- 入出力ヘルパ ----

    def write(self, data):
        self.out.write(data)

    def flush(self):
        self.out.flush()

    def readByteOrZero(self):
        """getch / 行入力用の小ヘルパ"""
        self.flush()
        ch = self.inp.read(1)
        return ch[0] if ch else 0

    # ---- 文字操作ヘルパ ----

    def currentChar(self):
        """現在の文字を返す"""
        if self.pos < self.slen:
            return self.s[self.pos]
        return 0

    def advance(self, count):
        """位置を前進させる"""
        self.pos += count

    def peek(self, offset):
        """先読みする"""
        if self.pos + offset < self.slen:
            return self.s[self.pos + offset]
        return 0

    def skipSpaces(self):
        """空白を読み飛ばす"""
        while self.currentChar() == 32:
            self.pos += 1

    def syntaxError(self):
        """構文エラーを報告する"""
        self.write(b"\nSyntaxerror in %d" % self.ln)
        self.flush()

    def skipChar(self, c):
        """期待する文字を読み飛ばす"""
        if self.currentChar() == c:
            self.pos += 1
            return
        self.syntaxError()

    # ---- 演算子・トークン取得 ----

    def getOperator2(self):
        """二項演算子を取得"""
        c = self.currentChar()
        if c in (61, 43, 45, 42, 47):      # = + - * /
            self.pos += 1
            return c
        if c == 60:                         # <
            self.pos += 1
            if self.currentChar() == 62:
                self.pos += 1
                return 78                   # 'N' 不等
            elif self.currentChar() == 61:
                self.pos += 1
                return 65                   # 'A' 以下
            return 60
        if c == 62:                         # >
            self.pos += 1
            if self.currentChar() == 61:
                self.pos += 1
                return 66                   # 'B' 以上
            return 62
        return 0

    def getOperator1(self):
        """単項演算子を取得"""
        c = self.currentChar()
        if c in (43, 45, 39, 35, 37):      # + - ' # %
            self.pos += 1
            return c
        return 0

    def getVariable(self):
        """変数名を取得（先頭1文字を返し、連続する英字を読み飛ばす）"""
        c = 0
        if is_alpha(self.currentChar()):
            c = self.currentChar()
            while self.pos < self.slen and is_alpha(self.s[self.pos]):
                self.pos += 1
        return c

    def getHexValue(self):
        """16進数を解析"""
        val = 0
        if not is_xdigit(self.currentChar()):
            return -1
        while is_xdigit(self.currentChar()):
            c = self.currentChar()
            if is_digit(c):
                d = c - 48
            else:
                d = to_upper(c) - 65 + 10
            val = val * 16 + d
            self.pos += 1
        return i16(val)

    def getDecimalValue(self):
        """10進数を解析"""
        val = 0
        if not is_digit(self.currentChar()):
            return -1
        while is_digit(self.currentChar()):
            val = val * 10 + (self.currentChar() - 48)
            self.pos += 1
        return i16(val)

    def scanString(self):
        """文字列リテラルの中身（閉じ " または NUL まで）を返す"""
        start = self.pos
        while self.currentChar() != 34 and self.currentChar() != 0:
            self.pos += 1
        return self.s[start:self.pos]

    def getString(self, maxlen):
        """文字列リテラルをバッファへ取得"""
        out = b""
        if self.currentChar() == 34:
            self.skipChar(34)
            out = self.scanString()[:maxlen - 1]
            self.skipChar(34)
        return out

    def printString(self):
        """文字列リテラルをそのまま出力"""
        if self.currentChar() == 34:
            self.skipChar(34)
            self.write(self.scanString())
            self.skipChar(34)

    def getConstant(self):
        """定数値を解析"""
        c = self.currentChar()
        if c == 34:
            buf = self.getString(256)
            v = 0
            if len(buf) > 0:
                v = buf[0]
            if len(buf) > 1:
                v = i16(v + buf[1] * 256)
            return v
        elif c == 36:                       # $
            self.skipChar(36)
            return self.getHexValue()
        elif is_digit(c):
            return self.getDecimalValue()
        return 0

    def term(self):
        """項（オペランド）を解析"""
        self.skipSpaces()

        # 括弧式
        if self.currentChar() == 40:
            self.skipChar(40)
            v = self.expression()
            self.skipSpaces()
            self.skipChar(41)
            return v

        # 変数
        c = self.getVariable()
        if c != 0:
            varIdx = to_upper(c) - 65

            if self.currentChar() == 58:    # :
                # バイト配列アクセス V:exp)
                self.skipChar(58)
                v = self.expression()
                self.skipChar(41)
                addr = (self.variables[varIdx] + v) & 0xFFFF
                return self.memory[addr]
            elif self.currentChar() == 40:  # (
                # ワード配列アクセス V(exp)
                self.skipChar(40)
                v = self.expression()
                self.skipChar(41)
                addr = (self.variables[varIdx] + v * 2) & 0xFFFF
                return i16(self.memory[addr] |
                           (self.memory[(addr + 1) & 0xFFFF] << 8))
            else:
                # 単純変数
                return self.variables[varIdx]

        # getch - 1文字読み込み
        if self.currentChar() == 36 and not is_xdigit(self.peek(1)):
            self.pos += 1
            return self.readByteOrZero()

        # 入力
        if self.currentChar() == 63:        # ?
            self.pos += 1
            self.flush()
            line = self.inp.readline(255)
            # 前後の空白を除去
            p = line.strip(b" \t\n\r")
            if p[:1] == b"$":
                return i16(strtol(p[1:], 16))
            return i16(strtol(p, 10))

        # 定数
        savedPos = self.pos
        v = self.getConstant()
        if v != 0 or self.pos != savedPos:
            return v

        # 単項演算子
        c = self.getOperator1()
        if c != 0:
            v = self.term()
            if c == 45:                     # -
                return i16(-v)
            elif c == 43:                   # +
                if v < 0:
                    return i16(-v)
                return v
            elif c == 35:                   # #
                return 0 if v != 0 else 1
            elif c == 39:                   # '
                if v > 0:
                    return random.randrange(0x80000000) % v
                return 0
            elif c == 37:                   # %
                return self.mod

        return 0

    def expression(self):
        """式を解析"""
        self.skipSpaces()
        v = self.term()

        while True:
            c = self.getOperator2()
            if c == 0:
                break

            v2 = self.term()

            if c == 43:
                v = i16(v + v2)
            elif c == 45:
                v = i16(v - v2)
            elif c == 42:
                v = i16(v * v2)
            elif c == 47:
                if v2 == 0:
                    self.write(b"Division by zero\n")
                    v = -1
                else:
                    self.mod = i16(c_mod(v, v2))
                    v = i16(c_div(v, v2))
            elif c == 61:
                v = 1 if v == v2 else 0
            elif c == 60:
                v = 1 if v < v2 else 0
            elif c == 78:
                v = 1 if v != v2 else 0
            elif c == 65:
                v = 1 if v <= v2 else 0
            elif c == 62:
                v = 1 if v > v2 else 0
            elif c == 66:
                v = 1 if v >= v2 else 0

        return v

    # ---- 行制御 ----

    def skipToNewline(self):
        """行末まで読み飛ばす"""
        while self.currentChar() != 10 and self.currentChar() != 0:
            self.pos += 1
        if self.currentChar() == 10:
            self.pos += 1

    def searchLine(self, targetLine):
        """プログラム中の行番号を検索"""
        self.s = self.pbuff
        self.slen = self.psize
        self.pos = 0

        # コメント行をスキップ
        if self.slen > 0 and self.s[0] == 35:
            while self.currentChar() != 10 and self.currentChar() != 0:
                self.pos += 1
            self.pos += 1

        while self.pos < self.slen:
            savedPos = self.pos
            lineNum = self.getDecimalValue()

            if lineNum == -1:
                return -1

            if lineNum >= targetLine:
                self.pos = savedPos
                return lineNum

            self.skipToNewline()

        return -1

    def gotoLine(self, lineNum):
        """行番号へジャンプ"""
        if lineNum == -1:
            self.ln = -1
        else:
            self.ln = self.searchLine(lineNum)

    # ---- スタック操作 ----

    def push(self, x):
        if self.sp >= len(self.stack):
            self.stack.append(None)
        self.stack[self.sp] = x
        self.sp += 1

    def slotInt(self, i):
        x = self.stack[i]
        return x if isinstance(x, int) else 0

    def slotStr(self, i):
        x = self.stack[i]
        return x if isinstance(x, bytes) else self.pbuff

    def setS(self, s):
        self.s = s
        self.slen = len(s)

    def gosub(self, lineNum):
        """サブルーチン呼び出し"""
        self.push(self.s)
        self.push(self.pos)
        self.gotoLine(lineNum)

    def returnFromSub(self):
        """サブルーチンから復帰"""
        if self.sp >= 2:
            self.sp -= 2
            self.pos = self.slotInt(self.sp + 1)
            self.setS(self.slotStr(self.sp))

    def doLoop(self):
        """DO ループ開始"""
        self.push(self.s)
        self.push(self.pos)

    def untilLoop(self):
        """UNTIL 条件"""
        if self.sp >= 2:
            self.sp -= 2
            savedPos = self.slotInt(self.sp + 1)
            savedS = self.slotStr(self.sp)

            v = self.expression()
            if v == 0:
                self.setS(savedS)
                self.pos = savedPos
                self.push(savedS)
                self.push(savedPos)

    def nextLoop(self):
        """FOR ループの NEXT"""
        if self.sp >= 3:
            self.sp -= 3
            toVal = self.slotInt(self.sp + 2)
            savedPos = self.slotInt(self.sp + 1)
            savedS = self.slotStr(self.sp)
            varIdx = self.slotInt(self.sp - 1) if self.sp >= 1 else 0
            self.sp -= 1

            v = self.expression()
            self.variables[varIdx] = v

            if v <= toVal:
                self.setS(savedS)
                self.pos = savedPos
                self.push(varIdx)
                self.push(savedS)
                self.push(savedPos)
                self.push(toVal)

    def ifStatement(self, condition):
        """IF 文"""
        if condition == 0:
            self.skipToNewline()
            self.pos -= 1

    # ---- ソース読み込み ----

    def loadSource(self, filename):
        """ソースファイルを読み込む。成功で 0、失敗で -1"""
        try:
            with open(filename, "rb") as fp:
                buf = fp.read()
        except (OSError, ValueError):
            return -1
        self.pbuff = buf
        self.psize = len(buf)
        return 0

    def loadSourceCommand(self):
        """コマンドからソースを読み込む"""
        self.skipSpaces()
        start = self.pos
        while self.currentChar() != 10 and self.currentChar() != 0:
            self.pos += 1
        filename = self.s[start:self.pos][:1023]
        self.loadSource(filename)

    def optionalCommand(self):
        """オプションコマンドを実行"""
        c1 = to_upper(self.currentChar())
        self.pos += 1
        c2 = to_upper(self.currentChar())
        self.pos += 1

        if c1 == 76 and c2 == 68:           # LD
            self.loadSourceCommand()
        elif c1 == 81 and c2 == 85:         # QU
            self.flush()
            sys.exit(0)
        elif c1 == 84 and c2 == 78:         # TN
            self.tron = 1
        elif c1 == 84 and c2 == 70:         # TF
            self.tron = 0
        elif c1 == 83 and c2 == 72:         # SH
            # Shell - セキュリティ上未実装
            self.write(b"Shell command not supported\n")
        elif c1 == 70 and c2 == 77:         # FM
            v = self.expression()
            self.forMode = v
        else:
            self.syntaxError()

    # ---- 実行本体 ----

    def run(self):
        """プログラムを実行"""
        while True:
            c = self.currentChar()

            if c == 0:
                return
            if self.ln == -1:
                return

            # 行番号を解析
            if self.ln != 0:
                v = self.getDecimalValue()
                if self.tron:
                    self.write(b"[%d]" % v)
                    self.flush()
                self.ln = v

                if self.currentChar() != 32:
                    self.skipToNewline()
                    continue

            # 文を実行
            while True:
                c = self.currentChar()

                if c == 0:
                    return
                elif c == 10:
                    self.pos += 1
                    break
                elif c == 32:
                    self.skipSpaces()
                    continue
                elif c == 34:               # "
                    # 文字列リテラル - 出力
                    self.printString()
                    self.flush()
                    continue
                elif c == 47:               # /
                    # 改行
                    self.skipChar(47)
                    self.write(b"\n")
                    self.flush()
                    continue
                elif c == 46:               # .
                    # 空白を出力
                    self.skipChar(46)
                    self.skipChar(61)
                    v = self.expression()
                    if v > 0:
                        self.write(b" " * v)
                    self.flush()
                    continue
                elif c == 42:               # *
                    # オプションコマンド
                    self.pos += 1
                    self.optionalCommand()
                    continue
                elif c == 63:               # ?
                    # 出力コマンド
                    self.pos += 1
                    c = self.currentChar()

                    if c == 61:
                        # 10進出力
                        self.skipChar(61)
                        v = self.expression()
                        self.write(b"%d" % v)
                        self.flush()
                    elif c == 63:
                        # 16進出力（4桁）
                        self.skipChar(63)
                        self.skipChar(61)
                        v = self.expression()
                        self.write(b"%04x" % (v & 0xFFFF))
                        self.flush()
                    elif c == 36:
                        # 16進出力（2桁）
                        self.skipChar(36)
                        self.skipChar(61)
                        v = self.expression()
                        self.write(b"%02x" % (v & 0xFF))
                        self.flush()
                    elif c == 40:
                        # 桁指定出力
                        self.skipChar(40)
                        width = self.expression()
                        self.skipChar(41)
                        self.skipChar(61)
                        v = self.expression()
                        self.write(b"%*d" % (width, v))
                        self.flush()
                    else:
                        self.syntaxError()
                        return
                    continue
                elif c == 39:               # '
                    # 乱数シード
                    self.pos += 1
                    self.skipChar(61)
                    v = self.expression()
                    random.seed(v & 0xFFFFFFFF)
                    continue
                elif c == 36:               # $
                    # 文字出力
                    self.pos += 1
                    self.skipChar(61)
                    v = self.expression()
                    self.write(bytes((v & 0xFF,)))
                    self.flush()
                    continue
                elif c == 35:               # #
                    # GOTO
                    self.pos += 1
                    self.skipChar(61)
                    v = self.expression()
                    self.gotoLine(v)
                    break
                elif c == 33:               # !
                    # GOSUB
                    self.pos += 1
                    self.skipChar(61)
                    v = self.expression()
                    self.gosub(v)
                    break
                elif c == 93:               # ]
                    # RETURN
                    self.pos += 1
                    self.returnFromSub()
                    continue
                elif c == 64:               # @
                    # DO/UNTIL/NEXT
                    self.pos += 1
                    if self.currentChar() == 61:
                        self.skipChar(61)
                        if self.currentChar() == 40:
                            # UNTIL
                            self.untilLoop()
                        else:
                            # NEXT
                            self.nextLoop()
                    else:
                        # DO
                        self.doLoop()
                    continue
                elif c == 59:               # ;
                    # IF
                    self.pos += 1
                    self.skipChar(61)
                    v = self.expression()
                    self.ifStatement(v)
                    continue
                elif is_alpha(c):
                    # 変数代入
                    varChar = self.getVariable()
                    varIdx = to_upper(varChar) - 65

                    if self.currentChar() == 58:
                        # バイト配列代入
                        self.pos += 1
                        idx = self.expression()
                        self.skipChar(41)
                        self.skipChar(61)
                        v = self.expression()
                        self.memory[(self.variables[varIdx] + idx) & 0xFFFF] = v & 0xFF
                    elif self.currentChar() == 40:
                        # ワード配列代入
                        self.pos += 1
                        idx = self.expression()
                        self.skipChar(41)
                        self.skipChar(61)
                        v = self.expression()
                        addr = (self.variables[varIdx] + idx * 2) & 0xFFFF
                        self.memory[addr] = v & 0xFF
                        self.memory[(addr + 1) & 0xFFFF] = (v >> 8) & 0xFF
                    else:
                        # 単純変数代入
                        self.skipChar(61)
                        v = self.expression()
                        self.variables[varIdx] = v

                    # FOR ループ
                    if self.currentChar() == 44:
                        self.skipChar(44)
                        toVal = self.expression()
                        v = self.variables[varIdx]

                        if v > toVal and self.forMode != 0:
                            # @= までスキップ
                            eof = False
                            while self.currentChar() != 64:
                                if self.currentChar() == 0:
                                    eof = True
                                    break
                                self.pos += 1
                            if not eof:
                                self.skipChar(64)
                                self.skipChar(61)
                                self.expression()
                        else:
                            self.push(varIdx)
                            self.push(self.s)
                            self.push(self.pos)
                            self.push(toVal)
                    continue

                self.syntaxError()
                return


def main():
    random.seed(int(time.time()))

    if len(sys.argv) >= 2:
        m = Miep()
        if m.loadSource(sys.argv[1]) != 0:
            sys.stderr.write("Error loading file: %s\n" % sys.argv[1])
            return 1
        try:
            m.gotoLine(1)
            m.run()
        except KeyboardInterrupt:
            m.flush()
            return 130
        m.flush()
    else:
        print("Usage: miep file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
