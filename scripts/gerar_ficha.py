"""Gera a ficha do jogador (estatísticas) e as conquistas do perfil em SVG.

Roda no GitHub Actions com o GITHUB_TOKEN padrão (só dados públicos).
Uso: python scripts/gerar_ficha.py <pasta_saida> [--mock dados.json]
"""
import datetime as dt
import json, math, os, sys, urllib.request
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTES = {
    "display": os.path.join(AQUI, "fontes", "lilita-one-400.woff2"),
    600: os.path.join(AQUI, "fontes", "nunito-600.woff2"),
    800: os.path.join(AQUI, "fontes", "nunito-800.woff2"),
    900: os.path.join(AQUI, "fontes", "nunito-900.woff2"),
}

TEXTO, TEXTO_2 = "#EEF3FF", "#B6C5F2"
CIANO, AMBAR, ROXO, VERDE, ROSA, AZUL = "#5CE1FF", "#FFB23F", "#A970FF", "#3EE08F", "#FF6FB5", "#4D8DFF"

# ------------------------------------------------------------------ dados
QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
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
    chave = "L" if k == "display" else f"N{k}"
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

def documento(W, H, titulo, corpo, defs_extra=""):
    glifos = "".join(f'<path id="{k}" d="{d}"/>' for k, d in _glifos.items()); _glifos.clear()
    titulo = titulo.replace("&", "&amp;").replace("<", "&lt;")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{titulo}</title>
