import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import unidecode
import requests
import glob
import re
import os

# ————————————— Configuração da página —————————————
st.set_page_config(page_title="Relatório: Trends × Desastres", layout="wide")

# ————————————— Funções auxiliares —————————————
def normalize(txt: str) -> str:
    return unidecode.unidecode(str(txt).strip().lower())

def detect_year_column(df: pd.DataFrame):
    for c in df.columns:
        if re.search(r'ano|year', c, re.I):
            return c
    return None

def detect_category_column(df: pd.DataFrame):
    for c in df.columns:
        if re.search(r'categoria|category', c, re.I):
            return c
    raise KeyError("Nenhuma coluna de categoria encontrada em Trends.")

def detect_region_column(df: pd.DataFrame):
    for c in df.columns:
        if re.search(r'regi.n|uf|estado', c, re.I):
            return c
    raise KeyError("Nenhuma coluna de região/estado encontrada em Trends.")

def detect_date_column(df: pd.DataFrame):
    for c in df.columns:
        if re.search(r'data|date', c, re.I):
            return c
    return None

# ————————————— 1. Carregar e tratar Trends —————————————
trends = pd.read_csv("/merge.csv")

year_col = detect_year_column(trends)
date_col = detect_date_column(trends)
if year_col:
    trends["ano"] = pd.to_numeric(trends[year_col], errors="coerce")
elif date_col:
    trends[date_col] = pd.to_datetime(trends[date_col], dayfirst=True, errors="coerce")
    trends["ano"] = trends[date_col].dt.year
else:
    st.error("Nenhuma coluna de ano/data encontrada em merge.csv.")
    st.stop()

trends = trends.dropna(subset=["ano"])
trends["ano"] = trends["ano"].astype(int)

cat_col = detect_category_column(trends)
reg_col = detect_region_column(trends)
trends = trends.rename(columns={cat_col: "categoria", reg_col: "região"})

trends["estado_norm"] = trends["região"].apply(normalize)
siglas_map = {
    "acre":"AC","alagoas":"AL","amapa":"AP","amazonas":"AM","bahia":"BA",
    "ceara":"CE","distrito federal":"DF","espirito santo":"ES","goias":"GO",
    "maranhao":"MA","mato grosso":"MT","mato grosso do sul":"MS","minas gerais":"MG",
    "para":"PA","paraiba":"PB","parana":"PR","pernambuco":"PE","piaui":"PI",
    "rio de janeiro":"RJ","rio grande do norte":"RN","rio grande do sul":"RS",
    "rondonia":"RO","roraima":"RR","santa catarina":"SC","sao paulo":"SP",
    "sergipe":"SE","tocantins":"TO"
}
trends["uf"] = trends["estado_norm"].map(siglas_map)
trends = trends.dropna(subset=["uf"])

# ————————————— 2. Carregar e tratar S2ID (vários anos) —————————————

