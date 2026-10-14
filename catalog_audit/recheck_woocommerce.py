"""Re-check a batch of WooCommerce leads against the live Store API before any contact."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import csv
import os
import time
from collections import Counter
from datetime import datetime
import requests
from catalog_scraper import intentar_woocommerce, detectar_errores_woocommerce, analizar_html_tienda
LOTE = [('https://example.com', 100)]
MINIMO_ERRORES_PARA_LEAD = 15
CARPETA_SALIDA = 'catalog_rescue_leads'
os.makedirs(CARPETA_SALIDA, exist_ok=True)
SALIDA_CSV = os.path.join(CARPETA_SALIDA, f'reverificacion_woocommerce_{datetime.now().strftime('%Y-%m-%d')}.csv')

def reverificar_tienda(dominio, errores_originales):
    try:
        productos = intentar_woocommerce(dominio)
    except Exception:
        productos = None
    if productos is None or len(productos) == 0:
        return {'tienda': dominio, 'errores_originales': errores_originales, 'errores_hoy': 0, 'sigue_como_woocommerce': False, 'whatsapp_hoy': '', 'veredicto': 'NO_RESPONDE', 'detalle': 'products endpoint no respondio o la tienda ya no es WooCommerce'}
    errores_hoy = detectar_errores_woocommerce(productos)
    n_errores_hoy = len(errores_hoy)
    whatsapp, tiene_pixel, posible_construccion, posible_mayorista, posible_mercado_no_co, senales_bot = analizar_html_tienda(dominio, len(productos))
    tipos = Counter((e[1] for e in errores_hoy))
    extras = {'tipo_error_principal': tipos.most_common(1)[0][0] if tipos else '', 'detalle_tipos_error': dict(tipos), 'evidencia_ejemplo': errores_hoy[0][0] if errores_hoy else '', 'tiene_pixel_ads': tiene_pixel, 'senales_bot_atencion': senales_bot, 'posible_mayorista': posible_mayorista, 'posible_mercado_no_co': posible_mercado_no_co}
    if posible_construccion:
        return {'tienda': dominio, 'errores_originales': errores_originales, 'errores_hoy': n_errores_hoy, 'sigue_como_woocommerce': True, 'whatsapp_hoy': whatsapp or '', **extras, 'veredicto': 'YA_NO_APLICA', 'detalle': "sitio muestra senales de 'en construccion' -- revisar a mano antes de descartar del todo"}
    if n_errores_hoy == 0:
        return {'tienda': dominio, 'errores_originales': errores_originales, 'errores_hoy': 0, 'sigue_como_woocommerce': True, 'whatsapp_hoy': whatsapp or '', **extras, 'veredicto': 'YA_NO_APLICA', 'detalle': 'el catalogo ya no muestra ningun error real -- probablemente ya lo corrigieron'}
    if not whatsapp:
        return {'tienda': dominio, 'errores_originales': errores_originales, 'errores_hoy': n_errores_hoy, 'sigue_como_woocommerce': True, 'whatsapp_hoy': '', **extras, 'veredicto': 'WHATSAPP_INVALIDO', 'detalle': 'el error sigue ahi pero no se encontro un whatsapp colombiano valido en el HTML actual'}
    if n_errores_hoy < MINIMO_ERRORES_PARA_LEAD:
        return {'tienda': dominio, 'errores_originales': errores_originales, 'errores_hoy': n_errores_hoy, 'sigue_como_woocommerce': True, 'whatsapp_hoy': whatsapp, **extras, 'veredicto': 'BAJO_VOLUMEN', 'detalle': f'bajo de {errores_originales} a {n_errores_hoy}, ya no alcanza el minimo de {MINIMO_ERRORES_PARA_LEAD}'}
    return {'tienda': dominio, 'errores_originales': errores_originales, 'errores_hoy': n_errores_hoy, 'sigue_como_woocommerce': True, 'whatsapp_hoy': whatsapp, **extras, 'veredicto': 'SIGUE_IGUAL', 'detalle': f'errores hoy: {n_errores_hoy} (antes {errores_originales}) -- listo para venta'}

def main():
    print(f'[*] Reverificando {len(LOTE)} leads de WooCommerce del lote del 12-sep')
    print(f'[*] Umbral minimo real de venta: {MINIMO_ERRORES_PARA_LEAD} errores\n')
    resultados = []
    for dominio, errores_originales in LOTE:
        print(f'[*] {dominio} (tenia {errores_originales} errores)...', end=' ', flush=True)
        try:
            resultado = reverificar_tienda(dominio, errores_originales)
        except Exception as e:
            resultado = {'tienda': dominio, 'errores_originales': errores_originales, 'errores_hoy': '', 'sigue_como_woocommerce': '', 'whatsapp_hoy': '', 'veredicto': 'NO_RESPONDE', 'detalle': f'error inesperado: {e}'}
        resultados.append(resultado)
        print(resultado['veredicto'])
        time.sleep(1.5)
    with open(SALIDA_CSV, 'w', newline='', encoding='utf-8') as f:
        campos = ['tienda', 'errores_originales', 'errores_hoy', 'sigue_como_woocommerce', 'whatsapp_hoy', 'veredicto', 'detalle', 'tipo_error_principal', 'detalle_tipos_error', 'evidencia_ejemplo', 'tiene_pixel_ads', 'senales_bot_atencion', 'posible_mayorista', 'posible_mercado_no_co']
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)
    conteo = {}
    for r in resultados:
        conteo[r['veredicto']] = conteo.get(r['veredicto'], 0) + 1
    print(f'\n[*] Reverificacion terminada. Resultado guardado en {SALIDA_CSV}\n')
    print('[*] Resumen:')
    for veredicto, cantidad in sorted(conteo.items(), key=lambda x: -x[1]):
        print(f'    {veredicto}: {cantidad}')
    print('\n[*] Que hacer con cada veredicto:')
    print("    SIGUE_IGUAL        -> pasar a 'listo para venta' tal cual")
    print('    BAJO_VOLUMEN       -> revisar a mano, puede que aun sirva segun tipo de error')
    print('    YA_NO_APLICA       -> descartar del lote de venta')
    print('    WHATSAPP_INVALIDO  -> buscar el numero de nuevo a mano antes de descartar')
    print('    NO_RESPONDE        -> reintentar en la proxima corrida, no descartar todavia')
if __name__ == '__main__':
    main()
