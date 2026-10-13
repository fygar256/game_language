# tetris.gm (TETRIS in GAME language)

`tetris.py`（supertext 版）を GAME 言語に移植し、`miep`（C 版）で動かします。

## ファイル構成

| ファイル | 説明 |
| --- | --- |
| `tetris.gm` | ゲーム本体（GAME 言語） |
| `miep.c` | GAME 言語インタプリタ。キー入力の `&` 項と待ち時間の `*WT` 命令を追加したもの |

## 起動方法

```
make
sudo ./miep tetris.gm
```

80桁×25行以上の端末で起動してください。

キーは `/dev/input/eventN` から直接読みます。このデバイスは通常 root しか読めないので、`sudo` で起動します。sudo を使わずに遊ぶ場合は、FreeBSD なら `/etc/devfs.rules` で読み取りを許可します。

```
[localrules=10]
add path 'input/event*' mode 0660 group operator
```

`/etc/rc.conf` に `devfs_system_ruleset="localrules"` を書き、`sudo service devfs restart` すると、operator グループのユーザーが読めるようになります。

キーボードは自動で探します。特定のデバイスを使う場合は環境変数 `MIEP_KBD` で指定します。

```
sudo MIEP_KBD=/dev/input/event7 ./miep tetris.gm
```

## ゲームの遊び方

起動すると「HIT ENTER」と表示されるので、ENTER を押すと始まります。

落ちてくるテトリスを動かしたり回したりして、横一列をそろえると消えます。積み上がって新しいテトリスが置けなくなったらゲームオーバーです。ゲームオーバーになったら `q` で終了します。

画面の左上に得点（SCORE）、出したテトリスの数（TETRIS）、消した行数（LINES）、その下に次のテトリス（NEXT）を表示します。

### キー操作

| 操作 | キー |
| --- | --- |
| 左に移動 | `4` / `←` |
| 右に移動 | `6` / `→` |
| 回転 | `SPACE` / `↑` |
| 速く落とす | `2` / `↓` |
| 終了 | `q` |

数字キーはテンキーでも、上段の数字キーでも操作できます。回転はキーを押し直すたびに1回だけ回ります。

### 得点

- 1コマごとに 1 点
- テトリスが固定されるたびに、消した行数 l に応じて 2^l×100 点（0行で 100、1行で 200、2行で 400、3行で 800、4行で 1600）

### 速さ

出したテトリスの数が増えると速くなります。テトリスは 2 コマに 1 マス落ちます。

| 出したテトリス数 | 1コマの長さ |
| --- | --- |
| 0〜39 | 70 ミリ秒 |
| 40〜70 | 58 ミリ秒 |
| 71〜100 | 46 ミリ秒 |
| 101〜130 | 35 ミリ秒 |
| 131〜160 | 23 ミリ秒 |
| 161〜 | 12 ミリ秒 |

`2` を押している間は 1コマ 20 ミリ秒になります（1マス約 40 ミリ秒で落ちます）。

### 回転と固定

- 回転して重なるときは、位置を少しずらして（キック）回せる場所を探します。I テトリスはさらに 2〜3 マス離れた位置も探します。
- 着地してから約 0.5 秒たつと固定されます。着地中に移動や回転をすると、15 回まで固定を先に延ばせます。

## しくみ

- `&n` はキーコード n のキーが押されていれば 1 を返します。キーコードは `/usr/include/dev/evdev/input-event-codes.h` の値です（`q`=16、`SPACE`=57、テンキーの `4`=75 など）。前回調べてから一瞬だけ押されたキーも 1 になるので、短く叩いたキーも取りこぼしません。
- 1コマごとに `*WT W` で W ミリ秒待ちます。
- ゲーム中は押したキーが端末に表示されません。終了時には端末の設定を戻し、ゲーム中に打った文字も捨てます。
- 画面は 40×25 マスで、1マスを2桁で描きます。フィールドは横 10 マス × 縦 24 マスです。ブロックは背景色で塗った2桁の空白で描き、枠は灰色です。L 字のテトリスは 256 色のオレンジ（`ESC[48;5;208m`）で描くので、256 色に対応した端末で遊んでください。
- 画面の内容（文字と色）はメモリ上の画面バッファに持ち、当たり判定やライン消去に使います。
- テトリスの形は、向きごとに4つのブロックの (dx, dy) をバイト配列に持っています。
- miep には時計がないので、着地してからの時間は 1コマ = W+3 ミリ秒と見積もって数えます（3 ミリ秒はインタプリタと画面出力にかかる時間の見積もり）。

### 調整

| 行 | 内容 | 既定値 |
| --- | --- | --- |
| 2510〜2560 | 出したテトリス数ごとの 1コマの長さ W（ミリ秒） | 70〜12 |
| 2250 | `2` を押しているときの 1コマの長さ | `W=20` |
| 2130 | 固定までの時間（ミリ秒） | `500` |
| 2120 | 固定を延ばせる回数 | `15` |
| 2270 | 1コマあたりの処理時間の見積もり（ミリ秒） | `3` |

## 原作との違い

