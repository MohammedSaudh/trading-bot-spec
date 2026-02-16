from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class SetupConfig:
    name: str
    htf_label: str
    ltf_label: str
    msb_max_wait_htf: int = 20
    context_ttl_htf: int = 10
    impulse_max_wait_ltf: int = 40
    entry_ttl_ltf: int = 30


@dataclass
class StrategyConfig:
    swing_left: int = 2
    swing_right: int = 2
    aoi_tol: float = 0.0
    atr_period_ltf: int = 14
    impulse_body_atr_k: float = 0.8
    risk_pct: float = 0.005
    allow_multiple_positions_per_symbol: bool = False
    initial_equity: float = 10_000.0


@dataclass
class HTFContext:
    direction: Direction
    lg_idx: int
    msb_idx: int
    msb_price: float
    aoi_levels: Dict[str, float]
    expiry_idx: int
    aoi_touch_idx: Optional[int] = None
    aoi_touch_level_name: Optional[str] = None


@dataclass
class PendingOrder:
    direction: Direction
    created_ltf_idx: int
    expiry_ltf_idx: int
    entry: float
    tp: float
    sl: float
    fib05: float
    fib0: float
    fib1: float
    setup_name: str
    htf_touch_idx: int


@dataclass
class OpenPosition:
    direction: Direction
    entry_ltf_idx: int
    entry_price: float
    tp: float
    sl: float
    fib05: float
    setup_name: str
    htf_touch_idx: int
    moved_to_be: bool = False


@dataclass
class Trade:
    setup_name: str
    direction: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    reason: str
    units: float
    pnl: float
    r_multiple: float


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    event_log: List[Dict] = field(default_factory=list)
    equity_curve: List[Tuple[pd.Timestamp, float]] = field(default_factory=list)


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def find_swings(df: pd.DataFrame, left: int, right: int) -> Tuple[pd.Series, pd.Series]:
    n = len(df)
    swing_high = pd.Series(False, index=df.index)
    swing_low = pd.Series(False, index=df.index)

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    for i in range(left, n - right):
        if highs[i] > highs[i - left : i].max() and highs[i] > highs[i + 1 : i + right + 1].max():
            swing_high.iloc[i] = True
        if lows[i] < lows[i - left : i].min() and lows[i] < lows[i + 1 : i + right + 1].min():
            swing_low.iloc[i] = True

    return swing_high, swing_low


def _last_true_before(mask: pd.Series, idx: int) -> Optional[int]:
    candidates = np.where(mask.iloc[:idx].to_numpy())[0]
    return int(candidates[-1]) if len(candidates) else None


def _aoi_from_leg(direction: Direction, leg_low: float, leg_high: float) -> Dict[str, float]:
    r = leg_high - leg_low
    if direction == Direction.LONG:
        return {
            "0.50": leg_high - 0.50 * r,
            "0.618": leg_high - 0.618 * r,
            "0.75": leg_high - 0.75 * r,
        }
    return {
        "0.50": leg_low + 0.50 * r,
        "0.618": leg_low + 0.618 * r,
        "0.75": leg_low + 0.75 * r,
    }


def _ltf_fib_from_impulse(direction: Direction, impulse_low: float, impulse_high: float) -> Dict[str, float]:
    r = impulse_high - impulse_low
    if direction == Direction.LONG:
        return {
            "fib0": impulse_high,
            "fib05": impulse_high - 0.5 * r,
            "fib075": impulse_high - 0.75 * r,
            "fib1": impulse_low,
        }
    return {
        "fib0": impulse_low,
        "fib05": impulse_low + 0.5 * r,
        "fib075": impulse_low + 0.75 * r,
        "fib1": impulse_high,
    }


