"""Gera a ficha do jogador (estatísticas) e as conquistas do perfil em SVG.

Roda no GitHub Actions com o GITHUB_TOKEN padrão (só dados públicos).
Uso: python scripts/gerar_ficha.py <pasta_saida> [--mock dados.json]
"""
import datetime as dt
import json, math, os, sys, urllib.request
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTES = {k: os.path.join(AQUI, "fontes", f"{k}.woff2") for k in ("syne-700", "manrope-400", "manrope-600", "manrope-700")}

# tokens do site da Agência Egon
BG, INK, MUTED = "#07060B", "#F4F0FF", "#B7ADC8"
LINE, VIOLET, VIOLET2 = "#B48CFF", "#8B5CF6", "#C4B5FD"
TONS = ["#C4B5FD", "#8B5CF6", "#6D28D9", "#4C1D95", "#2E1065"]  # linguagens em escala de violeta
PAD = 72

# ------------------------------------------------------------------ dados
QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { name stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
    pullRequests { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

def buscar(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "ficha-do-jogador"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    if resp.get("errors"):
        raise SystemExit(f"Erro da API do GitHub: {resp['errors']}")
    return resp["data"]["user"]

def sequencias(user, hoje):
    dias = [d for w in user["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    dias = [d for d in dias if d["date"] <= hoje.isoformat()]
    maior = atual = corrida = 0
    for d in dias:
        corrida = corrida + 1 if d["contributionCount"] > 0 else 0
        maior = max(maior, corrida)
    # sequência atual: conta para trás; se hoje ainda está zerado, começa de ontem
    i = len(dias) - 1
    if i >= 0 and dias[i]["contributionCount"] == 0:
        i -= 1
    while i >= 0 and dias[i]["contributionCount"] > 0:
        atual += 1; i -= 1
    return atual, maior

def resumir(user, hoje):
    repos = user["repositories"]["nodes"]
    langs = {}
    for r in repos:
        if r.get("name", "").lower() == user["login"].lower():
            continue  # o repositório do próprio perfil (gerador da ficha) não entra nas linguagens
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or "#8B949E"])
            langs[n][0] += e["size"]
    total = sum(v[0] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:5]
    atual, maior = sequencias(user, hoje)
    cc = user["contributionsCollection"]
    return dict(
        login=user["login"],
        contrib=cc["contributionCalendar"]["totalContributions"],
        commits=cc["totalCommitContributions"],
        repos=user["repositories"]["totalCount"],
        estrelas=sum(r["stargazerCount"] for r in repos),
        prs=user["pullRequests"]["totalCount"],
        seq_atual=atual, seq_maior=maior,
        linguagens=[(n, v[0] / total, v[1]) for n, (v) in top],
        n_linguagens=len(langs),
    )

# ------------------------------------------------------------------ texto como contorno
_tt, _glifos = {}, {}

def _fonte(k):
    if k not in _tt:
        _tt[k] = TTFont(FONTES[k])
    return _tt[k]

def largura(texto, k, size, spacing=0):
    f = _fonte(k); cmap = f.getBestCmap(); hmtx = f["hmtx"]
    return sum(hmtx[cmap.get(ord(c), cmap[32])][0] for c in texto) * size / f["head"].unitsPerEm + spacing * max(len(texto) - 1, 0)

def T(texto, k, size, x, y, fill, anchor="start", spacing=0):
    f = _fonte(k); gs = f.getGlyphSet(); cmap = f.getBestCmap(); hmtx = f["hmtx"]
    escala = size / f["head"].unitsPerEm
    w = largura(texto, k, size, spacing)
    x -= w / 2 if anchor == "middle" else (w if anchor == "end" else 0)
    chave = k.replace("-", "")
    usos, cur = [], 0.0
    for ch in texto:
        g = cmap.get(ord(ch)) or cmap[32]
        gid = f"{chave}_{g}".replace(".", "_")
        if gid not in _glifos:
            pen = SVGPathPen(gs, ntos=lambda n: str(round(n))); gs[g].draw(pen); _glifos[gid] = pen.getCommands()
        if _glifos[gid]:
            usos.append(f'<use href="#{gid}" x="{round(cur)}"/>')
        cur += hmtx[g][0] + spacing / escala
    return f'<g transform="translate({x:.1f},{y:.1f}) scale({escala:.5f},{-escala:.5f})" fill="{fill}">{"".join(usos)}</g>'

def documento(W, H, titulo, corpo):
    glifos = "".join(f'<path id="{k}" d="{d}"/>' for k, d in _glifos.items()); _glifos.clear()
    titulo = titulo.replace("&", "&amp;").replace("<", "&lt;")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{titulo}</title>
<defs>{glifos}
<clipPath id="cantos"><rect width="{W}" height="{H}" rx="24"/></clipPath>
<radialGradient id="brilho"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".35"/><stop offset=".68" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
</defs>
<g clip-path="url(#cantos)">
<rect width="{W}" height="{H}" fill="{BG}"/>
<circle cx="{W-100}" cy="40" r="380" fill="url(#brilho)"/>
{corpo}
</g>
<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="23.5" fill="none" stroke="{LINE}" stroke-opacity=".18" stroke-width="1.5"/>
</svg>
'''

def linha(x1, x2, y):
    return f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{LINE}" stroke-opacity=".18" stroke-width="1.5"/>'

def rotulo(t, x, y, anchor="start"):
    return T(t.upper(), "manrope-600", 17, x, y, VIOLET2, anchor, 17 * 0.16)

def dias(n):
    return f"{n} dia" if n == 1 else f"{n} dias"

def fmt(n):
    return f"{n:,}".replace(",", ".")

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

CONQUISTAS = [  # nome, meta, unidade (para o progresso), regra
    ("Primeiro passo", "1º repositório", "repositório", lambda d: (d["repos"], 1)),
    ("Construtor", "5 repositórios", "repositórios", lambda d: (d["repos"], 5)),
    ("Maratonista", "100 commits no ano", "commits no ano", lambda d: (d["commits"], 100)),
    ("Sequência de fogo", "7 dias seguidos", "dias seguidos", lambda d: (d["seq_maior"], 7)),
    ("Poliglota", "4 linguagens", "linguagens", lambda d: (d["n_linguagens"], 4)),
    ("Primeira estrela", "1 estrela", "estrela", lambda d: (d["estrelas"], 1)),
]

def ficha(d, hoje):
    W, H = 1200, 976
    W2 = W - PAD
    b = [rotulo("Atividade no GitHub", PAD, 104),
         T("Código em movimento.", "syne-700", 56, PAD - 2, 180, INK),
         T(f"@{d['login']}  |  atualizado em {hoje.day} {MESES[hoje.month-1]} {hoje.year}", "manrope-400", 17, W2, 104, MUTED, "end")]
    stats = [(fmt(d["contrib"]), "contribuições no último ano"), (fmt(d["commits"]), "commits no último ano"),
             (fmt(d["repos"]), "repositórios públicos"), (fmt(d["estrelas"]), "estrelas recebidas"),
             (dias(d["seq_atual"]), "sequência atual"), (dias(d["seq_maior"]), "maior sequência")]
    for linha_i in range(2):
        y = 232 + linha_i * 140
        b.append(linha(PAD, W2, y))
        for c in range(3):
            v, l = stats[linha_i * 3 + c]
            x = PAD + c * 352
            b.append(T(v, "syne-700", 48, x, y + 66, INK))
            b.append(T(l, "manrope-400", 18, x, y + 100, MUTED))
    # linguagens
    y = 512
    b.append(linha(PAD, W2, y))
    b.append(rotulo("Linguagens", PAD, y + 46))
    bx, bw, by = PAD, W2 - PAD, y + 70
    barras, x = [], bx
    for i, (nome, frac, _cor) in enumerate(d["linguagens"]):
        w = bw * frac
        barras.append(f'<rect x="{x:.1f}" y="{by}" width="{max(w, 2):.1f}" height="12" fill="{TONS[i % len(TONS)]}"/>')
        x += w
    b.append(f'<clipPath id="barra"><rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6"/></clipPath>')
    b.append(f'<g clip-path="url(#barra)"><rect x="{bx}" y="{by}" width="{bw}" height="12" fill="#1A1526"/>{"".join(barras)}</g>')
    lx = PAD
    for i, (nome, frac, _cor) in enumerate(d["linguagens"]):
        txt = f"{nome} {frac*100:.0f}%"
        b.append(f'<circle cx="{lx+6}" cy="{by+44}" r="6" fill="{TONS[i % len(TONS)]}"/>')
        b.append(T(txt, "manrope-400", 18, lx + 20, by + 50, MUTED))
        lx += largura(txt, "manrope-400", 18) + 48
    # conquistas
    y = 662
    feitas = sum(1 for *_, f in CONQUISTAS if f(d)[0] >= f(d)[1])
    b.append(linha(PAD, W2, y))
    b.append(rotulo("Conquistas", PAD, y + 46))
    b.append(T(f"{feitas} de {len(CONQUISTAS)} desbloqueadas", "manrope-400", 17, W2, y + 46, MUTED, "end"))
    cw, ch, gap = (W2 - PAD - 2 * 18) / 3, 84, 18
    for i, (nome, meta, unidade, f) in enumerate(CONQUISTAS):
        atual, alvo = f(d); ok = atual >= alvo
        x = PAD + (i % 3) * (cw + gap); cy = y + 70 + (i // 3) * (ch + gap)
        borda = f'stroke="{VIOLET}" stroke-opacity=".7"' if ok else f'stroke="{LINE}" stroke-opacity=".18"'
        b.append(f'<rect x="{x:.1f}" y="{cy}" width="{cw:.1f}" height="{ch}" rx="18" fill="#FFFFFF" fill-opacity=".02" {borda} stroke-width="1.5"/>')
        ix, iy = x + 42, cy + ch / 2
        if ok:
            b.append(f'<circle cx="{ix}" cy="{iy}" r="18" fill="{VIOLET}"/>')
            b.append(f'<path d="M{ix-7},{iy} l5,5 l9,-10" fill="none" stroke="#FFFFFF" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>')
            legenda = meta
        else:
            b.append(f'<circle cx="{ix}" cy="{iy}" r="18" fill="none" stroke="{LINE}" stroke-opacity=".35" stroke-width="1.5"/>')
            b.append(f'<rect x="{ix-6}" y="{iy-2}" width="12" height="10" rx="2" fill="none" stroke="{MUTED}" stroke-width="1.8"/>'
                     f'<path d="M{ix-3.5},{iy-2} v-3 a3.5,3.5 0 0 1 7,0 v3" fill="none" stroke="{MUTED}" stroke-width="1.8"/>')
            legenda = f"{fmt(min(atual, alvo))} de {fmt(alvo)} {unidade}"
        b.append(T(nome, "manrope-700", 20, x + 76, cy + 38, INK if ok else MUTED))
        b.append(T(legenda, "manrope-400", 16, x + 76, cy + 62, MUTED))
    titulo = (f"Atividade no GitHub de {d['login']}: {d['contrib']} contribuições e {d['commits']} commits nos últimos 12 meses, "
              f"{d['repos']} repositórios públicos, {d['estrelas']} estrelas, sequência atual de {dias(d['seq_atual'])} e maior sequência de {dias(d['seq_maior'])}. "
              f"{feitas} de {len(CONQUISTAS)} conquistas desbloqueadas.")
    return documento(W, H, titulo, "\n".join(b))

# ------------------------------------------------------------------ principal
def main():
    saida = sys.argv[1]
    os.makedirs(saida, exist_ok=True)
    hoje = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
    if "--mock" in sys.argv:
        user = json.load(open(sys.argv[sys.argv.index("--mock") + 1]))
    else:
        user = buscar(os.environ["USUARIO"], os.environ["GITHUB_TOKEN"])
    d = resumir(user, hoje)
    with open(os.path.join(saida, "ficha.svg"), "w", encoding="utf-8") as f:
        f.write(ficha(d, hoje))
    print(json.dumps({k: v for k, v in d.items() if k != "linguagens"}, ensure_ascii=False))

if __name__ == "__main__":
    main()
