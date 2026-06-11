#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JusEdital — Scraper de Editais
Fontes: Gran Cursos RSS + PCI Concursos notícias
Atualiza: /home/u932293412/domains/jusedital.com.br/public_html/index.html
Agendamento: diariamente às 07h10 (após scrapers individuais)
"""

import urllib.request
import urllib.error
import re
import json
import os
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
INDEX_PATH = '/home/u932293412/domains/jusedital.com.br/public_html/index.html'
LOG_PATH   = '/home/u932293412/domains/jusedital.com.br/public_html/scraper/scraper.log'
DATA_PATH  = '/home/u932293412/domains/jusedital.com.br/public_html/scraper/editais.json'

RSS_SOURCES = [
    {
        'url': 'https://blog.grancursosonline.com.br/feed/',
        'name': 'Gran Cursos Online',
        'title_tag': True,   # usa <title> direto
    },
    {
        'url': 'https://www.estrategiaconcursos.com.br/blog/feed/',
        'name': 'Estratégia Concursos',
        'title_tag': True,
    },
]

# Palavras-chave para classificar área
KW_JURIDICO = [
    'jurídic','juridic','mp ','mpf','mpdft','mpdf','tj ','tjdft','tjsp','tjrj',
    'dpf','delegad','promotor','procurador','defensor','magistratura',
    'advocac','oab','policia federal','pf ','agf','agu','pgr','pgfn',
    'pge','dpe','ministerio publico','ministério público','juiz','juízo',
    'tribunal','cartório','cartorio','escrivania','notarial',
]
KW_PORTUGUES = ['português','linguag','letras','redação','redacao','lingua portuguesa']
KW_STATUS_ABERTO = ['edital','inscriç','inscricao','aberto','aberta','abre','publicado','lança','vagas','banca definida','comissão formada']
KW_STATUS_RESULTADO = ['resultado','gabarito','aprovado','nomeação','nomeacao','convocado','homologado']

# Cursos recomendados por área (links Hotmart / Jurisperitus)
CURSOS = {
    'Jurídico': {
        'nome': 'Português Jurídico — Redação e Oratória',
        'link': 'https://go.hotmart.com/H106188380L',
        'icon': '⚖️'
    },
    'Português': {
        'nome': 'Português Inesquecível',
        'link': 'https://go.hotmart.com/H106034347T',
        'icon': '📝'
    },
    'Geral': {
        'nome': 'Planner do Concurseiro',
        'link': 'https://go.hotmart.com/H106034347T',
        'icon': '📋'
    },
}

# ─── FUNÇÕES AUXILIARES ───────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    linha = f"[{ts}] {msg}"
    print(linha)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(linha + '\n')
    except:
        pass

def fetch(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        }
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.read().decode('utf-8', errors='ignore')

def classify_area(text):
    t = text.lower()
    if any(k in t for k in KW_JURIDICO):
        return 'Jurídico'
    if any(k in t for k in KW_PORTUGUES):
        return 'Português'
    return 'Geral'

def classify_status(text):
    t = text.lower()
    if any(k in t for k in KW_STATUS_RESULTADO):
        return 'Resultado'
    if any(k in t for k in KW_STATUS_ABERTO):
        return 'Inscrições Abertas'
    return 'Previsto'

def parse_date(date_str):
    try:
        dt = parsedate_to_datetime(date_str.strip())
        return dt.strftime('%d/%m/%Y'), dt
    except:
        return date_str[:10], None

def extract_rss_items(content, source_name):
    items = re.split(r'<item>', content)[1:]
    result = []
    for item in items:
        # Título (com ou sem CDATA)
        title_m = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
        link_m  = re.search(r'<link>(https?://[^\s<]+)</link>', item)
        date_m  = re.search(r'<pubDate>([^<]+)</pubDate>', item)
        desc_m  = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
        cats    = re.findall(r'<category>(?:<!\[CDATA\[)?([^\]<]+)(?:\]\]>)?</category>', item)

        if not title_m:
            continue

        title = title_m.group(1).strip()
        title = re.sub(r'<[^>]+>', '', title).strip()
        if len(title) < 10:
            continue

        link    = link_m.group(1).strip() if link_m else ''
        date_raw = date_m.group(1).strip() if date_m else ''
        date_fmt, dt_obj = parse_date(date_raw)

        desc_raw = desc_m.group(1) if desc_m else ''
        desc = re.sub(r'<[^>]+>', '', desc_raw)[:250].strip()
        desc = re.sub(r'\s+', ' ', desc)

        full_text = title + ' ' + ' '.join(cats)
        area   = classify_area(full_text)
        status = classify_status(title)

        result.append({
            'id':      hash(link + title) & 0xFFFFFF,
            'title':   title,
            'link':    link,
            'date':    date_fmt,
            'dt_sort': date_raw,
            'area':    area,
            'status':  status,
            'desc':    desc,
            'source':  source_name,
            'cats':    cats[:4],
        })
    return result

# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def scrape_all():
    all_editais = []
    seen_titles = set()

    for src in RSS_SOURCES:
        try:
            log(f"Buscando: {src['name']} ({src['url']})")
            content = fetch(src['url'])
            items = extract_rss_items(content, src['name'])
            added = 0
            for item in items:
                key = item['title'].lower()[:50]
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_editais.append(item)
                    added += 1
            log(f"  → {added} editais únicos de {src['name']}")
        except Exception as e:
            log(f"  ERRO {src['name']}: {e}")

    # Ordenar por data (mais recentes primeiro)
    def sort_key(e):
        try:
            return parsedate_to_datetime(e['dt_sort'])
        except:
            return datetime(2000, 1, 1, tzinfo=timezone.utc)
    
    all_editais.sort(key=sort_key, reverse=True)
    log(f"Total: {len(all_editais)} editais coletados")
    return all_editais

# ─── GERAÇÃO DE HTML ──────────────────────────────────────────────────────────

STATUS_COLORS = {
    'Inscrições Abertas': ('#00c853', '🟢'),
    'Resultado':          ('#ff9800', '🏆'),
    'Previsto':           ('#c9973a', '📅'),
}

def edital_card_html(edital, idx, free_limit=2):
    area  = edital['area']
    status = edital['status']
    curso = CURSOS.get(area, CURSOS['Geral'])
    color, icon = STATUS_COLORS.get(status, ('#c9973a', '📋'))
    is_locked = idx >= free_limit

    locked_overlay = ''
    if is_locked:
        locked_overlay = '''
        <div class="card-locked-overlay">
            <div class="lock-content">
                <span class="lock-icon">🔒</span>
                <p>Cadastre-se gratuitamente para ver este edital</p>
                <a href="#cadastro" class="btn-unlock">Acessar Grátis</a>
            </div>
        </div>'''

    return f'''<div class="edital-card{' locked' if is_locked else ''}" data-area="{area}" data-status="{status}" style="position:relative">
    {locked_overlay}
    <div class="card-header">
        <span class="status-badge" style="background:{color}20;color:{color};border:1px solid {color}40">{icon} {status}</span>
        <span class="area-badge">{curso['icon']} {area}</span>
        <span class="card-date">📅 {edital['date']}</span>
    </div>
    <h3 class="card-title"><a href="{edital['link']}" target="_blank" rel="noopener">{edital['title']}</a></h3>
    <p class="card-desc">{edital['desc'][:160]}{'...' if len(edital['desc']) > 160 else ''}</p>
    <div class="card-footer">
        <span class="card-source">Fonte: {edital['source']}</span>
        <a href="{curso['link']}" target="_blank" class="btn-curso" rel="noopener">
            📚 {curso['nome']}
        </a>
    </div>
</div>'''

def gerar_html_editais(editais, free_limit=2):
    cards = []
    for i, e in enumerate(editais[:30]):  # máximo 30 cards
        cards.append(edital_card_html(e, i, free_limit))
    return '\n'.join(cards)

def gerar_html_alertas(editais):
    recentes = [e for e in editais if e['status'] == 'Inscrições Abertas'][:5]
    items = []
    for e in recentes:
        items.append(f'<li class="alerta-item"><span class="alerta-dot" style="background:#00c853"></span><a href="{e["link"]}" target="_blank" rel="noopener">{e["title"][:55]}...</a><small>{e["date"]}</small></li>')
    return '<ul class="alertas-list">' + '\n'.join(items) + '</ul>'

def gerar_html_stats(editais):
    total = len(editais)
    novos = len([e for e in editais if e['date'] == datetime.now().strftime('%d/%m/%Y')])
    abertas = len([e for e in editais if e['status'] == 'Inscrições Abertas'])
    return f'''<span class="stat-num" data-stat="total">{total}</span>
<span class="stat-num" data-stat="novos">{novos}</span>
<span class="stat-num" data-stat="abertas">{abertas}</span>
<span class="stat-num" data-stat="fontes">2</span>'''

# ─── ATUALIZAÇÃO DO SITE ──────────────────────────────────────────────────────

def atualizar_site(editais):
    if not os.path.exists(INDEX_PATH):
        log(f"ERRO: index.html não encontrado em {INDEX_PATH}")
        return False

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    ts = datetime.now().strftime('%d/%m/%Y %H:%M')

    # Substituir bloco de editais
    editais_html = gerar_html_editais(editais)
    html = re.sub(
        r'<!-- EDITAIS_INICIO -->.*?<!-- EDITAIS_FIM -->',
        f'<!-- EDITAIS_INICIO -->\n{editais_html}\n<!-- EDITAIS_FIM -->',
        html, flags=re.DOTALL
    )

    # Substituir bloco de alertas
    alertas_html = gerar_html_alertas(editais)
    html = re.sub(
        r'<!-- ALERTAS_INICIO -->.*?<!-- ALERTAS_FIM -->',
        f'<!-- ALERTAS_INICIO -->\n{alertas_html}\n<!-- ALERTAS_FIM -->',
        html, flags=re.DOTALL
    )

    # Atualizar timestamp no rodapé se existir
    html = re.sub(
        r'<!-- ULTIMA_ATUALIZACAO -->.*?<!-- /ULTIMA_ATUALIZACAO -->',
        f'<!-- ULTIMA_ATUALIZACAO -->Atualizado em: {ts}<!-- /ULTIMA_ATUALIZACAO -->',
        html, flags=re.DOTALL
    )

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    log(f"index.html atualizado com {min(len(editais), 30)} editais — {ts}")
    return True

def salvar_json(editais):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    data = {
        'atualizado_em': datetime.now().isoformat(),
        'total': len(editais),
        'editais': editais[:50]
    }
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"JSON salvo: {DATA_PATH}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    log("=" * 50)
    log("JusEdital Scraper — INICIANDO")
    
    editais = scrape_all()
    
    if not editais:
        log("AVISO: Nenhum edital coletado. Abortando atualização do site.")
        sys.exit(1)
    
    salvar_json(editais)
    ok = atualizar_site(editais)
    
    log(f"JusEdital Scraper — {'CONCLUÍDO' if ok else 'ERRO NA ATUALIZAÇÃO'}")
    log("=" * 50)
    sys.exit(0 if ok else 1)