def _build_htf_contexts(
    htf: pd.DataFrame,
    setup: SetupConfig,
    cfg: StrategyConfig,
    event_log: List[Dict],
) -> List[HTFContext]:
    swing_high, swing_low = find_swings(htf, cfg.swing_left, cfg.swing_right)
    contexts: List[HTFContext] = []

    for t in range(len(htf)):
        low_t = htf.iloc[t]["low"]
        high_t = htf.iloc[t]["high"]
        close_t = htf.iloc[t]["close"]

        last_sw_low = _last_true_before(swing_low, t)
        if last_sw_low is not None:
            lvl = htf.iloc[last_sw_low]["low"]
            if low_t < lvl and close_t > lvl:
                msb_swing_idx = _last_true_before(swing_high, t)
                if msb_swing_idx is not None:
                    msb_level = htf.iloc[msb_swing_idx]["high"]
                    event_log.append({"time": htf.index[t], "event": "HTF_LG_FOUND", "setup": setup.name, "dir": "LONG"})
                    for j in range(t + 1, min(len(htf), t + 1 + setup.msb_max_wait_htf)):
                        if htf.iloc[j]["close"] > msb_level:
                            leg_low = htf.iloc[t : j + 1]["low"].min()
                            leg_high = htf.iloc[t : j + 1]["high"].max()
                            context = HTFContext(
                                direction=Direction.LONG,
                                lg_idx=t,
                                msb_idx=j,
                                msb_price=msb_level,
                                aoi_levels=_aoi_from_leg(Direction.LONG, leg_low, leg_high),
                                expiry_idx=j + setup.context_ttl_htf,
                            )
                            contexts.append(context)
                            event_log.append({"time": htf.index[j], "event": "HTF_MSB_CONFIRMED", "setup": setup.name, "dir": "LONG"})
                            break

        last_sw_high = _last_true_before(swing_high, t)
        if last_sw_high is not None:
            lvl = htf.iloc[last_sw_high]["high"]
            if high_t > lvl and close_t < lvl:
                msb_swing_idx = _last_true_before(swing_low, t)
                if msb_swing_idx is not None:
                    msb_level = htf.iloc[msb_swing_idx]["low"]
                    event_log.append({"time": htf.index[t], "event": "HTF_LG_FOUND", "setup": setup.name, "dir": "SHORT"})
                    for j in range(t + 1, min(len(htf), t + 1 + setup.msb_max_wait_htf)):
                        if htf.iloc[j]["close"] < msb_level:
                            leg_low = htf.iloc[t : j + 1]["low"].min()
                            leg_high = htf.iloc[t : j + 1]["high"].max()
                            context = HTFContext(
                                direction=Direction.SHORT,
                                lg_idx=t,
                                msb_idx=j,
                                msb_price=msb_level,
                                aoi_levels=_aoi_from_leg(Direction.SHORT, leg_low, leg_high),
                                expiry_idx=j + setup.context_ttl_htf,
                            )
                            contexts.append(context)
                            event_log.append({"time": htf.index[j], "event": "HTF_MSB_CONFIRMED", "setup": setup.name, "dir": "SHORT"})
                            break

    for ctx in contexts:
        start = ctx.msb_idx
        end = min(len(htf) - 1, ctx.expiry_idx)
        for i in range(start, end + 1):
            lo = htf.iloc[i]["low"]
            hi = htf.iloc[i]["high"]
            touched_name = None
            for name, level in ctx.aoi_levels.items():
                if lo <= level + cfg.aoi_tol and hi >= level - cfg.aoi_tol:
                    touched_name = name
                    break
            if touched_name is not None:
                ctx.aoi_touch_idx = i
                ctx.aoi_touch_level_name = touched_name
                event_log.append(
                    {
                        "time": htf.index[i],
                        "event": f"HTF_AOI_TOUCH_{touched_name}",
                        "setup": setup.name,
                        "dir": ctx.direction.value.upper(),
                    }
                )
                break

    return [c for c in contexts if c.aoi_touch_idx is not None]


def _pnl(direction: Direction, entry: float, exit_px: float, units: float) -> float:
    if direction == Direction.LONG:
        return (exit_px - entry) * units
    return (entry - exit_px) * units


