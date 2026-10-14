"""Re-check pending leads against the fresh public catalog with false-positive filters and report which ones are still valid."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import csv, sys, os, re, time, glob, datetime
import requests
UA = {'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36'}
TIMEOUT = 20
MIN_ERRORES = 15
PALABRAS_REGALO = ('regalo', 'gratis', 'muestra', 'rifa', 'obsequio', 'cafe', 'café', 'propina', 'dona')
CONSTRUCCION = ('muy pronto', 'próximamente', 'proximamente', 'coming soon', 'en construcción', 'en construccion', 'sitio en mantenimiento', 'launching soon', 'on the horizon')
NO_CO = ('usd', 'united states', ' llc', 'miami', 'new york', 'california', 'texas', '+1 (')
MAYORISTA = ('lo compras en', 'lo venden en', 'tu ganancia', 'precio mayorista', 'hazte revendedor', 'catálogo para revendedores')
COTIZA = ('cotizar', 'cotiza', 'solicitar cotización', 'solicitar cotizacion', 'consultar precio', 'pide tu cotización', 'pide tu cotizacion', 'precio a consultar', 'contáctanos para el precio')
DEFECTO = ['optica-medellin.com', 'novamedicasas.com', 'pcware.com.co', 'pcgamermedellin.com', 'motozonecolombia.com', 'viajeserviexpress.com', 'orangemedicalstore.com', 'global-geosystems.com', 'supraindustrial.com.co', 'geoinstrumentoscol.com']
YA_VISTOS = ''

def dom(u):
    return re.sub('^https?://(www\\.)?', '', u.strip()).strip('/').lower()

def get(url, **kw):
    try:
        return requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    except Exception:
        return None

def html_roto(txt):
    return bool(txt) and txt.count('<') != txt.count('>')

def analizar_shopify(base):
    prods = []
    for p in (1, 2):
        r = get(f'{base}/products.json?limit=250&page={p}')
        if r is None or r.status_code != 200:
            if p == 1:
                return None
            break
        try:
            lote = r.json().get('products', [])
        except Exception:
            return None
        prods += lote
        if len(lote) < 250:
            break
    if not prods:
        return None
    err = []
    for x in prods:
        vs = x.get('variants', [])
        disp = any((v.get('available') for v in vs))
        titulo = x.get('title') or ''
        handle = x.get('handle') or ''
        link = f'{base}/products/{handle}'
        regalo = any((w in (titulo + handle).lower() for w in PALABRAS_REGALO))
        if not x.get('images') and disp:
            err.append(('sin_imagenes', link, titulo))
        if len(titulo) > 150:
            err.append(('titulo_largo', link, titulo))
        if html_roto(x.get('body_html') or ''):
            err.append(('html_roto', link, titulo))
        if not regalo:
            for v in vs:
                try:
                    pr = float(v.get('price') or 0)
                except Exception:
                    pr = 0
                if pr == 0 and v.get('available'):
                    err.append(('precio_faltante', link, titulo))
                    break
    return (len(prods), err)

def analizar_woo(base):
    prods = []
    for p in (1, 2):
        r = get(f'{base}/wp-json/wc/store/v1/products?per_page=100&page={p}')
        if r is None or r.status_code != 200:
            if p == 1:
                return None
            break
        try:
            lote = r.json()
        except Exception:
            return None
        if not isinstance(lote, list):
            return None
        prods += lote
        if len(lote) < 100:
            break
    if not prods:
        return None
    err = []
    for x in prods:
        titulo = re.sub('<[^>]+>', '', x.get('name') or '')
        link = x.get('permalink') or base
        stock = x.get('is_in_stock', True)
        regalo = any((w in (titulo + link).lower() for w in PALABRAS_REGALO))
        if not x.get('images') and stock:
            err.append(('sin_imagenes', link, titulo))
        if len(titulo) > 150:
            err.append(('titulo_largo', link, titulo))
        if html_roto(x.get('description') or ''):
            err.append(('html_roto', link, titulo))
        precio = str((x.get('prices') or {}).get('price') or '').strip()
        if precio in ('', '0') and stock and (not regalo):
            err.append(('precio_faltante', link, titulo))
    return (len(prods), err)

def revisar_home(base):
    r = get(base, allow_redirects=True)
    if r is None or r.status_code >= 400:
        return {'carga': False, 'constr': False, 'mayor': False, 'no_co': False, 'cotiza': False}
    t = r.text.lower()
    return {'carga': True, 'constr': any((w in t for w in CONSTRUCCION)), 'mayor': any((w in t for w in MAYORISTA)), 'no_co': any((w in t for w in NO_CO)), 'cotiza': any((w in t for w in COTIZA))}

def prefijo_raro(num):
    d = re.sub('\\D', '', num or '')
    d = d[-10:]
    if len(d) != 10 or d[0] != '3' or len(set(d)) == 1 or d.endswith('0000000'):
        return True
    p = d[:3]
    return not (p[:2] in ('30', '31', '32') or p in ('350', '351'))

def cargar_whatsapps():
    w = {}
    for f in glob.glob('leads_*.csv') + glob.glob('catalog_rescue_leads/leads_*.csv'):
        try:
            for x in csv.DictReader(open(f, encoding='utf-8-sig')):
                w[dom(x['tienda'])] = (x.get('whatsapp', ''), x.get('plataforma', ''), x.get('tiene_pixel_ads', ''))
        except Exception:
            pass
    return w

def lista_todo08():
    out = []
    try:
        for x in csv.DictReader(open('leads_2026-09-08.csv', encoding='utf-8-sig')):
            d = dom(x['tienda'])
            if int(x['errores_encontrados']) >= MIN_ERRORES and d not in YA_VISTOS:
                out.append(d)
    except Exception as e:
        print('No pude leer leads_2026-09-08.csv:', e)
    return out

def main():
    args = sys.argv[1:]
    if '--todo08' in args:
        dominios = lista_todo08()
    elif args:
        dominios = [dom(a) for a in args]
    else:
        dominios = DEFECTO
    if os.system('command -v termux-wake-lock >/dev/null 2>&1') == 0:
        os.system('termux-wake-lock')
    w = cargar_whatsapps()
    hoy = datetime.date.today().isoformat()
    salida = f'reverificacion_pendientes_{hoy}.csv'
    cols = ['dominio', 'plataforma', 'estado', 'motivo', 'productos_analizados', 'errores', 'sin_precio', 'sin_imagenes', 'titulo_largo', 'html_roto', 'pct_sin_precio', 'pixel_ads', 'whatsapp', 'aviso_whatsapp', 'evidencia_1', 'evidencia_2', 'evidencia_3', 'evidencia_4', 'evidencia_5']
    filas = []
    print(f'Reverificando {len(dominios)} tiendas...\n')
    for i, d in enumerate(dominios, 1):
        base = 'https://' + d
        wa, plat_csv, pixel = w.get(d, ('', '', ''))
        home = revisar_home(base)
        res = None
        plat = ''
        if plat_csv != 'WooCommerce':
            res = analizar_shopify(base)
            plat = 'Shopify' if res else ''
        if res is None:
            res = analizar_woo(base)
            plat = 'WooCommerce' if res else ''
        fila = dict.fromkeys(cols, '')
        fila.update(dominio=d, plataforma=plat, whatsapp=wa, pixel_ads=pixel, aviso_whatsapp='revisar numero (prefijo o relleno)' if prefijo_raro(wa) else '')
        if res is None:
            fila.update(estado='NO_RESPONDE', motivo='no se pudo leer el catalogo publico; reintentar')
        else:
            n, err = res
            cnt = {t: sum((1 for e in err if e[0] == t)) for t in ('precio_faltante', 'sin_imagenes', 'titulo_largo', 'html_roto')}
            total = len(err)
            pct = round(100 * cnt['precio_faltante'] / n) if n else 0
            principal = max(cnt, key=cnt.get) if total else ''
            ev = [e[1] for e in err if e[0] == principal][:5]
            estado, motivo = ('CONTACTABLE', 'sigue con el error real')
            if not home['carga']:
                estado, motivo = ('DESCARTAR', 'el sitio publico no carga')
            elif home['constr']:
                estado, motivo = ('DESCARTAR', 'sitio en construccion')
            elif total < 10:
                estado, motivo = ('DESCARTAR', f'solo {total} errores (menos de 10)')
            elif total < MIN_ERRORES:
                estado, motivo = ('REVISAR', f'{total} errores, franja 10 a 14: caso por caso')
            elif principal == 'precio_faltante' and (pct >= 80 or home['cotiza']):
                estado, motivo = ('REVISAR', f'{pct}% sin precio o la pagina habla de cotizar: posible cotiza por WhatsApp')
            elif home['mayor']:
                estado, motivo = ('REVISAR', 'posible tienda mayorista/reventa')
            elif home['no_co']:
                estado, motivo = ('REVISAR', 'posible mercado no colombiano (puede ser falso, mirar a mano)')
            elif n >= 20 and total >= n:
                estado, motivo = ('REVISAR', '100% parejo, sospechoso, verificar a mano')
            fila.update(estado=estado, motivo=motivo, productos_analizados=n, errores=total, sin_precio=cnt['precio_faltante'], sin_imagenes=cnt['sin_imagenes'], titulo_largo=cnt['titulo_largo'], html_roto=cnt['html_roto'], pct_sin_precio=pct)
            for k, l in enumerate(ev):
                fila[f'evidencia_{k + 1}'] = l
            fila['_principal'] = principal
        filas.append(fila)
        print(f'[{i}/{len(dominios)}] {d}: {fila['estado']} ({fila['motivo']})')
        time.sleep(1)
        with open(salida, 'w', newline='', encoding='utf-8-sig') as f:
            wr = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
            wr.writeheader()
            wr.writerows(filas)
    print('\n===== RESUMEN =====')
    for est in ('CONTACTABLE', 'REVISAR', 'DESCARTAR', 'NO_RESPONDE'):
        g = [f for f in filas if f['estado'] == est]
        print(f'\n{est}: {len(g)}')
        for f in g:
            extra = f' | {f['errores']} errores ({f.get('_principal', '')})' if f['errores'] != '' else ''
            aviso = f' | OJO: {f['aviso_whatsapp']}' if f['aviso_whatsapp'] else ''
            print(f'  - {f['dominio']}{extra}{aviso}')
            if est in ('CONTACTABLE', 'REVISAR') and f['evidencia_1']:
                print(f'    {f['evidencia_1']}')
    print(f'\nArchivo completo: {salida}')
    os.system('command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock')
if __name__ == '__main__':
    main()
