//+------------------------------------------------------------------+
//|                                              M1HistoryLogger.mq4 |
//|   M1(1分足)のヒストリーデータをCSVログとして専用フォルダへ書き出す |
//+------------------------------------------------------------------+
//| 動作概要                                                          |
//|  1. 起動時に出力先フォルダを自動作成(存在しなければ)               |
//|  2. 取得可能なM1確定足の全履歴を一括で書き出し                     |
//|  3. 以降、M1の新しい足が確定するたびに1行ずつ追記                  |
//|  4. 最終書き出し時刻を状態ファイルに保存し、再起動しても重複なし   |
//+------------------------------------------------------------------+
#property copyright "esa"
#property version   "1.00"
#property description "M1ヒストリーデータを専用フォルダへCSVログとして書き出します。"
#property description "任意のドライブ/フォルダへ出力する場合は「DLLの使用を許可する」にチェックしてください。"
#property strict
#property indicator_chart_window

//--- Windows API (任意のドライブ・フォルダへ書き込むために使用)
#import "kernel32.dll"
int  CreateFileW(string lpFileName,uint dwDesiredAccess,uint dwShareMode,int lpSecurityAttributes,
                 uint dwCreationDisposition,uint dwFlagsAndAttributes,int hTemplateFile);
int  WriteFile(int hFile,uchar &lpBuffer[],uint nNumberOfBytesToWrite,uint &lpNumberOfBytesWritten,int lpOverlapped);
int  ReadFile(int hFile,uchar &lpBuffer[],uint nNumberOfBytesToRead,uint &lpNumberOfBytesRead,int lpOverlapped);
uint SetFilePointer(int hFile,int lDistanceToMove,int lpDistanceToMoveHigh,uint dwMoveMethod);
uint GetFileSize(int hFile,int lpFileSizeHigh);
int  CloseHandle(int hObject);
int  CreateDirectoryW(string lpPathName,int lpSecurityAttributes);
uint GetFileAttributesW(string lpFileName);
#import

#define W_GENERIC_READ          ((uint)0x80000000)
#define W_GENERIC_WRITE         ((uint)0x40000000)
#define W_FILE_SHARE_READ_WRITE 0x00000003
#define W_CREATE_ALWAYS         2
#define W_OPEN_EXISTING         3
#define W_OPEN_ALWAYS           4
#define W_FILE_ATTR_NORMAL      0x00000080
#define W_FILE_ATTR_DIRECTORY   0x00000010
#define W_INVALID_ATTRIBUTES    0xFFFFFFFF
#define W_FILE_END              2
#define W_INVALID_HANDLE        -1

#define FLUSH_LINES             2000   // この行数ごとにディスクへ書き込む

//--- ファイル分割単位
enum ENUM_SPLIT_MODE
  {
   SPLIT_DAY   = 0, // 日別ファイル
   SPLIT_MONTH = 1, // 月別ファイル
   SPLIT_NONE  = 2  // 1ファイルに全て
  };

//--- 入力パラメータ
input string          InpSymbol       = "";                   // 対象通貨ペア(空欄=チャートの通貨ペア)
input bool            InpUseDLL       = true;                 // 任意フォルダへ出力(DLL使用)
input string          InpOutputDir    = "C:\\MT4_M1_History"; // 出力先フォルダ(DLL使用時・ドライブ名から指定)
input string          InpSandboxDir   = "MT4_M1_History";     // 出力先フォルダ(DLL不使用時・MQL4\Files配下)
input bool            InpSymbolSubDir = true;                 // 通貨ペアごとにサブフォルダを作成
input ENUM_SPLIT_MODE InpSplit        = SPLIT_DAY;            // ファイル分割単位
input int             InpMaxBars      = 0;                    // 初回に書き出す最大本数(0=取得可能な全履歴)
input string          InpSeparator    = ",";                  // 区切り文字
input bool            InpShowComment  = true;                 // チャート左上に状況を表示

