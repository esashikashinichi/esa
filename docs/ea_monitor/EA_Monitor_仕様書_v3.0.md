# EA_Monitor v3.0 仕様書

- ファイル: `EA_Monitor_v3.0.mq4`(置き場所: `MQL4/Experts`)
- 版の表記: ファイル名 / `#property version "3.00"` / 起動ログ「EA_Monitor v3.0 起動」の3か所で統一
- 旧版: `EA_Monitor.mq4`(v2)はそのまま残す
- 作成日: 2026-09-23

## 1. v2からの変更点

| # | 内容 | 目的 |
|---|---|---|
| 1 | `ea_monitor_m1state.csv` を追加。1分足ごとに1行、指標とラグナロク a〜e × 買い/売りの束の状態を記録 | 初弾の発火条件とナンピンの待機フィルターを特定するため(エントリーが無い足も記録) |
| 2 | ファイルに書き込めなかった行を捨てず、保留して次の周期に再送(最大20,000行) | Driveの同期中などで記録が消えていたため |
| 3 | 消えた注文の履歴が取れない時、捨てずに毎秒再確認。60回取れなければ `CLOSE_NOHIST` として記録 | 決済の取りこぼしで束の段数がずれていたため |
| 4 | 月末月初の稼働停止(自動売買ボタンを自動でOFF → 期間後にON) | 月末月初の相場を避けるため |
| 5 | 足替わりタイマーと稼働状態の表示(表示位置は左上/右上/左下/右下から選択) | 画面での確認用 |
| 6 | 起動時にTelegramへ起動通知 | Telegram設定が正しいかの確認用 |
| 7 | `OnTick()` を追加 | EAとして確実に認識させるため(移行ドキュメントの教訓2) |
| 8 | 既定値の変更: `FeatureBaseTF` = M1、`TelegramChatId` = 7173265821 | 現在の運用設定に合わせた |

既存の4つのCSV(`ea_monitor.csv` / `_equity` / `_baskets` / `_features`)は**列を変えていない**ので、v2から続けて記録できる。`ea_monitor.csv` の event 列に `CLOSE_NOHIST` が増えるだけ。

## 2. 月末月初の稼働停止

### 2.1 停止期間
- 日本時間(PCの時計とタイムゾーンから計算)で判定する。
- 「取引日」= 日本時間から `StopBoundaryHourJST`(初期値7)時間引いた日付。7時区切りなら、9/30 7:00〜10/1 6:59 が「9/30の取引日」。
- 営業日 = 月〜金。祝日(クリスマス・元日など)は考慮しない。
- 停止する取引日 = 月末の最終営業日から遡って `StopBusinessDaysBeforeMonthEnd` 日 〜 翌月の第1営業日から `StopBusinessDaysAfterMonthStart` 日。

| 月 | 停止期間(日本時間) |
|---|---|
| 2026年9月→10月 | 9/30(水) 7:00 〜 10/2(金) 7:00 |
| 2026年10月→11月 | 10/30(金) 7:00 〜 11/3(火) 7:00 |
| 2026年11月→12月 | 11/30(月) 7:00 〜 12/2(水) 7:00 |

※既存の `MonthEndStartStopper`(EA版・インジケーター版)は当月分の期間しか見ていないため、**月初の停止日が判定されない**(例: 10/1 は「稼働中」になる)。v3は前月末から続く期間も確認して、月初を正しく判定する。

### 2.2 動作

| 状況 | 動作 | 表示 |
|---|---|---|
| 期間外 | 何もしない | 月末月初:稼働中(緑) |
| 期間に入り、対象の建玉(magic 848/929)が残っている | 待つ。Telegramで開始時と1時間ごとに通知 | 月末月初:停止待ち(建玉N本)(オレンジ) |
| 期間中で建玉が0 | 自動売買ボタンをOFF。2秒後に状態を確認し、失敗なら最大3回押す。それでも失敗なら通知して10分後に再試行 | 月末月初:停止中(赤) |
| 期間中に手動でONに戻された | 手動の判断を優先し、その期間は自動でOFFにしない | 月末月初:停止期間(手動でON)(オレンジ) |
| 期間前から手動でOFF | 触らない(期間後もONにしない) | 月末月初:停止中(手動OFF)(赤) |
| 期間が終わった | **このEAがOFFにした場合だけ**ONに戻す | 月末月初:稼働中 |
| DLLが未許可 | 操作できないことを通知 | 月末月初:停止できません(DLL未許可)(赤紫) |

- 自動売買ボタンは、MT4の「自動売買」ボタンと同じコマンド(33020)をDLL(user32.dll)でMT4本体に送って押す。押す前に今の状態を確認し、逆に押さないようにする。
- 「このEAがOFFにした」ことはグローバル変数 `EA_MON_V3_AUTOOFF` に記憶する。MT4やEAを再起動しても、期間後にONへ戻せる。
- 自動売買をOFFにすると、**同じMT4のEAは全て**発注が止まる。ラグナロクの注文には利確・損切りの値が入っていないため、OFFの間は利確もナンピンもされない。そのため、初期設定は「建玉が0になってからOFF」にしている。
- 既存と同じ共有フラグ `EA_STOP_MONTH_END_START`(期間中=1)も立てる。v3を入れたら、表示が二重になるため `MonthEndStartStopper` は外してよい。
- Telegramに通知するタイミング: 期間に入った時、停止待ち(1時間ごと)、OFFにした時、ONに戻した時、失敗した時、期間が終わった時。

