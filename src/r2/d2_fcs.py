"""Rodada 2 — d2: listas FCS históricas (FY06–FY27), tipologia de trajetória e limiares FCS.

Fontes (data/raw, públicas na página FCS do Banco Mundial):
- fcs_list_FY06_FY26.pdf (uma página por ano fiscal; formatos variam por era);
- fcv_list_FY27.pdf e institutional_fragility_list_FY27.pdf;
- fcs_historical_note_FY27.pdf (limiares FY20–26) e fcv_methodology_summary_FY27.pdf (FY27).

Decisões (documentadas em outputs/r2/tables/fcs_decisions.csv):
- FY06–FY09 (LICUS / Fragile States): "marginal" entra só como fcs_marginal (estava na lista
  "para monitoramento"); fcs_any = severe/core.
- Categorias conflito × institucional só existem a partir de FY20; antes, apenas fcs_any.
- FY27: fcs_conflict = Public FCV List; fcs_institutional = Institutional Fragility List.
- Ano-calendário: a lista FYt vigora de julho de t−1 a junho de t e usa dados até t−1;
  atribuída ao ano-calendário t−1 (year = FY − 1).
"""
import re
import sys
from pathlib import Path

import country_converter as coco
import numpy as np
import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))
from r2config import CHRONIC_ROBUST, CHRONIC_SHARE, INTERIM, RAW, TAB, manifest_version  # noqa: E402

ALIASES = {  # grafias do PDF que o country_converter não resolve
    "solomonislands": "SLB", "timorleste": "TLS", "lao,pdr": "LAO", "lao, pdr": "LAO", "sao tome and pr": "STP",
    "kosovo": "XKX", "west bank and gaza": "PSE", "west bank and gaza (territory)": "PSE", "congo, rep": "COG",
    "micronesia, fed. sts": "FSM", "côte divoire": "CIV", "cote divoire": "CIV", "c�te divoire": "CIV",
    "guinea - bissau": "GNB", "guinea � bissau": "GNB", "syria": "SYR", "s�o tom� and pr�ncipe": "STP",
    "central african rep.": "CAF", "central afr. rep": "CAF", "congo, dem. rep": "COD",
}
STOP = re.compile(r"^((a/|b/|c/|d/|e/)\s*\S.{10,}|\*memo|for more information|specifically defined|notes?:|source)", re.I)
SKIP = re.compile(r"^(ida eligible|blend|ibrd only|territories|non-small states|small states|country|"
                  r"high|medium|conflict|institutional|and social|severe|core|marginal|political|peace|harmonized|"
                  r"missions|average|\(international\)|official use only|score|fy\d)", re.I)
cc = coco.CountryConverter()


def to_iso(name: str) -> str | None:
    s = re.sub(r"\((pc|PC)\)|\b[a-g]/|\s+\d+(\.\d+)?|\s+(P|PK|Pk|Y)\b", "", name).strip(" .*,")
    key = s.lower()
    if key in ALIASES:
        return ALIASES[key]
    if not s or SKIP.match(s) or len(s) < 4:
        return None
    iso = cc.convert(s, to="ISO3", not_found=None)
    return iso if isinstance(iso, str) and len(iso) == 3 and iso != s else None