//--- 内部状態
string   g_sym         = "";
string   g_safeSym     = "";
int      g_digits      = 5;
bool     g_dll         = false;
string   g_baseDir     = "";   // 実際の出力フォルダ
string   g_displayDir  = "";   // 表示用のフルパス
string   g_statePath   = "";
datetime g_lastWritten = 0;    // 書き出し済みの最終M1足の時刻
datetime g_lastBarTime = 0;    // 最後に処理したM1足(形成中)の時刻
long     g_totalLines  = 0;
string   g_lastError   = "";

//--- 書き込みバッファ
string   g_bufPath     = "";
string   g_buf         = "";
int      g_bufLines    = 0;
datetime g_bufLastTime = 0;

//+------------------------------------------------------------------+
//| 初期化                                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_sym = (InpSymbol == "") ? Symbol() : InpSymbol;
   if(!SymbolSelect(g_sym,true))
     {
      Alert("M1HistoryLogger: 通貨ペアが見つかりません: ",g_sym);
      return(INIT_PARAMETERS_INCORRECT);
     }
   g_safeSym = SafeFileName(g_sym);
   g_digits  = (int)MarketInfo(g_sym,MODE_DIGITS);

   if(StringLen(InpSeparator) == 0)
     {
      Alert("M1HistoryLogger: 区切り文字が空です。");
      return(INIT_PARAMETERS_INCORRECT);
     }

//--- 出力モードの決定
   g_dll = InpUseDLL;
   if(g_dll && !MQLInfoInteger(MQL_DLLS_ALLOWED))
     {
      Alert("M1HistoryLogger: DLLの使用が許可されていないため、MQL4\\Files\\",InpSandboxDir,
            " へ出力します。任意フォルダへ出力するには「DLLの使用を許可する」にチェックしてください。");
      g_dll = false;
     }

//--- 出力フォルダの組み立て
   string root;
   if(g_dll)
     {
      root = NormalizeDir(InpOutputDir);
      if(StringLen(root) < 3 || StringSubstr(root,1,2) != ":\\")
        {
         Alert("M1HistoryLogger: 出力先フォルダはドライブ名から指定してください(例: C:\\MT4_M1_History)。現在値: ",InpOutputDir);
         return(INIT_PARAMETERS_INCORRECT);
        }
     }
   else
     {
      root = NormalizeDir(InpSandboxDir);
      if(root == "")
         root = "MT4_M1_History";
     }
   g_baseDir = InpSymbolSubDir ? root + "\\" + g_safeSym : root;

   if(!EnsureDir(g_baseDir))
     {
      Alert("M1HistoryLogger: 出力フォルダを作成できません: ",g_baseDir);
      return(INIT_FAILED);
     }
   g_displayDir = g_dll ? g_baseDir
                        : TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL4\\Files\\" + g_baseDir;

//--- 前回の書き出し位置を読み込み(重複書き出し防止)
   g_statePath   = g_baseDir + "\\_state_" + g_safeSym + "_M1.txt";
   g_lastWritten = LoadState();

   Print("M1HistoryLogger: 出力先 = ",g_displayDir,
         " / 前回書き出し済み = ",(g_lastWritten > 0 ? TimeToString(g_lastWritten,TIME_DATE|TIME_MINUTES) : "なし(全履歴を書き出します)"));

   EventSetTimer(1);   // ティックが来ない時間帯(週末など)でも初回書き出しを実行
   UpdateComment();
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| 終了処理                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(Flush())
      SaveState();
   Comment("");
  }

//+------------------------------------------------------------------+
//| ティック毎                                                        |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   Process();
   return(rates_total);
  }

//+------------------------------------------------------------------+
//| タイマー(1秒毎)                                                   |
//+------------------------------------------------------------------+
void OnTimer()
  {
   Process();
  }

