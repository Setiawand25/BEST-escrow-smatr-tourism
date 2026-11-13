"""Single source of truth for every simulation parameter (Table VII of the manuscript)."""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAS = json.load(open(ROOT / "results" / "gas.json"))
MARG = json.load(open(ROOT / "results" / "marginal_sdg.json"))

def _median(mode, fn):
    r = next(x for x in GAS if x["mode"] == mode)
    return r["stats"][fn]["median"]

# --- measured on the local Cancun EVM (Hardhat), steady state (warm recipients) ---
GAS_CREATE = {m: _median(m, "create") for m in ("push", "accrue")}
GAS_CONFIRM = {m: _median(m, "confirm") for m in ("push", "accrue")}
GAS_COMPLETE = {m: _median(m, "complete") for m in ("push", "accrue")}
GAS_APPROVE = GAS[0]["approveGas"]            # one-time ERC-20 approval per new guest wallet
GAS_WITHDRAW = next(x for x in GAS if x["mode"] == "accrue")["stats"]["withdraw"]["median"]
GAS_SDG_MARGINAL = {m: MARG[m]["marginal"] for m in ("push", "accrue")}

def lifecycle_gas(mode="push", new_guest=False):
    g = GAS_CREATE[mode] + GAS_CONFIRM[mode] + GAS_COMPLETE[mode]
    return g + (GAS_APPROVE if new_guest else 0)

# --- protocol constants ---
SLOT_S = 12.0                 # Gasper slot [25]
SLOTS_PER_EPOCH = 32
BLOCK_GAS_LIMIT = 60_000_000  # raised 25 Nov 2025 [The Block]
EIP1559_TARGET = 0.5          # target = 50% of limit; base fee changes up to 12.5%/block
P_MISS = 0.01                 # missed-slot probability (assumption)
T_CUTOFF = 1.0                # tx must reach the builder >= 1 s before slot start (assumption)

# --- dataset / market inputs ---
ARRIVALS_JAN_JUN_2025 = 110_836  # foreign arrivals via Bandar Bentan Telani (Lagoi), Jan-Jun 2025, BPS Kepri
ARRIVALS_PER_YEAR = 2 * ARRIVALS_JAN_JUN_2025   # annualised (no seasonal adjustment; assumption)
GUESTS_PER_PARTY = 2          # assumption
NIGHTLY_SGD = 378.0           # Table V
SGD_USD = 0.783               # 21 Oct 2026
NIGHTLY_USD = NIGHTLY_SGD * SGD_USD
NIGHTS_MEAN = 2.0             # assumption (sensitivity 1-3)
PRICE_SIGMA = 0.5             # lognormal dispersion of booking value (assumption)
ETH_USD = 2725.0              # 5 Oct 2026 (sensitivity 1,500-5,000)

# --- cost model ---
LEGACY_LOW, LEGACY_HIGH = 0.175, 0.335   # OTA 15-30% [O'Connor et al. 2025] + card 2.5-3.5% (assumption)
RAMP_FEE = 0.010              # licensed fiat<->stablecoin conversion, assumption (0-1.5%)
SPEC_ORIGINAL = dict(h=0.78, p=0.15, c=0.05, s=0.02)
SPEC_REVISED = dict(h=0.90, p=0.05, c=0.03, s=0.02)

# --- latency model ---
WALLET_MEDIAN_S, WALLET_SIGMA = 10.0, 0.5   # assumption
H3_THRESHOLD = 0.05           # marginal SDG cost must be <= 5% of the amount allocated

def baseline_rate():
    return ARRIVALS_PER_YEAR / GUESTS_PER_PARTY / (365 * 86400)   # bookings / s
