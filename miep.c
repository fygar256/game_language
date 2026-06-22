/*
 * miep.c - MIEP interpreter (C port of miep.go)
 *
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

/* ---- スタックスロット（Go の interface{} に相当） ---- */
enum slot_kind { SK_STR, SK_INT, SK_I16 };

typedef struct {
    int kind;
    union {
        char   *sval;   /* プログラム文字列ポインタ */
        int     ival;   /* 位置・変数インデックス */
        int16_t i16;    /* ループ上限値など */
    } u;
} Slot;

#define STACK_MAX 65536

/* ---- インタプリタ状態 ---- */
typedef struct {
    int16_t variables[26];      /* A-Z 変数 */
    unsigned char memory[65536]; /* 64KB メモリ */
    char   *pbuff;              /* プログラムバッファ */
    int     psize;             /* プログラムサイズ */
    char   *s;                 /* 現在の解析対象文字列 */
    int     slen;              /* s の長さ */
    int     pos;               /* s 内の現在位置 */
    int     ln;                /* 現在行番号 */
    Slot    stack[STACK_MAX];  /* ランタイムスタック */
    int     sp;                /* スタックポインタ（要素数） */
    int     tron;              /* トレースモード */
    int16_t mod;               /* 剰余結果 */
    int     forMode;           /* FOR ループモード */
} Miep;

/* インスタンスは巨大なため静的領域に確保（ゼロ初期化される） */
static Miep M;

/* ---- 文字操作ヘルパ ---- */

/* currentChar: 現在の文字を返す */
static int currentChar(Miep *m) {
    if (m->pos < m->slen) {
        return (unsigned char)m->s[m->pos];
    }
    return 0;
}

/* advance: 位置を前進させる */
static void advance(Miep *m, int count) {
    m->pos += count;
}

/* peek: 先読みする */
static int peek(Miep *m, int offset) {
    if (m->pos + offset < m->slen) {
        return (unsigned char)m->s[m->pos + offset];
    }
    return 0;
}

/* skipSpaces: 空白を読み飛ばす */
static void skipSpaces(Miep *m) {
    while (currentChar(m) == ' ') {
        advance(m, 1);
    }
}

/* syntaxError: 構文エラーを報告する */
static void syntaxError(Miep *m) {
    printf("\nSyntaxerror in %d", m->ln);
    fflush(stdout);
}

/* skipChar: 期待する文字を読み飛ばす */
static void skipChar(Miep *m, int c) {
    if (currentChar(m) == c) {
        advance(m, 1);
        return;
    }
    syntaxError(m);
}

