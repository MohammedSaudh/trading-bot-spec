Trading Strategy Specification (Codex-ready)
Strategy name
HTF Liquidity Grab + MSB → HTF Fib AOI → LTF Reaction Fib Entry
Instruments
•	Market: FX (example shown: EURUSD)
•	Symbols: [CONFIG: list of pairs]
________________________________________
1) Multi-timeframe mapping
Setup A
•	HTF: 4H
•	LTF Entry TF: 15m
•	Rule: AOI drawn on 4H → entries only evaluated/executed on 15m.
Setup B
•	HTF: 1H
•	LTF Entry TF: 5m
•	Rule: AOI drawn on 1H → entries only evaluated/executed on 5m.
Cross-setup rule
•	Evaluate both setups independently.
•	[CONFIG] allow_multiple_positions_per_symbol = False (default: only one live position per symbol; if a position exists, ignore new setups)
________________________________________
2) Step 1 (HTF): Liquidity Grab + Market Structure Break
2.1 Swing detection (HTF)
Use fractal swings on HTF.
Config:
•	SWING_LEFT = 2
•	SWING_RIGHT = 2
Swing high at index i if:
•	high[i] > max(high[i-SWING_LEFT : i]) AND high[i] > max(high[i+1 : i+SWING_RIGHT+1])
Swing low at index i if:
•	low[i] < min(low[i-SWING_LEFT : i]) AND low[i] < min(low[i+1 : i+SWING_RIGHT+1])
2.2 Liquidity Grab (LG)
Bullish LG (sell-side sweep)
Let L = price of the most recent confirmed swing low before candle t.
•	low[t] < L AND close[t] > L
Bearish LG (buy-side sweep)
Let H = price of the most recent confirmed swing high before candle t.
•	high[t] > H AND close[t] < H
2.3 Market Structure Break (MSB)
After an LG occurs, define the MSB level as the most recent opposite swing before the LG candle.
Bullish MSB (after bullish LG)
Let MSB_LEVEL = last swing high before LG candle.
•	MSB occurs when: close[t] > MSB_LEVEL (close-break)
Bearish MSB (after bearish LG)
Let MSB_LEVEL = last swing low before LG candle.
•	MSB occurs when: close[t] < MSB_LEVEL
2.4 Sequence (state machine)
Config:
•	MSB_MAX_WAIT_HTF = 20 HTF candles
Bullish:
•	On LG_bull: store lg_idx, lg_level, msb_level and go to state LG_SEEN.
•	While in LG_SEEN:
o	If close > msb_level within wait window → emit HTF_LONG_CONFIRMED and store msb_idx.
o	If timeout → reset.
Bearish: mirror.
________________________________________
3) Step 2 (HTF): Draw Fib on the MSB impulse leg → AOI levels
3.1 MSB impulse leg anchors (HTF)
Once MSB is confirmed at msb_idx:
For LONG
•	leg_low = min(low[i]) for i in [lg_idx .. msb_idx]
•	leg_high = max(high[i]) for i in [lg_idx .. msb_idx]
•	R = leg_high - leg_low
Compute AOI levels (retracement down from high):
•	AOI_0_50 = leg_high - 0.50 * R
•	AOI_0_618 = leg_high - 0.618 * R
•	AOI_0_75 = leg_high - 0.75 * R
For SHORT
•	leg_high = max(high[i]) for i in [lg_idx .. msb_idx]
•	leg_low = min(low[i]) for i in [lg_idx .. msb_idx]
•	R = leg_high - leg_low
Compute AOI levels (retracement up from low):
•	AOI_0_50 = leg_low + 0.50 * R
•	AOI_0_618 = leg_low + 0.618 * R
•	AOI_0_75 = leg_low + 0.75 * R
3.2 AOI touch rule (your rule)
A valid “reaction opportunity” begins when price touches ANY of:
•	0.50 OR 0.618 OR 0.75 (HTF fib levels)
Config:
•	AOI_TOL_PIPS = [X] or AOI_TOL_ATR_K = [k] (default use pips/spread buffer)
Touch condition (long/short):
•	Consider AOI touched if the candle range intersects the level (or zone):
o	low <= level <= high (single line)
o	or zone: low <= level+tol AND high >= level-tol
Store:
•	aoi_touch_idx, aoi_level_touched in the active setup context.
Validity:
•	[CONFIG] CONTEXT_TTL_HTF = 10 HTF candles after MSB confirmation
________________________________________
4) Step 3 (LTF): Find reaction impulse from AOI → draw LTF Fib → enter at 0.75
4.1 Preconditions
Only evaluate LTF entries if:
•	HTF context is active & not expired
•	AOI has been touched (0.50 / 0.618 / 0.75)
•	LTF timeframe must match HTF:
o	If HTF=1H → use LTF=5m
o	If HTF=4H → use LTF=15m
4.2 Define LTF reaction impulse
After AOI touch, wait for an impulse move in the HTF direction.
Config:
•	ATR_LTF_PERIOD = 14
•	IMPULSE_BODY_ATR_K = 0.8
•	IMPULSE_MAX_WAIT_LTF = 40 candles (5m) / 20 candles (15m) (configurable)
Impulse candle definition:
LONG impulse (bullish displacement)
A candle t qualifies if:
•	close[t] > high[t-1]
•	AND abs(close[t]-open[t]) >= IMPULSE_BODY_ATR_K * ATR_LTF[t]
SHORT impulse (bearish displacement)
•	close[t] < low[t-1]
•	AND abs(close[t]-open[t]) >= IMPULSE_BODY_ATR_K * ATR_LTF[t]
When impulse occurs:
•	set impulse_end_idx = t
•	define impulse anchors using the move starting from AOI-touch to impulse end.
4.3 Draw LTF fib on reaction impulse leg
LONG
•	impulse_low = min(low[i]) for i in [aoi_touch_idx .. impulse_end_idx]
•	impulse_high = max(high[i]) for i in [aoi_touch_idx .. impulse_end_idx]
•	R = impulse_high - impulse_low
Fib levels (retracement down from high):
•	fib0 = impulse_high
•	fib05 = impulse_high - 0.50 * R
•	fib075 = impulse_high - 0.75 * R
•	fib1 = impulse_low
SHORT
•	impulse_high = max(high[i]) for i in [aoi_touch_idx .. impulse_end_idx]
•	impulse_low = min(low[i]) for i in [aoi_touch_idx .. impulse_end_idx]
•	R = impulse_high - impulse_low
Fib levels (retracement up from low):
•	fib0 = impulse_low
•	fib05 = impulse_low + 0.50 * R
•	fib075 = impulse_low + 0.75 * R
•	fib1 = impulse_high
4.4 Entry / TP / SL rules (your exact rules)
Entry (only on LTF fib 0.75):
•	Place LIMIT entry at fib075
Take Profit
•	TP = fib0
Stop Loss
•	SL = fib1
Move SL to Break-even
•	When price reaches fib05, set SL = entry_price (break-even)
o	LONG: if high >= fib05 → SL = entry
o	SHORT: if low <= fib05 → SL = entry
Config:
•	ENTRY_TTL_LTF = 30 candles (5m) / 20 candles (15m)
Cancel pending entry if any occurs before fill:
•	LONG:
o	if high >= fib0 (ran to TP without retrace) → cancel
o	if close <= fib1 (invalidates structure) → cancel
•	SHORT:
o	if low <= fib0 → cancel
o	if close >= fib1 → cancel
•	or if TTL exceeded.
________________________________________
5) Risk / sizing (placeholders for you to fill)
Codex needs explicit sizing rules. Choose one:
Option A: fixed risk per trade (recommended)
Config:
•	RISK_PCT = 0.5% (example)
•	equity = account_equity
•	risk_amount = equity * RISK_PCT
•	stop_distance = abs(entry - SL)
•	position_size = risk_amount / stop_distance (converted into lot units)
Option B: fixed lot size
Config:
•	LOT_SIZE = X
________________________________________
6) Execution details (defaults)
•	Evaluate signals on candle close.
•	Enter using limit at fib0.75.
•	Stops and TP placed immediately as bracket/OCO if broker supports.
•	Spread buffer:
o	[CONFIG] price_buffer = spread * buffer_k
________________________________________
7) Logging (required for debugging)
Log events with reason codes:
•	HTF_LG_FOUND
•	HTF_MSB_CONFIRMED
•	HTF_AOI_TOUCH_{0.50|0.618|0.75}
•	LTF_IMPULSE_FOUND
•	ORDER_PLACED_ENTRY_FIB075
•	MOVE_SL_TO_BE_FIB05
•	EXIT_TP_FIB0
•	EXIT_SL_FIB1
•	CANCEL_ENTRY_TIMEOUT
•	CANCEL_ENTRY_RAN_TO_TP
•	CANCEL_ENTRY_INVALIDATED

