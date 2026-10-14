"""Open the product pages flagged by the WooCommerce API as a customer would and confirm each error one by one, to rule out false positives."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import csv
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
import requests
from catalog_scraper import detectar_errores_woocommerce, activar_wake_lock
HEADERS = {'User-Agent': 'Mozilla/5.0'}
PAUSA_ENTRE_PAGINAS = 1.0
MAX_PAGINAS_API = 10
MAX_PRODUCTOS_POR_DEFECTO = 300
CARPETA_SALIDA = 'catalog_rescue_leads'
os.makedirs(CARPETA_SALIDA, exist_ok=True)
DOMINIOS_POR_DEFECTO = ['https://example.com']
FRASES_COTIZA = ('cotizar', 'cotiza ', 'cotizacion', 'cotización', 'solicitar precio', 'solicita tu cotiz', 'consultar precio', 'consulta el precio', 'precio a consultar', 'precio a convenir', 'pregunta por el precio', 'pídenos tu cotiz', 'pidenos tu cotiz')
RE_PRECIO_NUMERICO = re.compile('[0-9]{1,3}(?:[\\.,][0-9]{3})+|[0-9]{4,}')

def descargar(url, reintentos=2):
    for _ in range(reintentos):
        try:
            r = requests.get(url, timeout=20, headers=HEADERS)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429):
                time.sleep(3)
        except Exception:
            time.sleep(2)
    return None

def traer_catalogo_completo(dominio):
    todos = []
    for pagina in range(1, MAX_PAGINAS_API + 1):
        try:
            r = requests.get(f'{dominio}/wp-json/wc/store/v1/products?per_page=100&page={pagina}', timeout=20, headers=HEADERS)
        except Exception:
            return todos or None
        if r.status_code != 200:
            return todos or None
        try:
            data = r.json()
        except Exception:
            return todos or None
        if not isinstance(data, list) or not data:
            break
        todos.extend(data)
        if len(data) < 100:
            break
        time.sleep(PAUSA_ENTRE_PAGINAS)
    return todos or None

def _clase_del_producto(html, pid):
    m = re.search('id=["\\\']product-%s["\\\'][^>]*class=["\\\']([^"\\\']*)["\\\']' % pid, html)
    if not m:
        m = re.search('class=["\\\']([^"\\\']*)["\\\'][^>]*id=["\\\']product-%s["\\\']' % pid, html)
    return m.group(1) if m else ''

def pagina_dice_agotado(html, pid):
    if 'outofstock' in _clase_del_producto(html, pid):
        return True
    return bool(re.search('class=["\\\']stock out-of-stock["\\\']', html))

def _region(html, marcas, largo):
    for marca in marcas:
        i = html.find(marca)
        if i != -1:
            return html[i:i + largo]
    return None

def estado_imagen(html):
    galeria = _region(html, ('woocommerce-product-gallery',), 6000)
    if galeria is None:
        return None
    if 'woocommerce-placeholder' in galeria or 'gallery__image--placeholder' in galeria or 'placeholder.' in galeria:
        return 'PLACEHOLDER'
    return 'CON_IMAGEN'

def estado_precio(html):
    resumen = _region(html, ('entry-summary', 'class="summary'), 3500)
    if resumen is None:
        return None
    i = resumen.find('woocommerce-Price-amount')
    if i != -1 and RE_PRECIO_NUMERICO.search(resumen[i:i + 400]):
        return 'CON_PRECIO'
    texto = resumen.lower()
    if any((f in texto for f in FRASES_COTIZA)):
        return 'COTIZA'
    return 'SIN_PRECIO'

def verificar_error(tipo, producto, html):
    if tipo in ('titulo_largo', 'html_roto'):
        return ('CONFIRMADO_POR_DATOS', 'se confirma con los datos del catalogo')
    if html is None:
        return ('ERROR_CARGA', 'la pagina del producto no cargo')
    pid = producto.get('id', '')
    if pagina_dice_agotado(html, pid):
        return ('AGOTADO', 'la pagina lo muestra agotado')
    if tipo == 'sin_imagenes':
        estado = estado_imagen(html)
        if estado == 'PLACEHOLDER':
            return ('CONFIRMADO', 'la pagina muestra el icono de imagen vacia')
        if estado == 'CON_IMAGEN':
            return ('TIENE_IMAGEN', 'la API decia sin foto pero la pagina muestra foto')
        return ('NO_CONCLUYENTE', 'no se pudo leer la galeria de esta pagina')
    if tipo == 'precio_faltante':
        estado = estado_precio(html)
        if estado == 'SIN_PRECIO':
            return ('CONFIRMADO', 'la pagina no muestra precio ni pide cotizar')
        if estado == 'COTIZA':
            return ('COTIZA', 'la pagina pide cotizar o consultar el precio')
        if estado == 'CON_PRECIO':
            return ('TIENE_PRECIO', 'la API decia sin precio pero la pagina muestra precio')
        return ('NO_CONCLUYENTE', 'no se pudo leer el resumen de esta pagina')
    return ('NO_CONCLUYENTE', f'tipo de error sin verificacion de pagina: {tipo}')

def precio_en_pesos(producto):
    pr = producto.get('prices') or {}
    try:
        return int(pr.get('price') or 0) / 10 ** int(pr.get('currency_minor_unit', 0))
    except (ValueError, TypeError):
        return 0

def verificar_tienda(dominio, max_productos):
    print(f'\n[*] {dominio}: trayendo el catalogo completo...')
    productos = traer_catalogo_completo(dominio)
    if not productos:
        print('    [!] No respondio como WooCommerce. Nada que verificar.')
        return
    errores = detectar_errores_woocommerce(productos)
    por_permalink = {p.get('permalink'): p for p in productos}
    conteo_api = Counter((e[1] for e in errores))
    print(f'    {len(productos)} productos en el catalogo | la API marca {len(errores)} errores: {dict(conteo_api)}')
    if not errores:
        print('    Ningun error para verificar.')
        return
    a_revisar = errores[:max_productos]
    if len(errores) > max_productos:
        print(f'    (se abren solo los primeros {max_productos} de {len(errores)}; usa --max=NUMERO para cambiarlo)')
    nombre = re.sub('[^a-z0-9]+', '_', dominio.lower().replace('https://', '')).strip('_')
    salida = os.path.join(CARPETA_SALIDA, f'verificacion_{nombre}_{datetime.now().strftime('%Y-%m-%d')}.csv')
    campos = ['tienda', 'tipo_error', 'producto', 'precio', 'link', 'resultado', 'detalle']
    nuevo = not os.path.exists(salida)
    resultados = []
    with open(salida, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        if nuevo:
            writer.writeheader()
        for i, (link, tipo, _detalle) in enumerate(a_revisar, 1):
            producto = por_permalink.get(link, {})
            html = None
            if tipo not in ('titulo_largo', 'html_roto'):
                html = descargar(link)
                time.sleep(PAUSA_ENTRE_PAGINAS)
            resultado, detalle = verificar_error(tipo, producto, html)
            nombre_prod = producto.get('name', '')
            writer.writerow({'tienda': dominio, 'tipo_error': tipo, 'producto': nombre_prod, 'precio': int(precio_en_pesos(producto)), 'link': link, 'resultado': resultado, 'detalle': detalle})
            f.flush()
            resultados.append((tipo, resultado, nombre_prod, link, precio_en_pesos(producto)))
            if i % 10 == 0 or i == len(a_revisar):
                print(f'    [{i}/{len(a_revisar)}] verificados...', flush=True)
    print(f'\n[*] RESUMEN {dominio} (detalle en {salida})')
    for tipo in conteo_api:
        del_tipo = [r for r in resultados if r[0] == tipo]
        if not del_tipo:
            continue
        cuenta = Counter((r[1] for r in del_tipo))
        confirmados = cuenta.get('CONFIRMADO', 0) + cuenta.get('CONFIRMADO_POR_DATOS', 0)
        print(f'    {tipo}: la API marco {conteo_api[tipo]}, se abrieron {len(del_tipo)}')
        for res, n in cuenta.most_common():
            print(f'        {res}: {n}')
        print(f'        -> CONFIRMADOS (piso para el Mensaje 2): {confirmados}')
        confirmados_lista = [r for r in del_tipo if r[1] in ('CONFIRMADO', 'CONFIRMADO_POR_DATOS')]
        ejemplos = sorted(confirmados_lista, key=lambda r: r[4], reverse=True)[:3]
        if ejemplos:
            print('        ejemplos mas caros (gancho del Mensaje 1 y ejemplos del Mensaje 3);')
            print('        abre el primero a mano para comprobar:')
            for _t, _r, nom, lnk, precio in ejemplos:
                print(f'          - {nom[:90]} (${int(precio):,})\n            {lnk}'.replace(',', '.'))

def main():
    args = sys.argv[1:]
    max_productos = MAX_PRODUCTOS_POR_DEFECTO
    dominios = []
    for a in args:
        if a.startswith('--max='):
            try:
                max_productos = int(a.split('=', 1)[1])
            except ValueError:
                print('[!] --max debe ser un numero, por ejemplo --max=150')
                return
        else:
            d = a.strip().rstrip('/')
            if not d.startswith('http'):
                d = 'https://' + d
            dominios.append(d)
    if not dominios:
        dominios = list(DOMINIOS_POR_DEFECTO)
        print(f'[*] Sin dominios escritos: reviso el lote de hoy ({len(dominios)} tiendas). Puede tardar entre 15 y 25 minutos.')
    activar_wake_lock()
    for d in dominios:
        try:
            verificar_tienda(d, max_productos)
        except KeyboardInterrupt:
            print('\n[*] Detenido manualmente. Lo verificado ya quedo guardado en el CSV.')
            return
        except Exception as e:
            print(f'    [!] Error inesperado con {d}: {e}')
    print("\n[*] LISTO. Sube al chat los archivos que empiezan con 'verificacion_' de la carpeta")
    print(f'    {CARPETA_SALIDA}/ (uno por tienda). Con eso armo los mensajes.')
if __name__ == '__main__':
    main()
