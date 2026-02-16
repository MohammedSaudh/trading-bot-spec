# Trading Bot Strategy Spec

This repository now includes a runnable Python backtest implementation for the strategy defined in `trading-bot-spec.md.txt`.

## Strategy implemented
`HTF Liquidity Grab + MSB → HTF Fib AOI → LTF Reaction Fib Entry`

### Implemented flow
1. Detect HTF swing highs/lows (fractal left/right = 2).
2. Find liquidity grab (sweep + close back inside).
3. Confirm market structure break (MSB) within a max HTF wait window.
4. Build HTF AOI fib levels (0.50 / 0.618 / 0.75) and detect AOI touch.
5. After AOI touch, find LTF impulse in HTF direction using body-vs-ATR displacement.
6. Build LTF fib of impulse and place limit entry at fib 0.75.
7. Use TP=fib0, SL=fib1, move SL to BE at fib0.5.
8. Cancel pending orders on timeout / invalidation / ran-to-TP-first.
9. Position sizing uses fixed-risk percentage (`risk_pct`) of current equity.

## Files
- `backtest_strategy.py`: strategy logic and backtest runner.

## Data format
Create CSV files in `data/` with these names:
- `data/4H.csv`
- `data/1H.csv`
- `data/15m.csv`
- `data/5m.csv`

Each CSV must contain columns:
- `time` (ISO datetime)
- `open`
- `high`
- `low`
- `close`

## Run
```bash
python backtest_strategy.py
```

Outputs:
- terminal summary
- `backtest_trades.csv` (if trades exist)
- `backtest_events.csv` (if events exist)