des_files = glob.glob("/Desastres_2024.xls")
s2id_list = []
for path in des_files:
    fname = os.path.basename(path)
    ano_file = None
    m = re.match(r"Desastres_(\d{4})", fname)
    if m:
        ano_file = int(m.group(1))

    ext = os.path.splitext(path)[1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"
    df_temp = pd.read_excel(path, engine=engine)

    # normaliza colunas
    df_temp.columns = [normalize(c).replace(" ", "_") for c in df_temp.columns]
    # detectar coluna de ano, data ou usar ano do nome
    year_col2 = detect_year_column(df_temp)
    date_col2 = detect_date_column(df_temp)
    if year_col2:
        df_temp["ano"] = pd.to_numeric(df_temp[year_col2], errors="coerce")
    elif date_col2:
        df_temp[date_col2] = pd.to_datetime(df_temp[date_col2], dayfirst=True, errors="coerce")
        df_temp["ano"] = df_temp[date_col2].dt.year
    elif ano_file is not None:
        df_temp["ano"] = ano_file
    else:
        st.warning(f"Não reconheci o ano em '{fname}'.")
        continue

    df_temp = df_temp.dropna(subset=["ano"])
    df_temp["ano"] = df_temp["ano"].astype(int)

    uf_col = next((c for c in df_temp.columns if re.match(r'uf$|estado', c)), None)
    if not uf_col:
        st.warning(f"Ignorando '{fname}': sem coluna UF/estado.")
        continue

    df_temp = df_temp.rename(columns={uf_col: "uf"})
    df_temp["uf"] = (
        df_temp["uf"].astype(str)
        .apply(normalize)
        .map(lambda v: siglas_map.get(v, v.upper()))
    )

    s2id_list.append(df_temp[["uf", "ano"]])

if not s2id_list:
    st.error("Nenhum dado de Desastres carregado.")
    st.stop()

s2id = pd.concat(s2id_list, ignore_index=True)

# ————————————— 3. Sidebar: filtros dinâmicos —————————————
anos = sorted(trends["ano"].unique())
st.sidebar.header("Selecione os parâmetros")
ano_sel = st.sidebar.selectbox("Ano", anos)

cats_disp = sorted(trends[trends["ano"] == ano_sel]["categoria"].unique())
cat_sel = st.sidebar.multiselect("Categorias de desastre", cats_disp, default=cats_disp)

# aplicar filtros
tr_f = trends[(trends["ano"] == ano_sel) & (trends["categoria"].isin(cat_sel))]
des_f = s2id[s2id["ano"] == ano_sel]

# ————————————— 4. Agregações e merge —————————————
trend_agg = (
    tr_f.groupby("uf")["contagem"].mean().reset_index().rename(columns={"contagem": "buscas_medias"})
)

des_agg = des_f.groupby("uf").size().reset_index(name="num_desastres")

df = pd.merge(trend_agg, des_agg, on="uf", how="left").fillna({"num_desastres": 0})

if df.empty:
    st.error("Sem estados para esses filtros.")
else:
    # ————————————— 5. Narrativa e correlação —————————————
    corr = df["buscas_medias"].corr(df["num_desastres"])
    st.title("Entre Cliques e Catástrofes: O Marketing de Tendências na Percepção dos Desastres Climáticos no Brasil")
    st.markdown(f"- **Ano:** {ano_sel} | **Categorias:** {', '.join(cat_sel)}")
    st.markdown(f"### Pearson r = {corr:.3f}")
    if abs(corr) < 0.3:
        st.markdown("> Correlação fraca")
    elif abs(corr) < 0.7:
        st.markdown("> Correlação moderada")
    else:
        st.markdown("> Correlação forte")

    top_buscas = df.nlargest(3, "buscas_medias")["uf"].tolist()
    top_des    = df.nlargest(3, "num_desastres")["uf"].tolist()
    st.markdown(f"- **Top 3 buscas:** {', '.join(top_buscas)}")
    st.markdown(f"- **Top 3 desastres:** {', '.join(top_des)}")

    # ————————————— 6. Gráficos —————————————
    st.subheader("1. Dispersão: Buscas vs. Desastres")
    fig1 = px.scatter(df, x="buscas_medias", y="num_desastres", text="uf",
                      trendline="ols",
                      labels={"buscas_medias":"Média de buscas","num_desastres":"Nº de desastres"})
    fig1.update_traces(textposition="top center")
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("2. Comparativo por UF")
    fig2 = px.bar(df, x="uf", y=["buscas_medias","num_desastres"],
                  barmode="group",
                  labels={"value":"Valor","variable":"Métrica","uf":"UF"})
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("3. Evolução Anual das Buscas")
    ts = (trends[trends["categoria"].isin(cat_sel)]
          .groupby("ano")["contagem"]
          .mean()
          .reset_index())
    fig3 = px.line(ts, x="ano", y="contagem", markers=True,
                   labels={"contagem":"Média de buscas","ano":"Ano"})
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("4. Mapa – Intensidade de Buscas")
    df_map = df.copy()
    df_map["uf"] = df_map["uf"].astype(str)
    geojson = requests.get(
        "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson"
    ).json()
    for feat in geojson["features"]:
        feat["properties"]["id"] = siglas_map.get(normalize(feat["properties"]["name"]), feat["properties"]["name"])
    centroids = []
    for feat in geojson["features"]:
        uf_id = feat["properties"]["id"]
        coords = feat["geometry"]["coordinates"]
        lons, lats = [], []
        for poly in coords:
            for ring in poly:
                xs, ys = zip(*ring)
                lons += xs; lats += ys
        if lons:
            centroids.append({"uf":uf_id,"lon":sum(lons)/len(lons),"lat":sum(lats)/len(lats)})
    cent_df = pd.DataFrame(centroids); cent_df["uf"]=cent_df["uf"].astype(str)
    map_df = pd.merge(df_map, cent_df, on="uf", how="left")

    fig4 = go.Figure()
    fig4.add_trace(go.Choropleth(
        geojson=geojson, locations=map_df["uf"], z=map_df["buscas_medias"],
        featureidkey="properties.id", colorscale="Reds", marker_line_color="white",
        colorbar_title="Buscas médias"
    ))
    fig4.add_trace(go.Scattergeo(
        lon=map_df["lon"], lat=map_df["lat"], text=map_df["uf"],
        mode="text", textfont=dict(size=10,color="black"), showlegend=False
    ))
    fig4.update_geos(fitbounds="locations", visible=False)
    fig4.update_layout(margin={"r":0,"t":30,"l":0,"b":0}, height=600)
    st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Dados Consolidados por UF")
    st.dataframe(df.reset_index(drop=True))

    st.markdown("""
    **Referências**  
    1. Google Trends API (pytrends)  
    2. S2ID – Sistema Integrado de Informações sobre Desastres (MDR)  
    Desenvolvido por [Jairo Almeida](https://www.github.com/jairoalmeid)
    """)
