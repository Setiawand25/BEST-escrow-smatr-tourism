"""DUMMY data + analysis pipeline for the expert validation and the user survey.

!!! SIMULATED DATA — FORMAT REFERENCE ONLY — NOT RESEARCH RESULTS — DO NOT REPORT !!!
Replace data/*.csv with real responses and re-run: the same script then produces the real tables.
Writes results/human_eval_dummy.json and data/*.csv
"""
import json, numpy as np, pandas as pd, pathlib
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)
OUT = ROOT / "results"
rng = np.random.default_rng(7)
USE_EXISTING = (DATA / "expert_ratings.csv").exists() and (DATA / "survey_responses.csv").exists() and not (DATA / "DUMMY_MARKER").exists()

# ---------------- instruments ----------------
EXPERT_ITEMS = {
    "E01": ("Completeness", "The five layers cover all functions needed for booking, payment and settlement."),
    "E02": ("Completeness", "The booking state machine covers all realistic reservation outcomes."),
    "E03": ("Interoperability", "The architecture can integrate with existing OTA and PMS systems."),
    "E04": ("Interoperability", "Fiat and stablecoin payment routing is technically feasible."),
    "E05": ("Security", "The threat model covers the main risks of handling guest funds."),
    "E06": ("Security", "The implemented mitigations are adequate for a pilot."),
    "E07": ("Scalability", "The capacity margin is sufficient for Lagoi's demand."),
    "E08": ("Scalability", "The cost per booking is acceptable to hotel operators."),
    "E09": ("Applicability", "The revenue-sharing rule is acceptable to stakeholders."),
    "E10": ("Applicability", "The SDG community fund is meaningful for the destination."),
    "E11": ("Regulatory fit", "The design respects Indonesian currency and crypto-asset rules."),
    "E12": ("Regulatory fit", "The design respects personal-data-protection requirements."),
}
EXPERTS = [  # DUMMY profiles — replace with the real panel
    {"id": "X1", "role": "Blockchain developer (DUMMY)", "years": 8},
    {"id": "X2", "role": "Resort operations manager (DUMMY)", "years": 15},
    {"id": "X3", "role": "Tourism-policy academic (DUMMY)", "years": 10},
]
SUS = [f"SUS{i}" for i in range(1, 11)]  # standard 10-item System Usability Scale, 1-5
TAM = {"PU": ["PU1", "PU2", "PU3", "PU4"], "PEOU": ["PEOU1", "PEOU2", "PEOU3", "PEOU4"],
       "TR": ["TR1", "TR2", "TR3", "TR4"], "BI": ["BI1", "BI2", "BI3"]}

# ---------------- dummy generation ----------------
if not USE_EXISTING:
    rows = []
    for x in EXPERTS:
        bias = rng.normal(0, 0.25)
        for k, (dim, _) in EXPERT_ITEMS.items():
            base = 4.45 + bias + (-0.35 if dim == "Regulatory fit" else 0) + rng.normal(0, 0.45)
            rows.append({"expert": x["id"], "item": k, "dimension": dim, "rating": int(np.clip(round(base), 1, 5))})
    pd.DataFrame(rows).to_csv(DATA / "expert_ratings.csv", index=False)

    def likert(latent, n, loading=0.8, noise=0.6):
        return np.clip(np.round(3 + loading * latent[:, None] + rng.normal(0, noise, (len(latent), n))), 1, 5).astype(int)
    resp = []
    for group, n, mu in (("guest", 60, 0.55), ("staff", 20, 0.25)):
        u = rng.normal(mu, 0.8, n)        # latent usability attitude
        s = likert(u, 10)
        s[:, 1::2] = 6 - s[:, 1::2]        # SUS even items are negatively worded
        t = {c: likert(u * 0.7 + rng.normal(0, 0.5, n), len(items)) for c, items in TAM.items()}
        for i in range(n):
            r = {"respondent": f"{group[0].upper()}{i+1:03d}", "group": group}
            r.update({SUS[j]: int(s[i, j]) for j in range(10)})
            for c, items in TAM.items(): r.update({items[j]: int(t[c][i, j]) for j in range(len(items))})
            resp.append(r)
    pd.DataFrame(resp).to_csv(DATA / "survey_responses.csv", index=False)
    (DATA / "DUMMY_MARKER").write_text("Files in this folder are SIMULATED. Delete this marker after replacing them with real data.\n")
    pd.DataFrame([{"item": k, "dimension": d, "statement": s} for k, (d, s) in EXPERT_ITEMS.items()]).to_csv(DATA / "expert_instrument.csv", index=False)
    pd.DataFrame(EXPERTS).to_csv(DATA / "expert_panel_DUMMY.csv", index=False)

