//+------------------------------------------------------------------+
//|                                               EA_Monitor_v3.0.mq4 |
//|   対象EAの「振る舞い」を外から記録するブラックボックス監視EA        |
//|   v2: ナンピン/グリッド系EAの解析に特化した拡張版                   |
//|   v3.0: (1) ラグナロク a〜e の1分ごとの状態記録(m1state.csv)       |
//|         (2) 記録漏れ対策(書き込み失敗行の再送・決済取りこぼし補完)  |
//|         (3) 月末月初の稼働停止(自動売買ボタンを自動でOFF/ON)       |
//|         (4) 足替わりタイマーと稼働状態の表示(表示位置は4隅から選択) |
//|                                                                  |
//|   使い方:                                                         |
//|     1. 対象EAを通常どおりチャートに設定して稼働させる               |
//|     2. 別の空きチャートにこのEAを1本だけ設定する                    |
//|     3. 新規建て/決済/指値注文/SL・TP変更を検知するたび、           |
//|        その瞬間の相場状態・口座状態・ナンピン構造をCSVに記録        |
//|                                                                  |
//|   出力先: <データフォルダ>/MQL4/Files/ 配下に4ファイル             |
//|     - ea_monitor.csv          : 生イベントログ(1建玉イベント=1行)  |
//|     - ea_monitor_equity.csv   : 口座状態の定期スナップショット      |
//|     - ea_monitor_baskets.csv  : ナンピン束(バスケット)ごとの集計   |
//|     - ea_monitor_features.csv : バー確定ごとの特徴量+エントリー有無 |
//|       (「なぜそのタイミングで入ったか」をエントリー無しの足と比較  |
//|        できるようにするための、ロジック解析専用データセット)       |
//|     - ea_monitor_m1state.csv  : [v3] 1分ごとの指標+a〜eの束の状態   |
//|   （UseCommonFolder=true で Common/Files 配下）                    |
//|                                                                  |
//|   設置の注意(v3):                                                 |
//|     - 必ず MQL4/Experts に置く(Indicatorsでは動かない)             |
//|     - 月末月初の自動停止を使う場合は、このEAの設定「全般」タブで    |
//|       「DLLの使用を許可する」にチェックを入れる                     |
//|     - 自動売買ボタンをOFFにした後も、このEAはタイマーで動き続け、   |
//|       期間が終わったら自分でONに戻す                                |
//+------------------------------------------------------------------+
#property strict
#property version     "3.00"
#property description "EA_Monitor v3.0: 監視・記録 + 月末月初の自動停止 + 足替わりタイマー"

//--- 自動売買ボタンの操作(月末月初の停止用) -------------------------------
#import "user32.dll"
int GetAncestor(int hWnd, int gaFlags);
int PostMessageW(int hWnd, int Msg, int wParam, int lParam);
#import
#define WM_COMMAND              0x0111
#define MT4_CMD_TOGGLE_AUTOTRADE 33020   // MT4の「自動売買」ボタンと同じコマンド
#define GA_ROOT                 2

#define OP_BALANCE 6
#define OP_CREDIT  7

//--- 入力パラメータ ------------------------------------------------
extern string TargetMagics          = "0";     // 監視するマジックナンバー(カンマ区切り, "0"=全て)
extern string TargetSymbols         = "";      // 監視する通貨ペア(カンマ区切り, 空欄=全通貨ペア)
extern string LogFileName           = "ea_monitor.csv";         // 生イベントログ
extern string EquityFileName        = "ea_monitor_equity.csv";  // 口座状態の定期記録
extern string BasketFileName        = "ea_monitor_baskets.csv"; // ナンピン束ごとの集計
extern int    PollSeconds           = 1;       // イベント監視間隔(秒)
extern int    EquitySnapshotSeconds = 60;      // 口座状態スナップショットの間隔(秒)
extern bool   TrackPendingOrders    = true;    // 指値/逆指値注文のライフサイクルも監視するか
extern bool   UseCommonFolder       = false;   // 共有フォルダに出力するか
extern int    ServerGmtOffsetHours  = 2;       // ブローカーサーバー時間のGMTオフセット(セッション判定用の目安)

//--- エントリーロジック解析用(バー確定ごとの特徴量ログ) ---------------
extern bool   EnableFeatureLog      = true;               // ea_monitor_features.csv を出力するか
extern string FeatureBaseTF         = "M1";                // 特徴量をサンプリングする基準時間足
extern string FeatureFileName       = "ea_monitor_features.csv";

//--- Telegram通知 ----------------------------------------------------
//  事前準備: 1) BotFatherでBotを作成しTelegramBotTokenを取得
//            2) Botとのチャットを開始し、TelegramChatId(自分のchat_id)を取得
//            3) MT4「ツール>オプション>EA」の"WebRequestを許可するURL"に
//               https://api.telegram.org を追加しておくこと(必須)
extern bool   EnableTelegram             = true;    // Telegram通知を有効化するか
extern string TelegramBotToken           = "";      // BotFatherから取得したトークン
extern string TelegramChatId             = "7173265821"; // 通知先のchat_id
extern bool   TelegramNotifyOpen         = true;    // 新規建て/ナンピン追加弾/指値約定
extern bool   TelegramNotifyClose        = true;    // 決済
extern bool   TelegramNotifyBasketClose  = true;    // ナンピン束が全決済で完結した時のサマリ
extern bool   TelegramNotifyPending      = false;   // 指値の新規設置/キャンセル(頻度が多いので既定オフ)
extern bool   TelegramNotifyModify       = false;   // SL/TP変更(頻度が多いので既定オフ)
extern bool   TelegramNotifyMarginAlert  = true;    // 証拠金維持率が閾値を下回った時の警告
extern double TelegramMarginAlertPct     = 300.0;   // 警告を出す証拠金維持率(%)のしきい値
extern int    TelegramMarginAlertCooldownMin = 30;  // 警告の再送間隔(分, 維持率が低いままの間)
extern bool   TelegramNotifyStartup      = true;    // 起動時に起動通知を送る(設定が正しいかの確認用)
extern bool   TelegramNotifyMonthEndStop = true;    // 月末月初の停止/再開/失敗を通知する

//--- [v3] ラグナロク(a〜e)の1分ごとの状態記録 ---------------------------
extern bool   EnableM1StateLog     = true;                     // ea_monitor_m1state.csv を出力するか
extern string M1StateFileName      = "ea_monitor_m1state.csv";
extern int    RagnarokMagicBuy     = 848;                      // ラグナロクの買いのマジック
extern int    RagnarokMagicSell    = 929;                      // ラグナロクの売りのマジック
extern string RagnarokGrids        = "a,b,c,d,e";              // コメントの頭文字(ロジック名)
extern int    MissingCloseMaxTries = 60;                       // 決済履歴が取れない時の再試行回数(秒)

//--- [v3] 月末月初の稼働停止 ---------------------------------------------
enum ENUM_DISP_CORNER
{
   DISP_LEFT_UPPER  = 0, // 左上
   DISP_RIGHT_UPPER = 1, // 右上
   DISP_LEFT_LOWER  = 2, // 左下
   DISP_RIGHT_LOWER = 3  // 右下
};
extern bool   EnableMonthEndStop              = true;      // 月末月初の稼働停止を使うか
extern int    StopBusinessDaysBeforeMonthEnd  = 1;         // 月末: 最終営業日から何営業日を停止するか
extern int    StopBusinessDaysAfterMonthStart = 1;         // 月初: 第1営業日から何営業日を停止するか
extern int    StopBoundaryHourJST             = 7;         // 停止の開始・再開時刻(日本時間の時)
extern bool   AutoTradingOffOnStop            = true;      // 停止期間に自動売買ボタンをOFFにするか(要DLL許可)
extern bool   WaitFlatBeforeOff               = true;      // 対象の建玉が0になってからOFFにするか
extern string StopTargetMagics                = "848,929"; // 建玉0の判定に使うマジック(カンマ区切り, 0=全て)
extern int    WaitNotifyIntervalMin           = 60;        // 停止待ちの間のTelegram再通知間隔(分)
extern string StopFlagGlobalVariableName      = "EA_STOP_MONTH_END_START"; // 他EA向けの共有フラグ名
extern bool   TestForceStopPeriod             = false;     // 【動作確認用】今を停止期間として扱う(デモ口座で使う)

//--- [v3] 画面表示(足替わりタイマー + 稼働状態) ----------------------------
extern bool             ShowDisplay       = true;             // 画面に表示するか
extern ENUM_DISP_CORNER DisplayCorner     = DISP_LEFT_UPPER;  // 表示位置
extern int              DisplayX          = 10;               // 表示位置: 横(角からのピクセル)
extern int              DisplayY          = 20;               // 表示位置: 縦(角からのピクセル)
extern int              DisplayGapPx      = 10;               // タイマーと稼働表示の間隔(ピクセル)
extern string           DisplayFont       = "MS UI Gothic";   // 文字の種類
extern int              TimerFontSize     = 14;               // 足替わりタイマーの文字サイズ
extern int              StatusFontSize    = 12;               // 稼働表示の文字サイズ
extern color            TimerColorNormal  = clrYellow;        // タイマーの色(通常)
extern color            TimerColorWarn    = clrRed;           // タイマーの色(残りわずか)
extern int              TimerWarnSeconds  = 15;               // 何秒前から警告色にするか

//--- 建玉/注文の1件分のスナップショット ------------------------------
struct OrderSnap
{
   int      ticket;
   string   symbol;
   int      magic;
   int      type;       // OP_BUY..OP_SELLSTOP
   double   lots;
   double   openPrice;
   double   sl;
   double   tp;
   datetime openTime;
   string   comment;
};

//--- ナンピン束(同一symbol+magic+方向の建玉グループ)の状態 -----------
struct BasketState
{
   int      basketId;
   string   symbol;
   int      magic;
   int      type;            // OP_BUY or OP_SELL (束の方向)
   int      legCount;        // 現在の建玉数(ナンピン段数)
   int      maxLegs;         // これまでの最大段数
   double   totalLots;       // 現在の合計ロット
   double   maxTotalLots;    // これまでの最大合計ロット
   double   avgPrice;        // 現在の平均建値
   double   lastPrice;       // 直近に追加された建値
   double   lastLots;        // 直近に追加されたロット
   datetime firstOpenTime;   // 束が始まった時刻(1段目の建玉時刻)
   double   peakFloating;    // 束の含み益の最大値
   double   worstFloating;   // 束の含み損の最大値(最も小さい=マイナスが大きい)
   double   realizedSum;     // これまでに決済確定した損益の合計(スワップ/手数料込み)
   double   sumLotMultiplier;// 直前段比ロット倍率の合計(平均算出用)
   int      cntLotMultiplier;
   double   sumGridStepPts;  // 直前段との値幅(pt)の合計(平均算出用)
   int      cntGridStepPts;
};

//--- エントリー発生ログ(特徴量ログのラベル付けに使う軽量な履歴) -------
struct EntryLogItem
{
   string   symbol;
   datetime time;
   int      legIndex;   // 1=新規束の初弾, 2以上=ナンピン追加弾
};

//--- 内部状態 ------------------------------------------------------
OrderSnap    g_prevOrders[];     // 前回スキャン時点の対象注文スナップショット
BasketState  g_baskets[];        // 現在進行中のナンピン束一覧
int          g_nextBasketId = 1;
double       g_equityPeak   = 0;
datetime     g_lastEquitySnap = 0;

