"""Slot-level discrete-event simulation of booking transactions on Ethereum PoS (H2).
Writes results/des.json and figures/fig_latency.png."""
import json, sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import deque
from params import *

OUT = ROOT / "results"; FIG = ROOT / "figures"
MODE = "push"
G_CREATE, G_CONFIRM, G_COMPLETE = GAS_CREATE[MODE], GAS_CONFIRM[MODE] + GAS_APPROVE, GAS_COMPLETE[MODE]  # new guest: approval load added
G_BOOKING = G_CREATE + G_CONFIRM + G_COMPLETE
KAPPA = 50.0  # Beta concentration of per-block background utilisation

def run(m, u, horizon_s, seed, warm_frac=0.1):
    rng = np.random.default_rng(seed)
    lam = baseline_rate() * m
    n_slots = int(horizon_s / SLOT_S)
    # pre-generate arrivals
    nb = rng.poisson(lam * horizon_s)
    t_book = np.sort(rng.uniform(0, horizon_s, nb))
    nc = rng.poisson(lam * horizon_s)
    t_comp = np.sort(rng.uniform(0, horizon_s, nc))
    wallet = np.exp(np.log(WALLET_MEDIAN_S) + WALLET_SIGMA * rng.standard_normal(nb))
    a, b = u * KAPPA, (1 - u) * KAPPA
    # event list of pending submissions: (submit_time, gas, kind, booking_idx)
    future = [(t, G_CREATE, 0, i) for i, t in enumerate(t_book)] + [(t, G_COMPLETE, 2, -1) for t in t_comp]
    future.sort(key=lambda x: x[0])
    fut = deque(future)
    import heapq
    confirm_heap = []  # confirm txs generated after create inclusion
    queue = deque()
    lat = {0: [], 1: [], 2: []}; fin = []; e2e = []
    create_incl = np.full(nb, np.nan)
    backlog_end = 0
    for k in range(1, n_slots + 1):
        t_slot = k * SLOT_S
        cutoff = t_slot - T_CUTOFF
        # move eligible submissions into mempool queue (FIFO by submit time)
        while fut and fut[0][0] <= cutoff:
            queue.append(fut.popleft())
        while confirm_heap and confirm_heap[0][0] <= cutoff:
            queue.append(heapq.heappop(confirm_heap))
        if rng.random() < P_MISS:
            continue
        cap = BLOCK_GAS_LIMIT * (1 - rng.beta(a, b))
        epoch = (k) // SLOTS_PER_EPOCH
        t_final = (epoch + 3) * SLOTS_PER_EPOCH * SLOT_S
        while queue and queue[0][1] <= cap:
            ts, g, kind, i = queue.popleft()
            cap -= g
            if ts >= warm_frac * horizon_s:
                lat[kind].append(t_slot - ts)
                if kind == 1:
                    fin.append(t_final - ts)
                    e2e.append(t_slot - t_book[i])
            if kind == 0:
                create_incl[i] = t_slot
                heapq.heappush(confirm_heap, (t_slot + wallet[i], G_CONFIRM, 1, i))
        # FIFO: if head does not fit, block is closed (no reordering) — conservative
    backlog_end = len(queue)
    return lat, fin, e2e, backlog_end

def summarize(xs):
    xs = np.asarray(xs)
    if xs.size == 0: return None
    return {"median": float(np.median(xs)), "p95": float(np.percentile(xs, 95)), "p99": float(np.percentile(xs, 99)), "mean": float(xs.mean())}

def ci(vals):
    v = np.asarray([x for x in vals if x is not None], float)
    if v.size < 2: return None
    from scipy import stats
    h = stats.t.ppf(0.975, v.size - 1) * v.std(ddof=1) / np.sqrt(v.size)
    return [float(v.mean() - h), float(v.mean() + h)]

def rho(m, u):
    offered = baseline_rate() * m * G_BOOKING
    capacity = (1 - P_MISS) * BLOCK_GAS_LIMIT * (1 - u) / SLOT_S
    return offered / capacity

def theta_sat(u):
    return (1 - P_MISS) * BLOCK_GAS_LIMIT * (1 - u) / (SLOT_S * G_BOOKING)

res = {"G_booking": G_BOOKING, "baseline_rate": baseline_rate(), "theta_sat": {str(u): theta_sat(u) for u in (0.5, 0.9, 0.98)}}