def run_backtest(
    htf_data: Dict[str, pd.DataFrame],
    ltf_data: Dict[str, pd.DataFrame],
    setups: List[SetupConfig],
    cfg: StrategyConfig,
) -> BacktestResult:
    result = BacktestResult()
    equity = cfg.initial_equity

    all_contexts: List[Tuple[SetupConfig, HTFContext]] = []
    for setup in setups:
        htf = htf_data[setup.htf_label].copy()
        htf = htf.sort_index()
        contexts = _build_htf_contexts(htf, setup, cfg, result.event_log)
        all_contexts.extend((setup, c) for c in contexts)

    all_contexts.sort(key=lambda x: htf_data[x[0].htf_label].index[x[1].aoi_touch_idx])

    open_pos: Optional[OpenPosition] = None

    for setup, ctx in all_contexts:
        if open_pos is not None and not cfg.allow_multiple_positions_per_symbol:
            continue

        ltf = ltf_data[setup.ltf_label].copy().sort_index()
        ltf["atr"] = compute_atr(ltf, cfg.atr_period_ltf)

        htf_touch_time = htf_data[setup.htf_label].index[ctx.aoi_touch_idx]
        scan_start = ltf.index.searchsorted(htf_touch_time, side="left")
        scan_end = min(len(ltf), scan_start + setup.impulse_max_wait_ltf)

        impulse_end = None
        for i in range(max(scan_start, 1), scan_end):
            row = ltf.iloc[i]
            prev = ltf.iloc[i - 1]
            if np.isnan(row["atr"]):
                continue
            body = abs(row["close"] - row["open"])
            if ctx.direction == Direction.LONG:
                cond = row["close"] > prev["high"] and body >= cfg.impulse_body_atr_k * row["atr"]
            else:
                cond = row["close"] < prev["low"] and body >= cfg.impulse_body_atr_k * row["atr"]
            if cond:
                impulse_end = i
                result.event_log.append({"time": ltf.index[i], "event": "LTF_IMPULSE_FOUND", "setup": setup.name, "dir": ctx.direction.value.upper()})
                break

        if impulse_end is None:
            continue

        impulse_low = ltf.iloc[scan_start : impulse_end + 1]["low"].min()
        impulse_high = ltf.iloc[scan_start : impulse_end + 1]["high"].max()
        fib = _ltf_fib_from_impulse(ctx.direction, impulse_low, impulse_high)

        pending = PendingOrder(
            direction=ctx.direction,
            created_ltf_idx=impulse_end,
            expiry_ltf_idx=impulse_end + setup.entry_ttl_ltf,
            entry=fib["fib075"],
            tp=fib["fib0"],
            sl=fib["fib1"],
            fib05=fib["fib05"],
            fib0=fib["fib0"],
            fib1=fib["fib1"],
            setup_name=setup.name,
            htf_touch_idx=ctx.aoi_touch_idx,
        )

        result.event_log.append({"time": ltf.index[impulse_end], "event": "ORDER_PLACED_ENTRY_FIB075", "setup": setup.name, "dir": ctx.direction.value.upper()})

        filled = False
        position: Optional[OpenPosition] = None

        for i in range(impulse_end + 1, min(len(ltf), pending.expiry_ltf_idx + 1)):
            row = ltf.iloc[i]

            if not filled:
                if pending.direction == Direction.LONG:
                    if row["high"] >= pending.fib0:
                        result.event_log.append({"time": ltf.index[i], "event": "CANCEL_ENTRY_RAN_TO_TP", "setup": setup.name, "dir": "LONG"})
                        break
                    if row["close"] <= pending.fib1:
                        result.event_log.append({"time": ltf.index[i], "event": "CANCEL_ENTRY_INVALIDATED", "setup": setup.name, "dir": "LONG"})
                        break
                    if row["low"] <= pending.entry <= row["high"]:
                        filled = True
                        stop_dist = abs(pending.entry - pending.sl)
                        if stop_dist <= 0:
                            break
                        risk_amount = equity * cfg.risk_pct
                        units = risk_amount / stop_dist
                        position = OpenPosition(
                            direction=Direction.LONG,
                            entry_ltf_idx=i,
                            entry_price=pending.entry,
                            tp=pending.tp,
                            sl=pending.sl,
                            fib05=pending.fib05,
                            setup_name=setup.name,
                            htf_touch_idx=ctx.aoi_touch_idx,
                        )
                else:
                    if row["low"] <= pending.fib0:
                        result.event_log.append({"time": ltf.index[i], "event": "CANCEL_ENTRY_RAN_TO_TP", "setup": setup.name, "dir": "SHORT"})
                        break
                    if row["close"] >= pending.fib1:
                        result.event_log.append({"time": ltf.index[i], "event": "CANCEL_ENTRY_INVALIDATED", "setup": setup.name, "dir": "SHORT"})
                        break
                    if row["low"] <= pending.entry <= row["high"]:
                        filled = True
                        stop_dist = abs(pending.entry - pending.sl)
                        if stop_dist <= 0:
                            break
                        risk_amount = equity * cfg.risk_pct
                        units = risk_amount / stop_dist
                        position = OpenPosition(
                            direction=Direction.SHORT,
                            entry_ltf_idx=i,
                            entry_price=pending.entry,
                            tp=pending.tp,
                            sl=pending.sl,
                            fib05=pending.fib05,
                            setup_name=setup.name,
                            htf_touch_idx=ctx.aoi_touch_idx,
                        )

                if filled and position is not None:
                    open_pos = position
                    open_pos_units = units
                    continue

            if filled and position is not None:
                if not position.moved_to_be:
                    if position.direction == Direction.LONG and row["high"] >= position.fib05:
                        position.sl = position.entry_price
                        position.moved_to_be = True
                        result.event_log.append({"time": ltf.index[i], "event": "MOVE_SL_TO_BE_FIB05", "setup": setup.name, "dir": "LONG"})
                    elif position.direction == Direction.SHORT and row["low"] <= position.fib05:
                        position.sl = position.entry_price
                        position.moved_to_be = True
                        result.event_log.append({"time": ltf.index[i], "event": "MOVE_SL_TO_BE_FIB05", "setup": setup.name, "dir": "SHORT"})

                if position.direction == Direction.LONG:
                    hit_sl = row["low"] <= position.sl
                    hit_tp = row["high"] >= position.tp
                else:
                    hit_sl = row["high"] >= position.sl
                    hit_tp = row["low"] <= position.tp

                if hit_sl or hit_tp:
                    if hit_sl and hit_tp:
                        exit_px = position.sl
                        reason = "EXIT_SL_FIB1"
                    elif hit_tp:
                        exit_px = position.tp
                        reason = "EXIT_TP_FIB0"
                    else:
                        exit_px = position.sl
                        reason = "EXIT_SL_FIB1"

                    pnl = _pnl(position.direction, position.entry_price, exit_px, open_pos_units)
                    risk = abs(position.entry_price - pending.sl) * open_pos_units
                    r_multiple = pnl / risk if risk else 0.0
                    equity += pnl
                    result.trades.append(
                        Trade(
                            setup_name=setup.name,
                            direction=position.direction.value,
                            entry_time=ltf.index[position.entry_ltf_idx],
                            exit_time=ltf.index[i],
                            entry_price=position.entry_price,
                            exit_price=exit_px,
                            reason=reason,
                            units=open_pos_units,
                            pnl=pnl,
                            r_multiple=r_multiple,
                        )
                    )
                    result.event_log.append({"time": ltf.index[i], "event": reason, "setup": setup.name, "dir": position.direction.value.upper()})
                    result.equity_curve.append((ltf.index[i], equity))
                    open_pos = None
                    break
        else:
            if not filled:
                result.event_log.append({"time": ltf.index[min(len(ltf) - 1, pending.expiry_ltf_idx)], "event": "CANCEL_ENTRY_TIMEOUT", "setup": setup.name, "dir": ctx.direction.value.upper()})

    return result