double       g_cashFlowAdjustment = 0; // 入金/出金/クレジット増減の累計(ドローダウン計算からこの分を除外するため)
int          g_historyScanPos      = 0; // 資金移動履歴スキャンの現在位置(OrdersHistoryTotal()基準)

int    g_targetMagics[];
bool   g_matchAllMagic = false;
string g_targetSymbols[];
bool   g_matchAllSymbol = false;

string g_tfNames[]   = {"M5","M15","H1"};
int    g_tfPeriods[] = {PERIOD_M5,PERIOD_M15,PERIOD_H1};

EntryLogItem g_entryLog[];        // 直近のエントリー発生履歴(特徴量ログのラベル付け用)
string       g_featureSymbols[];  // 特徴量ログの対象通貨ペア一覧
datetime     g_lastFeatureBar[];  // 通貨ペアごとの最終確定バー時刻
int          g_featureTf = PERIOD_M5;

datetime     g_lastMarginAlert = 0; // Telegram証拠金警告のクールダウン管理

//--- [v3] 書き込みに失敗した行の保留キュー(Driveの同期中などでファイルが開けない時用) ----
string       g_pendFile[];
string       g_pendLine[];
datetime     g_lastAppendErrPrint = 0;
#define      MAX_PENDING_LINES 20000

//--- [v3] 消えたのに履歴が取れなかった注文(決済の取りこぼし防止) ------------
OrderSnap    g_missing[];
int          g_missingTries[];

//--- [v3] ラグナロクの束(a〜e × 買い/売り)の集計 ---------------------------
string       g_gridLetters[];
datetime     g_lastM1StateBar = 0;

//--- [v3] 月末月初の稼働停止 -------------------------------------------
#define      GV_AUTOOFF   "EA_MON_V3_AUTOOFF"      // 1 = このEAが自動売買をOFFにした
#define      GV_OVERRIDE  "EA_MON_V3_OVERRIDE_KEY" // 手動でONに戻された停止期間(期間の開始日)
int          g_stopMagics[];
int          g_stopState       = 0;   // 表示用の状態(StopStateText参照)
int          g_waitCount       = 0;   // 停止待ちの建玉数
datetime     g_lastWaitNotify  = 0;
bool         g_prevInPeriod    = false;
bool         g_firstStopEval   = true;
int          g_toggleWant      = -1;  // 自動売買ボタン操作の結果待ち(0=OFF待ち,1=ON待ち,-1=なし)
datetime     g_toggleSentAt    = 0;
int          g_toggleTries     = 0;
datetime     g_toggleRetryAfter = 0;
bool         g_dllWarned       = false;
bool         g_startupNotified = false;

//--- [v3] 画面表示 --------------------------------------------------------
#define      OBJ_TIMER_NAME   "EAMonV3_Timer"
#define      OBJ_STATUS_NAME  "EAMonV3_Status"
int          g_serverMinusLocal = 0;   // サーバー時間 − PC時間(秒)。ティックが無い間もタイマーを進めるため
datetime     g_lastTickServer   = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   ParseIntCsv(TargetMagics, g_targetMagics);
   g_matchAllMagic = (ArraySize(g_targetMagics) == 1 && g_targetMagics[0] == 0);

   ParseStringCsv(TargetSymbols, g_targetSymbols);
   g_matchAllSymbol = (ArraySize(g_targetSymbols) == 0);

   ParseStringCsv(RagnarokGrids, g_gridLetters);
   ParseIntCsv(StopTargetMagics, g_stopMagics);

   EventSetTimer(MathMax(1, PollSeconds));

   WriteHeaderIfNeeded(LogFileName,
      "server_time;local_time;event;ticket;magic;symbol;type;lots;"
      "open_price;sl;tp;close_price;profit;swap;commission;comment;"
      "bid;ask;spread_pts;hour;dow;session;"
      "basket_id;leg_index;basket_legs;basket_total_lots;basket_avg_price;"
      "lot_multiplier;grid_step_pts;grid_step_atr" + IndicatorHeader());

   WriteHeaderIfNeeded(EquityFileName,
      "server_time;local_time;balance;equity;margin;free_margin;margin_level_pct;"
      "open_positions;open_lots;floating_pnl_all;drawdown_from_peak_pct;num_baskets;"
      "cash_flow_adjustment");

   WriteHeaderIfNeeded(BasketFileName,
      "basket_id;symbol;magic;type;open_time;close_time;duration_min;max_legs;"
      "max_total_lots;final_realized_profit;avg_lot_multiplier;avg_grid_step_pts;"
      "peak_floating_profit;worst_floating_drawdown");

   // --- 特徴量ログ(エントリーロジック解析用)の初期化 ---
   g_featureTf = TFStringToConst(FeatureBaseTF);
   if(g_matchAllSymbol)
   {
      // 通貨ペア無指定だと全銘柄を都度スキャンできないため、チャート銘柄のみを対象にする
      ArrayResize(g_featureSymbols, 1);
      g_featureSymbols[0] = Symbol();
      Print("注意: TargetSymbols未指定のため、特徴量ログはチャート銘柄(", Symbol(), ")のみを対象にします。"
            "複数銘柄を解析したい場合はTargetSymbolsに明示してください。");
   }
   else
   {
      ArrayResize(g_featureSymbols, ArraySize(g_targetSymbols));
      for(int fi = 0; fi < ArraySize(g_targetSymbols); fi++) g_featureSymbols[fi] = g_targetSymbols[fi];
   }
   ArrayResize(g_lastFeatureBar, ArraySize(g_featureSymbols));
   for(int fj = 0; fj < ArraySize(g_lastFeatureBar); fj++)
      g_lastFeatureBar[fj] = iTime(g_featureSymbols[fj], g_featureTf, 0); // 起動直後のバーはラベル付け対象外にする

   if(EnableFeatureLog)
      WriteHeaderIfNeeded(FeatureFileName,
         "bar_time;symbol;tf;open;high;low;close;body_pts;upper_wick_pts;lower_wick_pts;"
         "is_bullish;same_dir_streak;"
         "rsi;ma20;ma50;maDist_pts;atr;macdM;macdS;stoK;cci;"
         "bb_upper;bb_lower;bb_width_pts;price_vs_bb;"
         "donchian20_high;donchian20_low;breakout_up;breakout_down;"
         "h1_ma50;h1_trend_dist_pts;"
         "spread_pts;hour;dow;session;"
         "entry_leg1_flag;entry_leg1_count;entry_any_flag;entry_any_count");

   // 起動時点の既存建玉/注文を記憶し、既存のナンピン束があれば復元する
   BuildCurrentSnapshot(g_prevOrders);
   RebuildBasketsFromSnapshot();

   g_cashFlowAdjustment = 0;
   g_historyScanPos = OrdersHistoryTotal(); // 起動以前の入出金は対象外(今この瞬間から先の履歴のみ追跡する)

   g_equityPeak = AccountEquity() - g_cashFlowAdjustment;
   g_lastEquitySnap = 0;

   if(EnableM1StateLog)
      WriteHeaderIfNeeded(M1StateFileName, M1StateHeader());
   g_lastM1StateBar = iTime(Symbol(), PERIOD_M1, 0); // 起動直後の足は途中からなので記録しない

   // 月末月初の判定・自動売買ボタンの操作・通知は最初のタイマー(1秒後)から行う
   SyncServerTime();
   UpdateDisplay();

   Print("EA_Monitor v3.0 起動: 監視間隔=", PollSeconds, "秒, TargetMagics=", TargetMagics,
         ", TargetSymbols=", (TargetSymbols=="" ? "(全通貨)" : TargetSymbols),
         ", 指値監視=", TrackPendingOrders, ", 特徴量ログ=", EnableFeatureLog, "(", FeatureBaseTF, ")",
         ", 1分状態ログ=", EnableM1StateLog, ", 月末月初停止=", EnableMonthEndStop,
         ", 自動売買OFF=", AutoTradingOffOnStop, ", DLL許可=", IsDllsAllowed());
   Print("EA_Monitor v3.0: ", NextStopWindowText());
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectDelete(OBJ_TIMER_NAME);
   ObjectDelete(OBJ_STATUS_NAME);
   GlobalVariableDel(StopFlagGlobalVariableName); // 判定する主体がいなくなるので共有フラグは消す
   // GV_AUTOOFF は残す(再起動後も「このEAがOFFにした」ことを覚えておき、期間後にONへ戻すため)
}

void OnTimer()
{
   SyncServerTime();
   FlushPendingLines();
   ScanForEvents();
   MaybeWriteEquitySnapshot();
   if(EnableFeatureLog) CheckBarFeatureLog();
   if(EnableM1StateLog) CheckM1StateLog();
   UpdateMonthEndStop();
   UpdateDisplay();
   SendStartupNotifyOnce();
}

// EAとして動かすためにOnTick()を用意する(移行ドキュメントの教訓2)。処理はタイマー側で行う
void OnTick()
{
   SyncServerTime();
   UpdateDisplay();
}

//+------------------------------------------------------------------+
//| CSVユーティリティ                                                 |
//+------------------------------------------------------------------+
int FileFlags()
{
   int f = FILE_READ | FILE_WRITE | FILE_ANSI;
   if(UseCommonFolder) f |= FILE_COMMON;
   return f;
}

void WriteHeaderIfNeeded(string fname, string header)
{
   int h = FileOpen(fname, FileFlags());
   if(h == INVALID_HANDLE) { Print("ファイルオープン失敗(", fname, ") err=", GetLastError()); return; }
   if(FileSize(h) == 0) FileWriteString(h, header + "\r\n");
   FileClose(h);
}

// [v3] 1行追記を試みる。開けなければfalse(呼び出し側で保留キューへ回す)
bool TryAppendLine(string fname, string line)
{
   int h = FileOpen(fname, FileFlags());
   if(h == INVALID_HANDLE)
   {
      if(TimeLocal() - g_lastAppendErrPrint >= 60)
      {
         Print("追記失敗(", fname, ") err=", GetLastError(), " → 保留して次の周期に再送します");
         g_lastAppendErrPrint = TimeLocal();
      }
      return false;
   }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, line + "\r\n");
   FileClose(h);
   return true;
}

bool HasPendingFor(string fname)
{
   for(int i = 0; i < ArraySize(g_pendFile); i++)
      if(g_pendFile[i] == fname) return true;
   return false;
}

void QueuePendingLine(string fname, string line)
{
   int n = ArraySize(g_pendFile);
   if(n >= MAX_PENDING_LINES)
   {
      Print("保留行が上限(", MAX_PENDING_LINES, ")に達したため、最も古い行を破棄: ", g_pendFile[0]);
      for(int i = 1; i < n; i++) { g_pendFile[i-1] = g_pendFile[i]; g_pendLine[i-1] = g_pendLine[i]; }
      n--;
   }
   ArrayResize(g_pendFile, n + 1);
   ArrayResize(g_pendLine, n + 1);
   g_pendFile[n] = fname;
   g_pendLine[n] = line;
}

// [v3] 行を捨てずに記録する。同じファイルに保留行があれば順番を守るため後ろに並べる
void AppendLine(string fname, string line)
{
   if(HasPendingFor(fname) || !TryAppendLine(fname, line))
      QueuePendingLine(fname, line);
}