//+------------------------------------------------------------------+
//| M1の新しい足が出たら確定足を書き出す                              |
//+------------------------------------------------------------------+
void Process()
  {
   datetime cur = iTime(g_sym,PERIOD_M1,0);
   if(cur == 0 || cur == g_lastBarTime)
      return;

   int written = ExportClosedBars();
   if(written >= 0)
      g_lastBarTime = cur;   // 成功時のみ更新(失敗時は次回リトライ)
   UpdateComment();
  }

//+------------------------------------------------------------------+
//| 未書き出しの確定足(shift>=1)を古い順に書き出す                   |
//| 戻り値: 書き出し本数 / -1=履歴未準備 / -2=書き込みエラー          |
//+------------------------------------------------------------------+
int ExportClosedBars()
  {
   ResetLastError();
   int bars = iBars(g_sym,PERIOD_M1);
   if(bars < 2 || GetLastError() == ERR_HISTORY_WILL_UPDATED)
     {
      g_lastError = "M1履歴の読み込み待ち";
      return(-1);
     }

   int start = bars - 1;
   if(g_lastWritten == 0 && InpMaxBars > 0 && start > InpMaxBars)
      start = InpMaxBars;
   if(g_lastWritten > 0)
     {
      int s = iBarShift(g_sym,PERIOD_M1,g_lastWritten,false);
      if(s >= 0 && s < start)
         start = s;
     }

   int count = 0;
   for(int i = start; i >= 1; i--)
     {
      datetime t = iTime(g_sym,PERIOD_M1,i);
      if(t <= g_lastWritten || t <= g_bufLastTime)
         continue;
      if(!QueueLine(FilePathFor(t),BarLine(i,t),t))
         return(-2);
      count++;
     }
   if(!Flush())
      return(-2);

   if(count > 0)
     {
      SaveState();
      g_lastError = "";
     }
   return(count);
  }

//+------------------------------------------------------------------+
//| 1本分のCSV行                                                      |
//+------------------------------------------------------------------+
string BarLine(const int shift,const datetime t)
  {
   return(TimeToString(t,TIME_DATE) + InpSeparator +
          TimeToString(t,TIME_MINUTES) + InpSeparator +
          DoubleToString(iOpen(g_sym,PERIOD_M1,shift),g_digits) + InpSeparator +
          DoubleToString(iHigh(g_sym,PERIOD_M1,shift),g_digits) + InpSeparator +
          DoubleToString(iLow(g_sym,PERIOD_M1,shift),g_digits) + InpSeparator +
          DoubleToString(iClose(g_sym,PERIOD_M1,shift),g_digits) + InpSeparator +
          IntegerToString(iVolume(g_sym,PERIOD_M1,shift)) + "\r\n");
  }

//+------------------------------------------------------------------+
//| CSVヘッダー(新規ファイル作成時のみ書き込み)                       |
//+------------------------------------------------------------------+
string Header()
  {
   return("Date" + InpSeparator + "Time" + InpSeparator + "Open" + InpSeparator + "High" + InpSeparator +
          "Low" + InpSeparator + "Close" + InpSeparator + "Volume" + "\r\n");
  }

//+------------------------------------------------------------------+
//| 足の時刻に対応する出力ファイルパス                                |
//+------------------------------------------------------------------+
string FilePathFor(const datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t,d);
   string name;
   switch(InpSplit)
     {
      case SPLIT_DAY:
         name = StringFormat("%s_M1_%04d%02d%02d.csv",g_safeSym,d.year,d.mon,d.day);
         break;
      case SPLIT_MONTH:
         name = StringFormat("%s_M1_%04d%02d.csv",g_safeSym,d.year,d.mon);
         break;
      default:
         name = g_safeSym + "_M1.csv";
         break;
     }
   return(g_baseDir + "\\" + name);
  }

