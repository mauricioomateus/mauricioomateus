"""Gera dark_mode.svg e light_mode.svg no estilo 'neofetch' para o perfil do GitHub.

Uso local:   python gerar.py
No Actions:  roda sozinho todo dia (veja .github/workflows/atualizar.yml)
Variável opcional: GITHUB_TOKEN (aumenta o limite da API e libera o GraphQL).
"""
import json, os, time, datetime
from html import escape
from pathlib import Path

import cv2
import numpy as np
import requests
from dateutil.relativedelta import relativedelta

AQUI = Path(__file__).parent
CFG = json.loads((AQUI / "config.json").read_text(encoding="utf-8"))
USER = CFG["usuario_github"]
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN")
API = "https://api.github.com"
HDR = {"Accept": "application/vnd.github+json"}
if TOKEN:
    HDR["Authorization"] = f"Bearer {TOKEN}"

LARG_INFO = 62          # largura (em caracteres) da coluna da direita
FONTE = 15              # fonte do texto, em px
ALT_LINHA = 19          # altura da linha do texto, em px
MARGEM = 24


# ----------------------------------------------------------------- dados
def get(url, **kw):
    for _ in range(6):
        r = requests.get(url, headers=HDR, timeout=30, **kw)
        if r.status_code == 202:          # GitHub ainda calculando estatísticas
            time.sleep(3)
            continue
        r.raise_for_status()
        return r.json()
    return None


def estatisticas():
    s = {"repos": 0, "contrib": 0, "stars": 0, "commits": 0,
         "followers": 0, "add": 0, "del": 0}
    try:
        u = get(f"{API}/users/{USER}")
        s["repos"], s["followers"] = u["public_repos"], u["followers"]

        repos, pag = [], 1
        while True:
            lote = get(f"{API}/users/{USER}/repos", params={"per_page": 100, "page": pag, "type": "owner"})
            repos += lote
            if len(lote) < 100:
                break
            pag += 1
        s["stars"] = sum(r["stargazers_count"] for r in repos)

        busca = get(f"{API}/search/commits", params={"q": f"author:{USER}", "per_page": 1})
        s["commits"] = busca["total_count"] if busca else 0

        # linhas de código adicionadas/removidas por você em cada repo seu
        for r in repos:
            if r.get("fork"):
                continue
            for c in get(f"{API}/repos/{r['full_name']}/stats/contributors") or []:
                if c.get("author") and c["author"]["login"].lower() == USER.lower():
                    s["add"] += sum(w["a"] for w in c["weeks"])
                    s["del"] += sum(w["d"] for w in c["weeks"])

        if TOKEN:   # repositórios em que você contribuiu (só com token)
            q = {"query": "query($l:String!){user(login:$l){repositoriesContributedTo("
                          "includeUserRepositories:true,contributionTypes:[COMMIT,PULL_REQUEST,REPOSITORY]){totalCount}}}",
                 "variables": {"l": USER}}
            g = requests.post(f"{API}/graphql", json=q, headers=HDR, timeout=30).json()
            s["contrib"] = g["data"]["user"]["repositoriesContributedTo"]["totalCount"]
    except Exception as e:
        print("Aviso: não consegui buscar tudo da API:", e)
    return s


def uptime():
    nasc = datetime.date.fromisoformat(CFG["nascimento"])
    d = relativedelta(datetime.date.today(), nasc)
    p = lambda n, u: f"{n} {u}{'s' if n != 1 else ''}"
    return f"{p(d.years, 'year')}, {p(d.months, 'month')}, {p(d.days, 'day')}"


# ----------------------------------------------------------------- ASCII
# do mais "vazio" ao mais "cheio"
RAMPA = " .'`^\",:;Il!i><~+_-?][}{1)(|tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


def carregar_foto():
    if CFG.get("foto") and (AQUI / CFG["foto"]).exists():
        img = cv2.imread(str(AQUI / CFG["foto"]))
    else:
        r = requests.get(f"https://github.com/{USER}.png?size=460", timeout=30)
        r.raise_for_status()
        img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    return img


RAMPA_LUZ = " `.-':_,^=;><+!rc*/z?sLTv)J7(|Fi{C}fI31tlu[neoZ5Yxjya]2ESwqkP6h9d4VpOGbUAKXHm8RD#$Bg0MNWQ%&@"
RAMPA_SIMPLES = " .:-=+*#%@"