// [v3] 保留行を古い順に再送する。失敗したファイルの行は順番を保ったまま残す
void FlushPendingLines()
{
   int n = ArraySize(g_pendFile);
   if(n == 0) return;
   string keptFile[]; string keptLine[];
   string failed = ";";
   for(int i = 0; i < n; i++)
   {
      bool skip = (StringFind(failed, ";" + g_pendFile[i] + ";") >= 0);
      if(!skip && TryAppendLine(g_pendFile[i], g_pendLine[i])) continue;
      if(!skip) failed += g_pendFile[i] + ";";
      int k = ArraySize(keptFile);
      ArrayResize(keptFile, k + 1); ArrayResize(keptLine, k + 1);
      keptFile[k] = g_pendFile[i]; keptLine[k] = g_pendLine[i];
   }
   int m = ArraySize(keptFile);
   ArrayResize(g_pendFile, m); ArrayResize(g_pendLine, m);
   for(int j = 0; j < m; j++) { g_pendFile[j] = keptFile[j]; g_pendLine[j] = keptLine[j]; }
}

string IndicatorHeader()
{
   string head = "";
   for(int i = 0; i < ArraySize(g_tfNames); i++)
   {
      string t = g_tfNames[i];
      head += ";rsi_"+t+";ma20_"+t+";ma50_"+t+";maDist_"+t+";atr_"+t
           +  ";macdM_"+t+";macdS_"+t+";stoK_"+t+";cci_"+t;
   }
   return head;
}

//+------------------------------------------------------------------+
//| フィルタ関連(マジックナンバー/通貨ペアのCSVパース)                 |
//+------------------------------------------------------------------+
void ParseIntCsv(string src, int &out[])
{
   ArrayResize(out, 0);
   string parts[];
   int n = StringSplit(src, ',', parts);
   for(int i = 0; i < n; i++)
   {
      string p = TrimStr(parts[i]);
      if(p == "") continue;
      int cnt = ArraySize(out);
      ArrayResize(out, cnt + 1);
      out[cnt] = (int)StringToInteger(p);
   }
   if(ArraySize(out) == 0) { ArrayResize(out, 1); out[0] = 0; }
}

void ParseStringCsv(string src, string &out[])
{
   ArrayResize(out, 0);
   if(TrimStr(src) == "") return;
   string parts[];
   int n = StringSplit(src, ',', parts);
   for(int i = 0; i < n; i++)
   {
      string p = TrimStr(parts[i]);
      if(p == "") continue;
      int cnt = ArraySize(out);
      ArrayResize(out, cnt + 1);
      out[cnt] = p;
   }
}

string TrimStr(string s)
{
   string r = s;
   StringTrimLeft(r);
   StringTrimRight(r);
   return r;
}

bool MagicMatches(int magic)
{
   if(g_matchAllMagic) return true;
   for(int i = 0; i < ArraySize(g_targetMagics); i++)
      if(g_targetMagics[i] == magic) return true;
   return false;
}

bool SymbolMatches(string sym)
{
   if(g_matchAllSymbol) return true;
   for(int i = 0; i < ArraySize(g_targetSymbols); i++)
      if(g_targetSymbols[i] == sym) return true;
   return false;
}

//+------------------------------------------------------------------+
//| 現在の対象注文一覧(建玉+指値/逆指値)をスナップショットとして構築   |
//+------------------------------------------------------------------+
void BuildCurrentSnapshot(OrderSnap &out[])
{
   ArrayResize(out, 0);
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(!MagicMatches(OrderMagicNumber())) continue;
      if(!SymbolMatches(OrderSymbol())) continue;
      if(OrderType() > OP_SELL && !TrackPendingOrders) continue;

      int n = ArraySize(out);
      ArrayResize(out, n + 1);
      out[n].ticket    = OrderTicket();
      out[n].symbol    = OrderSymbol();
      out[n].magic     = OrderMagicNumber();
      out[n].type      = OrderType();
      out[n].lots      = OrderLots();
      out[n].openPrice = OrderOpenPrice();
      out[n].sl        = OrderStopLoss();
      out[n].tp        = OrderTakeProfit();
      out[n].openTime  = OrderOpenTime();
      out[n].comment   = OrderComment();
   }
}

int FindByTicket(OrderSnap &arr[], int ticket)
{
   for(int i = 0; i < ArraySize(arr); i++)
      if(arr[i].ticket == ticket) return i;
   return -1;
}

//+------------------------------------------------------------------+
//| 起動時: 既に建っているポジションからナンピン束を復元               |
//|         (段数/平均値幅などは起動前の履歴が無いため1段目扱いになる) |
//+------------------------------------------------------------------+
void RebuildBasketsFromSnapshot()
{
   ArrayResize(g_baskets, 0);
   for(int i = 0; i < ArraySize(g_prevOrders); i++)
   {
      if(g_prevOrders[i].type > OP_SELL) continue; // 成行のみ
      ApplyLegToBasket(g_prevOrders[i], false);     // false=ログ出力なしで束情報だけ更新
   }
}

//+------------------------------------------------------------------+
//| バスケット検索/新規作成                                           |
//+------------------------------------------------------------------+
int FindBasketIndex(string sym, int magic, int type)
{
   for(int i = 0; i < ArraySize(g_baskets); i++)
      if(g_baskets[i].symbol == sym && g_baskets[i].magic == magic && g_baskets[i].type == type)
         return i;
   return -1;
}

int GetOrCreateBasket(string sym, int magic, int type)
{
   int idx = FindBasketIndex(sym, magic, type);
   if(idx >= 0) return idx;

   int n = ArraySize(g_baskets);
   ArrayResize(g_baskets, n + 1);
   g_baskets[n].basketId      = g_nextBasketId++;
   g_baskets[n].symbol        = sym;
   g_baskets[n].magic         = magic;
   g_baskets[n].type          = type;
   g_baskets[n].legCount      = 0;
   g_baskets[n].maxLegs       = 0;
   g_baskets[n].totalLots     = 0;
   g_baskets[n].maxTotalLots  = 0;
   g_baskets[n].avgPrice      = 0;
   g_baskets[n].lastPrice     = 0;
   g_baskets[n].lastLots      = 0;
   g_baskets[n].firstOpenTime = 0;
   g_baskets[n].peakFloating  = -1e18;
   g_baskets[n].worstFloating = 1e18;
   g_baskets[n].realizedSum   = 0;
   g_baskets[n].sumLotMultiplier = 0;
   g_baskets[n].cntLotMultiplier = 0;
   g_baskets[n].sumGridStepPts   = 0;
   g_baskets[n].cntGridStepPts   = 0;
   return n;
}

//+------------------------------------------------------------------+
//| 新規建玉を束に反映し、その場で分かる指標(段数/倍率/値幅)を返す      |
//+------------------------------------------------------------------+
void ApplyLegToBasket(OrderSnap &o, bool doLogRelatedStats,
                       int &basketIdOut, int &legIndexOut, int &legsOut,
                       double &totalLotsOut, double &avgPriceOut,
                       double &lotMultOut, double &gridStepPtsOut, double &gridStepAtrOut)
{
   int bi = GetOrCreateBasket(o.symbol, o.magic, o.type);
   double point = MarketInfo(o.symbol, MODE_POINT);
   double atr   = iATR(o.symbol, PERIOD_H1, 14, 0);

   if(g_baskets[bi].legCount == 0)
   {
      g_baskets[bi].firstOpenTime = o.openTime;
      lotMultOut     = 0;
      gridStepPtsOut = 0;
      gridStepAtrOut = 0;
   }
   else
   {
      lotMultOut = (g_baskets[bi].lastLots > 0) ? (o.lots / g_baskets[bi].lastLots) : 0;
      double dist = MathAbs(o.openPrice - g_baskets[bi].lastPrice);
      gridStepPtsOut = (point > 0) ? dist / point : 0;
      gridStepAtrOut = (atr   > 0) ? dist / atr   : 0;

      g_baskets[bi].sumLotMultiplier += lotMultOut; g_baskets[bi].cntLotMultiplier++;
      g_baskets[bi].sumGridStepPts   += gridStepPtsOut; g_baskets[bi].cntGridStepPts++;
   }

   double newTotal = g_baskets[bi].totalLots + o.lots;
   g_baskets[bi].avgPrice  = (newTotal > 0)
      ? (g_baskets[bi].avgPrice * g_baskets[bi].totalLots + o.openPrice * o.lots) / newTotal
      : o.openPrice;
   g_baskets[bi].totalLots = newTotal;
   g_baskets[bi].maxTotalLots = MathMax(g_baskets[bi].maxTotalLots, newTotal);
   g_baskets[bi].lastPrice = o.openPrice;
   g_baskets[bi].lastLots  = o.lots;
   g_baskets[bi].legCount++;
   g_baskets[bi].maxLegs = MathMax(g_baskets[bi].maxLegs, g_baskets[bi].legCount);

   basketIdOut  = g_baskets[bi].basketId;
   legIndexOut  = g_baskets[bi].legCount;
   legsOut      = g_baskets[bi].legCount;
   totalLotsOut = g_baskets[bi].totalLots;
   avgPriceOut  = g_baskets[bi].avgPrice;
}

// 起動時復元用の簡易オーバーロード(戻り値不要)
void ApplyLegToBasket(OrderSnap &o, bool dummy)
{
   int a; int b; int c; double d; double e; double f; double g2; double hh;
   ApplyLegToBasket(o, dummy, a, b, c, d, e, f, g2, hh);
}