//+------------------------------------------------------------------+
//| バッファへ1行追加(ファイルが変わる/一定行数でディスクへ書き込み) |
//+------------------------------------------------------------------+
bool QueueLine(const string path,const string line,const datetime t)
  {
   if(path != g_bufPath)
     {
      if(!Flush())
         return(false);
      g_bufPath = path;
     }
   g_buf        += line;
   g_bufLines++;
   g_bufLastTime = t;
   if(g_bufLines >= FLUSH_LINES)
      return(Flush());
   return(true);
  }

//+------------------------------------------------------------------+
//| バッファをファイルへ追記                                          |
//+------------------------------------------------------------------+
bool Flush()
  {
   if(g_bufLines == 0)
      return(true);

   bool ok = g_dll ? AppendDll(g_bufPath,g_buf) : AppendSandbox(g_bufPath,g_buf);
   if(!ok)
     {
      g_lastError = "書き込み失敗: " + g_bufPath;
      Print("M1HistoryLogger: ",g_lastError," (ファイルを他のアプリで開いている場合は閉じてください)");
      // 失敗分は破棄し、次回 g_lastWritten 以降を再書き出しする
      g_buf         = "";
      g_bufLines    = 0;
      g_bufPath     = "";
      g_bufLastTime = g_lastWritten;
      return(false);
     }

   g_totalLines += g_bufLines;
   g_lastWritten = g_bufLastTime;
   g_buf         = "";
   g_bufLines    = 0;
   return(true);
  }

//+------------------------------------------------------------------+
//| 追記(DLL: 任意のドライブ・フォルダ)                               |
//+------------------------------------------------------------------+
bool AppendDll(const string path,const string text)
  {
   int h = CreateFileW(path,W_GENERIC_WRITE,W_FILE_SHARE_READ_WRITE,0,W_OPEN_ALWAYS,W_FILE_ATTR_NORMAL,0);
   if(h == W_INVALID_HANDLE)
      return(false);

   bool isNew = (GetFileSize(h,0) == 0);
   SetFilePointer(h,0,0,W_FILE_END);

   bool ok = WriteBytes(h,isNew ? Header() + text : text);
   CloseHandle(h);
   return(ok);
  }

bool WriteBytes(const int h,const string s)
  {
   uchar buf[];
   int len = StringToCharArray(s,buf,0,WHOLE_ARRAY,CP_UTF8) - 1;   // 終端NULを除く
   if(len <= 0)
      return(true);
   uint written = 0;
   return(WriteFile(h,buf,(uint)len,written,0) != 0 && written == (uint)len);
  }