### 2.3 注意
- 建玉が0になった瞬間に押すため、同じ秒にラグナロクが新規に入ると、その建玉を持ったまま止まる可能性がある(確率は低い)。
- 建玉が0にならない限り止まらない。ラグナロクはa〜e × 買い/売りで常に建玉を持ちやすい。
- このEA自身は、自動売買OFFの間もタイマーで動き続ける前提で作っている。**実口座で使う前に、デモ口座で `TestForceStopPeriod = true` にして、OFF → 表示 → Telegram → falseに戻してON、の流れを必ず確認する。**

## 3. 画面表示

| 項目 | 内容 |
|---|---|
| 並び | `[足替わりタイマー] [月末月初の稼働状態]` を同じ行に表示。右側の角ではタイマーが左、稼働状態が角側 |
| 表示位置 | `DisplayCorner`(左上/右上/左下/右下のプルダウン)、`DisplayX` / `DisplayY` / `DisplayGapPx` |
| タイマー | このチャートの時間足の、次の足までの残り時間(MM:SS。H1以上は H:MM:SS)。ティックが無い間もPCの時計で1秒ごとに進む |
| タイマーの文字 | サイズ14(稼働状態の12より大きい)。通常は黄色、残り15秒から赤 |
| 変更できる値 | `TimerFontSize` / `StatusFontSize` / `TimerColorNormal` / `TimerColorWarn` / `TimerWarnSeconds` / `DisplayFont` |

## 4. ea_monitor_m1state.csv(1分ごとの状態)

1分足が切り替わるたびに1行。`bar_time` は新しい足の開始時刻(=ラグナロクが判定する瞬間)。指標は確定足(shift=1)の値。

| 列 | 内容 |
|---|---|
| bar_time; symbol; bid; ask; spread_pts | 時刻と価格 |
| close1 | 直前の確定した1分足の終値 |
| diff3; diff11; diff20 | bid − 3/11/20本前の1分足の終値(b/c/aの初弾の方向判定に対応) |
| m1_stoK9; m1_stoD9; m1_stoK5; m1_stoD5 | 1分足ストキャス(9,3,3)と(5,3,3)の%K・%D |
| m1_ma5; m1_ma10; m1_ma20; m1_rsi14; m1_atr14 | 1分足のSMA5/10/20、RSI14、ATR14 |
| m5_… | 5分足の同じ9項目 |
| equity; margin_level_pct; autotrading; stop_state | 口座の状態、自動売買ボタン(1=ON)、月末月初の状態番号 |
| {a〜e}_{buy/sell}_legs / _lots / _avg / _last_price / _sec_since_last / _adverse_pts / _floating | 束ごとのレグ数、合計ロット、平均建値、直前レグの価格、直前レグからの経過秒、直前レグからの逆行幅(pts、プラス=不利)、含み損益 |

- 束はラグナロクの建玉から直接集計する(magic 848=買い、929=売り、コメントの頭文字 a〜e)。
- 対象はEAを置いたチャートの通貨ペア。

## 5. 入力パラメータ(v3で追加)

| 変数 | 初期値 | 内容 |
|---|---|---|
| TelegramNotifyStartup | true | 起動通知を送る |
| TelegramNotifyMonthEndStop | true | 月末月初の通知を送る |
| EnableM1StateLog | true | 1分ごとの状態CSVを出す |
| M1StateFileName | ea_monitor_m1state.csv | ファイル名 |
| RagnarokMagicBuy / RagnarokMagicSell | 848 / 929 | ラグナロクのマジック |
| RagnarokGrids | a,b,c,d,e | コメントの頭文字 |
| MissingCloseMaxTries | 60 | 決済履歴の再確認回数(秒) |
| EnableMonthEndStop | true | 月末月初の停止を使う |
| StopBusinessDaysBeforeMonthEnd | 1 | 月末側の営業日数 |
| StopBusinessDaysAfterMonthStart | 1 | 月初側の営業日数 |
| StopBoundaryHourJST | 7 | 停止・再開の時刻(日本時間) |
| AutoTradingOffOnStop | true | 自動売買ボタンをOFFにする |
| WaitFlatBeforeOff | true | 建玉が0になってからOFFにする |
| StopTargetMagics | 848,929 | 建玉0の判定に使うマジック |
| WaitNotifyIntervalMin | 60 | 停止待ちの再通知間隔(分) |
| StopFlagGlobalVariableName | EA_STOP_MONTH_END_START | 他EA向けの共有フラグ名 |
| TestForceStopPeriod | false | 【動作確認用】今を停止期間として扱う |
| ShowDisplay | true | 画面表示 |
| DisplayCorner | 左上 | 表示位置 |
| DisplayX / DisplayY / DisplayGapPx | 10 / 20 / 10 | 位置と間隔(ピクセル) |
| DisplayFont | MS UI Gothic | 文字の種類 |
| TimerFontSize / StatusFontSize | 14 / 12 | 文字サイズ |
| TimerColorNormal / TimerColorWarn / TimerWarnSeconds | 黄 / 赤 / 15 | タイマーの色 |

## 6. 設置手順

1. `EA_Monitor_v3.0.mq4` を `MQL4/Experts` に置き、MetaEditorで開いてコンパイル(F7)。エラー0を確認する。
2. v2の設定画面で「保存」→ 設定ファイル(.set)を保存し、v3の設定画面で「読み込み」すると、Telegramのトークンなど今の設定を引き継げる(v3で増えた項目は初期値になる)。
3. 「全般」タブで「DLLの使用を許可する」にチェックを入れる(月末月初の自動停止に必要)。
4. v2をチャートから外し、同じチャートにv3を設定する。v2とv3を同時に動かすと、同じCSVに二重に記録されるので注意。
5. Telegramに「EA_Monitor v3.0 起動しました」が届くことを確認する。
6. 表示が二重になるため、`MonthEndStartStopper` はチャートから外す。
7. 実口座で使う前に、デモ口座で `TestForceStopPeriod = true` を試す(2.3節)。