//+------------------------------------------------------------------+
//| 決済を束に反映。束が消滅(全決済)したらtrueとサマリを返す           |
//+------------------------------------------------------------------+
bool ApplyCloseToBasket(string sym, int magic, int type, double lots, double realizedPnl,
                         BasketState &closedSummary)
{
   int bi = FindBasketIndex(sym, magic, type);
   if(bi < 0) return false;

   g_baskets[bi].totalLots -= lots;
   if(g_baskets[bi].totalLots < 0) g_baskets[bi].totalLots = 0;
   g_baskets[bi].legCount--;
   g_baskets[bi].realizedSum += realizedPnl;

   if(g_baskets[bi].legCount <= 0)
   {
      closedSummary = g_baskets[bi];
      // 配列から削除
      int last = ArraySize(g_baskets) - 1;
      g_baskets[bi] = g_baskets[last];
      ArrayResize(g_baskets, last);
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| 現在保有中の各束について含み損益の最大/最小を更新                  |
//+------------------------------------------------------------------+
void UpdateFloatingExtremes()
{
   for(int i = 0; i < ArraySize(g_baskets); i++)
   {
      double floating = 0;
      int total = OrdersTotal();
      for(int j = 0; j < total; j++)
      {
         if(!OrderSelect(j, SELECT_BY_POS, MODE_TRADES)) continue;
         if(OrderType() > OP_SELL) continue;
         if(OrderSymbol() != g_baskets[i].symbol) continue;
         if(OrderMagicNumber() != g_baskets[i].magic) continue;
         if(OrderType() != g_baskets[i].type) continue;
         floating += OrderProfit() + OrderSwap() + OrderCommission();
      }
      if(floating > g_baskets[i].peakFloating)  g_baskets[i].peakFloating  = floating;
      if(floating < g_baskets[i].worstFloating) g_baskets[i].worstFloating = floating;
   }
}

//+------------------------------------------------------------------+
//| 新規建て / 決済 / 指値の発生・消滅 / SL・TP変更 を検知してログ      |
//+------------------------------------------------------------------+
void ScanForEvents()
{
   ResolveMissingOrders(); // [v3] 前回までに履歴が取れなかった注文を再確認

   OrderSnap cur[];
   BuildCurrentSnapshot(cur);

   // --- 現在存在する注文をチェック(新規 or 継続) ---
   for(int i = 0; i < ArraySize(cur); i++)
   {
      int prevIdx = FindByTicket(g_prevOrders, cur[i].ticket);

      if(prevIdx < 0)
      {
         // 前回は存在しなかった = 完全新規
         if(cur[i].type <= OP_SELL)
            LogLifecycleEvent("OPEN", cur[i], 0, 0);
         else
            LogLifecycleEvent("PENDING_NEW", cur[i], 0, 0);
      }
      else
      {
         int prevType = g_prevOrders[prevIdx].type;
         if(prevType > OP_SELL && cur[i].type <= OP_SELL)
         {
            // 指値/逆指値が約定して成行ポジションになった
            LogLifecycleEvent("FILL", cur[i], 0, 0);
         }
         else if(prevType <= OP_SELL && cur[i].type <= OP_SELL)
         {
            // 既存ポジション: SL/TP変更を検知
            if(g_prevOrders[prevIdx].sl != cur[i].sl || g_prevOrders[prevIdx].tp != cur[i].tp)
               LogLifecycleEvent("MODIFY", cur[i], 0, 0);
         }
         else if(prevType > OP_SELL && cur[i].type > OP_SELL)
         {
            // 指値/逆指値の価格・SL/TP変更(グリッドEAが指値を置き直すケース)
            if(g_prevOrders[prevIdx].openPrice != cur[i].openPrice ||
               g_prevOrders[prevIdx].sl != cur[i].sl || g_prevOrders[prevIdx].tp != cur[i].tp)
               LogLifecycleEvent("PENDING_MODIFY", cur[i], 0, 0);
         }
      }
   }

   // --- 前回は存在したが今回消えた注文 ---
   for(int j = 0; j < ArraySize(g_prevOrders); j++)
   {
      int curIdx = FindByTicket(cur, g_prevOrders[j].ticket);
      if(curIdx >= 0) continue; // 継続中

      if(!OrderSelect(g_prevOrders[j].ticket, SELECT_BY_TICKET))
      {
         AddMissingOrder(g_prevOrders[j]); // [v3] 読み飛ばさず、次の周期に再確認する
         continue;
      }

      if(g_prevOrders[j].type <= OP_SELL)
      {
         // 成行ポジションが決済された
         LogLifecycleEvent("CLOSE", g_prevOrders[j], OrderClosePrice(),
                            OrderProfit() + OrderSwap() + OrderCommission());
      }
      else
      {
         // 指値/逆指値が約定せずに消えた = キャンセル/期限切れ
         LogLifecycleEvent("PENDING_CANCEL", g_prevOrders[j], 0, 0);
      }
   }

   UpdateFloatingExtremes();

   // スナップショットを更新
   ArrayResize(g_prevOrders, ArraySize(cur));
   for(int k = 0; k < ArraySize(cur); k++) g_prevOrders[k] = cur[k];
}

//+------------------------------------------------------------------+
//| [v3] 消えたが履歴が取れなかった注文の管理                          |
//|   v2では OrderSelect に失敗するとCLOSEを記録せずに捨てていたため、 |
//|   束の段数がずれる原因になっていた。v3では毎秒再確認し、           |
//|   MissingCloseMaxTries 回取れなければ CLOSE_NOHIST として記録する   |
//+------------------------------------------------------------------+
void AddMissingOrder(OrderSnap &o)
{
   for(int i = 0; i < ArraySize(g_missing); i++)
      if(g_missing[i].ticket == o.ticket) return;
   int n = ArraySize(g_missing);
   ArrayResize(g_missing, n + 1);
   ArrayResize(g_missingTries, n + 1);
   g_missing[n] = o;
   g_missingTries[n] = 0;
}

void ResolveMissingOrders()
{
   int n = ArraySize(g_missing);
   if(n == 0) return;
   OrderSnap keep[]; int keepTries[];
   for(int i = 0; i < n; i++)
   {
      bool done = false;
      if(OrderSelect(g_missing[i].ticket, SELECT_BY_TICKET))
      {
         if(g_missing[i].type <= OP_SELL)
            LogLifecycleEvent("CLOSE", g_missing[i], OrderClosePrice(),
                              OrderProfit() + OrderSwap() + OrderCommission());
         else
            LogLifecycleEvent("PENDING_CANCEL", g_missing[i], 0, 0);
         done = true;
      }
      else if(g_missingTries[i] + 1 >= MissingCloseMaxTries)
      {
         if(g_missing[i].type <= OP_SELL)
            LogLifecycleEvent("CLOSE_NOHIST", g_missing[i], 0, 0);
         else
            LogLifecycleEvent("PENDING_CANCEL", g_missing[i], 0, 0);
         done = true;
      }
      if(done) continue;
      int k = ArraySize(keep);
      ArrayResize(keep, k + 1); ArrayResize(keepTries, k + 1);
      keep[k] = g_missing[i]; keepTries[k] = g_missingTries[i] + 1;
   }
   int m = ArraySize(keep);
   ArrayResize(g_missing, m); ArrayResize(g_missingTries, m);
   for(int j = 0; j < m; j++) { g_missing[j] = keep[j]; g_missingTries[j] = keepTries[j]; }
}

//+------------------------------------------------------------------+
//| 1イベントを1行としてCSVに追記し、必要ならバスケット処理も行う      |
//| ※ OrderSelect済み(OrderSelect(ticket)呼び出し後)であることが前提 |
//+------------------------------------------------------------------+
void LogLifecycleEvent(string event, OrderSnap &o, double closePriceOverride, double realizedPnlOverride)
{
   int    basketId = 0, legIndex = 0, legs = 0;
   double totalLots = 0, avgPrice = 0, lotMult = 0, gridStepPts = 0, gridStepAtr = 0;

   if(event == "OPEN" || event == "FILL")
   {
      ApplyLegToBasket(o, true, basketId, legIndex, legs, totalLots, avgPrice,
                        lotMult, gridStepPts, gridStepAtr);
      RecordEntryForFeatureLog(o.symbol, TimeCurrent(), legIndex);
   }
   else if(event == "CLOSE" || event == "CLOSE_NOHIST")
   {
      BasketState closedSummary;
      bool basketClosed = ApplyCloseToBasket(o.symbol, o.magic, o.type, o.lots, realizedPnlOverride, closedSummary);
      int bi = FindBasketIndex(o.symbol, o.magic, o.type);
      if(bi >= 0)
      {
         basketId  = g_baskets[bi].basketId;
         legs      = g_baskets[bi].legCount;
         totalLots = g_baskets[bi].totalLots;
         avgPrice  = g_baskets[bi].avgPrice;
      }
      else if(basketClosed)
      {
         basketId  = closedSummary.basketId;
         legs      = 0;
         totalLots = 0;
         avgPrice  = 0;
         WriteBasketSummary(closedSummary, o.symbol, TimeCurrent());
      }
   }

   double bid    = MarketInfo(o.symbol, MODE_BID);
   double ask    = MarketInfo(o.symbol, MODE_ASK);
   double point  = MarketInfo(o.symbol, MODE_POINT);
   double spread = (point > 0) ? (ask - bid) / point : 0;
   datetime t = TimeCurrent();
   int hour = TimeHour(t);

   bool   isClose = (event == "CLOSE" || event == "CLOSE_NOHIST");
   double closePr = isClose ? closePriceOverride : 0;
   double profit  = isClose ? realizedPnlOverride : 0;
   double swap    = (event == "CLOSE") ? OrderSwap()       : 0;
   double comm    = (event == "CLOSE") ? OrderCommission() : 0;

   string row = TimeToString(t, TIME_DATE|TIME_SECONDS) + ";"
              + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + ";"
              + event + ";"
              + IntegerToString(o.ticket) + ";"
              + IntegerToString(o.magic) + ";"
              + o.symbol + ";"
              + OrderTypeStr(o.type) + ";"
              + DoubleToString(o.lots, 2) + ";"
              + DoubleToString(o.openPrice, 5) + ";"
              + DoubleToString(o.sl, 5) + ";"
              + DoubleToString(o.tp, 5) + ";"
              + DoubleToString(closePr, 5) + ";"
              + DoubleToString(profit, 2) + ";"
              + DoubleToString(swap, 2) + ";"
              + DoubleToString(comm, 2) + ";"
              + o.comment + ";"
              + DoubleToString(bid, 5) + ";"
              + DoubleToString(ask, 5) + ";"
              + DoubleToString(spread, 1) + ";"
              + IntegerToString(hour) + ";"
              + IntegerToString(TimeDayOfWeek(t)) + ";"
              + SessionLabel(hour) + ";"
              + IntegerToString(basketId) + ";"
              + IntegerToString(legIndex) + ";"
              + IntegerToString(legs) + ";"
              + DoubleToString(totalLots, 2) + ";"
              + DoubleToString(avgPrice, 5) + ";"
              + DoubleToString(lotMult, 3) + ";"
              + DoubleToString(gridStepPts, 1) + ";"
              + DoubleToString(gridStepAtr, 3)
              + IndicatorFields(o.symbol);

   AppendLine(LogFileName, row);
   Print("記録: ", event, " ", o.symbol, " #", o.ticket, " basket=", basketId, " leg=", legIndex);

   NotifyTelegramForEvent(event, o, closePr, profit, basketId, legIndex, legs, totalLots, avgPrice);
}

//+------------------------------------------------------------------+
//| イベント種別ごとにTelegram通知の要否を判定してメッセージを送る      |
//+------------------------------------------------------------------+
void NotifyTelegramForEvent(string event, OrderSnap &o, double closePr, double profit,
                             int basketId, int legIndex, int legs, double totalLots, double avgPrice)
{
   if(!EnableTelegram) return;

   string msg = "";

   if(event == "OPEN" || event == "FILL")
   {
      if(!TelegramNotifyOpen) return;
      string legLabel = (legIndex <= 1) ? "新規エントリー" : "ナンピン追加(" + IntegerToString(legIndex) + "段目)";
      msg = "[EA_Monitor] " + legLabel + "\n"
          + o.symbol + " " + OrderTypeStr(o.type) + " " + DoubleToString(o.lots, 2) + "lot @ " + DoubleToString(o.openPrice, 5) + "\n"
          + "basket#" + IntegerToString(basketId) + " " + IntegerToString(legIndex) + "/" + IntegerToString(legs) + "段"
          + " 合計" + DoubleToString(totalLots, 2) + "lot 平均" + DoubleToString(avgPrice, 5) + "\n"
          + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   }
   else if(event == "CLOSE" || event == "CLOSE_NOHIST")
   {
      if(!TelegramNotifyClose) return;
      msg = "[EA_Monitor] " + (event == "CLOSE" ? "決済" : "決済(履歴が取れず損益不明)") + "\n"
          + o.symbol + " " + OrderTypeStr(o.type) + " " + DoubleToString(o.lots, 2) + "lot @ " + DoubleToString(closePr, 5) + "\n"
          + "損益: " + DoubleToString(profit, 2) + "  (basket#" + IntegerToString(basketId) + " 残り" + IntegerToString(legs) + "段)\n"
          + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   }
   else if(event == "PENDING_NEW" || event == "PENDING_CANCEL" || event == "PENDING_MODIFY")
   {
      if(!TelegramNotifyPending) return;
      msg = "[EA_Monitor] " + event + "\n" + o.symbol + " " + OrderTypeStr(o.type)
          + " " + DoubleToString(o.lots, 2) + "lot @ " + DoubleToString(o.openPrice, 5);
   }
   else if(event == "MODIFY")
   {
      if(!TelegramNotifyModify) return;
      msg = "[EA_Monitor] SL/TP変更\n" + o.symbol + " #" + IntegerToString(o.ticket)
          + " SL=" + DoubleToString(o.sl, 5) + " TP=" + DoubleToString(o.tp, 5);
   }
   else return;

   SendTelegramMessage(msg);
}

//+------------------------------------------------------------------+
//| バスケット(ナンピン束)が全決済された際のサマリ行を出力             |
//+------------------------------------------------------------------+
void WriteBasketSummary(BasketState &b, string sym, datetime closeTime)
{
   double avgLotMult   = (b.cntLotMultiplier > 0) ? b.sumLotMultiplier / b.cntLotMultiplier : 0;
   double avgGridStep  = (b.cntGridStepPts   > 0) ? b.sumGridStepPts   / b.cntGridStepPts   : 0;
   double durationMin  = (b.firstOpenTime > 0) ? (double)(closeTime - b.firstOpenTime) / 60.0 : 0;

   string row = IntegerToString(b.basketId) + ";"
              + b.symbol + ";"
              + IntegerToString(b.magic) + ";"
              + OrderTypeStr(b.type) + ";"
              + TimeToString(b.firstOpenTime, TIME_DATE|TIME_SECONDS) + ";"
              + TimeToString(closeTime, TIME_DATE|TIME_SECONDS) + ";"
              + DoubleToString(durationMin, 1) + ";"
              + IntegerToString(b.maxLegs) + ";"
              + DoubleToString(b.maxTotalLots, 2) + ";"
              + DoubleToString(b.realizedSum, 2) + ";"
              + DoubleToString(avgLotMult, 3) + ";"
              + DoubleToString(avgGridStep, 1) + ";"
              + DoubleToString(b.peakFloating, 2) + ";"
              + DoubleToString(b.worstFloating, 2);

   AppendLine(BasketFileName, row);
   Print("ナンピン束クローズ: basket=", b.basketId, " ", b.symbol,
         " 最大段数=", b.maxLegs, " 実現損益=", DoubleToString(b.realizedSum, 2));

   if(EnableTelegram && TelegramNotifyBasketClose)
   {
      string msg = "[EA_Monitor] ナンピン束 完結\n"
                 + b.symbol + " " + OrderTypeStr(b.type) + "  最大" + IntegerToString(b.maxLegs) + "段\n"
                 + "実現損益: " + DoubleToString(b.realizedSum, 2) + "\n"
                 + "保有時間: " + DoubleToString(durationMin, 1) + "分  最大含み損: " + DoubleToString(b.worstFloating, 2);
      SendTelegramMessage(msg);
   }
}

//+------------------------------------------------------------------+
//| 入金/出金/クレジット増減(履歴上のOP_BALANCE・OP_CREDIT)を検出し、  |
//| その累計をg_cashFlowAdjustmentに積み上げる                        |
//| (これらは口座残高を動かすが「トレードの損益」ではないため、        |
//|  そのままドローダウン計算に使うと出金しただけで悪化して見えてしまう)|
//+------------------------------------------------------------------+
void UpdateCashFlowAdjustment()
{
   int total = OrdersHistoryTotal();
   for(int i = g_historyScanPos; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      int t = OrderType();
      if(t == OP_BALANCE || t == OP_CREDIT)
         g_cashFlowAdjustment += OrderProfit();
   }
   g_historyScanPos = total;
}

//+------------------------------------------------------------------+
//| 口座状態の定期スナップショット(イベントが無くても一定間隔で記録)    |
//+------------------------------------------------------------------+
void MaybeWriteEquitySnapshot()
{
   datetime now = TimeCurrent();
   if(g_lastEquitySnap != 0 && (now - g_lastEquitySnap) < EquitySnapshotSeconds) return;
   g_lastEquitySnap = now;

   UpdateCashFlowAdjustment();

   double balance = AccountBalance();
   double equity  = AccountEquity();
   double margin  = AccountMargin();
   double freeMargin = AccountFreeMargin();
   double marginLevel = (margin > 0) ? (equity / margin * 100.0) : 0;
   double floatingAll = equity - balance;

   // 入出金/クレジット増減の影響を除いた実質エクイティでドローダウンを計算する
   double adjustedEquity = equity - g_cashFlowAdjustment;
   if(adjustedEquity > g_equityPeak) g_equityPeak = adjustedEquity;
   double ddPct = (g_equityPeak > 0) ? (g_equityPeak - adjustedEquity) / g_equityPeak * 100.0 : 0;

   int openPositions = 0;
   double openLots = 0;
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() > OP_SELL) continue;
      if(!MagicMatches(OrderMagicNumber())) continue;
      if(!SymbolMatches(OrderSymbol())) continue;
      openPositions++;
      openLots += OrderLots();
   }

   string row = TimeToString(now, TIME_DATE|TIME_SECONDS) + ";"
              + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + ";"
              + DoubleToString(balance, 2) + ";"
              + DoubleToString(equity, 2) + ";"
              + DoubleToString(margin, 2) + ";"
              + DoubleToString(freeMargin, 2) + ";"
              + DoubleToString(marginLevel, 1) + ";"
              + IntegerToString(openPositions) + ";"
              + DoubleToString(openLots, 2) + ";"
              + DoubleToString(floatingAll, 2) + ";"
              + DoubleToString(ddPct, 2) + ";"
              + IntegerToString(ArraySize(g_baskets)) + ";"
              + DoubleToString(g_cashFlowAdjustment, 2);

   AppendLine(EquityFileName, row);

   if(EnableTelegram && TelegramNotifyMarginAlert && margin > 0 && marginLevel < TelegramMarginAlertPct)
   {
      if(g_lastMarginAlert == 0 || (now - g_lastMarginAlert) >= TelegramMarginAlertCooldownMin * 60)
      {
         g_lastMarginAlert = now;
         string msg = "[EA_Monitor] 証拠金維持率 警告\n"
                    + "維持率: " + DoubleToString(marginLevel, 1) + "% (しきい値" + DoubleToString(TelegramMarginAlertPct, 0) + "%)\n"
                    + "残高: " + DoubleToString(balance, 2) + "  有効証拠金: " + DoubleToString(equity, 2) + "\n"
                    + "含み損益: " + DoubleToString(floatingAll, 2) + "  保有束数: " + IntegerToString(ArraySize(g_baskets));
         SendTelegramMessage(msg);
      }
   }
   else if(marginLevel >= TelegramMarginAlertPct)
   {
      g_lastMarginAlert = 0; // しきい値を上回ったら警告状態を解除(再度下回った時にまた通知される)
   }
}