//+------------------------------------------------------------------+
//| 追記(DLL不使用: MQL4\Files配下)                                  |
//+------------------------------------------------------------------+
bool AppendSandbox(const string path,const string text)
  {
   int h = FileOpen(path,FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
      return(false);

   bool isNew = (FileSize(h) == 0);
   FileSeek(h,0,SEEK_END);
   if(isNew)
      FileWriteString(h,Header());
   uint n = FileWriteString(h,text);
   FileClose(h);
   return(n > 0 || StringLen(text) == 0);
  }

//+------------------------------------------------------------------+
//| 状態ファイル(最終書き出し時刻)の読み込み                         |
//+------------------------------------------------------------------+
datetime LoadState()
  {
   string s = "";
   if(g_dll)
     {
      int h = CreateFileW(g_statePath,W_GENERIC_READ,W_FILE_SHARE_READ_WRITE,0,W_OPEN_EXISTING,W_FILE_ATTR_NORMAL,0);
      if(h == W_INVALID_HANDLE)
         return(0);
      uchar buf[];
      ArrayResize(buf,256);
      uint rd = 0;
      ReadFile(h,buf,255,rd,0);
      CloseHandle(h);
      if(rd > 0)
         s = CharArrayToString(buf,0,(int)rd,CP_UTF8);
     }
   else
     {
      if(!FileIsExist(g_statePath))
         return(0);
      int h = FileOpen(g_statePath,FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
      if(h == INVALID_HANDLE)
         return(0);
      s = FileReadString(h);
      FileClose(h);
     }

   string parts[];
   if(StringSplit(s,'|',parts) < 1)
      return(0);
   return((datetime)StringToInteger(parts[0]));
  }

//+------------------------------------------------------------------+
//| 状態ファイルの保存 (形式: UNIX時刻|人が読める時刻)                |
//+------------------------------------------------------------------+
void SaveState()
  {
   if(g_lastWritten == 0)
      return;
   string s = IntegerToString((long)g_lastWritten) + "|" + TimeToString(g_lastWritten,TIME_DATE|TIME_MINUTES) + "\r\n";
   if(g_dll)
     {
      int h = CreateFileW(g_statePath,W_GENERIC_WRITE,W_FILE_SHARE_READ_WRITE,0,W_CREATE_ALWAYS,W_FILE_ATTR_NORMAL,0);
      if(h == W_INVALID_HANDLE)
         return;
      WriteBytes(h,s);
      CloseHandle(h);
     }
   else
     {
      int h = FileOpen(g_statePath,FILE_WRITE|FILE_TXT|FILE_ANSI);
      if(h == INVALID_HANDLE)
         return;
      FileWriteString(h,s);
      FileClose(h);
     }
  }

//+------------------------------------------------------------------+
//| フォルダ作成(階層ごとに作成)                                     |
//+------------------------------------------------------------------+
bool EnsureDir(const string path)
  {
   if(!g_dll)
     {
      FolderCreate(path);
      // 作成確認のため状態ファイル用のパスへ書き込めるかは初回書き出し時に判定
      return(true);
     }

   string parts[];
   int n = StringSplit(path,'\\',parts);
   string cur = "";
   for(int i = 0; i < n; i++)
     {
      if(parts[i] == "")
         continue;
      cur = (cur == "") ? parts[i] : cur + "\\" + parts[i];
      if(i == 0)
         continue;   // ドライブ名 (C:)
      if(!DirExistsDll(cur))
         CreateDirectoryW(cur,0);
     }
   return(DirExistsDll(path));
  }

bool DirExistsDll(const string path)
  {
   uint a = GetFileAttributesW(path);
   return(a != W_INVALID_ATTRIBUTES && (a & W_FILE_ATTR_DIRECTORY) != 0);
  }

//+------------------------------------------------------------------+
//| パス整形: / → \ 、末尾の \ を除去                                 |
//+------------------------------------------------------------------+
string NormalizeDir(string path)
  {
   path = StringTrimRight(StringTrimLeft(path));   // MQL4版は戻り値で返す
   StringReplace(path,"/","\\");
   while(StringLen(path) > 0 && StringSubstr(path,StringLen(path) - 1) == "\\")
      path = StringSubstr(path,0,StringLen(path) - 1);
   return(path);
  }

//+------------------------------------------------------------------+
//| ファイル名に使えない文字を _ に置換                               |
//+------------------------------------------------------------------+
string SafeFileName(string s)
  {
   string ng[] = {"\\","/",":","*","?","\"","<",">","|"};
   for(int i = 0; i < ArraySize(ng); i++)
      StringReplace(s,ng[i],"_");
   return(s);
  }

//+------------------------------------------------------------------+
//| チャート左上の状況表示                                            |
//+------------------------------------------------------------------+
void UpdateComment()
  {
   if(!InpShowComment)
      return;
   Comment("M1HistoryLogger [",g_sym,"]\n",
           "出力先: ",g_displayDir,"\n",
           "最終書き出し足: ",(g_lastWritten > 0 ? TimeToString(g_lastWritten,TIME_DATE|TIME_MINUTES) : "-"),"\n",
           "今回起動後の書き出し行数: ",g_totalLines,
           (g_lastError != "" ? "\n状態: " + g_lastError : ""));
  }
//+------------------------------------------------------------------+
