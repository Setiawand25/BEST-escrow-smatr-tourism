"""Cost-ratio (H1), SDG-allocation overhead (H3) and sensitivity analysis.
Writes results/cost.json and figures fig_gas.png, fig_cr.png, fig_tornado.png, fig_h3.png."""
import json, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from params import *

rng = np.random.default_rng(20261022)
OUT = ROOT / "results"; FIG = ROOT / "figures"; FIG.mkdir(exist_ok=True)
C1, C2, C3, C4, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": "#e4e3df",
                     "grid.linewidth": 0.5, "axes.spines.top": False, "axes.spines.right": False,
                     "legend.frameon": False, "savefig.dpi": 300})

def sample_values(n):
    nightly = NIGHTLY_USD * np.exp(rng.normal(0, PRICE_SIGMA, n))
    nights = np.minimum(1 + rng.poisson(NIGHTS_MEAN - 1, n), 7)
    return nightly * nights

V = sample_values(200_000)
V_MED = float(np.median(V))

def usd(gas, gwei, eth=ETH_USD): return gas * gwei * 1e-9 * eth
def cr_gas(gwei, v, mode="push", new_guest=False, eth=ETH_USD): return usd(lifecycle_gas(mode, new_guest), gwei, eth) / v
def cr_total(gwei, v, spec, mode="push", new_guest=False, eth=ETH_USD, ramp=RAMP_FEE):
    return cr_gas(gwei, v, mode, new_guest, eth) + ramp + spec["p"] + spec["c"]

res = {"V_median_usd": V_MED, "V_mean_usd": float(V.mean()), "nightly_usd": NIGHTLY_USD}
res["lifecycle_gas"] = {f"{m}{'_newguest' if ng else ''}": lifecycle_gas(m, ng) for m in ("push", "accrue") for ng in (False, True)}

# ---- H1 ----
grid = np.logspace(-1, 2, 61)
h1 = {}
for name, spec in (("original_78_15_5_2", SPEC_ORIGINAL), ("revised_90_5_3_2", SPEC_REVISED)):
    floor = RAMP_FEE + spec["p"] + spec["c"]
    # breakeven gas price at which median-booking CR_total hits the legacy lower bound
    room = LEGACY_LOW - floor
    be = {}
    for m in ("push", "accrue"):
        for ng in (False, True):
            be[f"{m}{'_newguest' if ng else ''}"] = (room * V_MED / (lifecycle_gas(m, ng) * 1e-9 * ETH_USD)) if room > 0 else None
    pts = {}
    for g in (0.5, 1, 10, 50):
        c = cr_total(g, V, spec, "push", True)
        pts[str(g)] = {"median": float(np.median(c)), "p90": float(np.percentile(c, 90)),
                       "share_below_legacy_low": float((c < LEGACY_LOW).mean())}
    h1[name] = {"non_gas_floor": floor, "breakeven_gwei_median_booking": be, "at_gwei_pushnewguest": pts}
res["H1"] = h1
res["cr_gas_median_booking"] = {str(g): {m: float(cr_gas(g, V_MED, m, True)) for m in ("push", "accrue")} for g in (0.5, 1, 10, 50)}
# maximum admissible intermediary share alpha_p + alpha_c (median booking, push, new guest)
res["max_intermediary_share"] = {str(g): float(LEGACY_LOW - RAMP_FEE - cr_gas(g, V_MED, "push", True)) for g in (1, 10, 50)}