//+------------------------------------------------------------------+
//| 簡易セッション判定(サーバー時間の時刻から大まかに判定する目安値)   |
//| ※ ブローカーのGMTオフセットにより実際のセッションとはズレるため   |
//|   ServerGmtOffsetHours を実際のブローカー設定に合わせて調整すること |
//+------------------------------------------------------------------+
string SessionLabel(int serverHour)
{
   int gmtHour = (serverHour - ServerGmtOffsetHours + 24) % 24;
   if(gmtHour >= 0 && gmtHour < 7)   return "Tokyo";
   if(gmtHour >= 7 && gmtHour < 12)  return "London_pre";
   if(gmtHour >= 12 && gmtHour < 16) return "London_NY_overlap";
   if(gmtHour >= 16 && gmtHour < 21) return "NewYork";
   return "Offhours";
}

//+------------------------------------------------------------------+
//| 各時間足のインジケーター値を ";" 区切りで返す                      |
//+------------------------------------------------------------------+
string IndicatorFields(string sym)
{
   string s = "";
   double bid = MarketInfo(sym, MODE_BID);
   double pt  = MarketInfo(sym, MODE_POINT);

   for(int i = 0; i < ArraySize(g_tfPeriods); i++)
   {
      int tf = g_tfPeriods[i];
      double rsi   = iRSI(sym, tf, 14, PRICE_CLOSE, 0);
      double ma20  = iMA(sym, tf, 20, 0, MODE_SMA, PRICE_CLOSE, 0);
      double ma50  = iMA(sym, tf, 50, 0, MODE_SMA, PRICE_CLOSE, 0);
      double atr   = iATR(sym, tf, 14, 0);
      double macdM = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 0);
      double macdS = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
      double stoK  = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_MAIN, 0);
      double cci   = iCCI(sym, tf, 14, PRICE_TYPICAL, 0);
      double maDist = (pt > 0) ? (bid - ma20) / pt : 0;

      s += ";" + DoubleToString(rsi, 2)
         + ";" + DoubleToString(ma20, 5)
         + ";" + DoubleToString(ma50, 5)
         + ";" + DoubleToString(maDist, 1)
         + ";" + DoubleToString(atr, 5)
         + ";" + DoubleToString(macdM, 6)
         + ";" + DoubleToString(macdS, 6)
         + ";" + DoubleToString(stoK, 2)
         + ";" + DoubleToString(cci, 2);
   }
   return s;
}

//+------------------------------------------------------------------+
//| エントリーロジック解析: バー確定ごとの特徴量+ラベル付けログ          |
//+------------------------------------------------------------------+
int TFStringToConst(string tf)
{
   string u = tf; StringToUpper(u);
   if(u == "M1")  return PERIOD_M1;
   if(u == "M5")  return PERIOD_M5;
   if(u == "M15") return PERIOD_M15;
   if(u == "M30") return PERIOD_M30;
   if(u == "H1")  return PERIOD_H1;
   if(u == "H4")  return PERIOD_H4;
   if(u == "D1")  return PERIOD_D1;
   if(u == "W1")  return PERIOD_W1;
   if(u == "MN1") return PERIOD_MN1;
   return PERIOD_M5;
}

// OPEN/FILL(=新規もしくはナンピン追加の建玉発生)を、特徴量ログのラベル付け用に記録
void RecordEntryForFeatureLog(string sym, datetime t, int legIndex)
{
   int n = ArraySize(g_entryLog);
   ArrayResize(g_entryLog, n + 1);
   g_entryLog[n].symbol   = sym;
   g_entryLog[n].time     = t;
   g_entryLog[n].legIndex = legIndex;
}

// 古くなったエントリー履歴を間引く(直近数本のバー分だけ残せば十分)
void PruneEntryLog(datetime cutoff)
{
   EntryLogItem kept[];
   for(int i = 0; i < ArraySize(g_entryLog); i++)
      if(g_entryLog[i].time >= cutoff)
      {
         int n = ArraySize(kept);
         ArrayResize(kept, n + 1);
         kept[n] = g_entryLog[i];
      }
   ArrayResize(g_entryLog, ArraySize(kept));
   for(int j = 0; j < ArraySize(kept); j++) g_entryLog[j] = kept[j];
}