# ---- baseline (S1), 30 replications x 3 days ----
R = 30
reps = [run(1, 0.5, 3 * 86400, 1000 + r) for r in range(R)]
guest = [summarize(l[0] + l[1]) for l, *_ in reps]
res["S1"] = {
    "reps": R,
    "guest_median_mean": float(np.mean([g["median"] for g in guest])), "guest_median_ci": ci([g["median"] for g in guest]),
    "guest_p95_mean": float(np.mean([g["p95"] for g in guest])), "guest_p95_ci": ci([g["p95"] for g in guest]),
    "guest_p99_mean": float(np.mean([g["p99"] for g in guest])), "guest_p99_ci": ci([g["p99"] for g in guest]),
    "guest_mean_mean": float(np.mean([g["mean"] for g in guest])), "guest_mean_ci": ci([g["mean"] for g in guest]),
    "e2e_median_mean": float(np.mean([np.median(e) for *_, e, _ in reps])), "e2e_median_ci": ci([np.median(e) for *_, e, _ in reps]),
    "finality_median_mean": float(np.mean([np.median(f) for _, f, _, _ in reps])), "finality_median_ci": ci([np.median(f) for _, f, _, _ in reps]),
    "n_guest_tx_per_rep": float(np.mean([len(l[0]) + len(l[1]) for l, *_ in reps])),
    "create_mean_mean": float(np.mean([np.mean(l[0]) for l, *_ in reps])), "create_mean_ci": ci([np.mean(l[0]) for l, *_ in reps]),
    "confirm_median_mean": float(np.mean([np.median(l[1]) for l, *_ in reps])),
}
res["closed_form_mean"] = SLOT_S / 2 + T_CUTOFF + SLOT_S * P_MISS / (1 - P_MISS)

# ---- S3 stress grid ----
grid = {}
MS = [1, 10, 50, 100, 200, 300, 500, 1000, 1500, 2000, 2500]
for u in (0.5, 0.9, 0.98):
    for m in MS:
        r_ = rho(m, u)
        if r_ > 1.6: continue
        RR = 10
        out = [run(m, u, 4 * 3600, 5000 + 97 * m + int(u * 100) * 7 + r) for r in range(RR)]
        meds = [np.median(l[0] + l[1]) if (l[0] + l[1]) else np.nan for l, *_ in out]
        p95 = [np.percentile(l[0] + l[1], 95) if (l[0] + l[1]) else np.nan for l, *_ in out]
        grid[f"{u}|{m}"] = {"u": u, "m": m, "rho": r_, "median": float(np.nanmean(meds)), "median_ci": ci(meds),
                            "p95": float(np.nanmean(p95)), "backlog_end_mean": float(np.mean([o[3] for o in out]))}
        print(u, m, round(r_, 3), round(np.nanmean(meds), 1), round(np.nanmean(p95), 1), np.mean([o[3] for o in out]), file=sys.stderr)
res["S3"] = grid
# boundary: largest m with median < 60 s and no growing backlog
bound = {}
for u in (0.5, 0.9, 0.98):
    ok = [v["m"] for v in grid.values() if v["u"] == u and v["median"] < 60 and v["rho"] < 1]
    bound[str(u)] = max(ok) if ok else None
res["H2_boundary_m"] = bound
json.dump(res, open(OUT / "des.json", "w"), indent=1)

# ---- figure ----
C = {0.5: ("#2a78d6", "o"), 0.9: ("#eb6834", "s"), 0.98: ("#1baf7a", "^")}
plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e4e3df", "grid.linewidth": 0.5, "legend.frameon": False, "savefig.dpi": 300})
fig, axs = plt.subplots(1, 2, figsize=(7.1, 2.2))
for u, (col, mk) in C.items():
    pts = sorted([v for v in grid.values() if v["u"] == u], key=lambda v: v["m"])
    ms = [p["m"] for p in pts]
    axs[0].plot(ms, [p["median"] for p in pts], color=col, marker=mk, ms=4, lw=1.4, label=f"u = {u}")
    axs[1].plot(ms, [p["rho"] for p in pts], color=col, marker=mk, ms=4, lw=1.4, label=f"u = {u}")
axs[0].axhline(60, color="#52514e", ls="--", lw=0.8); axs[0].text(1.1, 70, "H2 criterion (60 s)", fontsize=6.5, color="#52514e")
axs[0].set_xscale("log"); axs[0].set_yscale("log"); axs[0].set_xlabel("Load multiplier m"); axs[0].set_ylabel("Median inclusion latency (s)")
axs[1].axhline(1, color="#52514e", ls="--", lw=0.8)
axs[1].set_xscale("log"); axs[1].set_yscale("log"); axs[1].set_xlabel("Load multiplier m"); axs[1].set_ylabel("Utilisation ρ of residual capacity")
axs[0].legend(fontsize=7, loc="upper left"); axs[0].set_title("(a)", fontsize=8); axs[1].set_title("(b)", fontsize=8)
fig.tight_layout(); fig.savefig(FIG / "fig_latency.png"); plt.close(fig)
print(json.dumps({k: res[k] for k in ("S1", "closed_form_mean", "theta_sat", "H2_boundary_m")}, indent=1))