- `&` と `*WT` は C 版の `miep` と `beam.py` だけの機能です。`miep.py` では動きません。
- 矢印キーでも操作できるようにしました。
- 1コマの長さは、supertext の `sleep()` が実際に待つ時間を測ってミリ秒に置き換えました。
- 得点は 16 ビットの変数ではあふれるので、H×10000+L の2つに分けて持っています。
- 原作で白だった L 字のテトリスはオレンジにしました。得点と行数の数字は白ではなく端末の標準の文字色で表示します。白い背景の端末でも見えるようにするためです。
- 終了すると画面を消して端末に戻ります。

---

# English

# tetris.gm (TETRIS in GAME language)

This is a port of `tetris.py` (the supertext version) to the GAME language. It runs on `miep` (the C version).

## Files

| File | Description |
| --- | --- |
| `tetris.gm` | The game itself (GAME language) |
| `miep.c` | GAME language interpreter, extended with the `&` key-input term and the `*WT` wait command |

## How to run

```
make
sudo ./miep tetris.gm
```

Use a terminal of at least 80 columns × 25 lines.

Keys are read directly from `/dev/input/eventN`. These devices are normally readable only by root, so start the game with `sudo`. To play without sudo on FreeBSD, allow read access in `/etc/devfs.rules`:

```
[localrules=10]
add path 'input/event*' mode 0660 group operator
```

Then add `devfs_system_ruleset="localrules"` to `/etc/rc.conf` and run `sudo service devfs restart`; users in the operator group can then read the devices.

The keyboard is detected automatically. To use a specific device, set the `MIEP_KBD` environment variable:

```
sudo MIEP_KBD=/dev/input/event7 ./miep tetris.gm
```

## How to play

When the game starts, "HIT ENTER" is shown. Press ENTER to begin.

Move and rotate the falling pieces to complete horizontal lines, which then disappear. When a new piece can no longer be placed, the game is over. Press `q` on the game-over screen to quit.

The top left of the screen shows the score (SCORE), the number of pieces dealt (TETRIS), and the number of lines cleared (LINES). The next piece (NEXT) is shown below them.

### Controls

| Action | Key |
| --- | --- |
| Move left | `4` / `←` |
| Move right | `6` / `→` |
| Rotate | `SPACE` / `↑` |
| Drop faster | `2` / `↓` |
| Quit | `q` |

The number keys work on both the numeric keypad and the top row. Rotation turns the piece once per key press.

### Scoring

- 1 point per frame
- Each time a piece locks, 2^l×100 points for l cleared lines (100 for 0 lines, 200 for 1, 400 for 2, 800 for 3, 1600 for 4)

### Speed

The game speeds up as more pieces are dealt. A piece falls one cell every 2 frames.

| Pieces dealt | Frame length |
| --- | --- |
| 0–39 | 70 ms |
| 40–70 | 58 ms |
| 71–100 | 46 ms |
| 101–130 | 35 ms |
| 131–160 | 23 ms |
| 161– | 12 ms |

While `2` is held, a frame is 20 ms (a piece falls one cell about every 40 ms).

### Rotation and locking

- If a rotated piece would overlap something, the game tries slightly shifted positions (kicks) to find room. The I piece also tries positions 2–3 cells away.
- A piece locks about 0.5 seconds after it lands. Moving or rotating it while landed postpones the lock, up to 15 times.

## How it works

- `&n` returns 1 if the key with key code n is pressed. Key codes are the values in `/usr/include/dev/evdev/input-event-codes.h` (`q`=16, `SPACE`=57, keypad `4`=75, and so on). A key that was pressed briefly since the last check also returns 1, so short taps are not missed.
- Each frame waits W milliseconds with `*WT W`.
- Keys pressed during the game are not echoed to the terminal. On exit, the terminal settings are restored and the characters typed during the game are discarded.
- The screen is 40×25 cells, each drawn 2 columns wide. The playfield is 10 cells wide and 24 cells tall. Blocks are drawn as two spaces painted with a background color; the frame is gray. The L piece is drawn in 256-color orange (`ESC[48;5;208m`), so use a terminal that supports 256 colors.
- The screen contents (characters and colors) are kept in a screen buffer in memory, which is used for collision checks and line clearing.
- Each piece shape is stored as the (dx, dy) of its four blocks per rotation, in a byte array.
- miep has no clock, so the time since landing is counted by assuming one frame takes W+3 ms (3 ms is an estimate of the interpreter and screen output time).

### Tuning

| Line | Description | Default |
| --- | --- | --- |
| 2510–2560 | Frame length W (ms) for each number of pieces dealt | 70–12 |
| 2250 | Frame length while `2` is held | `W=20` |
| 2130 | Time until a landed piece locks (ms) | `500` |
| 2120 | How many times the lock can be postponed | `15` |
| 2270 | Estimated processing time per frame (ms) | `3` |

## Differences from the original

- `&` and `*WT` are available only in the C version of `miep` and in `beam.py`. They do not work in `miep.py`.
- Arrow keys were added as alternative controls.
- Frame lengths were converted to milliseconds by measuring how long supertext's `sleep()` actually waits.
- The score would overflow a 16-bit variable, so it is kept in two parts, H×10000+L.
- The L piece, white in the original, is orange. The score and line numbers use the terminal's default text color instead of white. Both changes keep them visible on terminals with a white background.
- On exit, the screen is cleared and you return to the terminal.
