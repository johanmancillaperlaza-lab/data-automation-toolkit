"""Download each store's public catalog (Shopify products.json / WooCommerce Store API), compute metrics, compare against the niche and generate findings."""
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
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import requests
try:
    from deliverables import nombre_limpio
except Exception:

    def nombre_limpio(r):
        return r.get('nombre') or r['dominio']
CARPETA = 'tiendas_leads'
MAX_PAGINAS = 8
PAUSA = 1.2
HILOS = 2
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
BANDAS = [(0, 40000), (40000, 80000), (80000, 130000), (130000, 200000), (200000, 10 ** 12)]
BANDAS_TXT = ['Menos de $40.000', '$40.000 a $80.000', '$80.000 a $130.000', '$130.000 a $200.000', 'Mas de $200.000']
AHORA = datetime.now(timezone.utc)

def cop(x):
    return '$' + f'{int(round(x)):,}'.replace(',', '.')

def pct(a, b):
    return round(100 * a / b) if b else 0

def mediana(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else 0

def cuartiles(v):
    v = sorted((x for x in v if x is not None))
    if len(v) >= 4:
        q = statistics.quantiles(v, n=4)
        return (q[0], q[2])
    m = mediana(v)
    return (m, m)

def fecha(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def num(x):
    try:
        return float(str(x).replace(',', ''))
    except (TypeError, ValueError):
        return None

def sin_html(t):
    return re.sub('\\s+', ' ', re.sub('<[^>]+>', ' ', t or '')).strip()

def get_json(url, intentos=3):
    espera = 5
    for _ in range(intentos):
        try:
            r = requests.get(url, headers={'User-Agent': UA, 'Accept': 'application/json'}, timeout=25)
        except requests.RequestException:
            time.sleep(2)
            continue
        if r.status_code == 429:
            time.sleep(espera)
            espera *= 2
            continue
        if r.status_code != 200:
            return (None, f'HTTP {r.status_code}')
        try:
            return (r.json(), '')
        except ValueError:
            return (None, 'respuesta no es JSON (posible anti-bot)')
    return (None, 'sin respuesta (429 o timeout)')

def bajar_shopify(dom):
    prods = []
    for p in range(1, MAX_PAGINAS + 1):
        data, err = get_json(f'https://{dom}/products.json?limit=250&page={p}')
        if data is None:
            if p == 1:
                return (None, err)
            break
        lote = data.get('products') or []
        prods += lote
        if len(lote) < 250:
            break
        time.sleep(PAUSA)
    return ([norm_shopify(x) for x in prods], '')

def norm_shopify(x):
    vs = x.get('variants') or []
    precios = [num(v.get('price')) for v in vs if num(v.get('price'))]
    precio = min(precios) if precios else 0
    desc = 0
    for v in vs:
        pr, cmp_ = (num(v.get('price')), num(v.get('compare_at_price')))
        if pr and cmp_ and (cmp_ > pr):
            desc = max(desc, round(100 * (cmp_ - pr) / cmp_))
    return dict(precio=precio, desc=desc, stock=any((v.get('available') for v in vs)) if vs else False, pub=fecha(x.get('created_at') or x.get('published_at')), imgs=len(x.get('images') or []), desc_len=len(sin_html(x.get('body_html'))), tipo=(x.get('product_type') or '').strip(), variantes=len(vs))

def bajar_woo(dom):
    prods = []
    for p in range(1, MAX_PAGINAS + 1):
        data, err = get_json(f'https://{dom}/wp-json/wc/store/v1/products?per_page=100&page={p}')
        if data is None or not isinstance(data, list):
            if p == 1:
                return (None, err or 'Store API no disponible')
            break
        prods += data
        if len(data) < 100:
            break
        time.sleep(PAUSA)
    return ([norm_woo(x) for x in prods], '')

def norm_woo(x):
    pr = x.get('prices') or {}
    menor = int(pr.get('currency_minor_unit') or 0)
    k = 10 ** menor
    precio = (num(pr.get('price')) or 0) / k
    regular = (num(pr.get('regular_price')) or 0) / k
    desc = round(100 * (regular - precio) / regular) if x.get('on_sale') and regular > precio > 0 else 0
    cats = x.get('categories') or []
    return dict(precio=precio, desc=desc, stock=bool(x.get('is_in_stock', True)), pub=None, imgs=len(x.get('images') or []), desc_len=len(sin_html(x.get('description') or x.get('short_description'))), tipo=(cats[0].get('name') if cats else '').strip(), variantes=max(1, len(x.get('variations') or [])))

def metricas(prods, fuente):
    n = len(prods)
    if not n:
        return {'estado': 'catalogo vacio'}
    precios = [p['precio'] for p in prods if p['precio'] > 0]
    q1, q3 = cuartiles(precios)
    con_desc = [p['desc'] for p in prods if p['desc'] > 0]
    fechas = [p['pub'] for p in prods if p['pub']]
    tipos = {}
    for p in prods:
        if p['tipo']:
            tipos.setdefault(p['tipo'].title(), []).append(p['precio'])
    bandas = [sum((1 for x in precios if a <= x < b)) for a, b in BANDAS]
    m = dict(estado='ok', fuente=fuente, n_real=n, pct_agotado=pct(sum((not p['stock'] for p in prods)), n), precio_med=round(mediana(precios)), precio_p25=round(q1), precio_p75=round(q3), pct_oferta=pct(len(con_desc), n), desc_medio=round(mediana(con_desc)) if con_desc else 0, dias_ultimo=(AHORA - max(fechas)).days if fechas else '', nuevos_30=sum((1 for d in fechas if (AHORA - d).days <= 30)) if fechas else '', nuevos_90=sum((1 for d in fechas if (AHORA - d).days <= 90)) if fechas else '', img_prom=round(sum((p['imgs'] for p in prods)) / n, 1), pct_una_foto=pct(sum((p['imgs'] <= 1 for p in prods)), n), pct_sin_desc=pct(sum((p['desc_len'] < 40 for p in prods)), n), pct_sin_tipo=pct(sum((not p['tipo'] for p in prods)), n), var_prom=round(sum((p['variantes'] for p in prods)) / n, 1), tipos_json=json.dumps({t: [len(v), round(mediana([x for x in v if x]))] for t, v in tipos.items()}, ensure_ascii=False), bandas_json=json.dumps(bandas))
    return m

def analizar_tienda(r):
    dom, plat = (r['dominio'], r['plataforma'])
    if plat == 'Shopify':
        prods, err = bajar_shopify(dom)
        fuente = 'Shopify products.json'
    else:
        prods, err = bajar_woo(dom)
        fuente = 'WooCommerce Store API'
    if prods is None:
        return (dom, {'estado': f'no se pudo leer ({err})'})
    return (dom, metricas(prods, fuente))

def sector(ms):
    ok = [m for m in ms if m.get('estado') == 'ok']
    return dict(n=len(ok), precio=mediana([m['precio_med'] for m in ok]), catalogo=mediana([m['n_real'] for m in ok]), oferta=mediana([m['pct_oferta'] for m in ok]), tiendas_oferta=pct(sum((m['pct_oferta'] > 0 for m in ok)), len(ok)), agotado=mediana([m['pct_agotado'] for m in ok]))
GANCHO = {'A': '[SALES MESSAGE PLACEHOLDER]', 'B': '[SALES MESSAGE PLACEHOLDER]', 'C': '[SALES MESSAGE PLACEHOLDER]'}

def hallazgos(m, sec, r):
    h = []
    n = m['n_real']
    d = m['dias_ultimo']
    if d != '' and d > 120 and (n >= 20):
        h.append((d, f'No publica productos nuevos hace {d} días (según la fecha de publicación de su catálogo).', 'Reactivar con lanzamientos y campañas de novedades.', f'no publicas productos nuevos hace {d} días.'))
    elif m['nuevos_90'] != '' and n >= 50 and (m['nuevos_90'] <= 2):
        k = m['nuevos_90']
        sujeto = 'Ningún producto nuevo' if k == 0 else 'Solo 1 producto nuevo' if k == 1 else f'Solo {k} productos nuevos'
        h.append((60, f'{sujeto} en 90 días con un catálogo de {n}.', 'Plan de lanzamientos para alimentar campañas de novedades.', 'no publicaste productos nuevos en los últimos 90 días.' if k == 0 else f'solo publicaste {k} producto{('s' if k > 1 else '')} nuevo{('s' if k > 1 else '')} en los últimos 90 días.'))
    if m['pct_agotado'] >= 30:
        h.append((m['pct_agotado'] + 20, f'{m['pct_agotado']}% de su catálogo está agotado (mediana del sector: {round(sec['agotado'])}%).', 'Pautar solo lo que tiene stock y reponer lo más vendido; evita gastar anuncios en agotados.', f'el {m['pct_agotado']}% de tu catálogo aparece agotado.'))
    if m['pct_oferta'] == 0 and n >= 30 and (sec['tiendas_oferta'] >= 50):
        h.append((65, f'No usa precio tachado ni ofertas en ningún producto; {sec['tiendas_oferta']}% de las tiendas del sector sí.', 'Campañas de ofertas y fechas clave (Día de la Madre, Black Friday, Navidad).', 'no usas precio tachado ni ofertas, y la mayoría del sector sí.'))
    elif m['pct_oferta'] >= 60:
        h.append((55, f'{m['pct_oferta']}% del catálogo está en oferta (descuento típico {m['desc_medio']}%).', 'Ordenar promociones y proteger margen: ofertas selectivas.', f'el {m['pct_oferta']}% de tu catálogo está en oferta.'))
    vs = round(100 * (m['precio_med'] / sec['precio'] - 1)) if sec['precio'] else 0
    if -100 < vs <= -25:
        h.append((abs(vs), f'Su precio típico ({cop(m['precio_med'])}) está {abs(vs)}% por debajo de la mediana del sector ({cop(sec['precio'])}).', 'Subir ticket con combos y upsell antes de escalar pauta.', f'tu precio típico está {abs(vs)}% por debajo del sector.'))
    elif 25 <= vs <= 100:
        h.append((vs, f'Su precio típico ({cop(m['precio_med'])}) está {vs}% por encima de la mediana del sector ({cop(sec['precio'])}).', 'Justificar el precio con contenido de marca y prueba social.', f'tu precio típico está {vs}% por encima del sector.'))
    if m['pct_sin_desc'] >= 40:
        h.append((m['pct_sin_desc'], f'{m['pct_sin_desc']}% de sus productos casi no tiene descripción.', 'Mejorar fichas de producto: sube la conversión de cada anuncio.', f'el {m['pct_sin_desc']}% de tus productos casi no tiene descripción.'))
    if m['pct_una_foto'] >= 50:
        h.append((m['pct_una_foto'] - 5, f'{m['pct_una_foto']}% de sus productos tiene una sola foto.', 'Producir más fotos y video para anuncios y catálogo dinámico.', f'el {m['pct_una_foto']}% de tus productos tiene una sola foto.'))
    if m['pct_sin_tipo'] >= 50 and n >= 30:
        h.append((45, f'{m['pct_sin_tipo']}% del catálogo no está clasificado por tipo de producto.', 'Ordenar colecciones para campañas por categoría.', f'el {m['pct_sin_tipo']}% de tu catálogo no está clasificado por categoría.'))
    if sec['catalogo'] and n < 0.5 * sec['catalogo']:
        h.append((40, f'Catálogo de {n} productos, menos de la mitad del típico del sector ({round(sec['catalogo'])}).', 'Priorizar los pocos productos fuertes en campañas concentradas.', f'tu catálogo ({n} productos) es menos de la mitad del típico del sector.'))
    h.sort(key=lambda x: -x[0])
    if not h:
        h = [(0, 'Catálogo sin problemas evidentes frente al sector.', 'Escalar lo que funciona: segmentación, remarketing y pruebas creativas.', 'tu catálogo está bien armado frente al sector y hay espacio para escalar.')]
    return h

def mensaje(r, top):
    return '[SALES MESSAGE PLACEHOLDER]'

def enriquecer(tiendas, cache):
    ms = [cache[r['dominio']] for r in tiendas if r['dominio'] in cache]
    sec = sector(ms)
    filas = []
    for r in tiendas:
        m = dict(cache.get(r['dominio'], {'estado': 'sin analizar'}))
        fila = {'dominio': r['dominio'], 'estado': m.get('estado', '')}
        if m.get('estado') == 'ok':
            fila.update({k: v for k, v in m.items() if k != 'estado'})
            fila['vs_precio'] = round(100 * (m['precio_med'] / sec['precio'] - 1)) if sec['precio'] else 0
            fila['vs_catalogo'] = round(100 * (m['n_real'] / sec['catalogo'] - 1)) if sec['catalogo'] else 0
            fila['vs_oferta'] = m['pct_oferta'] - round(sec['oferta'])
            top = hallazgos(m, sec, r)
            fila['hallazgos'] = '\n'.join((f'{i}. {t[1]}' for i, t in enumerate(top[:3], 1)))
            fila['oportunidad'] = top[0][2]
            fila['mensaje'] = mensaje(r, top)
        filas.append(fila)
    return (filas, sec)
CAMPOS = ['dominio', 'estado', 'fuente', 'n_real', 'pct_agotado', 'precio_med', 'precio_p25', 'precio_p75', 'pct_oferta', 'desc_medio', 'dias_ultimo', 'nuevos_30', 'nuevos_90', 'img_prom', 'pct_una_foto', 'pct_sin_desc', 'pct_sin_tipo', 'var_prom', 'vs_precio', 'vs_catalogo', 'vs_oferta', 'hallazgos', 'oportunidad', 'mensaje', 'tipos_json', 'bandas_json']

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv', nargs='?')
    ap.add_argument('--max', type=int, default=0)
    ap.add_argument('--rehacer', action='store_true')
    args = ap.parse_args()
    ruta = args.csv
    if not ruta:
        cands = sorted(glob.glob(os.path.join(CARPETA, 'tiendas_*.csv')))
        if not cands:
            raise SystemExit('No hay CSV en tiendas_leads/.')
        ruta = cands[-1]
    m = re.match('tiendas_(.+)_(\\d{4}-\\d{2}-\\d{2})\\.csv', os.path.basename(ruta))
    nicho, fch = (m.group(1), m.group(2)) if m else ('nicho', AHORA.strftime('%Y-%m-%d'))
    salida = os.path.join(CARPETA, f'analisis_{nicho}_{fch}.csv')
    ruta_cache = os.path.join(CARPETA, 'analisis_cache.json')
    with open(ruta, encoding='utf-8-sig', newline='') as f:
        tiendas = list(csv.DictReader(f))
    cache = {}
    if os.path.exists(ruta_cache) and (not args.rehacer):
        with open(ruta_cache, encoding='utf-8') as f:
            cache = json.load(f)
    pend = [r for r in tiendas if cache.get(r['dominio'], {}).get('estado') != 'ok']
    if args.max:
        pend = pend[:args.max]
    print(f'[*] {len(tiendas)} tiendas | {len(pend)} por analizar ({HILOS} a la vez, con pausas; sin gastar Serper)')
    with ThreadPoolExecutor(max_workers=HILOS) as ex:
        for dom, met in ex.map(analizar_tienda, pend):
            cache[dom] = met
            if met.get('estado') == 'ok':
                print(f'  OK  {dom:34s} {met['n_real']:>5} prod | agotado {met['pct_agotado']}% | oferta {met['pct_oferta']}%')
            else:
                print(f'  --  {dom:34s} {met['estado']}')
            with open(ruta_cache, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)
    filas, sec = enriquecer(tiendas, cache)
    with open(salida, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction='ignore')
        w.writeheader()
        w.writerows(filas)
    ok = sum((1 for x in filas if x['estado'] == 'ok'))
    print(f'\n[*] Listo: {ok} de {len(tiendas)} tiendas analizadas -> {salida}')
    if sec['n']:
        print(f'    Sector: precio tipico {cop(sec['precio'])} | catalogo tipico {round(sec['catalogo'])} | {sec['tiendas_oferta']}% usa ofertas')
    fallos = [x['dominio'] for x in filas if x['estado'] != 'ok']
    if fallos:
        print(f'    Sin analizar ({len(fallos)}): {', '.join(fallos[:8])}{('...' if len(fallos) > 8 else '')}')
        print('    Espera unos minutos y vuelve a correr: reintenta solo esas.')
    print('    Siguiente paso: python entregables.py')
if __name__ == '__main__':
    main()