<defs>{glifos}
<clipPath id="cantos"><rect width="{W}" height="{H}" rx="26"/></clipPath>
<linearGradient id="fundo" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0F1C55"/><stop offset="1" stop-color="#0B1545"/></linearGradient>
<linearGradient id="ouro" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFE08A"/><stop offset="1" stop-color="#F29A1F"/></linearGradient>
<linearGradient id="xp" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{CIANO}"/><stop offset="1" stop-color="{AZUL}"/></linearGradient>
<filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
{defs_extra}
</defs>
<g clip-path="url(#cantos)">
<rect width="{W}" height="{H}" fill="url(#fundo)"/>
{corpo}
</g>
</svg>
'''

# ------------------------------------------------------------------ ícones
def icone(tipo, cor="#FFFFFF", sw=2.2):
    s = f'fill="none" stroke="{cor}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
    return {
        "grade": f'<rect x="-11" y="-11" width="9" height="9" rx="2" {s}/><rect x="2" y="-11" width="9" height="9" rx="2" {s}/><rect x="-11" y="2" width="9" height="9" rx="2" {s}/><rect x="2" y="2" width="9" height="9" rx="2" fill="{cor}" stroke="{cor}" stroke-width="{sw}"/>',
        "commit": f'<circle cx="0" cy="0" r="5" {s}/><line x1="-13" y1="0" x2="-5" y2="0" {s}/><line x1="5" y1="0" x2="13" y2="0" {s}/>',
        "pasta": f'<path d="M-12,-8 h8 l3,3 h13 v14 h-24 Z" {s}/>',
        "estrela": f'<path d="M0,-12 l3.5,7.5 l8,1 l-6,5.5 l1.6,8 l-7.1,-4 l-7.1,4 l1.6,-8 l-6,-5.5 l8,-1 Z" {s}/>',
        "fogo": f'<path d="M0,12 c-7,0 -10,-5 -10,-10 c0,-6 5,-9 6,-15 c3,3 4,6 4,9 c2,-2 3,-4 3,-6 c4,4 7,8 7,12 c0,5 -4,10 -10,10 Z" {s}/>',
        "trofeu": f'<path d="M-7,-11 h14 v7 a7,7 0 0 1 -14,0 Z" {s}/><path d="M-7,-8 h-4 a4,4 0 0 0 4,6 M7,-8 h4 a4,4 0 0 1 -4,6" {s}/><path d="M0,3 v5 M-5,11 h10" {s}/>',
        "cadeado": f'<rect x="-8" y="-2" width="16" height="13" rx="3" {s}/><path d="M-5,-2 v-4 a5,5 0 0 1 10,0 v4" {s}/>',
        "bandeira": f'<path d="M-8,12 V-11 M-8,-10 h14 l-3,5 l3,5 h-14" {s}/>',
        "martelo": f'<path d="M-2,-6 l10,-6 l4,6 l-10,6 Z M2,-1 l-12,12" {s}/>',
        "raio": f'<path d="M2,-12 l-9,14 h7 l-2,10 l9,-14 h-7 Z" {s}/>',
        "linguas": f'<circle cx="0" cy="0" r="11" {s}/><path d="M-11,0 h22 M0,-11 c-5,5 -5,17 0,22 c5,-5 5,-17 0,-22" {s}/>',
    }[tipo]

def nivel_de(xp):
    nivel = int(math.sqrt(xp / 10)) + 1
    base, prox = 10 * (nivel - 1) ** 2, 10 * nivel ** 2
    return nivel, base, prox

def fmt(n):
    return f"{n:,}".replace(",", ".")

# ------------------------------------------------------------------ ficha
def ficha(d):
    W, H = 1200, 500
    b = []
    xp = d["contrib"]
    nivel, base, prox = nivel_de(xp)
    # emblema de nível
    hexa = " ".join(f"{110 + 58*math.cos(math.radians(60*i-90)):.1f},{118 + 58*math.sin(math.radians(60*i-90)):.1f}" for i in range(6))
    b.append(f'<polygon points="{hexa}" fill="{AMBAR}" opacity=".35" filter="url(#glow)"/>')
    b.append(f'<polygon points="{hexa}" fill="url(#ouro)" stroke="#FFF1C2" stroke-width="2.5"/>')
    b.append(T("NÍVEL", 900, 14, 110, 92, "#7A3E00", "middle", 1.5))
    b.append(T(str(nivel), "display", 50, 110, 142, "#5A2C00", "middle"))
    b.append(T("Ficha do jogador", "display", 40, 194, 112, TEXTO))
    b.append(T(f"@{d['login']}", 800, 18, 196, 142, TEXTO_2))
    # barra de XP
    pct = (xp - base) / max(prox - base, 1)
    b.append(f'<rect x="52" y="198" width="510" height="18" rx="9" fill="#1A2A6E"/>')
    b.append(f'<rect x="52" y="198" width="{max(18, 510*pct):.1f}" height="18" rx="9" fill="url(#xp)"/>')
    b.append(T(f"XP {fmt(xp)} de {fmt(prox)}", 800, 15, 52, 240, TEXTO))
    b.append(T("1 XP = 1 contribuição nos últimos 12 meses", 600, 15, 562, 240, TEXTO_2, "end"))
    # atributos
    stats = [("grade", fmt(d["contrib"]), "contribuições/ano", CIANO), ("commit", fmt(d["commits"]), "commits/ano", AZUL),
             ("pasta", fmt(d["repos"]), "repositórios", ROXO), ("estrela", fmt(d["estrelas"]), "estrelas", AMBAR),
             ("fogo", f"{d['seq_atual']}d", "sequência atual", "#FF7A1A"), ("trofeu", f"{d['seq_maior']}d", "maior sequência", VERDE)]
    for i, (ic, val, rot, cor) in enumerate(stats):
        x = 52 + (i % 3) * 172; y = 270 + (i // 3) * 76
        b.append(f'<rect x="{x}" y="{y}" width="160" height="64" rx="14" fill="#14256A" stroke="{cor}" stroke-opacity=".35"/>')
        b.append(f'<g transform="translate({x+26},{y+32})">{icone(ic, cor)}</g>')
        b.append(T(val, "display", 28, x + 50, y + 34, TEXTO))
        b.append(T(rot, 600, 13, x + 50, y + 53, TEXTO_2))
    # linguagens
    b.append(T("Linguagens nos repositórios", 800, 15, 52, 447, TEXTO_2))
    bx, bw, by = 300, 262, 435
    barras, x = [], bx
    for nome, frac, cor in d["linguagens"]:
        w = bw * frac
        barras.append(f'<rect x="{x:.1f}" y="{by}" width="{max(w, 2):.1f}" height="14" fill="{cor}"/>')
        x += w
    b.append(f'<clipPath id="barraL"><rect x="{bx}" y="{by}" width="{bw}" height="14" rx="7"/></clipPath>')
    b.append(f'<g clip-path="url(#barraL)"><rect x="{bx}" y="{by}" width="{bw}" height="14" fill="#1A2A6E"/>{"".join(barras)}</g>')
    lx = 52
    for nome, frac, cor in d["linguagens"][:4]:
        txt = f"{nome} {frac*100:.0f}%"
        b.append(f'<circle cx="{lx+5}" cy="471" r="5" fill="{cor}"/>')
        b.append(T(txt, 600, 13, lx + 15, 476, TEXTO_2))
        lx += largura(txt, 600, 13) + 34
    # divisória e conquistas
    b.append('<line x1="612" y1="50" x2="612" y2="456" stroke="#2A3F8F" stroke-width="2" stroke-dasharray="2 8" stroke-linecap="round"/>')
    b.append(conquistas_bloco(d, 650))
    titulo = (f"Ficha do jogador de {d['login']}: nível {nivel}, {d['contrib']} contribuições e {d['commits']} commits nos últimos 12 meses, "
              f"{d['repos']} repositórios públicos, {d['estrelas']} estrelas, sequência atual de {d['seq_atual']} dias e maior sequência de {d['seq_maior']} dias.")
    return documento(W, H, titulo, "\n".join(b))

CONQUISTAS = [
    ("Primeiro passo", "1º repositório", "bandeira", lambda d: (d["repos"], 1)),
    ("Construtor", "5 repositórios", "martelo", lambda d: (d["repos"], 5)),
    ("Maratonista", "100 commits/ano", "raio", lambda d: (d["commits"], 100)),
    ("Sequência de fogo", "7 dias seguidos", "fogo", lambda d: (d["seq_maior"], 7)),
    ("Poliglota", "4 linguagens", "linguas", lambda d: (d["n_linguagens"], 4)),
    ("Primeira estrela", "1 estrela", "estrela", lambda d: (d["estrelas"], 1)),
]

def conquistas_bloco(d, x0):
    b = []
    feitas = sum(1 for *_, f in CONQUISTAS if f(d)[0] >= f(d)[1])
    b.append(T("Conquistas", "display", 40, x0, 112, TEXTO))
    b.append(T(f"{feitas} de {len(CONQUISTAS)} desbloqueadas", 800, 18, x0, 142, TEXTO_2))
    for i, (nome, meta, ic, f) in enumerate(CONQUISTAS):
        atual, alvo = f(d)
        ok = atual >= alvo
        cx = x0 + 80 + (i % 3) * 170; cy = 216 + (i // 3) * 146
        if ok:
            b.append(f'<circle cx="{cx}" cy="{cy}" r="40" fill="{AMBAR}" opacity=".35" filter="url(#glow)"/>')
            b.append(f'<circle cx="{cx}" cy="{cy}" r="38" fill="url(#ouro)"/>')
            b.append(f'<circle cx="{cx}" cy="{cy}" r="29" fill="#1F3FAE" stroke="#FFF1C2" stroke-width="2"/>')
            b.append(f'<g transform="translate({cx},{cy}) scale(1.25)">{icone(ic, "#FFFFFF")}</g>')
            legenda, cor_leg = meta, TEXTO_2
        else:
            b.append(f'<circle cx="{cx}" cy="{cy}" r="38" fill="#1A2A6E" stroke="#2E418F" stroke-width="2" stroke-dasharray="4 5"/>')
            b.append(f'<g transform="translate({cx},{cy}) scale(1.2)" opacity=".75">{icone("cadeado", "#7F92CF")}</g>')
            legenda, cor_leg = f"{fmt(min(atual, alvo))} de {fmt(alvo)}", "#8EA0D8"
        b.append(T(nome, 800, 16, cx, cy + 62, TEXTO if ok else "#9AABDF", "middle"))
        b.append(T(legenda, 600, 13, cx, cy + 82, cor_leg, "middle"))
    return "\n".join(b)

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
        f.write(ficha(d))
    print(json.dumps({k: v for k, v in d.items() if k != "linguagens"}, ensure_ascii=False))

if __name__ == "__main__":
    main()