# ---- sensitivity (tornado) on CR_total, revised spec, push, new guest, g = 10 gwei, median booking ----
G_REF = 10.0
base = cr_total(G_REF, V_MED, SPEC_REVISED, "push", True)
factors = [
    ("ETH price US$1,500–5,000", lambda lo: cr_total(G_REF, V_MED, SPEC_REVISED, "push", True, eth=1500 if lo else 5000)),
    ("Gas price 1–50 gwei", lambda lo: cr_total(1 if lo else 50, V_MED, SPEC_REVISED, "push", True)),
    ("Stay length 1–3 nights", lambda lo: cr_total(G_REF, NIGHTLY_USD * (3 if lo else 1), SPEC_REVISED, "push", True)),
    ("Ramp fee 0–1.5%", lambda lo: cr_total(G_REF, V_MED, SPEC_REVISED, "push", True, ramp=0.0 if lo else 0.015)),
    ("Settlement accrue vs push", lambda lo: cr_total(G_REF, V_MED, SPEC_REVISED, "accrue" if lo else "push", True)),
    ("Returning vs new guest", lambda lo: cr_total(G_REF, V_MED, SPEC_REVISED, "push", not lo)),
]
tor = [(n, float(f(True)), float(f(False))) for n, f in factors]
tor.sort(key=lambda t: abs(t[2] - t[1]))
res["tornado"] = {"g_ref": G_REF, "base": float(base), "factors": tor}

# ---- H3: marginal on-chain cost of the SDG allocation relative to the amount allocated ----
h3 = {}
for m in ("push", "accrue"):
    dg = GAS_SDG_MARGINAL[m] + (GAS_WITHDRAW / (baseline_rate() * 30 * 86400) if m == "accrue" else 0)  # monthly pull
    be = H3_THRESHOLD * SPEC_REVISED["s"] * V_MED / (dg * 1e-9 * ETH_USD)
    frac = {str(g): float((usd(dg, g) / (SPEC_REVISED["s"] * V) <= H3_THRESHOLD).mean()) for g in (1, 10, 50)}
    ratio_med = {str(g): float(usd(dg, g) / (SPEC_REVISED["s"] * V_MED)) for g in (1, 10, 50)}
    h3[m] = {"marginal_gas": dg, "breakeven_gwei_median": float(be), "share_bookings_meeting": frac, "ratio_median": ratio_med}
res["H3"] = h3

# ---- correctness check of the split rule (not a hypothesis) ----
amt = np.round(V[:100_000] * 1e6).astype(np.int64)
bps = np.array([500, 300, 200])
shares = (amt[:, None] * bps[None, :]) // 10_000
hotel_rem = amt - shares.sum(1)
naive_hotel = amt * 9000 // 10_000
res["split_check"] = {"n": int(amt.size), "remainder_violations": int(((hotel_rem + shares.sum(1)) != amt).sum()),
                      "naive_violations": int(((naive_hotel + shares.sum(1)) != amt).sum())}

# ---- EIP-1559 base-fee escalation during sustained congestion ----
esc = {}
for u in (0.5, 0.7, 0.9, 0.98):
    step = 1 + 0.125 * (u - EIP1559_TARGET) / EIP1559_TARGET
    esc[str(u)] = {"per_block": step, "after_25_blocks_5min": step ** 25, "after_75_blocks_15min": step ** 75}
res["eip1559"] = esc
json.dump(res, open(OUT / "cost.json", "w"), indent=1)

# ================= figures =================
W1 = 3.45  # IEEE single column (in)
# Fig: gas per function (measured)
fig, ax = plt.subplots(figsize=(W1, 2.1))
labels = ["approve()\n(new guest)", "createBooking()", "confirmPayment()", "completeStay()", "withdraw()\n(accrue, periodic)"]
push = [GAS_APPROVE, GAS_CREATE["push"], GAS_CONFIRM["push"], GAS_COMPLETE["push"], 0]
accr = [GAS_APPROVE, GAS_CREATE["accrue"], GAS_CONFIRM["accrue"], GAS_COMPLETE["accrue"], GAS_WITHDRAW]
y = np.arange(len(labels)); h = 0.36
ax.barh(y - h/2 - 0.01, np.array(push) / 1e3, h, color=C1, label="Push settlement")
ax.barh(y + h/2 + 0.01, np.array(accr) / 1e3, h, color=C2, label="Accrue + pull")
for yi, v in zip(y, push):
    if v: ax.text(v/1e3 + 2, yi - h/2, f"{v/1e3:.1f}", va="center", fontsize=6.5, color=INK)