// 各対象通貨ペアで新しいバーが確定したかを確認し、確定していれば特徴量行を出力する
void CheckBarFeatureLog()
{
   for(int i = 0; i < ArraySize(g_featureSymbols); i++)
   {
      string sym = g_featureSymbols[i];
      datetime curBar = iTime(sym, g_featureTf, 0);
      if(curBar == 0 || curBar == g_lastFeatureBar[i]) continue;

      datetime closedBarTime = iTime(sym, g_featureTf, 1); // 直近に確定したバーの開始時刻
      if(g_lastFeatureBar[i] != 0 && closedBarTime > 0)
         WriteFeatureRow(sym, closedBarTime, g_lastFeatureBar[i], curBar);

      g_lastFeatureBar[i] = curBar;
   }

   // バー足の5本分より古いエントリー履歴は不要なので間引く
   int periodSec = PeriodSeconds(g_featureTf);
   PruneEntryLog(TimeCurrent() - periodSec * 5);
}

int PeriodSeconds(int tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return 60;
      case PERIOD_M5:  return 300;
      case PERIOD_M15: return 900;
      case PERIOD_M30: return 1800;
      case PERIOD_H1:  return 3600;
      case PERIOD_H4:  return 14400;
      case PERIOD_D1:  return 86400;
      case PERIOD_W1:  return 604800;
      case PERIOD_MN1: return 2678400;
   }
   return 300;
}

// 直近に確定したバー[prevBarTime, curBarTime)の間にエントリーが起きたか数える
void CountEntriesInRange(string sym, datetime fromTime, datetime toTime,
                          int &leg1Count, int &anyCount)
{
   leg1Count = 0; anyCount = 0;
   for(int i = 0; i < ArraySize(g_entryLog); i++)
   {
      if(g_entryLog[i].symbol != sym) continue;
      if(g_entryLog[i].time < fromTime || g_entryLog[i].time >= toTime) continue;
      anyCount++;
      if(g_entryLog[i].legIndex == 1) leg1Count++;
   }
}

// 確定したバー1本分の特徴量+エントリー有無ラベルをCSVに出力
void WriteFeatureRow(string sym, datetime closedBarTime, datetime prevBarTime, datetime curBarTime)
{
   int tf = g_featureTf;
   double point = MarketInfo(sym, MODE_POINT);
   if(point <= 0) return;

   // 確定した足(shift=1)のローソク足情報
   double o  = iOpen(sym, tf, 1);
   double h  = iHigh(sym, tf, 1);
   double l  = iLow(sym, tf, 1);
   double c  = iClose(sym, tf, 1);
   double body  = MathAbs(c - o) / point;
   double upW   = (h - MathMax(o, c)) / point;
   double lowW  = (MathMin(o, c) - l) / point;
   bool   bull  = (c > o);

   // 直近の連続陽線/陰線本数(最大10本まで)
   int streak = 0;
   for(int s = 1; s <= 10; s++)
   {
      bool b = (iClose(sym, tf, s) > iOpen(sym, tf, s));
      if(s == 1) { streak = 1; continue; }
      bool prevB = (iClose(sym, tf, s-1) > iOpen(sym, tf, s-1));
      if(b == prevB) streak++; else break;
   }
   if(!bull) streak = -streak; // 陰線側はマイナスで表現

   double rsi   = iRSI(sym, tf, 14, PRICE_CLOSE, 1);
   double ma20  = iMA(sym, tf, 20, 0, MODE_SMA, PRICE_CLOSE, 1);
   double ma50  = iMA(sym, tf, 50, 0, MODE_SMA, PRICE_CLOSE, 1);
   double atr   = iATR(sym, tf, 14, 1);
   double macdM = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 1);
   double macdS = iMACD(sym, tf, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
   double stoK  = iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_MAIN, 1);
   double cci   = iCCI(sym, tf, 14, PRICE_TYPICAL, 1);
   double maDist = (c - ma20) / point;

   double bbUpper = iBands(sym, tf, 20, 2, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double bbLower = iBands(sym, tf, 20, 2, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bbWidth = (bbUpper - bbLower) / point;
   double priceVsBb = (bbUpper > bbLower) ? (c - bbLower) / (bbUpper - bbLower) : 0.5;

   double donHigh = iHigh(sym, tf, iHighest(sym, tf, MODE_HIGH, 20, 2));
   double donLow  = iLow(sym, tf, iLowest(sym, tf, MODE_LOW, 20, 2));
   bool breakUp   = (h >= donHigh);
   bool breakDown = (l <= donLow);

   double h1Ma50 = iMA(sym, PERIOD_H1, 50, 0, MODE_SMA, PRICE_CLOSE, 0);
   double h1Dist = (point > 0) ? (c - h1Ma50) / point : 0;

   double bid    = MarketInfo(sym, MODE_BID);
   double ask    = MarketInfo(sym, MODE_ASK);
   double spread = (ask - bid) / point;
   int hour = TimeHour(closedBarTime);

   int leg1Count = 0, anyCount = 0;
   CountEntriesInRange(sym, prevBarTime, curBarTime, leg1Count, anyCount);

   string row = TimeToString(closedBarTime, TIME_DATE|TIME_SECONDS) + ";"
              + sym + ";"
              + FeatureBaseTF + ";"
              + DoubleToString(o, 5) + ";"
              + DoubleToString(h, 5) + ";"
              + DoubleToString(l, 5) + ";"
              + DoubleToString(c, 5) + ";"
              + DoubleToString(body, 1) + ";"
              + DoubleToString(upW, 1) + ";"
              + DoubleToString(lowW, 1) + ";"
              + (bull ? "1" : "0") + ";"
              + IntegerToString(streak) + ";"
              + DoubleToString(rsi, 2) + ";"
              + DoubleToString(ma20, 5) + ";"
              + DoubleToString(ma50, 5) + ";"
              + DoubleToString(maDist, 1) + ";"
              + DoubleToString(atr, 5) + ";"
              + DoubleToString(macdM, 6) + ";"
              + DoubleToString(macdS, 6) + ";"
              + DoubleToString(stoK, 2) + ";"
              + DoubleToString(cci, 2) + ";"
              + DoubleToString(bbUpper, 5) + ";"
              + DoubleToString(bbLower, 5) + ";"
              + DoubleToString(bbWidth, 1) + ";"
              + DoubleToString(priceVsBb, 3) + ";"
              + DoubleToString(donHigh, 5) + ";"
              + DoubleToString(donLow, 5) + ";"
              + (breakUp ? "1" : "0") + ";"
              + (breakDown ? "1" : "0") + ";"
              + DoubleToString(h1Ma50, 5) + ";"
              + DoubleToString(h1Dist, 1) + ";"
              + DoubleToString(spread, 1) + ";"
              + IntegerToString(hour) + ";"
              + IntegerToString(TimeDayOfWeek(closedBarTime)) + ";"
              + SessionLabel(hour) + ";"
              + (leg1Count > 0 ? "1" : "0") + ";"
              + IntegerToString(leg1Count) + ";"
              + (anyCount  > 0 ? "1" : "0") + ";"
              + IntegerToString(anyCount);

   AppendLine(FeatureFileName, row);
}

//+------------------------------------------------------------------+
//| Telegram通知                                                      |
//+------------------------------------------------------------------+
string UrlEncode(string src)
{
   uchar bytes[];
   int n = StringToCharArray(src, bytes, 0, WHOLE_ARRAY, CP_UTF8);
   string out = "";
   for(int i = 0; i < n; i++)
   {
      uchar b = bytes[i];
      if(b == 0) break; // NUL終端をスキップ
      if((b >= 'A' && b <= 'Z') || (b >= 'a' && b <= 'z') || (b >= '0' && b <= '9')
         || b == '-' || b == '_' || b == '.' || b == '~')
         out += CharToString(b);
      else
         out += StringFormat("%%%02X", b);
   }
   return out;
}

void SendTelegramMessage(string text)
{
   if(!EnableTelegram) return;
   if(TelegramBotToken == "" || TelegramChatId == "")
   {
      Print("Telegram通知: BotTokenまたはChatIdが未設定です");
      return;
   }

   string url = "https://api.telegram.org/bot" + TelegramBotToken + "/sendMessage";
   string postFields = "chat_id=" + TelegramChatId + "&text=" + UrlEncode(text);

   uchar data[];
   int dn = StringToCharArray(postFields, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, MathMax(dn - 1, 0)); // 末尾のNUL終端を除去

   uchar result[];
   string resultHeaders;
   ResetLastError();
   int res = WebRequest("POST", url, "Content-Type: application/x-www-form-urlencoded\r\n",
                         5000, data, result, resultHeaders);

   if(res == -1)
   {
      int err = GetLastError();
      if(err == 4060)
         Print("Telegram送信失敗: WebRequestが許可されていません。"
               "ツール>オプション>EA で https://api.telegram.org を許可URLに追加してください。");
      else
         Print("Telegram送信失敗 err=", err);
   }
   else if(res != 200)
   {
      // [v3] トークン・chat_idの間違い(401/404/400)などを見逃さないようにする
      Print("Telegram送信失敗: HTTP ", res, " (トークンまたはchat_idが正しいか確認してください) ",
            CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8));
   }
}

