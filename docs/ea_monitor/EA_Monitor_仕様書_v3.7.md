# EA_Monitor v3.7 仕様書

- ファイル: `EA_Monitor_v3.7.mq4`(置き場所: `MQL4/Experts`)
- 版の表記: 次の3か所で統一している。
  - ファイル名
  - `#property version "3.70"`
  - 起動ログ「EA_Monitor v3.7 起動」と、Telegramの起動通知「[EA_Monitor v3.7] 起動しました」
- 旧版はそのまま残す。
  - `EA_Monitor.mq4`(v2)
  - `EA_Monitor_v3.5.mq4`(v3.0。v3.5の名前で稼働中)
  - `EA_Monitor_v3.6.mq4`
- 作成日: 2026-09-25
- v3.6の変更(ロジックごとの束の判定)を全て含む。v3.6以前の機能はそのままなので、v3.6の仕様書を参照。
- 注意: この環境ではMQL4のコンパイルを確認できない。MetaEditorでコンパイルし、エラーが出たら内容を知らせてほしい。

## 0. v3.7の変更点(v3.6からの差分)

**目的**: 解析19で特定できなかった次の3点を、実機で特定する。
1. 初弾の発火条件
2. ナンピンの反発確認の幅
3. 早期決済の数値

1分ごとの記録では足の中の動きが分からないため、ティックごとに値動きを追跡し、イベントの時だけ要約を1行書く。ティックを全部記録する方式は重いので採らない(以前のShinさんの判断)。

**追加したファイル**: `ea_monitor_events_v37.csv`(新しいファイル。既存のCSVの列は変えていない)

- 列は、過去のログから同じ項目を作る再構成ファイル(`tools/ragnarok/prior_extremes.py` の出力)と**全く同じ**にしてある。
- そのため、実機の記録と過去の再構成をそのまま並べて比べられる。
- 違いは精度だけ。再構成はM1足の高値・安値で近似する。v3.7はティックで測る。

**追加した入力**

| 入力 | 既定値 | 意味 |
|---|---|---|
| `EnableEventLog` | true | `ea_monitor_events_v37.csv` を出力するか |
| `EventFileName` | `ea_monitor_events_v37.csv` | 出力ファイル名 |
| `NanpinMinSeconds` | 420 | ナンピンの時間条件(記録用。ラグナロクの動作は変えない) |
| `NanpinMinPts` | 110 | ナンピンの値幅条件(記録用) |
| `ProbeProfitPts` | 100 | 含み益がこの幅に達した時刻を記録する(早期決済の調査用) |

**記録の対象**
- マジックが `RagnarokMagicBuy`(848)または `RagnarokMagicSell`(929)の注文だけ。
- コメントが「英字_数字」(例: `b_3`)の注文だけ。

**値動きの追跡**
- 進行中の束ごとに、最後のレグ以降の値動きを追跡する。
- 更新するタイミングは、ティックごと(`OnTick`)と1秒ごと(`OnTimer`)の両方。
- 追跡する項目:

| 項目 | 測り方 |
|---|---|
| 最大逆行 | 最後のレグの建値から、買いはask、売りはbidで測る。時刻も記録する |
| 高値・安値 | 最後のレグ以降のbidの高値・安値 |
| 条件が揃った時刻 | 時間(420秒)と値幅(110pts)の条件が初めて揃った時刻 |
| 最大含み益(MFE) | 平均建値から、買いはbid、売りはaskで測る。時刻も記録する |
| 最大含み損 | 平均建値から、MFEと同じ価格で測る |
| 100pts到達 | 含み益が100ptsに初めて達した時刻と、その後の最小含み益 |

- 新しいレグが入ると、これらを初期化して測り直す。
- **必ずGOLDmicroのチャートに設定すること。**
  - `OnTick` はチャートの通貨ペアのティックでしか動かない。
  - 別の通貨ペアのチャートだと1秒ごとの更新だけになり、1秒の間の高値・安値を取りこぼす。

## 1. `ea_monitor_events_v37.csv` の列

区切りは `;`。値が無い列は空欄。価格はドル、幅は pts(0.01ドル)、時刻はサーバー時間。

**共通**