for yi, v in zip(y, accr):
    if v: ax.text(v/1e3 + 2, yi + h/2, f"{v/1e3:.1f}", va="center", fontsize=6.5, color=INK)
ax.set_yticks(y, labels, fontsize=7); ax.invert_yaxis(); ax.set_xlabel("Measured gas (×10³), median")
ax.set_xlim(0, 150); ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=2, fontsize=7); ax.grid(axis="y", visible=False)
fig.tight_layout(); fig.savefig(FIG / "fig_gas.png"); plt.close(fig)

# Fig: CR_total vs gas price, two specs, with legacy band
fig, ax = plt.subplots(figsize=(W1, 2.2))
ax.axhspan(LEGACY_LOW * 100, LEGACY_HIGH * 100, color="#e9e8e4", lw=0)
ax.text(0.12, 25.5, "Legacy OTA + card band (17.5–33.5%)", fontsize=6.5, color=MUTED)
for spec, col, lab, mk in ((SPEC_ORIGINAL, C2, "Original spec. 78/15/5/2", "s"), (SPEC_REVISED, C1, "Revised spec. 90/5/3/2", "o")):
    med = [np.median(cr_total(g, V, spec, "push", True)) * 100 for g in grid]
    p10 = [np.percentile(cr_total(g, V, spec, "push", True), 10) * 100 for g in grid]
    p90 = [np.percentile(cr_total(g, V, spec, "push", True), 90) * 100 for g in grid]
    ax.fill_between(grid, p10, p90, color=col, alpha=0.15, lw=0)
    ax.plot(grid, med, color=col, lw=1.6, label=lab, marker=mk, markevery=10, ms=4)
ax.set_xscale("log"); ax.set_xlabel("Gas price (gwei)"); ax.set_ylabel("CR$_{total}$ (%)")
ax.set_ylim(0, 40); ax.legend(loc="upper left", fontsize=7)
fig.tight_layout(); fig.savefig(FIG / "fig_cr.png"); plt.close(fig)

# Fig: tornado
fig, ax = plt.subplots(figsize=(W1, 1.8))
for i, (n, lo, hi) in enumerate(tor):
    ax.barh(i, (hi - base) * 100, left=base * 100, color=C2, height=0.55)
    ax.barh(i, (lo - base) * 100, left=base * 100, color=C1, height=0.55)
ax.axvline(base * 100, color=INK, lw=0.8)
ax.set_yticks(range(len(tor)), [t[0] for t in tor], fontsize=7)
ax.set_xlabel("CR$_{total}$ (%)")
ax.grid(axis="y", visible=False)
fig.tight_layout(); fig.savefig(FIG / "fig_tornado.png"); plt.close(fig)

# Fig: H3 overhead ratio vs gas price
fig, ax = plt.subplots(figsize=(W1, 2.0))
for m, col, lab, mk in (("push", C1, "Push: per-booking transfer", "o"), ("accrue", C2, "Accrue: ledger credit + monthly pull", "s")):
    r = [usd(h3[m]["marginal_gas"], g) / (SPEC_REVISED["s"] * V_MED) * 100 for g in grid]
    ax.plot(grid, r, color=col, lw=1.6, label=lab, marker=mk, markevery=10, ms=4)
ax.axhline(H3_THRESHOLD * 100, color=MUTED, lw=0.8, ls="--"); ax.text(0.11, 6.6, "H3 threshold (5%)", fontsize=6.5, color=MUTED)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("Gas price (gwei)")
ax.set_ylabel("Overhead / allocation (%)"); ax.legend(loc="lower right", fontsize=6.5)
fig.tight_layout(); fig.savefig(FIG / "fig_h3.png"); plt.close(fig)
print(json.dumps(res, indent=1))