//+------------------------------------------------------------------+
//| ヘルパー                                                          |
//+------------------------------------------------------------------+
string OrderTypeStr(int t)
{
   switch(t)
   {
      case OP_BUY:       return "buy";
      case OP_SELL:      return "sell";
      case OP_BUYLIMIT:  return "buylimit";
      case OP_SELLLIMIT: return "selllimit";
      case OP_BUYSTOP:   return "buystop";
      case OP_SELLSTOP:  return "sellstop";
   }
   return "unknown";
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| [v3] 時刻                                                         |
//|   TimeCurrent() はティックが来た時しか進まないため、               |
//|   「サーバー時間 − PC時間」を覚えておき、PC時計で毎秒進める         |
//+------------------------------------------------------------------+
void SyncServerTime()
{
   datetime tc = TimeCurrent();
   if(tc != g_lastTickServer)
   {
      g_lastTickServer   = tc;
      g_serverMinusLocal = (int)(tc - TimeLocal());
   }
}

datetime ServerNow()
{
   datetime est = TimeLocal() + g_serverMinusLocal;
   datetime tc  = TimeCurrent();
   return (est < tc) ? tc : est;
}

datetime JstNow()
{
   return TimeGMT() + 9 * 3600; // PCの時計とタイムゾーン設定から計算した日本時間
}

//+------------------------------------------------------------------+
//| [v3] ラグナロク(a〜e × 買い/売り)の1分ごとの状態記録                |
//|   1分足が切り替わるたびに1行。エントリーが無い足も記録するので、   |
//|   「条件を満たしたのに入らなかった足」を後から取り出せる           |
//+------------------------------------------------------------------+
string M1StateHeader()
{
   string h = "bar_time;symbol;bid;ask;spread_pts;close1;diff3;diff11;diff20";
   string tfs[2] = {"m1", "m5"};
   for(int t = 0; t < 2; t++)
      h += ";" + tfs[t] + "_stoK9;" + tfs[t] + "_stoD9;" + tfs[t] + "_stoK5;" + tfs[t] + "_stoD5;"
         + tfs[t] + "_ma5;" + tfs[t] + "_ma10;" + tfs[t] + "_ma20;" + tfs[t] + "_rsi14;" + tfs[t] + "_atr14";
   h += ";equity;margin_level_pct;autotrading;stop_state";
   string dirs[2] = {"buy", "sell"};
   for(int g = 0; g < ArraySize(g_gridLetters); g++)
      for(int d = 0; d < 2; d++)
      {
         string k = g_gridLetters[g] + "_" + dirs[d];
         h += ";" + k + "_legs;" + k + "_lots;" + k + "_avg;" + k + "_last_price;"
            + k + "_sec_since_last;" + k + "_adverse_pts;" + k + "_floating";
      }
   return h;
}

void CheckM1StateLog()
{
   datetime cur = iTime(Symbol(), PERIOD_M1, 0);
   if(cur == 0 || cur == g_lastM1StateBar) return;
   if(g_lastM1StateBar != 0) WriteM1StateRow(Symbol(), cur);
   g_lastM1StateBar = cur;
}

string TfIndicatorBlock(string sym, int tf)
{
   return ";" + DoubleToString(iStochastic(sym, tf, 9, 3, 3, MODE_SMA, 0, MODE_MAIN,   1), 2)
        + ";" + DoubleToString(iStochastic(sym, tf, 9, 3, 3, MODE_SMA, 0, MODE_SIGNAL, 1), 2)
        + ";" + DoubleToString(iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_MAIN,   1), 2)
        + ";" + DoubleToString(iStochastic(sym, tf, 5, 3, 3, MODE_SMA, 0, MODE_SIGNAL, 1), 2)
        + ";" + DoubleToString(iMA(sym, tf, 5,  0, MODE_SMA, PRICE_CLOSE, 1), 5)
        + ";" + DoubleToString(iMA(sym, tf, 10, 0, MODE_SMA, PRICE_CLOSE, 1), 5)
        + ";" + DoubleToString(iMA(sym, tf, 20, 0, MODE_SMA, PRICE_CLOSE, 1), 5)
        + ";" + DoubleToString(iRSI(sym, tf, 14, PRICE_CLOSE, 1), 2)
        + ";" + DoubleToString(iATR(sym, tf, 14, 1), 5);
}

int GridIndexFromComment(string comment)
{
   int us = StringFind(comment, "_");
   if(us <= 0) return -1;
   string head = StringSubstr(comment, 0, us);
   for(int g = 0; g < ArraySize(g_gridLetters); g++)
      if(g_gridLetters[g] == head) return g;
   return -1;
}

void WriteM1StateRow(string sym, datetime barTime)
{
   double bid = MarketInfo(sym, MODE_BID);
   double ask = MarketInfo(sym, MODE_ASK);
   double pt  = MarketInfo(sym, MODE_POINT);
   if(pt <= 0) return;

   // --- a〜e × 買い/売りの束を、ラグナロクの建玉から直接集計する ---
   int nSlot = ArraySize(g_gridLetters) * 2;
   int      legs[];  double lots[];  double sumPx[];  datetime lastT[];  double lastPx[];  double flt[];
   ArrayResize(legs, nSlot); ArrayResize(lots, nSlot); ArrayResize(sumPx, nSlot);
   ArrayResize(lastT, nSlot); ArrayResize(lastPx, nSlot); ArrayResize(flt, nSlot);
   for(int z = 0; z < nSlot; z++) { legs[z] = 0; lots[z] = 0; sumPx[z] = 0; lastT[z] = 0; lastPx[z] = 0; flt[z] = 0; }

   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != sym || OrderType() > OP_SELL) continue;
      if(OrderMagicNumber() != RagnarokMagicBuy && OrderMagicNumber() != RagnarokMagicSell) continue;
      int g = GridIndexFromComment(OrderComment());
      if(g < 0) continue;
      int s = g * 2 + (OrderType() == OP_BUY ? 0 : 1);
      legs[s]++;
      lots[s]  += OrderLots();
      sumPx[s] += OrderLots() * OrderOpenPrice();
      flt[s]   += OrderProfit() + OrderSwap() + OrderCommission();
      if(OrderOpenTime() >= lastT[s]) { lastT[s] = OrderOpenTime(); lastPx[s] = OrderOpenPrice(); }
   }

   double equity = AccountEquity();
   double margin = AccountMargin();
   string row = TimeToString(barTime, TIME_DATE|TIME_SECONDS) + ";" + sym
              + ";" + DoubleToString(bid, 5) + ";" + DoubleToString(ask, 5)
              + ";" + DoubleToString((ask - bid) / pt, 1)
              + ";" + DoubleToString(iClose(sym, PERIOD_M1, 1), 5)
              + ";" + DoubleToString(bid - iClose(sym, PERIOD_M1, 3), 5)   // b: 3本前の足の終値との差
              + ";" + DoubleToString(bid - iClose(sym, PERIOD_M1, 11), 5)  // c: 11分前
              + ";" + DoubleToString(bid - iClose(sym, PERIOD_M1, 20), 5)  // a: 20分前
              + TfIndicatorBlock(sym, PERIOD_M1)
              + TfIndicatorBlock(sym, PERIOD_M5)
              + ";" + DoubleToString(equity, 2)
              + ";" + DoubleToString(margin > 0 ? equity / margin * 100.0 : 0, 1)
              + ";" + (AutoTradingIsOn() ? "1" : "0")
              + ";" + IntegerToString(g_stopState);

   datetime now = ServerNow();
   for(int s2 = 0; s2 < nSlot; s2++)
   {
      bool isBuy = (s2 % 2 == 0);
      double avg = (lots[s2] > 0) ? sumPx[s2] / lots[s2] : 0;
      double adv = 0; int since = 0;
      if(legs[s2] > 0)
      {
         adv   = isBuy ? (lastPx[s2] - bid) / pt : (bid - lastPx[s2]) / pt; // プラス=直前レグから不利方向
         since = (int)(now - lastT[s2]);
      }
      row += ";" + IntegerToString(legs[s2])
           + ";" + DoubleToString(lots[s2], 2)
           + ";" + DoubleToString(avg, 5)
           + ";" + DoubleToString(lastPx[s2], 5)
           + ";" + IntegerToString(since)
           + ";" + DoubleToString(adv, 1)
           + ";" + DoubleToString(flt[s2], 2);
   }
   AppendLine(M1StateFileName, row);
}

//+------------------------------------------------------------------+
//| [v3] 月末月初の停止期間の判定(日本時間・営業日=月〜金)             |
//|   「取引日」= 日本時間から StopBoundaryHourJST 時間引いた日付。     |
//|   例: 7時区切りなら 9/30 7:00〜10/1 6:59 が「9/30の取引日」。       |
//|   停止する取引日 = 月末の最終営業日から遡ってN日 〜 翌月の第1営業日  |
//|   からM日。祝日(クリスマス・元日など)は考慮しない。                 |
//|   ※既存のMonthEndStartStopperは当月分しか見ていないため月初の日が   |
//|     判定されなかった。v3は前月末の期間も確認して月初を正しく判定する |
//+------------------------------------------------------------------+
bool IsBizDay(datetime d)
{
   int w = TimeDayOfWeek(d);
   return (w != 0 && w != 6);
}

datetime DateOnly(datetime t) { return t - (t % 86400); }

datetime AddBizDays(datetime d, int step)
{
   int dir = (step >= 0) ? 1 : -1;
   int remaining = MathAbs(step);
   datetime cur = d;
   while(remaining > 0)
   {
      cur += dir * 86400;
      if(IsBizDay(cur)) remaining--;
   }
   return cur;
}

datetime FirstOfMonth(datetime d)
{
   return StringToTime(StringFormat("%04d.%02d.01 00:00", TimeYear(d), TimeMonth(d)));
}

datetime MonthEndDate(datetime d)
{
   int y = TimeYear(d), m = TimeMonth(d) + 1;
   if(m > 12) { m = 1; y++; }
   return StringToTime(StringFormat("%04d.%02d.01 00:00", y, m)) - 86400;
}

// dの月の月末と、その翌月の月初にまたがる停止期間(取引日ベース)を返す。期間が無ければfalse
bool StopWindowForMonth(datetime d, datetime &ws, datetime &we)
{
   if(StopBusinessDaysBeforeMonthEnd < 1 && StopBusinessDaysAfterMonthStart < 1) return false;
   datetime monthEnd = MonthEndDate(d);
   datetime lastBiz  = IsBizDay(monthEnd) ? monthEnd : AddBizDays(monthEnd, -1);
   datetime firstNxt = monthEnd + 86400;
   datetime firstBiz = IsBizDay(firstNxt) ? firstNxt : AddBizDays(firstNxt, 1);
   ws = (StopBusinessDaysBeforeMonthEnd  >= 1) ? AddBizDays(lastBiz, -(StopBusinessDaysBeforeMonthEnd - 1)) : firstBiz;
   we = (StopBusinessDaysAfterMonthStart >= 1) ? AddBizDays(firstBiz, StopBusinessDaysAfterMonthStart - 1) : lastBiz;
   return true;
}

datetime TradingDayJst()
{
   return DateOnly(JstNow() - StopBoundaryHourJST * 3600);
}

// 今が停止期間かどうか。keyOut=期間の開始日(期間ごとの識別に使う)
bool InStopPeriod(datetime &keyOut)
{
   keyOut = 0;
   if(TestForceStopPeriod) { keyOut = 1; return true; }
   datetime td = TradingDayJst();
   datetime ws = 0, we = 0;
   if(StopWindowForMonth(td, ws, we) && td >= ws && td <= we) { keyOut = ws; return true; }
   datetime prevMonthDay = FirstOfMonth(td) - 86400;
   if(StopWindowForMonth(prevMonthDay, ws, we) && td >= ws && td <= we) { keyOut = ws; return true; }
   return false;
}

string JstText(datetime tradingDay)
{
   string wd[7] = {"日","月","火","水","木","金","土"};
   return StringFormat("%d/%d(%s) %d:00", TimeMonth(tradingDay), TimeDay(tradingDay),
                       wd[TimeDayOfWeek(tradingDay)], StopBoundaryHourJST);
}

// 次(または現在)の停止期間を「9/30(水) 7:00 〜 10/2(金) 7:00(日本時間)」の形で返す
string NextStopWindowText()
{
   if(!EnableMonthEndStop) return "月末月初の停止: 無効";
   datetime td = TradingDayJst();
   datetime ws = 0, we = 0;
   datetime prevMonthDay = FirstOfMonth(td) - 86400;
   if(!(StopWindowForMonth(prevMonthDay, ws, we) && td <= we))
   {
      if(!StopWindowForMonth(td, ws, we)) return "月末月初の停止: 期間なし(日数が0)";
   }
   // 再開は停止最終日の翌営業日ではなく、翌日の区切り時刻
   return "月末月初の停止期間: " + JstText(ws) + " 〜 " + JstText(we + 86400) + " (日本時間)";
}

//+------------------------------------------------------------------+
//| [v3] 自動売買ボタンの状態確認と操作                                |
//+------------------------------------------------------------------+
bool AutoTradingIsOn()
{
   return (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) != 0);
}