# ---------------- analysis (same for real data) ----------------
ex = pd.read_csv(DATA / "expert_ratings.csv")
wide = ex.pivot(index="item", columns="expert", values="rating")
k = wide.shape[1]; n_items = wide.shape[0]
icvi = (wide >= 4).mean(axis=1)
aiken = ((wide - 1).sum(axis=1)) / (k * (5 - 1))                     # Aiken's V, 5-point scale
ranks = wide.rank(axis=0)
S = ((ranks.sum(axis=1) - ranks.sum(axis=1).mean()) ** 2).sum()
kendall_w = 12 * S / (k ** 2 * (n_items ** 3 - n_items))
dims = ex.groupby("dimension")["rating"].agg(["mean", "std"]).round(2)
expert = {"n_experts": k, "n_items": n_items, "mean_rating": round(ex.rating.mean(), 2),
          "S_CVI_Ave": round(icvi.mean(), 3), "items_ICVI_below_0.78": int((icvi < 0.78).sum()),
          "Aiken_V_min": round(aiken.min(), 3), "Aiken_V_mean": round(aiken.mean(), 3),
          "Kendall_W": round(kendall_w, 3), "by_dimension": dims.reset_index().to_dict("records")}

sv = pd.read_csv(DATA / "survey_responses.csv")
odd, even = SUS[0::2], SUS[1::2]
sv["SUS_score"] = ((sv[odd] - 1).sum(axis=1) + (5 - sv[even]).sum(axis=1)) * 2.5
def alpha(df):
    k_ = df.shape[1]; return k_ / (k_ - 1) * (1 - df.var(axis=0, ddof=1).sum() / df.sum(axis=1).var(ddof=1))
def grade(x):  # Bangor et al. (2009) adjective scale
    return "Excellent" if x >= 85.5 else "Good" if x >= 71.4 else "OK" if x >= 50.9 else "Poor"
survey = {}
for g, d in sv.groupby("group"):
    m, sd, n = d.SUS_score.mean(), d.SUS_score.std(ddof=1), len(d)
    h = stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n)
    survey[g] = {"n": n, "SUS_mean": round(m, 1), "SUS_sd": round(sd, 1), "SUS_95CI": [round(m - h, 1), round(m + h, 1)], "grade": grade(m),
                 **{f"{c}_mean": round(d[items].mean(axis=1).mean(), 2) for c, items in TAM.items()}}
t, p = stats.ttest_ind(sv[sv.group == "guest"].SUS_score, sv[sv.group == "staff"].SUS_score, equal_var=False)
survey["welch_t_guest_vs_staff"] = {"t": round(float(t), 2), "p": round(float(p), 4)}
survey["cronbach_alpha"] = {c: round(alpha(sv[items]), 3) for c, items in TAM.items()} | {"SUS": round(alpha(pd.concat([sv[odd], 6 - sv[even]], axis=1)), 3)}

res = {"WARNING": "SIMULATED DUMMY DATA - FORMAT REFERENCE ONLY - NOT RESEARCH RESULTS" if (DATA / "DUMMY_MARKER").exists() else "real data",
       "expert_panel": expert, "survey": survey}
json.dump(res, open(OUT / "human_eval_dummy.json", "w"), indent=1, default=float)
print(json.dumps(res, indent=1, default=float))