def ascii_luz(bgr, largura, limiar=0.30, rampa=RAMPA_LUZ):
    """Estilo 'luz': só as partes iluminadas (rosto, pescoço, contornos) viram texto;
    o que é escuro (fundo e cabelo) some. Claro = caractere denso."""
    H, W = bgr.shape[:2]
    cinza = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cinza = cv2.medianBlur(cinza, 7)                              # tira a textura do fundo
    lo, hi = np.percentile(cinza, 1), np.percentile(cinza, 99)
    norm = np.clip((cinza - lo) / max(1, hi - lo), 0, 1) ** 0.65  # autocontraste + gama
    altura = int(largura * H / W * 0.5)
    g = cv2.resize(norm, (largura, altura), interpolation=cv2.INTER_AREA)
    linhas = []
    for y in range(altura):
        lin = ""
        for x in range(largura):
            fora = ((x + .5 - largura / 2) / (largura / 2)) ** 2 + ((y + .5 - altura / 2) / (altura / 2)) ** 2 > 0.97
            v = g[y, x]
            lin += " " if fora or v < limiar else rampa[min(len(rampa) - 1, int((v - limiar) / (1 - limiar) * len(rampa)))]
        linhas.append(lin.rstrip())
    while linhas and not linhas[0]:
        linhas.pop(0)
    while linhas and not linhas[-1]:
        linhas.pop()
    return linhas


def ascii_art(bgr, largura):
    estilo = CFG.get("estilo_ascii", "luz")
    if estilo == "luz":
        return ascii_luz(bgr, largura, CFG.get("limiar", 0.30))
    if estilo == "luz-simples":
        return ascii_luz(bgr, largura, CFG.get("limiar", 0.35), RAMPA_SIMPLES)
    return ascii_tinta(bgr, largura)