bool PressAutoTradingButton()
{
   if(!IsDllsAllowed()) return false; // DLL未許可でDLL関数を呼ぶとEAが止まるため必ず確認する
   int hwnd = (int)ChartGetInteger(0, CHART_WINDOW_HANDLE);
   int root = GetAncestor(hwnd, GA_ROOT);
   if(root == 0) return false;
   PostMessageW(root, WM_COMMAND, MT4_CMD_TOGGLE_AUTOTRADE, 0);
   return true;
}

int CountStopTargetPositions()
{
   bool all = (ArraySize(g_stopMagics) == 1 && g_stopMagics[0] == 0);
   int n = 0;
   int total = OrdersTotal();
   for(int i = 0; i < total; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderType() > OP_SELL) continue;
      bool hit = all;
      for(int k = 0; k < ArraySize(g_stopMagics) && !hit; k++)
         if(OrderMagicNumber() == g_stopMagics[k]) hit = true;
      if(hit) n++;
   }
   return n;
}

void NotifyStop(string text)
{
   Print("[月末月初] ", text);
   if(EnableTelegram && TelegramNotifyMonthEndStop)
      SendTelegramMessage("[EA_Monitor] 月末月初\n" + text + "\n" + TimeToString(JstNow(), TIME_DATE|TIME_MINUTES) + " (日本時間)");
}

bool OurAutoOffFlag()
{
   return (GlobalVariableCheck(GV_AUTOOFF) && GlobalVariableGet(GV_AUTOOFF) > 0);
}

// ボタンを押して結果待ちにする(want: 0=OFFにしたい, 1=ONにしたい)
void RequestAutoTrading(int want)
{
   if(!IsDllsAllowed())
   {
      if(!g_dllWarned)
      {
         NotifyStop("自動売買ボタンを操作できません: DLLの使用が許可されていません。"
                    "EAの設定「全般」タブで「DLLの使用を許可する」にチェックしてください。");
         g_dllWarned = true;
      }
      return;
   }
   if(PressAutoTradingButton())
   {
      g_toggleWant   = want;
      g_toggleSentAt = TimeLocal();
      g_toggleTries  = 1;
   }
}

//+------------------------------------------------------------------+
//| [v3] 月末月初の停止: 毎秒呼ばれる状態管理                           |
//|   期間中: (建玉が0になったら) 自動売買OFF → 他EAも含め発注が止まる |
//|   期間後: このEAがOFFにした場合だけONに戻す(手動OFFは触らない)      |
//|   期間中に手動でONに戻されたら、その期間はもう自動でOFFにしない     |
//+------------------------------------------------------------------+
void UpdateMonthEndStop()
{
   if(!EnableMonthEndStop)
   {
      g_stopState = 4;
      GlobalVariableSet(StopFlagGlobalVariableName, 0.0);
      return;
   }

   datetime key = 0;
   bool inP = InStopPeriod(key);
   GlobalVariableSet(StopFlagGlobalVariableName, inP ? 1.0 : 0.0); // 既存MonthEndStartStopperと同じ共有フラグ
   bool on   = AutoTradingIsOn();
   bool ours = OurAutoOffFlag();

   // --- 期間の出入りの通知 ---
   if(g_firstStopEval || inP != g_prevInPeriod)
   {
      if(inP)
         NotifyStop("停止期間に入りました。\n" + NextStopWindowText());
      else if(!g_firstStopEval)
         NotifyStop("停止期間が終わりました。");
      g_prevInPeriod  = inP;
      g_firstStopEval = false;
   }

   // --- ボタン操作の結果待ち(2秒ごとに確認、最大3回押す) ---
   if(g_toggleWant >= 0)
   {
      if((on ? 1 : 0) == g_toggleWant)
      {
         if(g_toggleWant == 0)
         {
            GlobalVariableSet(GV_AUTOOFF, 1.0);
            NotifyStop("自動売買をOFFにしました(全EAの発注が止まります)。\n" + NextStopWindowText());
         }
         else
         {
            GlobalVariableDel(GV_AUTOOFF);
            NotifyStop("自動売買をONに戻しました(稼働再開)。");
         }
         g_toggleWant = -1;
      }
      else if(TimeLocal() - g_toggleSentAt >= 2)
      {
         if(g_toggleTries < 3)
         {
            PressAutoTradingButton();
            g_toggleSentAt = TimeLocal();
            g_toggleTries++;
         }
         else
         {
            NotifyStop(g_toggleWant == 0 ? "自動売買をOFFにできませんでした(3回失敗)。手動でOFFにしてください。10分後に再試行します。"
                                         : "自動売買をONに戻せませんでした(3回失敗)。手動でONにしてください。10分後に再試行します。");
            g_toggleWant = -1;
            g_toggleRetryAfter = TimeLocal() + 600;
         }
      }
      return;
   }

   if(inP)
   {
      // 期間中に誰かがONに戻した = 手動の判断を優先し、この期間はもう自動でOFFにしない
      if(ours && on)
      {
         GlobalVariableDel(GV_AUTOOFF);
         GlobalVariableSet(GV_OVERRIDE, (double)key);
         NotifyStop("停止期間中に自動売買が手動でONにされました。この期間は自動でOFFにしません。");
         ours = false;
      }
      bool overridden = (GlobalVariableCheck(GV_OVERRIDE) && GlobalVariableGet(GV_OVERRIDE) == (double)key);

      if(!on)                    { g_stopState = ours ? 2 : 3; return; }
      if(!AutoTradingOffOnStop)  { g_stopState = 7; return; }
      if(overridden)             { g_stopState = 6; return; }
      if(!IsDllsAllowed())       { g_stopState = 5; RequestAutoTrading(0); return; }

      int n = CountStopTargetPositions();
      if(WaitFlatBeforeOff && n > 0)
      {
         bool firstWait = (g_stopState != 1);
         g_stopState = 1;
         g_waitCount = n;
         if(firstWait || TimeLocal() - g_lastWaitNotify >= WaitNotifyIntervalMin * 60)
         {
            NotifyStop("停止待ち: 建玉が " + IntegerToString(n) + " 本残っています。0本になったら自動売買をOFFにします。");
            g_lastWaitNotify = TimeLocal();
         }
         return;
      }
      if(TimeLocal() < g_toggleRetryAfter) return;
      RequestAutoTrading(0);
      return;
   }

   // --- 期間外 ---
   g_stopState = 0;
   if(ours)
   {
      if(on)
         GlobalVariableDel(GV_AUTOOFF); // 既にON(手動で戻された等)なら記憶だけ消す
      else if(TimeLocal() >= g_toggleRetryAfter)
         RequestAutoTrading(1);
   }
}

string StopStateText(color &clr)
{
   switch(g_stopState)
   {
      case 1: clr = clrOrange;    return "月末月初:停止待ち(建玉" + IntegerToString(g_waitCount) + "本)";
      case 2: clr = clrRed;       return "月末月初:停止中";
      case 3: clr = clrRed;       return "月末月初:停止中(手動OFF)";
      case 4: clr = clrGray;      return "月末月初:無効";
      case 5: clr = clrMagenta;   return "月末月初:停止できません(DLL未許可)";
      case 6: clr = clrOrange;    return "月末月初:停止期間(手動でON)";
      case 7: clr = clrRed;       return "月末月初:停止期間(表示のみ)";
   }
   if(!AutoTradingIsOn()) { clr = clrGray; return "月末月初:稼働中(自動売買OFF)"; }
   clr = clrLimeGreen;
   return "月末月初:稼働中";
}

//+------------------------------------------------------------------+
//| [v3] 画面表示: [足替わりタイマー] [月末月初の稼働状態] を同じ行に    |
//+------------------------------------------------------------------+
int TextWidthPx(string text, int size)
{
   uint w = 0, h = 0;
   TextSetFont(DisplayFont, -size * 10);
   TextGetSize(text, w, h);
   return (int)w;
}

void PlaceLabel(string name, string text, int size, color clr, int x)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
   }
   int anchor = ANCHOR_LEFT_UPPER;
   if(DisplayCorner == DISP_RIGHT_UPPER) anchor = ANCHOR_RIGHT_UPPER;
   if(DisplayCorner == DISP_LEFT_LOWER)  anchor = ANCHOR_LEFT_LOWER;
   if(DisplayCorner == DISP_RIGHT_LOWER) anchor = ANCHOR_RIGHT_LOWER;
   ObjectSetInteger(0, name, OBJPROP_CORNER, (int)DisplayCorner);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, DisplayY);
   ObjectSetText(name, text, size, DisplayFont, clr);
}

void UpdateDisplay()
{
   if(!ShowDisplay)
   {
      ObjectDelete(OBJ_TIMER_NAME);
      ObjectDelete(OBJ_STATUS_NAME);
      return;
   }

   // --- 足替わりタイマー(このチャートの時間足) ---
   int periodSec = PeriodSeconds(Period());
   int remain = (int)(iTime(Symbol(), Period(), 0) + periodSec - ServerNow());
   if(remain < 0) remain = 0;
   string timerText = (periodSec >= 3600)
      ? StringFormat("%d:%02d:%02d", remain / 3600, (remain % 3600) / 60, remain % 60)
      : StringFormat("%02d:%02d", remain / 60, remain % 60);
   color timerClr = (remain <= TimerWarnSeconds) ? TimerColorWarn : TimerColorNormal;

   // --- 稼働状態 ---
   color stClr = clrLimeGreen;
   string stText = StopStateText(stClr);

   // タイマーは幅が秒ごとに揺れないよう「00:00」の幅で配置する
   int timerW  = TextWidthPx(periodSec >= 3600 ? "00:00:00" : "00:00", TimerFontSize);
   int statusW = TextWidthPx(stText, StatusFontSize);
   bool rightSide = (DisplayCorner == DISP_RIGHT_UPPER || DisplayCorner == DISP_RIGHT_LOWER);

   if(!rightSide)
   {
      PlaceLabel(OBJ_TIMER_NAME,  timerText, TimerFontSize,  timerClr, DisplayX);
      PlaceLabel(OBJ_STATUS_NAME, stText,    StatusFontSize, stClr,    DisplayX + timerW + DisplayGapPx);
   }
   else
   {
      // 右寄せ: 稼働表示を角側に置き、その左にタイマーを置く
      PlaceLabel(OBJ_STATUS_NAME, stText,    StatusFontSize, stClr,    DisplayX);
      PlaceLabel(OBJ_TIMER_NAME,  timerText, TimerFontSize,  timerClr, DisplayX + statusW + DisplayGapPx);
   }
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| [v3] 起動通知(最初のタイマーで1回だけ。Telegram設定の確認を兼ねる)  |
//+------------------------------------------------------------------+
void SendStartupNotifyOnce()
{
   if(g_startupNotified) return;
   g_startupNotified = true;
   string msg = "[EA_Monitor v3.0] 起動しました\n"
              + "口座: " + IntegerToString(AccountNumber()) + "  " + Symbol() + "\n"
              + "自動売買: " + (AutoTradingIsOn() ? "ON" : "OFF")
              + "  DLL許可: " + (IsDllsAllowed() ? "あり" : "なし") + "\n"
              + NextStopWindowText();
   Print(msg);
   if(EnableTelegram && TelegramNotifyStartup) SendTelegramMessage(msg);
}
