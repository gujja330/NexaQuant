//+------------------------------------------------------------------+
//|                                              NexaQuant_EA.mq5     |
//|   Core NexaQuant engine as a native MT5 Expert Advisor.          |
//|   No Python, no Wine — drag onto a chart and it trades.          |
//|                                                                  |
//|   Faithful port of the VALIDATED core:                          |
//|     * regime gate (ADX) + EMA20/50 trend continuation (long+short)|
//|     * Donchian breakout edge (optional)                          |
//|     * hard ATR stop (2xATR)                                      |
//|     * momentum-ride exit (close vs EMA20) + scale-out at +1.5R    |
//|       then stop->breakeven                                       |
//|     * CONFIDENCE-scaled dynamic lot (ADX strength), risk %/trade  |
//|                                                                  |
//|   NOT included (Python-side): macro/fundamental gate, multi-      |
//|   lookback TSM gold filter, AI meta-label, weekly self-learning.  |
//|                                                                  |
//|   USAGE: compile in MetaEditor (F7) -> ALWAYS run Strategy Tester |
//|   first -> then drag onto a BTCUSDc H4 (and XAUUSDc H4) chart.    |
//|   Enable: Tools>Options>Expert Advisors>Allow algorithmic trading.|
//+------------------------------------------------------------------+
#property copyright "NexaQuant"
#property version   "1.00"
#include <Trade/Trade.mqh>

//--- inputs (match the validated config; tune in Strategy Tester) ---
input double InpRiskPct      = 0.5;    // risk % of balance per trade (base)
input double InpMaxRiskPct   = 2.0;    // cap after confidence scaling
input int    InpEMAfast      = 20;
input int    InpEMAslow      = 50;
input int    InpADXperiod    = 14;
input double InpADXtrend     = 25.0;   // ADX >= this => TREND regime
input int    InpATRperiod    = 14;
input double InpStopMult     = 2.0;    // stop = entry -/+ StopMult*ATR
input double InpPartialAtR    = 1.5;   // scale-out trigger (R multiple)
input double InpPartialFrac   = 0.40;  // fraction to bank at the scale-out
input bool   InpUseTrend     = true;   // trade the regime-trend edge
input bool   InpUseBreakout  = true;   // trade the Donchian breakout edge
input int    InpDonchian     = 20;     // breakout channel length (bars)
input double InpConfCap      = 3.0;    // max confidence size multiplier
input long   InpMagic        = 990001; // EA id (use a different one per chart if you like)

CTrade        trade;
int           hEMAfast, hEMAslow, hADX, hATR;
datetime      lastBarTime = 0;
bool          scaled = false;          // has this position been scaled out yet?
double        entryRisk = 0.0;         // price stop distance at entry (for R math)

//+------------------------------------------------------------------+
int OnInit()
{
   hEMAfast = iMA(_Symbol, _Period, InpEMAfast, 0, MODE_EMA, PRICE_CLOSE);
   hEMAslow = iMA(_Symbol, _Period, InpEMAslow, 0, MODE_EMA, PRICE_CLOSE);
   hADX     = iADX(_Symbol, _Period, InpADXperiod);
   hATR     = iATR(_Symbol, _Period, InpATRperiod);
   if(hEMAfast==INVALID_HANDLE || hEMAslow==INVALID_HANDLE || hADX==INVALID_HANDLE || hATR==INVALID_HANDLE)
      return(INIT_FAILED);
   trade.SetExpertMagicNumber(InpMagic);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason)
{
   IndicatorRelease(hEMAfast); IndicatorRelease(hEMAslow);
   IndicatorRelease(hADX);     IndicatorRelease(hATR);
}