/* isAlpha: 英字判定 */
static int isAlphaC(int c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

/* isDigit: 数字判定 */
static int isDigitC(int c) {
    return c >= '0' && c <= '9';
}

/* isXDigit: 16進数字判定 */
static int isXDigitC(int c) {
    return isDigitC(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

/* toUpper: 大文字化 */
static int toUpperC(int c) {
    if (c >= 'a' && c <= 'z') {
        return c - 'a' + 'A';
    }
    return c;
}

/* ---- 演算子・トークン取得 ---- */

/* getOperator2: 二項演算子を取得 */
static int getOperator2(Miep *m) {
    int c = currentChar(m);
    switch (c) {
    case '=': case '+': case '-': case '*': case '/':
        advance(m, 1);
        return c;
    case '<':
        advance(m, 1);
        if (currentChar(m) == '>') {
            advance(m, 1);
            return 'N'; /* 不等 */
        } else if (currentChar(m) == '=') {
            advance(m, 1);
            return 'A'; /* 以下 */
        }
        return '<';
    case '>':
        advance(m, 1);
        if (currentChar(m) == '=') {
            advance(m, 1);
            return 'B'; /* 以上 */
        }
        return '>';
    default:
        return 0;
    }
}

/* getOperator1: 単項演算子を取得 */
static int getOperator1(Miep *m) {
    int c = currentChar(m);
    switch (c) {
    case '+': case '-': case '\'': case '#': case '%':
        advance(m, 1);
        return c;
    default:
        return 0;
    }
}

/* getVariable: 変数名を取得（先頭1文字を返し、連続する英字を読み飛ばす） */
static int getVariable(Miep *m) {
    int c = 0;
    if (isAlphaC(currentChar(m))) {
        c = currentChar(m);
        while (m->pos < m->slen && isAlphaC((unsigned char)m->s[m->pos])) {
            advance(m, 1);
        }
    }
    return c;
}

/* getHexValue: 16進数を解析 */
static int16_t getHexValue(Miep *m) {
    long val = 0;
    if (!isXDigitC(currentChar(m))) {
        return -1;
    }
    while (isXDigitC(currentChar(m))) {
        int c = currentChar(m);
        int d;
        if (c >= '0' && c <= '9') {
            d = c - '0';
        } else {
            d = toUpperC(c) - 'A' + 10;
        }
        val = val * 16 + d;
        advance(m, 1);
    }
    return (int16_t)val;
}

/* getDecimalValue: 10進数を解析 */
static int16_t getDecimalValue(Miep *m) {
    long val = 0;
    if (!isDigitC(currentChar(m))) {
        return -1;
    }
    while (isDigitC(currentChar(m))) {
        val = val * 10 + (currentChar(m) - '0');
        advance(m, 1);
    }
    return (int16_t)val;
}

/* getString: 文字列リテラルをバッファへ取得 */
static int getString(Miep *m, char *out, int maxlen) {
    int n = 0;
    if (currentChar(m) == '"') {
        skipChar(m, '"');
        while (currentChar(m) != '"' && currentChar(m) != 0) {
            if (n < maxlen - 1) {
                out[n++] = (char)currentChar(m);
            }
            advance(m, 1);
        }
        skipChar(m, '"');
    }
    out[n] = '\0';
    return n;
}

/* printString: 文字列リテラルをそのまま出力（バッファ不要） */
static void printString(Miep *m) {
    if (currentChar(m) == '"') {
        skipChar(m, '"');
        while (currentChar(m) != '"' && currentChar(m) != 0) {
            putchar(currentChar(m));
            advance(m, 1);
        }
        skipChar(m, '"');
    }
}

/* 式評価は相互再帰するので前方宣言 */
static int16_t expression(Miep *m);

/* getConstant: 定数値を解析 */
static int16_t getConstant(Miep *m) {
    if (currentChar(m) == '"') {
        char buf[256];
        int n = getString(m, buf, (int)sizeof(buf));
        int16_t v = 0;
        if (n > 0) {
            v = (int16_t)(unsigned char)buf[0];
        }
        if (n > 1) {
            v = (int16_t)(v + (int16_t)((unsigned char)buf[1]) * 256);
        }
        return v;
    } else if (currentChar(m) == '$') {
        skipChar(m, '$');
        return getHexValue(m);
    } else if (isDigitC(currentChar(m))) {
        return getDecimalValue(m);
    }
    return 0;
}

/* getch / 行入力用の小ヘルパ */
static int readByteOrZero(void) {
    int ch = getchar();
    return (ch == EOF) ? 0 : (unsigned char)ch;
}

/* term: 項（オペランド）を解析 */
static int16_t term(Miep *m) {
    int16_t v;
    int c;

    skipSpaces(m);

    /* 括弧式 */
    if (currentChar(m) == '(') {
        skipChar(m, '(');
        v = expression(m);
        skipSpaces(m);
        skipChar(m, ')');
        return v;
    }

    /* 変数 */
    c = getVariable(m);
    if (c != 0) {
        int varIdx = toUpperC(c) - 'A';

        if (currentChar(m) == ':') {
            /* バイト配列アクセス V:exp) */
            skipChar(m, ':');
            v = expression(m);
            skipChar(m, ')');
            {
                uint16_t addr = (uint16_t)(int16_t)(m->variables[varIdx] + v);
                return (int16_t)m->memory[addr];
            }
        } else if (currentChar(m) == '(') {
            /* ワード配列アクセス V(exp) */
            skipChar(m, '(');
            v = expression(m);
            skipChar(m, ')');
            {
                int16_t a = (int16_t)(m->variables[varIdx] + v * 2);
                uint16_t addr = (uint16_t)a;
                return (int16_t)(m->memory[addr] |
                                 ((int16_t)m->memory[(uint16_t)(addr + 1)] << 8));
            }
        } else {
            /* 単純変数 */
            return m->variables[varIdx];
        }
    }

    /* getch - 1文字読み込み */
    if (currentChar(m) == '$' && !isXDigitC(peek(m, 1))) {
        advance(m, 1);
        return (int16_t)readByteOrZero();
    }

    /* 入力 */
    if (currentChar(m) == '?') {
        char line[256];
        advance(m, 1);
        if (fgets(line, (int)sizeof(line), stdin) == NULL) {
            line[0] = '\0';
        }
        /* 前後の空白を除去 */
        {
            char *p = line;
            char *end;
            while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') {
                p++;
            }
            end = p + strlen(p);
            while (end > p && (end[-1] == ' ' || end[-1] == '\t' ||
                               end[-1] == '\n' || end[-1] == '\r')) {
                end--;
            }
            *end = '\0';
            if (p[0] == '$') {
                return (int16_t)strtol(p + 1, NULL, 16);
            }
            return (int16_t)strtol(p, NULL, 10);
        }
    }

    /* 定数 */
    {
        int savedPos = m->pos;
        v = getConstant(m);
        if (v != 0 || m->pos != savedPos) {
            return v;
        }
    }

    /* 単項演算子 */
    c = getOperator1(m);
    if (c != 0) {
        v = term(m);
        switch (c) {
        case '-':
            return (int16_t)(-v);
        case '+':
            if (v < 0) {
                return (int16_t)(-v);
            }
            return v;
        case '#':
            if (v != 0) {
                return 0;
            }
            return 1;
        case '\'':
            if (v > 0) {
                return (int16_t)(rand() % (int)v);
            }
            return 0;
        case '%':
            return m->mod;
        }
    }

    return 0;
}

/* expression: 式を解析 */
static int16_t expression(Miep *m) {
    int16_t v, v2;
    int c;

    skipSpaces(m);
    v = term(m);

    for (;;) {
        c = getOperator2(m);
        if (c == 0) {
            break;
        }

        v2 = term(m);

        switch (c) {
        case '+': v = (int16_t)(v + v2); break;
        case '-': v = (int16_t)(v - v2); break;
        case '*': v = (int16_t)(v * v2); break;
        case '/':
            if (v2 == 0) {
                printf("Division by zero\n");
                v = -1;
            } else {
                m->mod = (int16_t)(v % v2);
                v = (int16_t)(v / v2);
            }
            break;
        case '=': v = (v == v2) ? 1 : 0; break;
        case '<': v = (v <  v2) ? 1 : 0; break;
        case 'N': v = (v != v2) ? 1 : 0; break;
        case 'A': v = (v <= v2) ? 1 : 0; break;
        case '>': v = (v >  v2) ? 1 : 0; break;
        case 'B': v = (v >= v2) ? 1 : 0; break;
        }
    }

    return v;
}

/* ---- 行制御 ---- */

/* skipToNewline: 行末まで読み飛ばす */
static void skipToNewline(Miep *m) {
    while (currentChar(m) != '\n' && currentChar(m) != 0) {
        advance(m, 1);
    }
    if (currentChar(m) == '\n') {
        advance(m, 1);
    }
}

/* searchLine: プログラム中の行番号を検索 */
static int16_t searchLine(Miep *m, int16_t targetLine) {
    m->s = m->pbuff;
    m->slen = m->psize;
    m->pos = 0;

    /* コメント行をスキップ */
    if (m->slen > 0 && m->s[0] == '#') {
        while (currentChar(m) != '\n' && currentChar(m) != 0) {
            advance(m, 1);
        }
        advance(m, 1);
    }

    while (m->pos < m->slen) {
        int savedPos = m->pos;
        int16_t lineNum = getDecimalValue(m);

        if (lineNum == -1) {
            return -1;
        }

        if (lineNum >= targetLine) {
            m->pos = savedPos;
            return lineNum;
        }

        skipToNewline(m);
    }

    return -1;
}

/* gotoLine: 行番号へジャンプ */
static void gotoLine(Miep *m, int16_t lineNum) {
    if (lineNum == -1) {
        m->ln = -1;
    } else {
        m->ln = (int)searchLine(m, lineNum);
    }
}

/* ---- スタック操作 ---- */

static void pushStr(Miep *m, char *s) {
    m->stack[m->sp].kind = SK_STR;
    m->stack[m->sp].u.sval = s;
    m->sp++;
}
static void pushInt(Miep *m, int i) {
    m->stack[m->sp].kind = SK_INT;
    m->stack[m->sp].u.ival = i;
    m->sp++;
}
static void pushI16(Miep *m, int16_t i) {
    m->stack[m->sp].kind = SK_I16;
    m->stack[m->sp].u.i16 = i;
    m->sp++;
}

/* gosub: サブルーチン呼び出し */
static void gosub(Miep *m, int16_t lineNum) {
    pushStr(m, m->s);
    pushInt(m, m->pos);
    gotoLine(m, lineNum);
}

/* returnFromSub: サブルーチンから復帰 */
static void returnFromSub(Miep *m) {
    if (m->sp >= 2) {
        m->sp -= 2;
        m->pos = m->stack[m->sp + 1].u.ival;
        m->s   = m->stack[m->sp].u.sval;
        m->slen = m->psize; /* s は常に pbuff を指す */
    }
}

/* doLoop: DO ループ開始 */
static void doLoop(Miep *m) {
    pushStr(m, m->s);
    pushInt(m, m->pos);
}

/* untilLoop: UNTIL 条件 */
static void untilLoop(Miep *m) {
    if (m->sp >= 2) {
        int16_t v;
        int   savedPos;
        char *savedS;
        m->sp -= 2;
        savedPos = m->stack[m->sp + 1].u.ival;
        savedS   = m->stack[m->sp].u.sval;

        v = expression(m);
        if (v == 0) {
            m->s = savedS;
            m->slen = m->psize;
            m->pos = savedPos;
            pushStr(m, savedS);
            pushInt(m, savedPos);
        }
    }
}

/* nextLoop: FOR ループの NEXT */
static void nextLoop(Miep *m) {
    if (m->sp >= 3) {
        int16_t toVal;
        int     savedPos;
        char   *savedS;
        int     varIdx;
        int16_t v;

        m->sp -= 3;
        toVal    = m->stack[m->sp + 2].u.i16;
        savedPos = m->stack[m->sp + 1].u.ival;
        savedS   = m->stack[m->sp].u.sval;
        varIdx   = m->stack[m->sp - 1].u.ival;
        m->sp--;

        v = expression(m);
        m->variables[varIdx] = v;

        if (v <= toVal) {
            m->s = savedS;
            m->slen = m->psize;
            m->pos = savedPos;
            pushInt(m, varIdx);
            pushStr(m, savedS);
            pushInt(m, savedPos);
            pushI16(m, toVal);
        }
    }
}

/* ifStatement: IF 文 */
static void ifStatement(Miep *m, int16_t condition) {
    if (condition == 0) {
        skipToNewline(m);
        m->pos--;
    }
}

/* ---- ソース読み込み ---- */

/* loadSource: ソースファイルを読み込む。成功で 0、失敗で -1 */
static int loadSource(Miep *m, const char *filename) {
    FILE *fp;
    long size;
    char *buf;

    fp = fopen(filename, "rb");
    if (fp == NULL) {
        return -1;
    }
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return -1;
    }
    size = ftell(fp);
    if (size < 0) {
        fclose(fp);
        return -1;
    }
    rewind(fp);

    buf = (char *)malloc((size_t)size + 1);
    if (buf == NULL) {
        fclose(fp);
        return -1;
    }
    if (size > 0 && fread(buf, 1, (size_t)size, fp) != (size_t)size) {
        free(buf);
        fclose(fp);
        return -1;
    }
    buf[size] = '\0';
    fclose(fp);

    free(m->pbuff);
    m->pbuff = buf;
    m->psize = (int)size;
    return 0;
}

/* loadSourceCommand: コマンドからソースを読み込む */
static void loadSourceCommand(Miep *m) {
    int start;
    char filename[1024];
    int n = 0;

    skipSpaces(m);
    start = m->pos;
    while (currentChar(m) != '\n' && currentChar(m) != 0) {
        advance(m, 1);
    }
    {
        int len = m->pos - start;
        int i;
        for (i = 0; i < len && i < (int)sizeof(filename) - 1; i++) {
            filename[n++] = m->s[start + i];
        }
        filename[n] = '\0';
    }
    loadSource(m, filename);
}

/* optionalCommand: オプションコマンドを実行 */
static void optionalCommand(Miep *m) {
    int c1 = toUpperC(currentChar(m));
    advance(m, 1);
    {
        int c2 = toUpperC(currentChar(m));
        advance(m, 1);

        if (c1 == 'L' && c2 == 'D') {
            loadSourceCommand(m);
        } else if (c1 == 'Q' && c2 == 'U') {
            exit(0);
        } else if (c1 == 'T' && c2 == 'N') {
            m->tron = 1;
        } else if (c1 == 'T' && c2 == 'F') {
            m->tron = 0;
        } else if (c1 == 'S' && c2 == 'H') {
            /* Shell - セキュリティ上未実装 */
            printf("Shell command not supported\n");
        } else if (c1 == 'F' && c2 == 'M') {
            int16_t v = expression(m);
            m->forMode = (int)v;
        } else {
            syntaxError(m);
        }
    }
}

/* ---- 実行本体 ---- */

/* run: プログラムを実行 */
static void run(Miep *m) {
    for (;;) {
        int c = currentChar(m);

        if (c == 0) {
            return;
        }
        if (m->ln == -1) {
            return;
        }

        /* 行番号を解析 */
        if (m->ln != 0) {
            int16_t v = getDecimalValue(m);
            if (m->tron) {
                printf("[%d]", (int)v);
                fflush(stdout);
            }
            m->ln = (int)v;

            if (currentChar(m) != ' ') {
                skipToNewline(m);
                continue;
            }
        }

        /* 文を実行 */
        for (;;) {
            c = currentChar(m);

            if (c == 0) {
                return;
            } else if (c == '\n') {
                advance(m, 1);
                break;
            } else if (c == ' ') {
                skipSpaces(m);
                continue;
            } else if (c == '"') {
                /* 文字列リテラル - 出力 */
                printString(m);
                fflush(stdout);
                continue;
            } else if (c == '/') {
                /* 改行 */
                skipChar(m, '/');
                putchar('\n');
                continue;
            } else if (c == '.') {
                /* 空白を出力 */
                int16_t v, i;
                skipChar(m, '.');
                skipChar(m, '=');
                v = expression(m);
                for (i = 0; i < v; i++) {
                    putchar(' ');
                }
                fflush(stdout);
                continue;
            } else if (c == '*') {
                /* オプションコマンド */
                advance(m, 1);
                optionalCommand(m);
                continue;
            } else if (c == '?') {
                /* 出力コマンド */
                advance(m, 1);
                c = currentChar(m);

                if (c == '=') {
                    /* 10進出力 */
                    int16_t v;
                    skipChar(m, '=');
                    v = expression(m);
                    printf("%d", (int)v);
                    fflush(stdout);
                } else if (c == '?') {
                    /* 16進出力（4桁） */
                    int16_t v;
                    skipChar(m, '?');
                    skipChar(m, '=');
                    v = expression(m);
                    printf("%04x", (unsigned)(uint16_t)v);
                    fflush(stdout);
                } else if (c == '$') {
                    /* 16進出力（2桁） */
                    int16_t v;
                    skipChar(m, '$');
                    skipChar(m, '=');
                    v = expression(m);
                    printf("%02x", (unsigned)(uint8_t)v);
                    fflush(stdout);
                } else if (c == '(') {
                    /* 桁指定出力 */
                    int16_t width, v;
                    skipChar(m, '(');
                    width = expression(m);
                    skipChar(m, ')');
                    skipChar(m, '=');
                    v = expression(m);
                    printf("%*d", (int)width, (int)v);
                    fflush(stdout);
                } else {
                    syntaxError(m);
                    return;
                }
                continue;
            } else if (c == '\'') {
                /* 乱数シード */
                int16_t v;
                advance(m, 1);
                skipChar(m, '=');
                v = expression(m);
                srand((unsigned)v);
                continue;
            } else if (c == '$') {
                /* 文字出力 */
                int16_t v;
                advance(m, 1);
                skipChar(m, '=');
                v = expression(m);
                printf("%c", (unsigned char)v);
                fflush(stdout);
                continue;
            } else if (c == '#') {
                /* GOTO */
                int16_t v;
                advance(m, 1);
                skipChar(m, '=');
                v = expression(m);
                gotoLine(m, v);
                break;
            } else if (c == '!') {
                /* GOSUB */
                int16_t v;
                advance(m, 1);
                skipChar(m, '=');
                v = expression(m);
                gosub(m, v);
                break;
            } else if (c == ']') {
                /* RETURN */
                advance(m, 1);
                returnFromSub(m);
                continue;
            } else if (c == '@') {
                /* DO/UNTIL/NEXT */
                advance(m, 1);
                if (currentChar(m) == '=') {
                    skipChar(m, '=');
                    if (currentChar(m) == '(') {
                        /* UNTIL */
                        untilLoop(m);
                    } else {
                        /* NEXT */
                        nextLoop(m);
                    }
                } else {
                    /* DO */
                    doLoop(m);
                }
                continue;
            } else if (c == ';') {
                /* IF */
                int16_t v;
                advance(m, 1);
                skipChar(m, '=');
                v = expression(m);
                ifStatement(m, v);
                continue;
            } else if (isAlphaC(c)) {
                /* 変数代入 */
                int varChar = getVariable(m);
                int varIdx = toUpperC(varChar) - 'A';

                if (currentChar(m) == ':') {
                    /* バイト配列代入 */
                    int16_t idx, v;
                    advance(m, 1);
                    idx = expression(m);
                    skipChar(m, ')');
                    skipChar(m, '=');
                    v = expression(m);
                    m->memory[(uint16_t)(int16_t)(m->variables[varIdx] + idx)] =
                        (unsigned char)v;
                } else if (currentChar(m) == '(') {
                    /* ワード配列代入 */
                    int16_t idx, v;
                    int16_t addr;
                    advance(m, 1);
                    idx = expression(m);
                    skipChar(m, ')');
                    skipChar(m, '=');
                    v = expression(m);
                    addr = (int16_t)(m->variables[varIdx] + idx * 2);
                    m->memory[(uint16_t)addr] = (unsigned char)v;
                    m->memory[(uint16_t)(addr + 1)] = (unsigned char)(v >> 8);
                } else {
                    /* 単純変数代入 */
                    int16_t v;
                    skipChar(m, '=');
                    v = expression(m);
                    m->variables[varIdx] = v;
                }

                /* FOR ループ */
                if (currentChar(m) == ',') {
                    int16_t toVal, v;
                    skipChar(m, ',');
                    toVal = expression(m);
                    v = m->variables[varIdx];

                    if (v > toVal && m->forMode != 0) {
                        /* @= までスキップ */
                        int eof = 0;
                        while (currentChar(m) != '@') {
                            if (currentChar(m) == 0) {
                                eof = 1;
                                break;
                            }
                            advance(m, 1);
                        }
                        if (!eof) {
                            skipChar(m, '@');
                            skipChar(m, '=');
                            expression(m);
                        }
                    } else {
                        pushInt(m, varIdx);
                        pushStr(m, m->s);
                        pushInt(m, m->pos);
                        pushI16(m, toVal);
                    }
                }
                continue;
            }

            syntaxError(m);
            return;
        }
    }
}

int main(int argc, char *argv[]) {
    srand((unsigned)time(NULL));

    if (argc >= 2) {
        Miep *m = &M;
        if (loadSource(m, argv[1]) != 0) {
            fprintf(stderr, "Error loading file: %s\n", argv[1]);
            return 1;
        }
        gotoLine(m, 1);
        run(m);
    } else {
        printf("Usage: miep file\n");
    }
    return 0;
}