def cells(page) -> list[dict]:
    """Agrupa palavras da mesma linha em células (lacuna horizontal > 8 pt separa colunas)."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
    lines: dict[float, list] = {}
    for w in words:
        lines.setdefault(round(w["top"] / 3), []).append(w)
    out = []
    for k in sorted(lines):
        ws = sorted(lines[k], key=lambda w: w["x0"])
        cur = [ws[0]]
        for w in ws[1:]:
            if w["x0"] - cur[-1]["x1"] > 8:
                out.append({"top": k, "x0": cur[0]["x0"], "text": " ".join(x["text"] for x in cur)})
                cur = [w]
            else:
                cur.append(w)
        out.append({"top": k, "x0": cur[0]["x0"], "text": " ".join(x["text"] for x in cur)})
    return out


def header_x(cs, pattern):
    xs = [c["x0"] for c in cs if re.search(pattern, c["text"])]
    return min(xs) if xs else None


def parse_page(page) -> tuple[int, pd.DataFrame]:
    text = page.extract_text() or ""
    fy = int(re.search(r"FY\s?(\d{2})", text.split("\n")[0]).group(1)) + 2000
    cs = cells(page)
    stop_top = min([c["top"] for c in cs if STOP.match(c["text"].strip())] + [1e9])
    # na era LICUS, o texto introdutório vem antes da tabela: começa na linha "FYxx ... Countries/States"
    start_top = -1
    if fy <= 2009:
        start_top = max(c["top"] for c in cs if re.search(r"(LICUS Countries|Fragile States)$", c["text"]))
    rows = []
    x_inst = x_med = x_marg = None
    if fy >= 2020:
        x_inst = header_x(cs, r"INSTITUTIONAL|^HIGH INSTITUTIONAL|^HIGH$") if fy >= 2023 else \
            min(c["x0"] for c in cs if c["text"].startswith("HIGH") and c["x0"] > 300)
        x_med = header_x(cs, r"MEDIUM-INTENSITY") if fy <= 2022 else None
    if fy <= 2009:
        x_marg = header_x([c for c in cs if c["top"] > start_top - 3 and len(c["text"]) < 20], r"^Marginal")
    for c in cs:
        if c["top"] <= start_top or c["top"] >= stop_top:
            continue
        iso = to_iso(c["text"])
        if iso is None:
            continue
        r = {"fy": fy, "iso3": iso, "nome_pdf": c["text"], "fcs_any": 1, "fcs_marginal": 0,
             "fcs_conflict": np.nan, "fcs_institutional": np.nan, "intensidade": ""}
        if fy >= 2020:
            inst = c["x0"] >= x_inst - 20          # dados da coluna começam até ~11 pt antes do cabeçalho
            r["fcs_conflict"], r["fcs_institutional"] = int(not inst), int(inst)
            if fy <= 2022 and not inst:
                r["intensidade"] = "media" if c["x0"] >= x_med - 5 else "alta"
        if fy <= 2009 and x_marg is not None and c["x0"] >= x_marg - 5:
            r["fcs_any"], r["fcs_marginal"] = 0, 1
        rows.append(r)
    return fy, pd.DataFrame(rows)


def parse_fy27() -> pd.DataFrame:
    rows = []
    for f, col in [("fcv_list_FY27.pdf", "fcs_conflict"), ("institutional_fragility_list_FY27.pdf", "fcs_institutional")]:
        t = pdfplumber.open(RAW / f).pages[0].extract_text()
        for iso in re.findall(r"\b([A-Z]{3})$", t, flags=re.M):
            rows.append({"fy": 2027, "iso3": iso, col: 1})
    d = pd.DataFrame(rows).groupby(["fy", "iso3"], as_index=False).max()
    d[["fcs_conflict", "fcs_institutional"]] = d[["fcs_conflict", "fcs_institutional"]].fillna(0).astype(int)
    d["fcs_any"], d["fcs_marginal"], d["intensidade"], d["nome_pdf"] = 1, 0, "", ""
    return d


def thresholds() -> pd.DataFrame:
    """Extrai os limiares do texto das notas; cada valor é conferido contra o trecho citado."""
    hist = " ".join((p.extract_text() or "") for p in pdfplumber.open(RAW / "fcs_historical_note_FY27.pdf").pages)
    fy27 = " ".join((p.extract_text() or "") for p in pdfplumber.open(RAW / "fcv_methodology_summary_FY27.pdf").pages)
    hist, fy27 = re.sub(r"\s+", " ", hist), re.sub(r"\s+", " ", fy27)
    spec = [  # (metodologia, criterio, fonte, valor, unidade, trecho que deve existir no texto)
        ("FY20-26", "alta: mortes absolutas >", "ACLED", 250, "mortes", "absolute number of conflict deaths above 250 according to ACLED"),
        ("FY20-26", "alta: mortes absolutas >", "UCDP", 150, "mortes", "and 150 according to UCDP; and (ii)"),
        ("FY20-26", "alta: mortes per capita >", "ACLED e UCDP", 10, "por 100 mil", "above 10 per 100,000 according to both ACLED and UCDP"),
        ("FY20-26", "media: mortes absolutas >", "ACLED", 250, "mortes", "250 according to ACLED and 150 according to UCDP; and (b) between 2 and 10"),
        ("FY20-26", "media: mortes absolutas >", "UCDP", 150, "mortes", "250 according to ACLED and 150 according to UCDP; and (b) between 2 and 10"),
        ("FY20-26", "media: per capita entre (min)", "ACLED", 2, "por 100 mil", "between 2 and 10 per 100,000 population according to ACLED"),
        ("FY20-26", "media: per capita entre (max)", "ACLED", 10, "por 100 mil", "between 2 and 10 per 100,000 population according to ACLED"),
        ("FY20-26", "media: per capita entre (min)", "UCDP", 1, "por 100 mil", "between 1 and 10 according to UCDP"),
        ("FY20-26", "media: per capita entre (max)", "UCDP", 10, "por 100 mil", "between 1 and 10 according to UCDP"),
        ("FY20-26", "deterioracao rapida: per capita entre (min)", "ACLED", 1, "por 100 mil", "between 1 and 2 (ACLED)"),
        ("FY20-26", "deterioracao rapida: per capita entre (max)", "ACLED", 2, "por 100 mil", "between 1 and 2 (ACLED)"),
        ("FY20-26", "deterioracao rapida: per capita entre (min)", "UCDP", 0.5, "por 100 mil", "0.5 and 1 (UCDP)"),
        ("FY20-26", "deterioracao rapida: per capita entre (max)", "UCDP", 1, "por 100 mil", "0.5 and 1 (UCDP)"),
        ("FY20-26", "deterioracao rapida: mortes mais que dobram no ano", "ACLED e UCDP", 2, "razão", "the number of casualties more than doubling in the last year"),
        ("FY20-26", "fragilidade: CPIA <", "CPIA (menor entre WB, AfDB, ADB)", 3.0, "nota", "that is below 3.0"),
        ("FY20-26", "fragilidade: refugiados por 100 mil >=", "UNHCR", 2000, "por 100 mil", "flight across borders of 2,000 or more per 100,000 population"),
        ("FY27", "unidade afetada: mortes per capita >=", "ACLED (subnacional)", 2, "por 100 mil", "meets or exceeds 2 per 100,000 population"),
        ("FY27", "unidade afetada: mortes >=", "ACLED (subnacional)", 2, "mortes", "the unit records at least 2 fatalities"),
        ("FY27", "populacao em unidades afetadas >=", "ACLED + WorldPop", 20, "%", "At least 20% of the country's population resides in violence-affected"),
        ("FY27", "mortes totais >=", "ACLED", 50, "mortes", "At least 50 total conflict fatalities recorded"),
        ("FY27", "violencia claramente politica > ambigua", "ACLED (tipo de ator)", 1, "razão", "Clearly Political Violence exceed those from Ambiguous Political Violence"),
        ("FY27", "continuidade: sai após n períodos abaixo", "-", 2, "períodos", "two consecutive reference periods"),
    ]
    rows = []
    for met, crit, src, val, unit, quote in spec:
        docs = [(hist, "fcs_historical_note_FY27.pdf")] if met == "FY20-26" else             [(fy27, "fcv_methodology_summary_FY27.pdf"), (hist, "fcs_historical_note_FY27.pdf")]
        found = [n for d, n in docs if quote in d]
        if not found:
            sys.exit(f"PARADA: trecho não encontrado em {[n for _, n in docs]}: {quote!r}")
        name = found[0]
        rows.append({"metodologia": met, "criterio": crit, "fonte_dados": src, "valor": val, "unidade": unit,
                     "trecho_citado": quote, "documento": name, "versao_documento": manifest_version(name)})
    rows.append({"metodologia": "regra propria", "criterio": "eventos concentrados: descarta país-ano se > share das mortes em janela de dias",
                 "fonte_dados": "UCDP GED (datas)", "valor": 0.75, "unidade": "share (janela 3 dias)",
                 "trecho_citado": "NÃO CONSTA das notas publicadas; regra dos autores (decisão do usuário 2026-10-15)",
                 "documento": "-", "versao_documento": "-"})
    return pd.DataFrame(rows)


EXIST_START_FY = {"SSD": 2012}   # Estados criados no período: parcela calculada só nos FY de existência


def trajectories(long: pd.DataFrame, share: float) -> pd.Series:
    fys = sorted(long.fy.unique())
    w = long.pivot_table(index="iso3", columns="fy", values="fcs_any", aggfunc="max").reindex(columns=fys).fillna(0)
    for iso, fy0 in EXIST_START_FY.items():
        if iso in w.index:
            w.loc[iso, [f for f in fys if f < fy0]] = np.nan
    out = {}
    for iso, row in w.iterrows():
        r = row.dropna().to_numpy()
        half = len(r) // 2
        frac, early, late = r.mean(), r[:half].mean(), r[half:].mean()
        if frac >= share:
            out[iso] = "cronico"
        elif late > early and r[-3:].max() == 1 and r[:3].max() == 0:
            out[iso] = "entrada"
        elif early > late and r[:3].max() == 1 and r[-3:].max() == 0:
            out[iso] = "saida"
        else:
            out[iso] = "intermitente"
    return pd.Series(out)


def main() -> None:
    pdf = pdfplumber.open(RAW / "fcs_list_FY06_FY26.pdf")
    parts, counts = [], []
    for page in pdf.pages:
        fy, d = parse_page(page)
        d = d.drop_duplicates(["fy", "iso3"])
        parts.append(d)
        counts.append({"fy": fy, "n_fcs_any": int(d.fcs_any.sum()), "n_marginal": int(d.fcs_marginal.sum()),
                       "n_conflict": int(d.fcs_conflict.sum()) if fy >= 2020 else np.nan,
                       "n_institutional": int(d.fcs_institutional.sum()) if fy >= 2020 else np.nan})
    fy27 = parse_fy27()
    parts.append(fy27)
    counts.append({"fy": 2027, "n_fcs_any": len(fy27), "n_marginal": 0, "n_conflict": int(fy27.fcs_conflict.sum()),
                   "n_institutional": int(fy27.fcs_institutional.sum())})
    long = pd.concat(parts, ignore_index=True).sort_values(["fy", "iso3"])
    long["year"] = long.fy - 1
    fys = sorted(long.fy.unique())
    assert fys == list(range(2006, 2028)), fys
    long.to_csv(TAB / "fcs_list_long.csv", index=False)

    traj = pd.DataFrame({f"traj_{int(s * 100)}": trajectories(long[long.fcs_any == 1], s)
                         for s in [CHRONIC_SHARE, *CHRONIC_ROBUST]})
    n_fy = pd.Series(len(fys), index=traj.index) - pd.Series({k: v - fys[0] for k, v in EXIST_START_FY.items()}).reindex(traj.index).fillna(0)
    traj["share_anos_fcs"] = long[long.fcs_any == 1].groupby("iso3").fy.nunique() / n_fy
    traj = traj.rename(columns={f"traj_{int(CHRONIC_SHARE * 100)}": "trajetoria"}).rename_axis("iso3").reset_index()
    traj.to_csv(TAB / "fcs_trajectories.csv", index=False)
    long.merge(traj[["iso3", "trajetoria"]], on="iso3", how="left").to_parquet(INTERIM / "r2_fcs.parquet", index=False)

    thr = thresholds()
    thr.to_csv(TAB / "fcs_thresholds_used.csv", index=False)
    pd.DataFrame([
        ("marginal FY06–09", "fcs_marginal = 1, fora de fcs_any (lista 'para monitoramento')"),
        ("categorias", "conflito × institucional só a partir de FY20; antes, só fcs_any"),
        ("FY27", "fcs_conflict = Public FCV List; fcs_institutional = Institutional Fragility List"),
        ("ano-calendário", "year = FY − 1"),
        ("existência", "SSD avaliado só a partir de FY12 (independência em julho de 2011); decisão do usuário 2026-10-16"),
        ("trajetória", f"crônico: ≥ {CHRONIC_SHARE:.0%} dos FY06–FY27 na lista; entrada: fora nos 3 primeiros e dentro em algum dos 3 "
                       "últimos, mais anos na 2ª metade; saída: o inverso; demais com algum ano = intermitente; nunca = sem anos"),
    ], columns=["regra", "decisao"]).to_csv(TAB / "fcs_decisions.csv", index=False)

    cnt = pd.DataFrame(counts).sort_values("fy")
    cnt.to_csv(TAB / "fcs_counts_by_fy.csv", index=False)
    print(cnt.to_string(index=False))
    print(f"\nPaíses que já estiveram na lista: {traj.iso3.nunique()}")
    for c in [x for x in traj.columns if x.startswith("traj")]:
        print(f"  {c}: {traj[c].value_counts().to_dict()}")
    print("\nCrônicos (80%):", " ".join(sorted(traj[traj.trajetoria == "cronico"].iso3)))
    print("\nLimiares extraídos:\n" + thr[["metodologia", "criterio", "fonte_dados", "valor", "unidade"]].to_string(index=False))


if __name__ == "__main__":
    main()
