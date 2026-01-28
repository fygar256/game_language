# GAME Language Interpreter

昔懐かしのGAME言語のインタプリタをCで書いてみました。

資料が少ないもので、オリジナルとは少し変わっていると思いますが、一応Linux/FreeBSD上での実装ということで、ご勘弁いただきたいと思います。

GAME言語は今は廃れてしまいましたが、1980年前後にマイコンで手軽に使える処理系として一世を風靡しました。僕も当時中学生の頃、GAME言語を参考に独自のインタプリタ・コンパイラを作って遊んでいたものです。

そのエディタ・インタプリタ・コンパイラシステム（一応IDE)はMIEPといい、今回のGAME言語インタプリタの名前もmiepにしました。MIEPの他に、高校生の頃、MIGというコンパイラも作りました。それはIDEを作ろうと思っていたのですが、途中で断念して、コンパイラシステムだけになりました。それでも、インラインアセンブラを装備するなどしていました。



このプログラムはエラーチェックなどが十分ではないです。

コンパイル、インストール、実行

カレントディレクトリにmiep.cを置き、コンソールで、cc miep.c -o miepとしてコンパイルして下さい。

インストールは、sudo cp miep /usr/bin/として、/usr/bin/にmiepを配置するだけです。

実行は、miep [file.gm]として動かして下さい。

miep では、シバンをつけることができます。シバンを付けて実行権を付けると、シェルからスクリプトをコマンドのように実行できます。

シバンのサンプル

#!/usr/bin/env miep

使い方

GAME言語のファイル拡張子はgmであるらしいので、ここではそれに則ります。

サンプルプログラムは、インタプリタ起動時に引数で指定すると読み込まれます。

コマンドプロンプトからは*ld filename.gmとして読み込んで下さい。#=1でrunです。

*がついているコマンドはオプショナルコマンドで、ユーザーが追加できるようにしてあります。（と言ってもインタプリタのソースを書き換える必要がありますが)

エディタはついてないです。行末が0xa（LF)で終わるテキストを読み込めます。

文法

syntax.docにあります。

履歴

・2023年1月31日 16ビット配列の取得の所にバグがあったので訂正。

・2023年2月1日　マイナーチェンジ。

・2023年2月2日　バグ修正 ver 0.9

・2023年2月3日　getch()関数を内包 ver 0.9.1

・2023年2月4日　for文修正 ver 0.9.2

・2023年2月8日　for文の普通の言語モードで動作するのを　*FM 1に、GAME言語モードで動作するのを*FM 0にする。 ver 0.9.3

・2024年7月24日 数のサポートをushortからshortにする。 ver 1.0.0

・2024年8月24日 1文字入力の呼び出しをgetch()からgetchar()にする。これにより一般のC言語に対応。名前をgamecとする。ver 1.0.1

### in English

I wrote an interpreter for the nostalgic GAME language in C.

There's little documentation, so it's a little different from the original, but please bear with me as it's an implementation on Linux.

The GAME language is now obsolete, but around 1980 it was all the rage as a processing system that could be easily used on microcontrollers. I also had fun creating my own interpreter/compiler based on the GAME language back then.

This program lacks sufficient error checking.

Compile, Install, and Run

Place miep.c in the current directory and compile it in the console with cc miep.c -o miep.

To install, simply place miep in /usr/local/bin/ with sudo cp miep /usr/local/bin/.

To run, run it as miep [file.gm].

You can add a shebang to miep. By adding a shebang and granting execution permissions, you can run the script like a command from a Linux shell.

Shebang Sample

#!/usr/bin/env miep

Usage

The file extension for the GAME language is apparently gm, so we'll follow that here.

The sample program can be loaded by specifying it as an argument when starting the interpreter.

From the command prompt, load it as *ld filename.gm. Enter #=1 to run it.

Commands marked with an * are optional and can be added by the user. (Although you will need to rewrite the interpreter source.)

No editor is included. Text ending with 0xa (LF) can be read.

Syntax

See syntax.doc.

History

- January 31, 2023: Fixed a bug in obtaining 16-bit arrays.

- February 1, 2023: Minor changes.

・February 2, 2023: Bug fixes, version 0.9

・February 3, 2023: Included the getch() function, version 0.9.1

・February 4, 2023: Fixed the for statement, version 0.9.2

・February 8, 2023: Changed the for statement's normal language mode to FM 1 and its game language mode to FM 0. version 0.9.3

・July 24, 2024: Changed number support from ushort to short. version 1.0.0

・August 24, 2024: Changed the single-character input call from getch() to getchar(), making it compatible with general C language. version 1.0.1


Translated with DeepL.com (free version)


# GAME Language Compiler

# 日本語

GAME言語からCへ変換するコンパイラをpythonで書いてみました。

GAME言語コンパイラ -  gamecomp.py

`./gamecomp.py file.gm >out.c`とすると、GAME言語で書かれたfile.gmをCのソースに変換し、out.cに出力します。

out.cはccでコンパイル可能です。 `cc out.c -o a.out`、`./a.out`で実行することが出来ます。

一般に冗長さを許せば、低級なプログラム言語で書かれたソースは、より高級なプログラム言語に翻訳することが容易です。

最適化はできていません。エラーチェックが甘いです。

ccのインラインアセンブラを使用しているので、x86_64 linux/FreeBSDシステム用です。

!=n(gosub)と] (ret) が機械依存部で、それ以外は機械独立です。完全に機械独立にし、一般のCコンパイラに掛けることができるようにすることが今後の課題ですが、C言語の仕様上、サブルーチン呼び出しを記述するのは難しいかも知れません。

一応完成 version 1.0.0 2024/8/26

ちょっとヴァージョンアップ、改名。 version 1.0.1 2024/8/27

剰余計算結果取得のバグ修正 version1.0.2 2025/04/11

FreeBSDシステム用に、コールスタックを１６バイトアライメントに調整するデバッグ。 version 1.0.3　2025/08/31

# 今後の課題の問題点

・for-next,do-untl文の、for文またはdo文一つに対して複数のnext文、until文がある場合には対応していません。

・for文の終値に変数を使うと、カウントアップとして扱われる。

・next文に２重以上の括弧があるとバグる。

# in English 

I wrote a compiler in python to convert from GAME language to C.

GAME language compiler - gamecomp.py

`. /gamecomp.py file.gm >out.c` will convert file.gm written in GAME language to C source and output to out.c.

out.c can be compiled with cc. `cc out.c -o a.out`, `. /a.out` to execute it.

In general, if verbosity is allowed, sources written in lower-level programming languages can be easily translated into higher-level programming languages.

It is not optimized. Error checking is lax.

It uses the cc inline assembler and is for x86_64 linux/FreeBSD systems.

! =n(gosub) and] (ret) are machine dependent parts, the rest are machine independent. It is my future task to make it completely machine-independent so that it can be hung on a general C compiler, but it may be difficult to write subroutine calls due to the C language specification.

Any way completed. version 1.0.0 8/26/2024

A little version up, renamed. version 1.0.1 8/27/2024

Fixed a bug in obtaining the remainder calculation result version1.0.2 04/11/2025

# Issues for future work

The for-next and do-untl statements do not support the case where there are multiple next and until statements for a single for or do statement.

If a variable is used for the end value of a for statement, it is treated as a count-up.

If there are two or more parentheses in the next statement, it is buggy.

