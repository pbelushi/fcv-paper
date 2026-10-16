"""Rodada 2 — 04: o que o canal do PIB prevê mecanicamente para a pobreza (Q3, §6.4).

Para cada tratado T1 elegível para as análises de pobreza (≥ 3 anos de pesquisa antes do onset) com
distribuição observada antes do onset (última pesquisa nacional s ≤ g−1):
1. x(e) = queda proporcional do PIB per capita = 1 − exp(ATT_ln(e)), e = 0…5, usando (a) o ATT dinâmico
   agregado do CS REG e (b) o ATT da coorte do país (agregação group, constante em e).
2. Sob distribuição constante (hipótese do PIP para extrapolação), pobreza na linha z após queda x da renda
   = pobreza na linha z/(1 − x) da distribuição original. Consulta à API do PIP (fill_gaps=false, mesma
   versão da rodada 1) com povline = 3,00/(1 − x) no ano s. Respostas salvas em data/raw e no MANIFEST.
3. Δp.p. implícito = 100·[H(z/(1−x)) − H(z)]; agregado com pesos iguais por país (como o ATT simple do CS
   com coortes de 1–3 países), média em e = 0…5.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import truststore

truststore.inject_into_ssl()
sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402
from r2config import MIN_PRE_SURVEYS, RAW, TAB, manifest_version, save_raw  # noqa: E402

API = "https://api.worldbank.org/pip/v1/pip"
Z = 3.0


def eligible(p: pd.DataFrame) -> pd.DataFrame:
    tr = p[p.status_t1 == "tratado"]
    rows = []
    for iso, d in tr.groupby("iso3"):
        g = int(d.g_t1.iloc[0])
        pre = d[(d.year < g) & (d.survey_pip == 1)]
        if len(pre) >= MIN_PRE_SURVEYS:
            rows.append({"iso3": iso, "g": g, "s": int(pre.year.max()), "n_pre_surveys": len(pre)})
    return pd.DataFrame(rows)


def query(iso, year, line, version, cache):
    key = f"{iso}|{year}|{line:.6f}"
    if key in cache:
        return cache[key]
    params = {"country": iso, "year": year, "povline": round(line, 6), "fill_gaps": "false", "version": version,
              "ppp_version": 2021, "format": "json"}
    r = requests.get(API, params=params, timeout=120)
    if r.status_code != 200:
        sys.exit(f"ERRO na API do PIP: {r.url} -> {r.status_code}")
    js = [x for x in r.json() if x.get("reporting_level") == "national"]
    cache[key] = js
    return js


def main() -> None:
    p = C.panel()
    d = C.onset_sample(p)
    r = C.cs(d, "ln_gdppc")["r"]
    dyn = r["dyn"]["table"].set_index("term").estimate
    grp = r["group"]["table"].set_index("term").estimate
    el = eligible(p)
    version = [v for v in pd.read_csv(RAW / "MANIFEST.csv").versao if "PROD" in str(v)][0]
    cache_path = RAW / "pip_passthrough_queries.json"
    cache = json.load(open(cache_path)) if cache_path.exists() else {}
    rows = []
    for t in el.itertuples():
        base = query(t.iso3, t.s, Z, version, cache)
        if not base:
            continue
        wt = base[0]["welfare_type"]
        h0 = np.mean([x["headcount"] for x in base if x["welfare_type"] == wt])
        for variant, xs in [("ATT agregado", {e: 1 - np.exp(dyn[e]) for e in range(0, 6)}),
                            ("ATT da coorte", {e: 1 - np.exp(grp.get(t.g, np.nan)) for e in range(0, 6)})]:
            for e, x in xs.items():
                if not np.isfinite(x):
                    continue
                res = query(t.iso3, t.s, Z / (1 - x), version, cache)
                h1 = np.mean([y["headcount"] for y in res if y["welfare_type"] == wt])
                rows.append({"iso3": t.iso3, "g": t.g, "ano_pesquisa": t.s, "welfare_type": wt, "variante": variant, "e": e,
                             "queda_pib": x, "povline": Z / (1 - x), "pov_base": 100 * h0, "pov_implicita": 100 * h1,
                             "delta_pp": 100 * (h1 - h0)})
    body = json.dumps(cache).encode()
    save_raw(cache_path.name, body, "PIP", f"{API}?country={{iso}}&year={{s}}&povline={{3/(1-x)}}&fill_gaps=false",
             version, "CC BY 4.0 (World Bank Open Data terms)")
    pt = pd.DataFrame(rows)
    pt.to_csv(TAB / "passthrough_by_country.csv", index=False)
    agg = (pt.groupby(["variante", "iso3"]).delta_pp.mean().groupby("variante")
           .agg(delta_pp_medio="mean", delta_pp_mediana="median", n_paises="size")).reset_index()
    by_e = pt.groupby(["variante", "e"]).agg(queda_pib=("queda_pib", "mean"), delta_pp=("delta_pp", "mean")).reset_index()
    agg.to_csv(TAB / "passthrough.csv", index=False)
    by_e.to_csv(TAB / "passthrough_by_e.csv", index=False)
    print(f"Elegíveis: {len(el)} tratados com ≥ {MIN_PRE_SURVEYS} pesquisas antes do onset; consultas à API: {len(cache)}")
    print("ATT dinâmico ln PIB pc (e = 0..5):", {e: round(float(dyn[e]), 4) for e in range(6)})
    print(by_e.round(3).to_string(index=False))
    print(agg.round(3).to_string(index=False))
    _ = manifest_version


if __name__ == "__main__":
    main()
