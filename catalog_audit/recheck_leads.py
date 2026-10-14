"""Re-check the stores of an existing leads CSV against their live public catalog, without repeating the full search, and group them by confirmed error count."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import sys
import csv
import os
import time
from datetime import datetime
from catalog_scraper import intentar_shopify, intentar_woocommerce, detectar_errores_shopify, detectar_errores_woocommerce, analizar_html_tienda
UMBRAL_CALIFICA_SIN_DUDA = 15
UMBRAL_EVALUAR_MINIMO = 10

def clasificar(n_errores):
    if n_errores >= UMBRAL_CALIFICA_SIN_DUDA:
        return 'CALIFICA'
    elif n_errores >= UMBRAL_EVALUAR_MINIMO:
        return 'EVALUAR'
    else:
        return 'DECAYO'

def main():
    if len(sys.argv) < 2:
        print('Uso: python3 verificar_leads_hoy.py ruta/al/leads_FECHA.csv')
        sys.exit(1)
    ruta_csv_original = sys.argv[1]
    if not os.path.exists(ruta_csv_original):
        print(f'[!] No encuentro el archivo: {ruta_csv_original}')
        sys.exit(1)
    with open(ruta_csv_original, newline='', encoding='utf-8') as f:
        leads_originales = list(csv.DictReader(f))
    tiendas_vistas = {}
    for row in leads_originales:
        tiendas_vistas[row['tienda']] = row
    print(f'[*] {len(tiendas_vistas)} tiendas unicas a re-verificar HOY ({datetime.now().strftime('%Y-%m-%d')})')
    fecha = datetime.now().strftime('%Y-%m-%d')
    salida_resumen = f'verificacion_{fecha}.csv'
    salida_detalle = f'verificacion_detalle_{fecha}.csv'
    resumen_rows = []
    detalle_rows = []
    for i, (dominio, row_original) in enumerate(tiendas_vistas.items(), 1):
        print(f'[{i}/{len(tiendas_vistas)}] Verificando {dominio} ...', end=' ')
        try:
            productos = intentar_shopify(dominio)
            plataforma = 'Shopify'
            if productos is None:
                productos = intentar_woocommerce(dominio)
                plataforma = 'WooCommerce'
            if productos is None or len(productos) == 0:
                print('SIN RESPUESTA (tienda caida, bloqueada, o cambio de plataforma)')
                resumen_rows.append({'tienda': dominio, 'errores_csv_original': row_original.get('errores_encontrados', ''), 'errores_reales_hoy': 'N/D', 'estado': 'SIN_RESPUESTA', 'whatsapp': row_original.get('whatsapp', '')})
                continue
            if plataforma == 'Shopify':
                errores = detectar_errores_shopify(productos)
            else:
                errores = detectar_errores_woocommerce(productos)
            n_errores = len(errores)
            estado = clasificar(n_errores)
            print(f'{n_errores} errores reales hoy -> {estado}')
            resumen_rows.append({'tienda': dominio, 'errores_csv_original': row_original.get('errores_encontrados', ''), 'errores_reales_hoy': n_errores, 'estado': estado, 'whatsapp': row_original.get('whatsapp', '')})
            if estado in ('CALIFICA', 'EVALUAR'):
                for url_producto, tipo_error, detalle in errores:
                    detalle_rows.append({'tienda': dominio, 'estado': estado, 'tipo_error': tipo_error, 'link_producto': dominio.rstrip('/') + url_producto, 'detalle': detalle})
            time.sleep(1)
        except Exception as e:
            print(f'ERROR inesperado, sigo con la siguiente: {e}')
            resumen_rows.append({'tienda': dominio, 'errores_csv_original': row_original.get('errores_encontrados', ''), 'errores_reales_hoy': 'ERROR', 'estado': 'ERROR_SCRIPT', 'whatsapp': row_original.get('whatsapp', '')})
            continue
    with open(salida_resumen, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['tienda', 'errores_csv_original', 'errores_reales_hoy', 'estado', 'whatsapp'])
        writer.writeheader()
        writer.writerows(resumen_rows)
    with open(salida_detalle, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['tienda', 'estado', 'tipo_error', 'link_producto', 'detalle'])
        writer.writeheader()
        writer.writerows(detalle_rows)
    n_califica = sum((1 for r in resumen_rows if r['estado'] == 'CALIFICA'))
    n_evaluar = sum((1 for r in resumen_rows if r['estado'] == 'EVALUAR'))
    n_decayo = sum((1 for r in resumen_rows if r['estado'] == 'DECAYO'))
    n_sin_respuesta = sum((1 for r in resumen_rows if r['estado'] == 'SIN_RESPUESTA'))
    print(f'\n[*] Listo. Resumen guardado en {salida_resumen}')
    print(f'    Detalle (link por link) guardado en {salida_detalle}')
    print(f'\n    CALIFICA (15+):      {n_califica}')
    print(f'    EVALUAR (10-14):     {n_evaluar}')
    print(f'    DECAYO (<10 hoy):    {n_decayo}')
    print(f'    SIN_RESPUESTA:       {n_sin_respuesta}')
if __name__ == '__main__':
    main()