//--- helper: copy one indicator value at shift -------------------------------
double Val(int handle, int shift)
{
   double b[]; if(CopyBuffer(handle, 0, shift, 1, b) < 1) return(0.0); return(b[0]);
}
//--- confidence multiplier from ADX (mirrors playbook.confidence_size) -------
double Confidence(double adx)
{
   double c = 1.0 + MathMax(0.0, MathMin(InpConfCap-1.0, (adx-25.0)/15.0));
   return(c);
}
//--- dynamic lot from risk (mirrors live_trader._calc_lots) ------------------
double LotsForRisk(double stopDistPrice, double conf)
{
   double riskPct = MathMin(InpRiskPct*conf, InpMaxRiskPct) / 100.0;
   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * riskPct;
   double tickVal = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickVal<=0 || tickSz<=0 || stopDistPrice<=0) return(0.0);
   double lossPerLot = (stopDistPrice / tickSz) * tickVal;     // money lost per 1.0 lot at the stop
   if(lossPerLot<=0) return(0.0);
   double lots = riskMoney / lossPerLot;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lots = MathFloor(lots/step)*step;
   if(lots < vmin) lots = (vmin*lossPerLot <= riskMoney*1.5) ? vmin : 0.0;  // feasibility skip
   if(lots > vmax) lots = vmax;
   return(lots);
}
//--- is there an open position from THIS ea on THIS symbol? ------------------
bool HasPosition()
{
   if(!PositionSelect(_Symbol)) return(false);
   return(PositionGetInteger(POSITION_MAGIC)==InpMagic);
}

//+------------------------------------------------------------------+
void OnTick()
{
   // act once per CLOSED bar
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == lastBarTime) return;
   lastBarTime = t;

   double emaF = Val(hEMAfast,1), emaS = Val(hEMAslow,1);
   double adx  = Val(hADX,1),     atr  = Val(hATR,1);
   double close= iClose(_Symbol,_Period,1);
   double ema20now = Val(hEMAfast,1);
   if(atr<=0) return;

   //================= manage an open position =================
   if(HasPosition())
   {
      long   ptype = PositionGetInteger(POSITION_TYPE);
      int    sd    = (ptype==POSITION_TYPE_BUY) ? 1 : -1;
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double vol   = PositionGetDouble(POSITION_VOLUME);
      double rmult = (entryRisk>0) ? sd*(close-entry)/entryRisk : 0.0;

      // 1) scale-out at +PartialAtR, then stop -> breakeven
      if(!scaled && rmult >= InpPartialAtR)
      {
         double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
         double cut = MathFloor((vol*InpPartialFrac)/step)*step;
         if(cut>=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN))
            trade.PositionClosePartial(_Symbol, cut);
         trade.PositionModify(_Symbol, entry, PositionGetDouble(POSITION_TP)); // SL->breakeven
         scaled=true; return;
      }
      // 2) momentum-ride exit: long exits below EMA20, short exits above
      bool momOk = (sd==1) ? (close>ema20now) : (close<ema20now);
      if(!momOk) { trade.PositionClose(_Symbol); scaled=false; }
      return;   // one position at a time per chart
   }

   //================= look for a NEW entry =================
   scaled = false;
   bool trend  = (adx >= InpADXtrend);
   int  side   = 0;

   if(InpUseTrend && trend)
   {
      if(emaF>emaS) side=1; else if(emaF<emaS) side=-1;
   }
   if(side==0 && InpUseBreakout && InpDonchian>0)
   {
      double hh=iHigh(_Symbol,_Period,iHighest(_Symbol,_Period,MODE_HIGH,InpDonchian,2));
      double ll=iLow (_Symbol,_Period,iLowest (_Symbol,_Period,MODE_LOW, InpDonchian,2));
      if(close>hh) side=1; else if(close<ll) side=-1;
   }
   if(side==0) return;

   double conf = Confidence(adx);
   double stopDist = InpStopMult*atr;
   double lots = LotsForRisk(stopDist, conf);
   if(lots<=0) return;                 // too small for this balance -> skip (protects $10 acct)

   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   entryRisk = stopDist;
   if(side==1) { double sl=ask-stopDist; trade.Buy (lots,_Symbol,ask,sl,0,"nexa"); }
   else        { double sl=bid+stopDist; trade.Sell(lots,_Symbol,bid,sl,0,"nexa"); }
}
//+------------------------------------------------------------------+