| 列 | 内容 |
|---|---|
| event | `ENTRY`(初弾) / `NANPIN`(ナンピン) / `BASKET_CLOSE`(束の決済) / `OPEN_STATUS`(再構成ファイルだけ。最後の時点で決済されていない束) |
| time | 記録した時刻 |
| logic, side, basket, leg | ロジック(a〜e)、buy/sell、束ID、段の番号(コメントの数字) |
| price, bid, ask, spread_pts | 建値、記録した瞬間のbid・ask、スプレッド |
| gap | 記録の注意。`restored`(起動時に復元した束で、起動前の値動きを含まない)、`close_nohist`(決済履歴が取れなかった)、`no_basket`(追加先の束が見つからない)。再構成ファイルでは `leg_missing` / `close_missing` / `close_not_logged` も使う |

**ENTRY(初弾)**: 発火条件を調べるための列

| 列 | 内容 |
|---|---|
| mom3_pts / mom11_pts / mom20_pts | 今のbid − 3/11/20本前のM1足の終値(bの方向ルールは3本前、cは11本前) |
| mom_m15c2_pts | 今のbid − 2本前のM15足の終値(aの方向ルール。解析20) |
| prev_bar_open/high/low/close | 1本前のM1足 |
| high5/low5, high15/low15, high60/low60 | 直近5/15/60本のM1足の高値・安値 |
| sec_since_prev_entry / sec_since_prev_close | 同じロジック・方向の、前回の初弾・前回の束の決済からの秒数 |

**NANPIN(ナンピン)**: 反発確認の幅を調べるための列

| 列 | 内容 |
|---|---|
| prev_leg_price / prev_leg_time / sec_since_prev_leg | 直前のレグの建値・時刻・経過秒数 |
| lot_ratio | 直前のレグに対するロットの倍率 |
| adv_now_pts | 今回の建値の、直前のレグからの逆行幅 |
| adv_max_pts / adv_max_time | 直前のレグ以降の最大逆行と時刻(= 直前の高値・安値) |
| high_since_prev / low_since_prev | 直前のレグ以降のbidの高値・安値 |
| bounce_pts | 最大逆行 − 今回の逆行(底からどれだけ戻って入ったか) |
| cond_met_time / wait_sec | 時間と値幅の条件が揃った時刻と、そこからナンピンまでの待ち秒数 |

**BASKET_CLOSE(束の決済)**: 早期決済の数値を調べるための列

| 列 | 内容 |
|---|---|
| legs / total_lots / avg_price | 最大段数、最大合計ロット、平均建値 |
| close_price / close_pts / profit_yen | 決済価格、平均建値からの決済幅、実現損益(円) |
| sec_since_last_leg / sec_since_first_leg | 最後のレグ・最初のレグからの秒数 |
| mfe_pts / mfe_time / sec_mfe_to_close | 最後のレグ以降の最大含み益、その時刻、そこから決済までの秒数 |
| mae_pts | 最後のレグ以降の最大含み損 |
| reach100_time / min_fav_after_reach100 | 含み益が100pts(`ProbeProfitPts`)に初めて達した時刻と、その後の最小含み益 |
| last_bid / fav_now_pts | 再構成ファイルの `OPEN_STATUS` だけで使う(今のbidと今の含み益) |

## 2. 入れ替えの手順

1. `EA_Monitor_v3.7.mq4` を `MQL4/Experts` に置き、MetaEditorでコンパイルする。
2. 今の EA_Monitor(v3.5)をチャートから外し、v3.7を**GOLDmicroのチャート**に設定する。
   - 設定は .set で引き継ぐ。
   - Telegramのトークンは入力欄に入れる。**トークンはコードに書かない。**
3. 「DLLの使用を許可する」はv3と同じ(月末月初の停止を使う場合)。
4. v3.5からの入れ替えでは、v3.6の変更も同時に入る。
   - 束の集計は `ea_monitor_baskets_v36.csv`(logic列付き)に出力されるようになる。
   - 旧 `ea_monitor_baskets.csv` はそのまま残る。
5. 起動の直後に建っている束は `restored` の印付きになる(起動前の値動きを含まないため)。次の初弾からは完全な記録になる。

## 3. 確認のしかた

- 起動ログに「EA_Monitor v3.7 起動 … イベント記録=true」と出る。
- `MQL4/Files/ea_monitor_events_v37.csv` にヘッダー行が1行でき、初弾・ナンピン・決済のたびに1行ずつ増える。
- 数日分がたまったら、再構成ファイル(過去分)と合わせて解析する。