def ascii_tinta(bgr, largura):
    """Converte a foto em linhas de texto.

    - Remove o fundo azulado (pixels saturados e não muito escuros) e mantém só
      a maior área conectada: cabelo, rosto, pescoço e camisa.
    - CLAHE realça o contraste local, para aparecer mecha de cabelo e traço do rosto.
    - Mapeamento 'tinta': escuro = caractere denso (igual ao exemplo do anexo).
    """
    H, W = bgr.shape[:2]
    altura = int(largura * H / W * 0.5)          # caractere é ~2x mais alto que largo

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1] / 255, hsv[..., 2]
    fundo = ((sat > CFG.get("fundo_saturacao", 0.42)) & (val > 16)).astype(np.uint8)
    fundo = cv2.morphologyEx(fundo, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    fundo = cv2.morphologyEx(fundo, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    cinza = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cinza = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(6, 6)).apply(cinza)

    g = cv2.resize(cinza, (largura, altura), interpolation=cv2.INTER_AREA) / 255
    f = cv2.resize(fundo.astype(float), (largura, altura), interpolation=cv2.INTER_AREA)

    yy, xx = np.mgrid[0:altura, 0:largura]
    circulo = ((xx + .5 - largura / 2) / (largura / 2)) ** 2 + ((yy + .5 - altura / 2) / (altura / 2)) ** 2 <= 0.97
    sujeito = ((f < 0.5) & circulo).astype(np.uint8)

    # mantém só a maior mancha (tira pontinhos soltos no fundo)
    n, rotulos, stats, _ = cv2.connectedComponentsWithStats(sujeito, connectivity=8)
    if n > 1:
        maior = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        sujeito = (rotulos == maior)

    linhas = []
    for y in range(altura):
        lin = "".join(RAMPA[min(len(RAMPA) - 1, int((1 - g[y, x]) * len(RAMPA)))] if sujeito[y, x] else " "
                      for x in range(largura))
        linhas.append(lin.rstrip())
    while linhas and not linhas[0]:
        linhas.pop(0)
    while linhas and not linhas[-1]:
        linhas.pop()
    return linhas


# ----------------------------------------------------------------- texto da direita
def linha_chave(chave, valor, largura=LARG_INFO):
    """'. Chave: ........ valor' preenchendo com pontos até a largura."""
    pontos = max(1, largura - len(f". {chave}:") - len(valor) - 2)
    return [("txt", ". "), ("key", chave), ("txt", ":"), ("dot", " " + "." * pontos + " "), ("val", valor)]


def cabecalho(titulo, largura=LARG_INFO):
    return [("txt", f"- {titulo} " + "—" * (largura - len(titulo) - 6) + "-—-")]


def montar_info(s):
    L = [[("txt", CFG["titulo"] + " " + "—" * (LARG_INFO - len(CFG["titulo"]) - 4) + "-—-")]]
    for i, sec in enumerate(CFG["secoes"]):
        if i:
            L.append([("txt", ". ")])
        for k, v in sec:
            L.append(linha_chave(k, v.replace("{uptime}", uptime())))
    L.append([("txt", "")])
    L.append(cabecalho("Contact"))
    for k, v in CFG["contato"]:
        L.append(linha_chave(k, v))
    L.append([("txt", "")])
    L.append(cabecalho("GitHub Stats"))

    def par(k1, v1, k2, v2, contrib=None):
        v1s, v2s = f"{v1:,}", f"{v2:,}"
        extra = f" {{Contributed: {contrib}}}" if contrib else ""
        p1 = max(1, 36 - len(f". {k1}: ") - len(v1s) - len(extra))
        p2 = max(1, LARG_INFO - 43 - len(k2) - len(v2s))
        seg = [("txt", ". "), ("key", k1), ("txt", ":"), ("dot", " " + "." * p1 + " "), ("val", v1s)]
        if extra:
            seg += [("txt", " {"), ("key", "Contributed"), ("txt", ": "), ("val", str(contrib)), ("txt", "}")]
        return seg + [("txt", " | "), ("key", k2), ("txt", ":"), ("dot", " " + "." * p2 + " "), ("val", v2s)]

    L.append(par("Repos", s["repos"], "Stars", s["stars"], s["contrib"]))
    L.append(par("Commits", s["commits"], "Followers", s["followers"]))
    loc = s["add"] - s["del"]
    a, d = f"{s['add']:,}++", f"{s['del']:,}--"
    pts = max(1, LARG_INFO - len(". Lines of Code on GitHub:") - len(f"{loc:,}") - len(a) - len(d) - 9)
    L.append([("txt", ". "), ("key", "Lines of Code on GitHub"), ("txt", ":"),
              ("dot", " " + "." * pts + " "), ("val", f"{loc:,}"),
              ("txt", " ( "), ("add", a), ("txt", ", "), ("del", d), ("txt", " )")])
    return L


# ----------------------------------------------------------------- SVG
TEMAS = {
    "dark":  dict(bg="#161b22", borda="#30363d", txt="#c9d1d9", key="#ffa657", val="#a5d6ff",
                  dot="#616e7f", add="#3fb950", dele="#f85149", art="#c9d1d9"),
    "light": dict(bg="#f6f8fa", borda="#d0d7de", txt="#24292f", key="#953800", val="#0a3069",
                  dot="#c2cfde", add="#1a7f37", dele="#cf222e", art="#24292f"),
}
FONTES = "Consolas, 'DejaVu Sans Mono', 'Courier New', monospace"


def svg(arte, info, tema):
    t = TEMAS[tema]
    alt_info = len(info) * ALT_LINHA
    # a arte ocupa a mesma altura do texto, com fonte menor para ter mais detalhe
    lh_arte = alt_info / len(arte)
    fs_arte = lh_arte / 1.2
    larg_arte = max(len(l) for l in arte) * fs_arte * 0.6
    x_info = MARGEM + larg_arte + 30
    largura = int(x_info + LARG_INFO * FONTE * 0.6 + MARGEM)
    altura = int(alt_info + 2 * MARGEM)
    cls = {"txt": "t", "key": "k", "val": "v", "dot": "d", "add": "a", "del": "r"}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" '
           f'viewBox="0 0 {largura} {altura}" font-family="{FONTES}">',
           f'<style>.t{{fill:{t["txt"]}}}.k{{fill:{t["key"]}}}.v{{fill:{t["val"]}}}.d{{fill:{t["dot"]}}}'
           f'.a{{fill:{t["add"]}}}.r{{fill:{t["dele"]}}}text{{white-space:pre}}</style>',
           f'<rect x=".5" y=".5" width="{largura - 1}" height="{altura - 1}" rx="12" fill="{t["bg"]}" stroke="{t["borda"]}"/>',
           f'<text xml:space="preserve" font-size="{fs_arte:.2f}px" fill="{t["art"]}">']
    y0 = MARGEM + fs_arte
    for i, l in enumerate(arte):
        out.append(f'<tspan x="{MARGEM}" y="{y0 + i * lh_arte:.1f}">{escape(l)}</tspan>')
    out.append("</text>")
    out.append(f'<text xml:space="preserve" font-size="{FONTE}px" class="t">')
    for i, segs in enumerate(info):
        partes = "".join(f'<tspan class="{cls[c]}">{escape(s)}</tspan>' for c, s in segs)
        out.append(f'<tspan x="{x_info:.1f}" y="{MARGEM + FONTE + i * ALT_LINHA}">{partes}</tspan>')
    out.append("</text></svg>")
    return "\n".join(out)


def gerar(s, foto):
    info = montar_info(s)
    H, W = foto.shape[:2]
    x0, y0, x1, y1 = CFG.get("recorte", [0.12, 0.03, 0.88, 0.92])   # foca no personagem
    foto = foto[int(H * y0):int(H * y1), int(W * x0):int(W * x1)]
    arte = ascii_art(foto, CFG.get("largura_ascii", 64))
    for tema in ("dark", "light"):
        (AQUI / f"{tema}_mode.svg").write_text(svg(arte, info, tema), encoding="utf-8")


if __name__ == "__main__":
    s = estatisticas()
    gerar(s, carregar_foto())
    print("Gerado:", s)
