"""Build the Excel files and the PDF sector report from the stores CSV."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
import csv
import glob
import json
import os
import re
import statistics
from datetime import datetime
from xml.sax.saxutils import escape
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
CARPETA_ENTRADA = 'tiendas_leads'
CARPETA_SALIDA = 'entregables'
VALIDACION = {'muestra': 64, 'A': (28, 47), 'B': (1, 5), 'C': (1, 11)}
ETIQUETA_GRUPO = {'A': 'A - Pixel de Meta instalado', 'B': 'B - Solo ID de Google Ads', 'C': 'C - Sin pixel ni ID detectado'}
COLUMNAS = [('Grupo', 30), ('Nombre', 28), ('Web', 28), ('WhatsApp', 16), ('Chat WhatsApp', 24), ('Telefono', 16), ('Correo', 30), ('Instagram', 20), ('Plataforma', 14), ('Pixel o ads instalado', 16), ('Pixel de Meta', 13), ('ID Google Ads', 18), ('# Productos', 11), ('Precio tipico (COP)', 16), ('Anuncios en Meta (CO)', 18), ('Google Transparencia', 18), ('Nota', 45)]
COLS_MUESTRA = {'Telefono', 'Nota'}
ANALISIS_COLUMNAS = [('Productos reales', 11), ('% agotado', 10), ('Precio mediano (COP)', 15), ('% en oferta', 10), ('Dias sin producto nuevo', 14), ('Nuevos (90 dias)', 11), ('Precio vs sector', 12), ('Hallazgos', 72), ('Oportunidad para la agencia', 48), ('Mensaje de apertura', 80)]
MUESTRA_ANALISIS = {'Productos reales', '% agotado', 'Precio mediano (COP)', '% en oferta', 'Dias sin producto nuevo', 'Hallazgos'}
FORMATO_ANALISIS = {'% agotado': '0"%"', '% en oferta': '0"%"', 'Precio mediano (COP)': '"$"#,##0', 'Precio vs sector': '+0"%";-0"%";0"%"'}

def cargar(ruta):
    with open(ruta, encoding='utf-8-sig', newline='') as f:
        filas = list(csv.DictReader(f))
    for r in filas:
        r['_n'] = int(r['n_productos']) if str(r['n_productos']).isdigit() else 0
        r['_p'] = int(r['precio_tipico']) if str(r['precio_tipico']).isdigit() else 0
        r['_senal'] = r['pixel_meta'] == 'si' or bool(r['google_ads_id'])
    orden = {'A': 0, 'B': 1, 'C': 2}
    filas.sort(key=lambda r: (orden.get(r['grupo'], 3), -r['_n']))
    return filas

def cargar_analisis(ruta_tiendas):
    m = re.match('tiendas_(.+_\\d{4}-\\d{2}-\\d{2})\\.csv', os.path.basename(ruta_tiendas))
    if not m:
        return {}
    ruta = os.path.join(os.path.dirname(ruta_tiendas), f'analisis_{m.group(1)}.csv')
    if not os.path.exists(ruta):
        return {}
    with open(ruta, encoding='utf-8-sig', newline='') as f:
        return {x['dominio']: x for x in csv.DictReader(f) if x.get('estado') == 'ok'}

def _n(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return ''

def _valores_analisis(r, muestra):
    a = r.get('_an')
    if not a:
        return {}
    hall = a['hallazgos'].split('\n')
    if muestra:
        extra = len(hall) - 1
        txt = hall[0] + (f'  (+{extra} hallazgo{('s' if extra > 1 else '')} mas en la base completa)' if extra > 0 else '')
    else:
        txt = a['hallazgos']
    return {'Productos reales': productos_txt(int(_n(a['n_real']) or 0), True), '% agotado': _n(a['pct_agotado']), 'Precio mediano (COP)': _n(a['precio_med']), '% en oferta': _n(a['pct_oferta']), 'Dias sin producto nuevo': _n(a['dias_ultimo']), 'Nuevos (90 dias)': _n(a['nuevos_90']), 'Precio vs sector': _n(a['vs_precio']), 'Hallazgos': txt, 'Oportunidad para la agencia': a['oportunidad'], 'Mensaje de apertura': a['mensaje']}

def _med(vals):
    vals = [v for v in vals if v]
    return int(statistics.median(vals)) if vals else 0

def estadisticas(filas):
    t = len(filas)
    pct = lambda n: round(100 * n / t) if t else 0
    a = sum((r['grupo'] == 'A' for r in filas))
    b = sum((r['grupo'] == 'B' for r in filas))
    c = sum((r['grupo'] == 'C' for r in filas))
    con_aw = sum((bool(r['google_ads_id']) for r in filas))
    s = dict(total=t, a=a, b=b, c=c, con_aw=con_aw, senal=a + b, shopify=sum((r['plataforma'] == 'Shopify' for r in filas)), woo=sum((r['plataforma'] == 'WooCommerce' for r in filas)), wa=sum((bool(r['whatsapp']) for r in filas)), mail=sum((bool(r['email']) for r in filas)), ig=sum((bool(r['instagram']) for r in filas)), c_gtm=sum((r['grupo'] == 'C' and r['gtm'] == 'si' for r in filas)), med_prod=_med([r['_n'] for r in filas]), med_precio=_med([r['_p'] for r in filas]), pct=pct)
    return s

def nombre_limpio(r):
    n = (r.get('nombre') or '').strip()
    stem = re.sub('[^a-z0-9]', '', r['dominio'].lower().split('.')[0])
    partes = [p.strip() for p in re.split('\\s[-|:\\u2013\\u2014]\\s', n) if p.strip()]
    if len(partes) > 1:
        for p in partes:
            if re.sub('[^a-z0-9]', '', p.lower()) in stem or stem in re.sub('[^a-z0-9]', '', p.lower()):
                return p
        return min(partes, key=len)
    return n or stem

def wa_link(num):
    d = re.sub('\\D', '', num or '')
    return f'https://wa.me/{d}' if d else ''

def productos_txt(n, real=False):
    if real:
        return '2000+' if n >= 2000 else n or ''
    return '1000+' if n >= 1000 else n or ''

def _fila_excel(r, relleno=''):
    senal = 'Si' if r['_senal'] else 'No detectado'
    wa = r['whatsapp']
    v = {'Grupo': ETIQUETA_GRUPO.get(r['grupo'], r['grupo']), 'Nombre': nombre_limpio(r), 'Web': r['dominio'], 'WhatsApp': (wa, wa_link(wa)) if wa else '', 'Chat WhatsApp': (wa_link(wa).replace('https://', ''), wa_link(wa)) if wa else '', 'Telefono': r['telefono'], 'Correo': r['email'], 'Instagram': r['instagram'], 'Plataforma': r['plataforma'], 'Pixel o ads instalado': senal, 'Pixel de Meta': 'Si' if r['pixel_meta'] == 'si' else 'No', 'ID Google Ads': r['google_ads_id'] or ('No detectado' if relleno else ''), '# Productos': productos_txt(int(_n(r['_an']['n_real']) or 0), True) if r.get('_an') else productos_txt(r['_n']), 'Precio tipico (COP)': r['_p'] or '', 'Anuncios en Meta (CO)': ('abrir', r['link_meta_co']), 'Google Transparencia': ('abrir', r['link_google_ads']), 'Nota': r.get('nota', '')}
    v.update(_valores_analisis(r, bool(relleno)))
    if relleno:
        for k, val in v.items():
            if val in ('', None):
                v[k] = relleno
        if r.get('plataforma') == 'WooCommerce':
            for k in ('Dias sin producto nuevo', 'Nuevos (90 dias)'):
                if v.get(k) == relleno:
                    v[k] = 'No aplica (WooCommerce)'
    return v

def _hoja_tiendas(ws, filas, muestra=False):
    azul = PatternFill('solid', fgColor='1F3A5F')
    hay_an = any((r.get('_an') for r in filas))
    cols = [c for c in COLUMNAS if not (muestra and c[0] in COLS_MUESTRA)]
    if muestra and hay_an:
        cols = [c for c in cols if c[0] != 'Precio tipico (COP)']
    if hay_an:
        cols += [c for c in ANALISIS_COLUMNAS if not muestra or c[0] in MUESTRA_ANALISIS]
    for i, (nombre, ancho) in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=nombre)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = azul
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.row_dimensions[1].height = 30
    for n, r in enumerate(filas, 2):
        fila = _fila_excel(r, relleno='No disponible' if muestra else '')
        for i, (nombre, _) in enumerate(cols, 1):
            val = fila.get(nombre, 'No disponible' if muestra else '')
            c = ws.cell(row=n, column=i)
            if isinstance(val, tuple):
                c.value, c.hyperlink = val
                c.font = Font(color='0563C1', underline='single')
            else:
                c.value = val
            if nombre == 'Precio tipico (COP)':
                c.number_format = '"$"#,##0'
            if nombre in FORMATO_ANALISIS:
                c.number_format = FORMATO_ANALISIS[nombre]
            if nombre in ('Hallazgos', 'Oportunidad para la agencia', 'Mensaje de apertura'):
                c.alignment = Alignment(wrap_text=True, vertical='top')
            if nombre in ('# Productos',):
                c.alignment = Alignment(horizontal='right')
    if hay_an:
        for n in range(2, len(filas) + 2):
            ws.row_dimensions[n].height = 64 if not muestra else 48
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = f'A1:{get_column_letter(len(cols))}{len(filas) + 1}'

def _hoja_leeme(ws, nicho):
    lineas = [f'Base de tiendas colombianas - {nicho}', '', 'Como leer esta base', '- Las tiendas se encontraron en Google; despues se reviso cada sitio.', "- 'Pixel o ads instalado' significa que se detecto un pixel de Meta o un ID de Google Ads en el sitio. NO significa que hoy esten pagando pauta.", '- En una verificacion manual de 64 tiendas, 28 de 47 con pixel de Meta (60%) tenian anuncios activos en Meta Colombia; sin ninguna senal, 1 de 11. Es una muestra pequena: el pixel marca a quien tiene mas probabilidad de pautar, no garantiza que hoy lo haga.', '- El ID de Google Ads se detecto en el sitio; su contraste con Google Transparencia fue solo parcial.', "- Compruebalo en un toque: usa los links 'Anuncios en Meta' y 'Google Transparencia' de cada fila.", '- Grupo A: ya invierten o invirtieron en pauta -> ofrece mejorar o escalar.', '- Grupo B: usan Google Ads sin pixel de Meta -> ofrece sumar Meta.', '- Grupo C: sin senal detectada -> ofrece empezar a anunciar.', '- La deteccion lee el HTML de la pagina de inicio; un pixel cargado solo desde Google Tag Manager puede no verse.', '- Precio tipico = mediana de precios de la primera pagina del catalogo. Precio mediano = mediana de todo el catalogo: es el que se compara con el sector.', '- Analisis de catalogo (si esta presente): se calcula con el catalogo publico de cada tienda (productos, precios, stock, ofertas, fechas de publicacion). Compara cada tienda contra la mediana de este mismo nicho.', "- 'Hallazgos' son observaciones del catalogo, no del negocio interno: una tienda puede tener stock en otro canal o fechas editadas a mano.", "- 'Mensaje de apertura' es un borrador: reemplaza [tu nombre] y [tu agencia]."]
    for i, l in enumerate(lineas, 1):
        c = ws.cell(row=i, column=1, value=l)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        if i in (1, 3):
            c.font = Font(bold=True, size=13 if i == 1 else 11)
    ws.column_dimensions['A'].width = 110

def hoja_sector(ws, filas, nicho):
    an = [r['_an'] for r in filas if r.get('_an')]
    n = len(an)
    if not n:
        return
    f = lambda k: [_n(a[k]) for a in an if _n(a[k]) != '']
    azul = PatternFill('solid', fgColor='1F3A5F')
    fila = [1]

    def titulo(t, grande=False):
        c = ws.cell(row=fila[0], column=1, value=t)
        c.font = Font(bold=True, size=14 if grande else 12, color='1F3A5F')
        fila[0] += 1

    def linea(*vals, cab=False):
        for i, v in enumerate(vals, 1):
            c = ws.cell(row=fila[0], column=i, value=v)
            if cab:
                c.font = Font(bold=True, color='FFFFFF')
                c.fill = azul
                c.alignment = Alignment(wrap_text=True, horizontal='center')
        fila[0] += 1
    titulo(f'Analisis del sector - {nicho} ({n} tiendas con catalogo leido)', True)
    fila[0] += 1
    titulo('Resumen')
    linea('Precio tipico del sector (mediana de medianas)', int(statistics.median(f('precio_med'))))
    linea('Catalogo tipico (productos)', int(statistics.median(f('n_real'))))
    linea('Tiendas que usan ofertas (precio tachado)', f'{round(100 * sum((x > 0 for x in f('pct_oferta'))) / n)}%')
    linea('Descuento tipico donde hay oferta', f'{int(statistics.median([x for x in f('desc_medio') if x > 0] or [0]))}%')
    linea('Catalogo agotado (mediana)', f'{int(statistics.median(f('pct_agotado')))}%')
    ult = f('dias_ultimo')
    if ult:
        linea('Tiendas con lanzamientos en los ultimos 90 dias', f'{sum((x <= 90 for x in ult))} de {len(ult)}')
        linea('Tiendas sin productos nuevos hace mas de 120 dias', f'{sum((x > 120 for x in ult))} de {len(ult)}')
    fila[0] += 1
    from catalog_analysis import BANDAS_TXT
    tot = [0] * len(BANDAS_TXT)
    for a in an:
        for i, x in enumerate(json.loads(a['bandas_json'] or '[]')):
            tot[i] += x
    suma = sum(tot) or 1
    titulo('Donde se concentran los precios (% de productos del sector)')
    linea('Rango de precio', '% de productos', cab=True)
    for t, x in zip(BANDAS_TXT, tot):
        linea(t, f'{round(100 * x / suma)}%')
    fila[0] += 1
    import unicodedata

    def clave(t):
        t = unicodedata.normalize('NFD', t.lower())
        t = ''.join((ch for ch in t if unicodedata.category(ch) != 'Mn'))
        return re.sub('(es|s)$', '', t.strip())
    cats, nombres = ({}, {})
    for a in an:
        for t, (cnt, med) in json.loads(a['tipos_json'] or '{}').items():
            k = clave(t)
            if cnt > nombres.get(k, ('', 0))[1]:
                nombres[k] = (t, cnt)
            c = cats.setdefault(k, {'t': 0, 'p': 0, 'm': []})
            c['t'] += 1
            c['p'] += cnt
            if med:
                c['m'].append(med)
    titulo('Mapa de categorias: donde hay competencia y donde hay huecos')
    linea('Categoria', 'Tiendas que la venden', 'Productos', 'Precio mediano', 'Competencia', cab=True)
    for k, c in sorted(cats.items(), key=lambda x: (-x[1]['t'], -x[1]['p']))[:18]:
        t = nombres[k][0]
        sh = c['t'] / n
        nivel = 'Alta' if sh >= 0.4 else 'Media' if sh >= 0.15 else 'Baja (hueco)'
        linea(t, c['t'], c['p'], int(statistics.median(c['m'])) if c['m'] else '', nivel)
    fila[0] += 1
    titulo('Como usar este analisis')
    for t in ('Las categorias son las que cada tienda escribe en su catalogo: sirven de orientacion, no como clasificacion exacta.', 'Competencia baja = pocas tiendas la venden: espacio para posicionarse.', 'Competencia alta = mercado saturado: la pauta se gana con oferta y marca.', 'Los hallazgos por tienda estan en la hoja Tiendas, con mensaje de apertura listo para copiar.'):
        ws.cell(row=fila[0], column=1, value='- ' + t)
        fila[0] += 1
    ws.column_dimensions['A'].width = 58
    for col in 'BCDE':
        ws.column_dimensions[col].width = 20
    for row in ws.iter_rows(min_row=1, max_row=fila[0]):
        for c in row:
            if isinstance(c.value, int) and c.column > 1:
                c.number_format = '#,##0'

def hacer_excel(filas, ruta, nicho, con_leeme=True, muestra=False):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Tiendas'
    _hoja_tiendas(ws, filas, muestra)
    if con_leeme:
        if any((r.get('_an') for r in filas)):
            hoja_sector(wb.create_sheet('Analisis sector'), filas, nicho)
        _hoja_leeme(wb.create_sheet('Leeme'), nicho)
    wb.save(ruta)

def elegir_muestra(filas, n=5):

    def completa(r):
        return bool(r['whatsapp'] and r['email'] and r['instagram'])

    def calidad(r):
        oculto = r['grupo'] == 'C' and r['plataforma'] == 'Shopify'
        hall = (r.get('_an') or {}).get('hallazgos', '')
        fuerza = 0 if not hall or 'sin problemas' in hall else len(hall.split('\n'))
        return (not oculto, fuerza, bool(r.get('_an')), completa(r), not r.get('nota'), bool(r['whatsapp']) + bool(r['email']) + bool(r['instagram']), r['_n'])
    por = {g: sorted([r for r in filas if r['grupo'] == g and r['whatsapp']], key=calidad, reverse=True) for g in 'ABC'}
    cupo = {'A': 2, 'B': 1, 'C': 2}
    elegidas = []
    for g in 'ABC':
        elegidas += por[g][:cupo[g]]
    if len(elegidas) < n:
        resto = [r for r in sorted(filas, key=calidad, reverse=True) if r not in elegidas and r['whatsapp']]
        elegidas += resto[:n - len(elegidas)]
    return elegidas[:n]

def _limpio(t):
    return re.sub('[^\\x20-\\x7E\\u00A0-\\u00FF]', '', t or '').strip()

def hallazgos(s, nicho):
    p = s['pct']
    h = [f'{s['a']} de {s['total']} tiendas ({p(s['a'])}%) tienen pixel de Meta instalado.', f'{s['con_aw']} de {s['total']} ({p(s['con_aw'])}%) tienen un ID de Google Ads en el sitio; {s['b']} lo tienen sin pixel de Meta.', f'{s['senal']} de {s['total']} ({p(s['senal'])}%) tienen al menos una de las dos senales; {s['c']} ({p(s['c'])}%) no muestran ninguna.', f'Plataforma: {s['shopify']} en Shopify y {s['woo']} en WooCommerce.', f'Contacto directo: {s['wa']} con WhatsApp ({p(s['wa'])}%), {s['mail']} con correo ({p(s['mail'])}%), {s['ig']} con Instagram ({p(s['ig'])}%).']
    if s['med_prod']:
        h.append(f'Catalogo tipico: {s['med_prod']} productos por tienda (mediana).')
    if s['med_precio']:
        h.append(f'Precio tipico del sector: ${s['med_precio']:,} COP (mediana de medianas).'.replace(',', '.'))
    v = VALIDACION
    pc = lambda x: round(100 * x[0] / x[1])
    h.append(f'Validacion manual (muestra de {v['muestra']} tiendas, Biblioteca de Anuncios de Meta, Colombia): {v['A'][0]} de {v['A'][1]} tiendas con pixel de Meta ({pc(v['A'])}%) tenian anuncios activos; con solo ID de Google Ads, {v['B'][0]} de {v['B'][1]} ({pc(v['B'])}%); sin ninguna senal, {v['C'][0]} de {v['C'][1]} ({pc(v['C'])}%).')
    return h

def hacer_pdf(filas, s, ruta, titulo, nicho):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        print('[!] reportlab no esta instalado: pip install reportlab --break-system-packages (en Termux: pkg install python-pillow primero). PDF omitido.')
        return False
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=ss['Title'], fontSize=20, leading=24, textColor=colors.HexColor('#1F3A5F'))
    h2 = ParagraphStyle('h2', parent=ss['Heading2'], fontSize=13, spaceBefore=12, textColor=colors.HexColor('#1F3A5F'))
    cuerpo = ParagraphStyle('c', parent=ss['BodyText'], fontSize=10.5, leading=15)
    chico = ParagraphStyle('s', parent=ss['BodyText'], fontSize=8.5, leading=11, textColor=colors.HexColor('#555555'))
    celda = ParagraphStyle('t', parent=ss['BodyText'], fontSize=8, leading=10)
    doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm, title=titulo)
    el = [Paragraph(escape(titulo), h1), Paragraph(f'Colombia - datos al {datetime.now().strftime('%d/%m/%Y')} - {s['total']} tiendas analizadas', chico), Spacer(1, 8), Paragraph('Hallazgos', h2)]
    for linea in hallazgos(s, nicho):
        el.append(Paragraph('&bull; ' + escape(linea), cuerpo))
    top = sorted([r for r in filas if r['_senal']], key=lambda r: (-bool(r['whatsapp']), -r['_n']))[:30]
    el.append(Paragraph(f'Top {len(top)} tiendas con senal de publicidad', h2))
    el.append(Paragraph('Primero las que tienen WhatsApp; luego por tamano de catalogo entre las tiendas con pixel de Meta o ID de Google Ads. Un catalogo grande suele indicar mas capacidad de inversion.', chico))
    el.append(Spacer(1, 4))
    datos = [['#', 'Tienda', 'Web', 'Plataforma', 'Senal', 'Productos']]
    for i, r in enumerate(top, 1):
        senal = 'Meta + Google' if r['pixel_meta'] == 'si' and r['google_ads_id'] else 'Meta' if r['pixel_meta'] == 'si' else 'Google'
        datos.append([str(i), Paragraph(escape(_limpio(nombre_limpio(r))[:40]), celda), Paragraph(escape(r['dominio']), celda), r['plataforma'], senal, str(productos_txt(r['_n']) or '-')])
    tabla = Table(datos, colWidths=[0.8 * cm, 5 * cm, 5.2 * cm, 2.5 * cm, 2.4 * cm, 1.8 * cm], repeatRows=1)
    tabla.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3A5F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 8), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F1F4F8')]), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D0D7E2'))]))
    el.append(tabla)
    el.append(Paragraph('Como leer estos datos', h2))
    for t in ('Las tiendas se encontraron en Google y despues se reviso cada sitio para detectar pixel de Meta e ID de Google Ads.', "'Senal' significa pixel o ID instalado en el sitio; no garantiza que hoy paguen pauta. En la verificacion manual, 6 de cada 10 tiendas con pixel de Meta tenian anuncios activos en Colombia, frente a 1 de 11 sin senal (muestra pequena).", 'El ID de Google Ads se detecto en el sitio; su contraste con Google Transparencia fue solo parcial.', 'La deteccion lee el HTML de la pagina de inicio; un pixel cargado solo desde Google Tag Manager puede no verse' + (f' ({s['c_gtm']} tiendas del grupo C tienen GTM).' if s['c_gtm'] else '.'), 'Cada fila del Excel trae un link para comprobar sus anuncios en la Biblioteca de Anuncios de Meta y en Google Transparencia.'):
        el.append(Paragraph('&bull; ' + escape(t), chico))
    doc.build(el)
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv', nargs='?')
    ap.add_argument('--titulo', default='')
    args = ap.parse_args()
    ruta = args.csv
    if not ruta:
        cands = sorted(glob.glob(os.path.join(CARPETA_ENTRADA, 'tiendas_*.csv')))
        if not cands:
            raise SystemExit('No hay CSV en tiendas_leads/. Corre tienda_scraper.py')
        ruta = cands[-1]
    m = re.match('tiendas_(.+)_(\\d{4}-\\d{2}-\\d{2})\\.csv', os.path.basename(ruta))
    nicho = m.group(1) if m else 'nicho'
    fecha = m.group(2) if m else datetime.now().strftime('%Y-%m-%d')
    titulo = args.titulo or f'Sector {nicho.replace('_', ' ')}: tiendas online en Colombia y su inversion en publicidad'
    filas = cargar(ruta)
    an = cargar_analisis(ruta)
    for r in filas:
        if r['dominio'] in an:
            r['_an'] = an[r['dominio']]
    if an:
        print(f'[*] Analisis de catalogo encontrado: {len(an)} tiendas')
    if not filas:
        raise SystemExit('El CSV esta vacio.')
    s = estadisticas(filas)
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    f_full = os.path.join(CARPETA_SALIDA, f'Base_Tiendas_{nicho}_{fecha}.xlsx')
    f_muestra = os.path.join(CARPETA_SALIDA, f'Muestra_{nicho}.xlsx')
    f_pdf = os.path.join(CARPETA_SALIDA, f'Sector_{nicho}_{fecha}.pdf')
    hacer_excel(filas, f_full, nicho)
    hacer_excel(elegir_muestra(filas), f_muestra, nicho, con_leeme=False, muestra=True)
    print(f'[+] {f_full}  ({s['total']} tiendas)')
    print(f'[+] {f_muestra}  (5 filas)')
    if hacer_pdf(filas, s, f_pdf, titulo, nicho):
        print(f'[+] {f_pdf}')
    print(f'\nResumen: {s['a']} grupo A | {s['b']} grupo B | {s['c']} grupo C | {s['wa']} con WhatsApp')
if __name__ == '__main__':
    main()
