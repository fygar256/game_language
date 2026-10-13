# ahonokotank.gm (AHONOKO TANK in GAME language)

昔懐かしのPCゲームを今のパソコンに移植しようシリーズ Games in the attic その4 の、GAME 言語版です。

`ahotan/ahonokotank.py`（supertext 版）を GAME 言語に移植し、`miep`（C 版）で動かします。

## ファイル構成

| ファイル | 説明 |
| --- | --- |
| `ahonokotank.gm` | ゲーム本体（GAME 言語） |
| `miep.c` | GAME 言語インタプリタ。キー入力の `&` 項と待ち時間の `*WT` 命令を追加したもの |

マップは本体にデータとして埋め込んであるので、`ahotan.map` は不要です。

## 起動方法

```
make
sudo ./miep ahonokotank.gm
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
sudo MIEP_KBD=/dev/input/event7 ./miep ahonokotank.gm
```

## ゲームの遊び方

左右のタンクを、右と左に分けて二人でプレイする対戦型ゲームです。

弾はタンクの向きに移動するので、タンクで弾を遠隔操作し、相手を砲撃してください。

先に3ポイント取ったほうが勝ちです。ポイントが入ったら ENTER で次のラウンドに進みます。

### キー操作

| | 上 | 下 | 左 | 右 | 発射 |
| --- | --- | --- | --- | --- | --- |
| LEFT (◯) | `e` | `c` | `s` | `f` | `z` |
| RIGHT (●) | `8` | `2` | `4` | `6` | `0` |

RIGHT はテンキーでも、上段の数字キーでも操作できます。`q` を押したらゲームから抜けます。

## しくみ

- `&n` はキーコード n のキーが押されていれば 1 を返します。キーコードは `/usr/include/dev/evdev/input-event-codes.h` の値です（`e`=18、テンキーの `8`=72 など）。前回調べてから一瞬だけ押されたキーも 1 になるので、短く叩いたキーも取りこぼしません。
- 1コマごとに `*WT A` で A ミリ秒待ちます。
- ゲーム中は押したキーが端末に表示されません。終了時には端末の設定を戻し、ゲーム中に打った文字も捨てます。
- 画面は1マスを2桁で描きます。壁は緑、タンクは ◯ と ●、砲身と弾は ｜ と －、命中は ＊ です。

### 調整

`ahonokotank.gm` の行100 で変えられます。

| 変数 | 説明 | 既定値 |
| --- | --- | --- |
| `A` | 1コマの長さ（ミリ秒） | `50` |
| `M` | 弾が1マス進むコマ数（大きいほど遅い） | `1` |

## 原作との違い

- `&` と `*WT` は C 版の `miep` と `beam.py` だけの機能です。`miep.py` では動きません。

---

# English

# ahonokotank.gm (AHONOKO TANK in GAME language)

Games in the attic, part 4: the GAME language version.

This is a port of `ahotan/ahonokotank.py` (the supertext version) to the GAME language. It runs on `miep` (the C version).

## Files

| File | Description |
| --- | --- |
| `ahonokotank.gm` | The game itself (GAME language) |
| `miep.c` | GAME language interpreter, extended with the `&` key-input term and the `*WT` wait command |

The map is embedded in the program as data, so `ahotan.map` is not needed.

## How to run

```
make
sudo ./miep ahonokotank.gm
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
sudo MIEP_KBD=/dev/input/event7 ./miep ahonokotank.gm
```

## How to play

A two-player battle game: one player controls the left tank, the other the right tank.

Bullets travel in the direction the tank is facing, so steer your bullet with your tank and shoot your opponent.

The first to score 3 points wins. After each point, press ENTER to start the next round.

### Controls

| | Up | Down | Left | Right | Fire |
| --- | --- | --- | --- | --- | --- |
| LEFT (◯) | `e` | `c` | `s` | `f` | `z` |
| RIGHT (●) | `8` | `2` | `4` | `6` | `0` |

RIGHT can use either the numeric keypad or the number keys on the top row. Press `q` to quit.

## How it works

- `&n` returns 1 if the key with key code n is pressed. Key codes are the values in `/usr/include/dev/evdev/input-event-codes.h` (`e`=18, keypad `8`=72, and so on). A key that was pressed briefly since the last check also returns 1, so short taps are not missed.
- Each frame waits A milliseconds with `*WT A`.
- Keys pressed during the game are not echoed to the terminal. On exit, the terminal settings are restored and the characters typed during the game are discarded.
- Each cell is drawn 2 columns wide. Walls are green, the tanks are ◯ and ●, barrels and bullets are ｜ and －, and a hit is ＊.

### Tuning

Change these on line 100 of `ahonokotank.gm`.

| Variable | Description | Default |
| --- | --- | --- |
| `A` | Length of one frame (milliseconds) | `50` |
| `M` | Frames per bullet step (larger is slower) | `1` |

## Differences from the original

- `&` and `*WT` are available only in the C version of `miep` and in `beam.py`. They do not work in `miep.py`.
