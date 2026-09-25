//+------------------------------------------------------------------+
//|                                                    EA_Monitor.mq4 |
//|   対象EAの「振る舞い」を外から記録するブラックボックス監視EA        |
//|   v2: ナンピン/グリッド系EAの解析に特化した拡張版                   |
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
//|   （UseCommonFolder=true で Common/Files 配下）                    |
//+------------------------------------------------------------------+
#property strict

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
extern string FeatureBaseTF         = "M5";                // 特徴量をサンプリングする基準時間足
extern string FeatureFileName       = "ea_monitor_features.csv";

//--- Telegram通知 ----------------------------------------------------
//  事前準備: 1) BotFatherでBotを作成しTelegramBotTokenを取得
//            2) Botとのチャットを開始し、TelegramChatId(自分のchat_id)を取得
//            3) MT4「ツール>オプション>EA」の"WebRequestを許可するURL"に
//               https://api.telegram.org を追加しておくこと(必須)
extern bool   EnableTelegram             = false;   // Telegram通知を有効化するか
extern string TelegramBotToken           = "";      // BotFatherから取得したトークン
extern string TelegramChatId             = "";      // 通知先のchat_id
extern bool   TelegramNotifyOpen         = true;    // 新規建て/ナンピン追加弾/指値約定
extern bool   TelegramNotifyClose        = true;    // 決済
extern bool   TelegramNotifyBasketClose  = true;    // ナンピン束が全決済で完結した時のサマリ
extern bool   TelegramNotifyPending      = false;   // 指値の新規設置/キャンセル(頻度が多いので既定オフ)
extern bool   TelegramNotifyModify       = false;   // SL/TP変更(頻度が多いので既定オフ)
extern bool   TelegramNotifyMarginAlert  = true;    // 証拠金維持率が閾値を下回った時の警告
extern double TelegramMarginAlertPct     = 300.0;   // 警告を出す証拠金維持率(%)のしきい値
extern int    TelegramMarginAlertCooldownMin = 30;  // 警告の再送間隔(分, 維持率が低いままの間)

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

//+------------------------------------------------------------------+
int OnInit()
{
   ParseIntCsv(TargetMagics, g_targetMagics);
   g_matchAllMagic = (ArraySize(g_targetMagics) == 1 && g_targetMagics[0] == 0);

   ParseStringCsv(TargetSymbols, g_targetSymbols);
   g_matchAllSymbol = (ArraySize(g_targetSymbols) == 0);

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

   Print("EA_Monitor v2 起動: 監視間隔=", PollSeconds, "秒, TargetMagics=", TargetMagics,
         ", TargetSymbols=", (TargetSymbols=="" ? "(全通貨)" : TargetSymbols),
         ", 指値監視=", TrackPendingOrders, ", 特徴量ログ=", EnableFeatureLog, "(", FeatureBaseTF, ")");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
{
   ScanForEvents();
   MaybeWriteEquitySnapshot();
   if(EnableFeatureLog) CheckBarFeatureLog();
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

void AppendLine(string fname, string line)
{
   int h = FileOpen(fname, FileFlags());
   if(h == INVALID_HANDLE) { Print("追記失敗(", fname, ") err=", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, line + "\r\n");
   FileClose(h);
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

      if(!OrderSelect(g_prevOrders[j].ticket, SELECT_BY_TICKET)) continue;

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
   else if(event == "CLOSE")
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

   double closePr = (event == "CLOSE") ? closePriceOverride : 0;
   double profit  = (event == "CLOSE") ? realizedPnlOverride : 0;
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
   else if(event == "CLOSE")
   {
      if(!TelegramNotifyClose) return;
      msg = "[EA_Monitor] 決済\n"
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
