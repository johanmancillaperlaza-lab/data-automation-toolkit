"""Find Shopify and WooCommerce stores by niche (Serper), read each public catalog (products.json / WooCommerce Store API) and flag real catalog errors, ignoring blocks, 403s and verification pages."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
import csv
import re
import time
import os
import shutil
import subprocess
import atexit
from datetime import datetime
from collections import Counter
SERPER_API_KEYS = [k.strip() for k in os.getenv('SERPER_API_KEYS', 'YOUR_SERPER_API_KEY').split(',') if k.strip()]
_current_key_index = 0

def _get_current_key():
    global _current_key_index
    return SERPER_API_KEYS[_current_key_index % len(SERPER_API_KEYS)]

def _rotate_key():
    global _current_key_index
    _current_key_index += 1
    print('   Rotando a Serper key #' + str(_current_key_index % len(SERPER_API_KEYS) + 1), flush=True)
NICHOS = ['ropa mujer', 'ropa hombre', 'ropa oversize', 'ropa tallas grandes', 'zapatos', 'tenis originales', 'botas', 'sandalias', 'accesorios moda', 'gafas de sol', 'relojes', 'bolsos y carteras', 'billeteras', 'belleza y cosmeticos', 'productos capilares', 'maquillaje', 'skincare', 'perfumes', 'productos de barberia', 'deportes y fitness', 'ropa deportiva', 'articulos de gym', 'suplementos deportivos', 'bicicletas y accesorios', 'articulos de pesca', 'camping y outdoor', 'hogar y decoracion', 'cocina y electrodomesticos', 'organizacion del hogar', 'ropa de cama', 'iluminacion hogar', 'tecnologia y electronica', 'audifonos', 'accesorios celular', 'gaming', 'computadores y perifericos', 'smartwatch', 'mascotas', 'bebes y ninos', 'juguetes', 'ropa de bebe', 'articulos escolares', 'joyeria y bisuteria', 'suplementos', 'vitaminas', 'muebles', 'colchones', 'papeleria', 'libros', 'vinos y licores', 'decoracion navideña', 'herramientas y ferreteria', 'repuestos de moto', 'accesorios de carro', 'instrumentos musicales', 'articulos de oficina', 'plantas y jardineria', 'agencia de turismo', 'tours y excursiones', 'turismo receptivo', 'paquetes turisticos', 'distribuidor ferretero mayorista', 'repuestos maquinaria agricola', 'equipos medicos y dotacion hospitalaria', 'insumos odontologicos mayorista', 'materiales de construccion mayorista', 'repuestos para tractocamiones', 'maquinaria pesada y montacargas', 'plantas electricas industriales', 'equipos de topografia', 'dotacion industrial epp', 'distribuidor mayorista veterinario', 'insumos de laboratorio clinico', 'repuestos industriales colombia', 'equipos de soldadura mayorista']
RESULTADOS_POR_NICHO = 100
MINIMO_ERRORES_PARA_LEAD = 10
PLANTILLAS_QUERY = ['tienda online Colombia comprar {nicho} whatsapp', 'comprar {nicho} online Colombia envio gratis', 'tienda virtual {nicho} Colombia contraentrega', 'tienda online Bogota comprar {nicho} whatsapp', 'tienda online Medellin comprar {nicho} whatsapp', 'tienda online Cali comprar {nicho} whatsapp', 'tienda online Barranquilla comprar {nicho} whatsapp', 'tienda online Cartagena comprar {nicho} whatsapp', 'tienda online Bucaramanga comprar {nicho} whatsapp', 'tienda online Pereira comprar {nicho} whatsapp']
DOMINIOS_IGNORADOS = ('instagram.com', 'facebook.com', 'wa.me', 'tiktok.com', 'youtube.com', 'twitter.com', 'x.com', 'linkedin.com', 'pinterest.com', 'mercadolibre.com.co', 'amazon.com', 'wikipedia.org')
PALABRAS_SITIO_EN_CONSTRUCCION = ('muy pronto', 'proximamente', 'próximamente', 'en construccion', 'en construcción', 'coming soon', 'under construction', 'sitio en mantenimiento', 'volveremos pronto', 'estamos trabajando en')
PALABRAS_MAYORISTA = ('lo compras en', 'lo venden en', 'tu ganancia', 'precio mayorista', 'precio de distribuidor', 'hazte revendedor', 'se dropshipper', 'catalogo para revendedores', 'catálogo para revendedores')
PALABRAS_MERCADO_NO_CO = ('usd', 'united states', ' llc', 'miami', ' fl ', 'new york', 'california', 'texas', '+1 (', '+1(')
CARPETA_SALIDA = 'catalog_rescue_leads'
os.makedirs(CARPETA_SALIDA, exist_ok=True)
SALIDA_CSV = os.path.join(CARPETA_SALIDA, f'leads_{datetime.now().strftime('%Y-%m-%d')}.csv')
SALIDA_DETALLE_CSV = os.path.join(CARPETA_SALIDA, f'errores_detalle_{datetime.now().strftime('%Y-%m-%d')}.csv')
DOMINIOS_YA_VISTOS_TXT = os.path.join(CARPETA_SALIDA, 'dominios_procesados.txt')

def desactivar_wake_lock():
    try:
        subprocess.run(['termux-wake-unlock'], timeout=10)
        print('[*] Wake lock liberado')
    except Exception:
        pass

def activar_wake_lock():
    if shutil.which('termux-wake-lock') is None:
        print('[!] termux-wake-lock no esta disponible aqui (¿Pydroid?). Deja la pantalla encendida para que no se corte la corrida.')
        return
    try:
        subprocess.run(['termux-wake-lock'], check=True, timeout=10)
        atexit.register(desactivar_wake_lock)
        print('[*] Wake lock activado -- el celular no dormira el script')
    except Exception as e:
        print(f'[!] No pude activar el wake lock ({e}). Deja la pantalla encendida para que no se corte la corrida.')
NICHOS_POR_CORRIDA = 15
ARCHIVO_POSICION_CICLO = os.path.join(CARPETA_SALIDA, 'posicion_ciclo_nichos.txt')

def obtener_nichos_de_hoy():
    if os.path.exists(ARCHIVO_POSICION_CICLO):
        with open(ARCHIVO_POSICION_CICLO, encoding='utf-8') as f:
            posicion = int(f.read().strip() or 0)
    else:
        posicion = 0
    total = len(NICHOS)
    fin = posicion + NICHOS_POR_CORRIDA
    if fin <= total:
        nichos_hoy = NICHOS[posicion:fin]
    else:
        nichos_hoy = NICHOS[posicion:total] + NICHOS[0:fin - total]
    nueva_posicion = fin % total
    with open(ARCHIVO_POSICION_CICLO, 'w', encoding='utf-8') as f:
        f.write(str(nueva_posicion))
    vueltas_para_completar_ciclo = -(-total // NICHOS_POR_CORRIDA)
    return (nichos_hoy, posicion, vueltas_para_completar_ciclo)

def _una_busqueda_serper(query, num_reintentos=3):
    for intento in range(num_reintentos):
        try:
            r = requests.post('https://google.serper.dev/search', headers={'X-API-KEY': _get_current_key(), 'Content-Type': 'application/json'}, json={'q': query, 'num': RESULTADOS_POR_NICHO}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                dominios = []
                for item in data.get('organic', []):
                    link = item.get('link', '')
                    if link:
                        dominio = re.sub('^https?://(www\\.)?', '', link).split('/')[0]
                        dominios.append(f'https://{dominio}')
                return list(set(dominios))
            elif r.status_code in (401, 402, 403, 429):
                _rotate_key()
                time.sleep(2)
                continue
            else:
                time.sleep(2 ** intento)
        except Exception as e:
            print(f"    [!] Error en busqueda '{query}': {e}")
            time.sleep(2 ** intento)
    return []

def buscar_tiendas_por_nicho(nicho):
    dominios = set()
    for plantilla in PLANTILLAS_QUERY:
        query = plantilla.format(nicho=nicho)
        dominios.update(_una_busqueda_serper(query))
        time.sleep(0.5)
    return list(dominios)

def intentar_shopify(dominio):
    try:
        r = requests.get(f'{dominio}/products.json?limit=250', timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return None
        data = r.json()
        productos = data.get('products')
        if productos is None:
            return None
        return productos
    except Exception:
        return None

def intentar_woocommerce(dominio):
    try:
        r = requests.get(f'{dominio}/wp-json/wc/store/v1/products?per_page=100', timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, list):
            return None
        return data
    except Exception:
        return None

def intentar_vtex(dominio):
    try:
        r = requests.get(f'{dominio}/api/catalog_system/pub/products/search?_from=0&_to=49', timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code not in (200, 206):
            return None
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        return data
    except Exception:
        return None
PALABRAS_PRECIO_CERO_VALIDO = ('regalo', 'gratis', 'muestra', 'rifa', 'obsequio', 'sorteo', 'sample')

def _precio_cero_es_error_real(titulo, handle, variante):
    texto = f'{titulo} {handle}'.lower()
    if any((palabra in texto for palabra in PALABRAS_PRECIO_CERO_VALIDO)):
        return False
    if variante.get('available') is False:
        return False
    return True

def _producto_esta_disponible_shopify(variantes):
    if not variantes:
        return True
    return any((v.get('available') is not False for v in variantes))

def detectar_errores_shopify(productos):
    errores = []
    for p in productos:
        titulo = p.get('title', '') or ''
        descripcion = p.get('body_html', '') or ''
        handle = p.get('handle', '') or ''
        url_producto = f'/products/{handle}'
        if len(titulo) > 150:
            errores.append((url_producto, 'titulo_largo', f'{len(titulo)} caracteres'))
        if re.search('<[a-z][\\s\\S]*?>', descripcion) and len(descripcion) > 0:
            if descripcion.count('<') != descripcion.count('>'):
                errores.append((url_producto, 'html_roto', 'etiquetas sin cerrar'))
        if not p.get('vendor'):
            errores.append((url_producto, 'falta_marca', 'vendor vacio'))
        variantes = p.get('variants', [])
        if not p.get('images'):
            if _producto_esta_disponible_shopify(variantes):
                errores.append((url_producto, 'sin_imagenes', 'producto sin foto'))
        for v in variantes:
            if v.get('price') in (None, '0.00', '0') and _precio_cero_es_error_real(titulo, handle, v):
                errores.append((url_producto, 'precio_faltante', f'variante {v.get('title', '')}'))
    return errores

def detectar_errores_woocommerce(productos):
    errores = []
    for p in productos:
        titulo = p.get('name', '') or ''
        descripcion = p.get('description', '') or ''
        permalink = p.get('permalink', '')
        if len(titulo) > 150:
            errores.append((permalink, 'titulo_largo', f'{len(titulo)} caracteres'))
        if descripcion.count('<') != descripcion.count('>'):
            errores.append((permalink, 'html_roto', 'etiquetas sin cerrar'))
        en_stock = p.get('is_in_stock', True)
        if not p.get('images') and en_stock:
            errores.append((permalink, 'sin_imagenes', 'producto sin foto'))
        precios = p.get('prices', {})
        texto = f'{titulo} {permalink}'.lower()
        es_regalo = any((palabra in texto for palabra in PALABRAS_PRECIO_CERO_VALIDO))
        if (not precios or precios.get('price') in (None, '0', '')) and en_stock and (not es_regalo):
            errores.append((permalink, 'precio_faltante', 'sin precio'))
    return errores
RE_TELEFONO = re.compile('(?:\\+?57)?[\\s\\-\\.]?3\\d{2}[\\s\\-\\.]?\\d{3}[\\s\\-\\.]?\\d{4}')
RE_WA_LINK = re.compile('(?:wa\\.me/|api\\.whatsapp\\.com/send/?\\?phone=)(\\d{10,15})')
RE_PIXEL_ADS = re.compile('fbq\\(|gtag\\(|googletagmanager\\.com|connect\\.facebook\\.net')
RE_BOT_ATENCION = re.compile('wati\\.io|callbell\\.eu|zenvia\\.com|take\\.net|blip\\.ai|gupshup\\.io|interakt\\.ai|trengo\\.(?:co|com)|zoko\\.io|rasayel\\.io|360dialog\\.com|kommo\\.com|jivochat\\.com|jivosite\\.com|tidio\\.co|crisp\\.chat|manychat\\.com', re.IGNORECASE)
FRASES_POLITICA_DATOS_FORMAL = ('politica de tratamiento de datos', 'política de tratamiento de datos', 'aviso de privacidad', 'habeas data')
UMBRAL_CATALOGO_GRANDE = 150

def calcular_senales_bot_atencion(html_lower, cantidad_productos):
    puntaje = 0
    if RE_BOT_ATENCION.search(html_lower):
        puntaje += 1
    if any((frase in html_lower for frase in FRASES_POLITICA_DATOS_FORMAL)):
        puntaje += 1
    if cantidad_productos > UMBRAL_CATALOGO_GRANDE:
        puntaje += 1
    return puntaje

def _es_numero_de_relleno(solo_digitos_celular):
    digitos_unicos = len(set(solo_digitos_celular))
    if digitos_unicos <= 2:
        return True
    return False

def validar_y_normalizar_telefono_co(numero):
    if not numero:
        return None
    solo_digitos = re.sub('\\D', '', numero)
    celular = None
    if solo_digitos.startswith('57') and len(solo_digitos) == 12 and (solo_digitos[2] == '3'):
        celular = solo_digitos[2:]
    elif len(solo_digitos) == 10 and solo_digitos[0] == '3':
        celular = solo_digitos
    else:
        return None
    if _es_numero_de_relleno(celular):
        return None
    return '+57' + celular

def analizar_html_tienda(dominio, cantidad_productos=0):
    try:
        r = requests.get(dominio, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return (None, False, False, False, False, 0)
        html = r.text
        html_lower = html.lower()
        wa_match = RE_WA_LINK.search(html)
        numero = wa_match.group(1) if wa_match else None
        if not numero:
            tel_match = RE_TELEFONO.search(html)
            numero = re.sub('[\\s\\-\\.]', '', tel_match.group(0)) if tel_match else None
        numero_valido = validar_y_normalizar_telefono_co(numero)
        tiene_pixel = bool(RE_PIXEL_ADS.search(html))
        posible_construccion = any((p in html_lower for p in PALABRAS_SITIO_EN_CONSTRUCCION))
        posible_mayorista = any((p in html_lower for p in PALABRAS_MAYORISTA))
        posible_mercado_no_co = any((p in html_lower for p in PALABRAS_MERCADO_NO_CO))
        senales_bot = calcular_senales_bot_atencion(html_lower, cantidad_productos)
        return (numero_valido, tiene_pixel, posible_construccion, posible_mayorista, posible_mercado_no_co, senales_bot)
    except Exception:
        return (None, False, False, False, False, 0)

def cargar_dominios_vistos():
    if not os.path.exists(DOMINIOS_YA_VISTOS_TXT):
        return set()
    with open(DOMINIOS_YA_VISTOS_TXT, encoding='utf-8') as f:
        return set((line.strip() for line in f if line.strip()))

def marcar_dominio_visto(dominio):
    with open(DOMINIOS_YA_VISTOS_TXT, 'a', encoding='utf-8') as f:
        f.write(dominio + '\n')

def guardar_lead_inmediato(lead):
    existe = os.path.exists(SALIDA_CSV)
    with open(SALIDA_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=lead.keys())
        if not existe:
            writer.writeheader()
        writer.writerow(lead)

def guardar_detalle_errores(dominio, nicho, plataforma, errores):
    existe = os.path.exists(SALIDA_DETALLE_CSV)
    with open(SALIDA_DETALLE_CSV, 'a', newline='', encoding='utf-8') as f:
        campos = ['tienda', 'nicho', 'plataforma', 'tipo_error', 'link_producto', 'detalle']
        writer = csv.DictWriter(f, fieldnames=campos)
        if not existe:
            writer.writeheader()
        for url_producto, tipo_error, detalle in errores:
            link_completo = dominio.rstrip('/') + url_producto
            writer.writerow({'tienda': dominio, 'nicho': nicho, 'plataforma': plataforma, 'tipo_error': tipo_error, 'link_producto': link_completo, 'detalle': detalle})

def main():
    vistos = cargar_dominios_vistos()
    print(f'[*] {len(vistos)} dominios ya procesados en corridas anteriores (se saltan)')
    nichos_hoy, posicion_inicio, vueltas_ciclo = obtener_nichos_de_hoy()
    total_queries = len(nichos_hoy) * len(PLANTILLAS_QUERY)
    print(f'[*] Tanda de hoy: nichos {posicion_inicio + 1} a {posicion_inicio + len(nichos_hoy)} de {len(NICHOS)} (un ciclo completo toma {vueltas_ciclo} corridas)')
    print(f'[*] {len(nichos_hoy)} nichos x {len(PLANTILLAS_QUERY)} variantes de query = {total_queries} busquedas a Serper (~{total_queries * 2} creditos esta corrida)')
    print(f'[*] Umbral minimo de errores por lead: {MINIMO_ERRORES_PARA_LEAD} (catalogos por debajo de esto se descartan, no son "rescate de catalogo")')
    total_leads_nuevos = 0
    total_errores_script = 0
    total_descartados_bajo_volumen = 0
    whatsapp_a_tiendas = {}
    for nicho in nichos_hoy:
        print(f'\n[*] Nicho: {nicho}')
        try:
            dominios = buscar_tiendas_por_nicho(nicho)
        except Exception as e:
            print(f'    [!] Fallo buscando el nicho completo, sigo con el siguiente: {e}')
            continue
        print(f'    {len(dominios)} dominios candidatos encontrados')
        for dominio in dominios:
            if dominio in vistos:
                continue
            if any((ignorado in dominio for ignorado in DOMINIOS_IGNORADOS)):
                continue
            try:
                marcar_dominio_visto(dominio)
                vistos.add(dominio)
                productos = intentar_shopify(dominio)
                plataforma = 'Shopify'
                if productos is None:
                    productos = intentar_woocommerce(dominio)
                    plataforma = 'WooCommerce'
                if productos is None:
                    productos = intentar_vtex(dominio)
                    plataforma = 'VTEX'
                if productos is None or len(productos) == 0:
                    continue
                if plataforma == 'Shopify':
                    errores = detectar_errores_shopify(productos)
                elif plataforma == 'WooCommerce':
                    errores = detectar_errores_woocommerce(productos)
                else:
                    with open(os.path.join(CARPETA_SALIDA, 'vtex_estructuras_sin_calibrar.txt'), 'a', encoding='utf-8') as f:
                        f.write(f'\n{'=' * 60}\n{dominio}\n')
                        f.write(str(productos[0])[:2000])
                    continue
                if not errores:
                    continue
                if len(errores) < MINIMO_ERRORES_PARA_LEAD:
                    total_descartados_bajo_volumen += 1
                    continue
                whatsapp, tiene_pixel, posible_construccion, posible_mayorista, posible_mercado_no_co, senales_bot = analizar_html_tienda(dominio, len(productos))
                if not whatsapp:
                    continue
                tipos_error = Counter((e[1] for e in errores))
                tipo_principal = tipos_error.most_common(1)[0][0]
                lead = {'tienda': dominio, 'nicho': nicho, 'plataforma': plataforma, 'productos_analizados': len(productos), 'errores_encontrados': len(errores), 'tipo_error_principal': tipo_principal, 'detalle_tipos_error': dict(tipos_error), 'evidencia_ejemplo': errores[0][0] if errores else '', 'tiene_pixel_ads': tiene_pixel, 'whatsapp': whatsapp, 'posible_en_construccion': posible_construccion, 'posible_mayorista': posible_mayorista, 'posible_mercado_no_co': posible_mercado_no_co, 'senales_bot_atencion': senales_bot}
                guardar_lead_inmediato(lead)
                guardar_detalle_errores(dominio, nicho, plataforma, errores)
                whatsapp_a_tiendas.setdefault(whatsapp, []).append(dominio)
                total_leads_nuevos += 1
                alertas = []
                if posible_construccion:
                    alertas.append('posible sitio en construccion')
                if posible_mayorista:
                    alertas.append('posible mayorista/distribuidor')
                if posible_mercado_no_co:
                    alertas.append('posible mercado no colombiano')
                if senales_bot >= 2:
                    alertas.append(f'probable bot/servicio al cliente ({senales_bot}/3 senales)')
                sufijo_alerta = f' -- ALERTA: {', '.join(alertas)}' if alertas else ''
                print(f'    [+] LEAD guardado: {dominio} | {len(errores)} errores | {whatsapp}{sufijo_alerta}')
                time.sleep(1)
            except Exception as e:
                total_errores_script += 1
                print(f'    [!] Error inesperado con {dominio}, sigo con la siguiente: {e}')
                continue
    print(f'\n[*] Corrida terminada. {total_leads_nuevos} leads nuevos guardados en {SALIDA_CSV}')
    print(f'    Detalle completo de cada error individual (link por link) en {SALIDA_DETALLE_CSV}')
    print(f'    {total_descartados_bajo_volumen} tiendas con errores reales pero por debajo de {MINIMO_ERRORES_PARA_LEAD} (no calificaron como rescate de catalogo, se descartaron)')
    if total_errores_script:
        print(f'    ({total_errores_script} tiendas fallaron con error inesperado y se saltaron -- si este numero es alto, pega la salida completa en el chat para revisarlo)')
    print('    Todos los leads guardados superan el minimo -- ninguno se descarta por exceso de volumen.')
    repetidos = {wa: tiendas for wa, tiendas in whatsapp_a_tiendas.items() if len(tiendas) > 1}
    if repetidos:
        print(f'\n[!] {len(repetidos)} numero(s) de WhatsApp aparecen en mas de una tienda esta corrida -- revisa a mano antes de contactar, probablemente es un widget de chat generico o la agencia que diseno los sitios, no el dueno real:')
        for wa, tiendas in repetidos.items():
            print(f'    {wa}: {', '.join(tiendas)}')
    else:
        print('\n[*] Ningun WhatsApp repetido entre tiendas distintas esta corrida.')
if __name__ == '__main__':
    activar_wake_lock()
    try:
        main()
    except KeyboardInterrupt:
        print('\n[*] Detenido manualmente. Lo que ya se guardó en el CSV está a salvo, puedes volver a correr el script y sigue donde quedó (no repite dominios).')
    except Exception as e:
        print(f'\n[!] El script se detuvo por un error no previsto: {e}')
        print('    Todo lo que ya se guardó en el CSV antes de esto está a salvo. Pega este mensaje en el chat para que lo revise.')