def load_ohlc_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    req = {"time", "open", "high", "low", "close"}
    missing = req - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {path}: {sorted(missing)}")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.set_index("time").sort_index()


def summarize(result: BacktestResult, initial_equity: float) -> pd.DataFrame:
    if not result.trades:
        return pd.DataFrame(
            [
                {
                    "trades": 0,
                    "win_rate": 0.0,
                    "net_pnl": 0.0,
                    "return_pct": 0.0,
                    "avg_r": 0.0,
                }
            ]
        )
    tdf = pd.DataFrame([t.__dict__ for t in result.trades])
    wins = (tdf["pnl"] > 0).mean()
    net = tdf["pnl"].sum()
    avg_r = tdf["r_multiple"].mean()
    return pd.DataFrame(
        [
            {
                "trades": len(tdf),
                "win_rate": float(wins),
                "net_pnl": float(net),
                "return_pct": float(net / initial_equity),
                "avg_r": float(avg_r),
            }
        ]
    )


if __name__ == "__main__":
    # Example wiring:
    # python backtest_strategy.py
    # expecting CSVs in ./data/{1H,4H,5m,15m}.csv
    cfg = StrategyConfig()
    setups = [
        SetupConfig(name="HTF_4H_LTF_15m", htf_label="4H", ltf_label="15m", impulse_max_wait_ltf=20, entry_ttl_ltf=20),
        SetupConfig(name="HTF_1H_LTF_5m", htf_label="1H", ltf_label="5m", impulse_max_wait_ltf=40, entry_ttl_ltf=30),
    ]

    htf = {
        "4H": load_ohlc_csv("data/4H.csv"),
        "1H": load_ohlc_csv("data/1H.csv"),
    }
    ltf = {
        "15m": load_ohlc_csv("data/15m.csv"),
        "5m": load_ohlc_csv("data/5m.csv"),
    }

    res = run_backtest(htf_data=htf, ltf_data=ltf, setups=setups, cfg=cfg)
    print(summarize(res, cfg.initial_equity).to_string(index=False))

    if res.trades:
        pd.DataFrame([t.__dict__ for t in res.trades]).to_csv("backtest_trades.csv", index=False)
    if res.event_log:
        pd.DataFrame(res.event_log).to_csv("backtest_events.csv", index=False)
