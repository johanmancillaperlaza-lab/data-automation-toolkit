"""Collect Reddit posts of people asking for CV help across many subreddits, validate them with an LLM and export the leads to CSV and HTML."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import datetime
import time
import requests
import random
import re
import csv
import os
import json
BIGMODEL_API_KEY = os.getenv('BIGMODEL_API_KEY', 'YOUR_BIGMODEL_API_KEY')
BIGMODEL_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID', 'YOUR_REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET', 'YOUR_REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'data-automation-toolkit/0.1 (by u/YOUR_REDDIT_USERNAME)')
SUBREDDITS = ['resumes', 'resumesupport', 'resume', 'resumehelp', 'resumecritique', 'resumefeedback', 'resumereview', 'cv', 'cvreview', 'cvsupport', 'europass', 'ratemyresume', 'ratemycv', 'fixmyresume', 'fixmycv', 'jobs', 'jobsearch', 'jobhunting', 'jobsearchhacks', 'jobpostings', 'jobopenings', 'careerguidance', 'careeradvice', 'career_advice', 'careerchange', 'careerpath', 'getemployed', 'findapath', 'backtowork', 'adulting', 'povertyfinance', 'recruitinghell', 'interviewprep', 'interviews', 'interviewfeedback', 'cscareerquestions', 'cscareerquestionsEU', 'cscareerquestionsCAD', 'cscareerquestionsIN', 'ITCareerQuestions', 'sysadminjobs', 'devopsjobs', 'dataengineering', 'datascience', 'MachineLearning', 'learnprogramming', 'programming', 'webdev', 'frontend', 'backend', 'softwareengineering', 'ExperiencedDevs', 'cybersecurity', 'cloudcomputing', 'aws', 'azure', 'gcp', 'python', 'java', 'javascript', 'reactjs', 'angular', 'dotnet', 'csharp', 'gamedev', 'gamedesign', 'gamingjobs', 'financialcareers', 'accounting', 'finance', 'consulting', 'MBA', 'fpanda', 'audit', 'privateequity', 'investmentbanking', 'actuary', 'supplychain', 'logistics', 'sales', 'marketing', 'digitalmarketing', 'socialmedia', 'contentmarketing', 'humanresources', 'recruiting', 'realestate', 'propertymanagement', 'nursing', 'medicine', 'premed', 'medicalschool', 'residency', 'pharmacy', 'pharmacist', 'labrats', 'clinicalresearch', 'biotech', 'bioinformatics', 'publichealth', 'engineeringstudents', 'MechanicalEngineering', 'civilengineering', 'electricalengineering', 'ChemicalEngineering', 'AerospaceEngineering', 'biomedicalengineering', 'industrialengineering', 'materials', 'chemistry', 'biology', 'physics', 'geology', 'environmentalscience', 'lawyers', 'LawSchool', 'paralegal', 'Teachers', 'teaching', 'education', 'highereducation', 'gradschool', 'gradadmissions', 'college', 'university', 'student', 'internships', 'graphic_design', 'UI_Design', 'UXDesign', 'productdesign', 'interiordesign', 'architecture', 'filmmakers', 'videoediting', 'animation', '3Dmodeling', 'photography', 'illustration', 'remotework', 'freelance', 'freelanceWriters', 'Upwork', 'Fiverr', 'digitalnomad', 'UKJobs', 'UniUK', 'AskUK', 'AusFinance', 'australia', 'AusJobs', 'canadajobs', 'canada', 'torontoJobs', 'india', 'indianworkplace', 'IndiaJobs', 'developersIndia', 'Philippines', 'phcareers', 'germany', 'de', 'arbeitsleben', 'france', 'italy', 'espana', 'es', 'mexico', 'Argentina', 'Colombia', 'chile', 'peru', 'uruguay', 'paraguay', 'bolivia', 'ecuador', 'venezuela', 'costarica', 'panama', 'brazil', 'brdev', 'portugal', 'netherlands', 'sweden', 'norway', 'denmark', 'finland', 'poland', 'czech', 'hungary', 'greece', 'turkey', 'dubai', 'qatar', 'saudiarabia', 'kuwait', 'oman', 'bahrain', 'jordan', 'lebanon', 'israel', 'singapore', 'malaysia', 'indonesia', 'thailand', 'vietnam', 'southafrica', 'nigeria', 'kenya', 'egypt', 'morocco', 'tunisia', 'algeria', 'japanlife', 'japan', 'korea', 'china', 'shanghai', 'taiwan', 'hongkong', 'espanol', 'latinos', 'trabajos', 'empleos', 'forodeempleo', 'chileempleos', 'colombiaempleo', 'mexicoempleo', 'argentinaempleo', 'peruempleos', 'venezuelaempleos', 'brasil', 'vagas', 'empregos', 'curriculos', 'deutschland', 'stellenanzeigen', 'arbeitsmarkt', 'frankreich', 'italia', 'lavoro', 'francejobs', 'italyjobs', 'germanyjobs', 'netherlandsjobs', 'swedenjobs', 'norwayjobs', 'denmarkjobs', 'finlandjobs', 'polandjobs', 'czechjobs', 'hungaryjobs', 'greecejobs', 'turkeyjobs', 'uaejobs', 'qatarjobs', 'saudijobs', 'singaporejobs', 'malaysiajobs', 'indonesiajobs', 'thailandjobs', 'vietnamjobs', 'philippinesjobs', 'southafricajobs', 'nigerianjobs', 'kenyajobs', 'egyptjobs', 'moroccojobs', 'algeriajobs', 'japanjobs', 'koreajobs', 'chinajobs', 'taiwanjobs', 'ColombiaEmpleo', 'MexicoEmpleo', 'ChileEmpleos', 'PeruJobs', 'ArgentinaJobs', 'BrasilJobs', 'SpainJobs', 'GermanyJobs', 'FranceJobs', 'ItalyJobs', 'NetherlandsJobs', 'SwedenJobs', 'IndiaJobs', 'PhilippinesJobs', 'SingaporeJobs', 'MalaysiaJobs', 'JapanJobs', 'KoreaJobs']
PAIS_POR_SUBREDDIT = {'UKJobs': 'United Kingdom', 'UniUK': 'United Kingdom', 'AskUK': 'United Kingdom', 'AusFinance': 'Australia', 'australia': 'Australia', 'AusJobs': 'Australia', 'canadajobs': 'Canada', 'canada': 'Canada', 'torontoJobs': 'Canada', 'india': 'India', 'indianworkplace': 'India', 'IndiaJobs': 'India', 'developersIndia': 'India', 'Philippines': 'Philippines', 'phcareers': 'Philippines', 'germany': 'Germany', 'de': 'Germany', 'arbeitsleben': 'Germany', 'france': 'France', 'frankreich': 'France', 'francejobs': 'France', 'italy': 'Italy', 'italia': 'Italy', 'italyjobs': 'Italy', 'espana': 'Spain', 'es': 'Spain', 'espanol': 'Spain', 'mexico': 'Mexico', 'mexicoempleo': 'Mexico', 'MexicoEmpleo': 'Mexico', 'Argentina': 'Argentina', 'argentinaempleo': 'Argentina', 'ArgentinaJobs': 'Argentina', 'Colombia': 'Colombia', 'colombiaempleo': 'Colombia', 'ColombiaEmpleo': 'Colombia', 'chile': 'Chile', 'chileempleos': 'Chile', 'ChileEmpleos': 'Chile', 'peru': 'Peru', 'peruempleos': 'Peru', 'PeruJobs': 'Peru', 'uruguay': 'Uruguay', 'paraguay': 'Paraguay', 'bolivia': 'Bolivia', 'ecuador': 'Ecuador', 'venezuela': 'Venezuela', 'venezuelaempleos': 'Venezuela', 'costarica': 'Costa Rica', 'panama': 'Panama', 'brazil': 'Brazil', 'brdev': 'Brazil', 'brasil': 'Brazil', 'vagas': 'Brazil', 'empregos': 'Brazil', 'BrasilJobs': 'Brazil', 'portugal': 'Portugal', 'empregospt': 'Portugal', 'curriculos': 'Portugal', 'netherlands': 'Netherlands', 'netherlandsjobs': 'Netherlands', 'NetherlandsJobs': 'Netherlands', 'sweden': 'Sweden', 'swedenjobs': 'Sweden', 'SwedenJobs': 'Sweden', 'norway': 'Norway', 'norwayjobs': 'Norway', 'denmark': 'Denmark', 'denmarkjobs': 'Denmark', 'finland': 'Finland', 'finlandjobs': 'Finland', 'poland': 'Poland', 'polandjobs': 'Poland', 'czech': 'Czech Republic', 'czechjobs': 'Czech Republic', 'hungary': 'Hungary', 'hungaryjobs': 'Hungary', 'greece': 'Greece', 'greecejobs': 'Greece', 'turkey': 'Turkey', 'turkeyjobs': 'Turkey', 'dubai': 'United Arab Emirates', 'uaejobs': 'United Arab Emirates', 'qatar': 'Qatar', 'qatarjobs': 'Qatar', 'saudiarabia': 'Saudi Arabia', 'saudijobs': 'Saudi Arabia', 'kuwait': 'Kuwait', 'oman': 'Oman', 'bahrain': 'Bahrain', 'jordan': 'Jordan', 'lebanon': 'Lebanon', 'israel': 'Israel', 'singapore': 'Singapore', 'singaporejobs': 'Singapore', 'SingaporeJobs': 'Singapore', 'malaysia': 'Malaysia', 'malaysiajobs': 'Malaysia', 'MalaysiaJobs': 'Malaysia', 'indonesia': 'Indonesia', 'indonesiajobs': 'Indonesia', 'thailand': 'Thailand', 'thailandjobs': 'Thailand', 'vietnam': 'Vietnam', 'vietnamjobs': 'Vietnam', 'southafrica': 'South Africa', 'southafricajobs': 'South Africa', 'nigeria': 'Nigeria', 'nigerianjobs': 'Nigeria', 'kenya': 'Kenya', 'kenyajobs': 'Kenya', 'egypt': 'Egypt', 'egyptjobs': 'Egypt', 'morocco': 'Morocco', 'moroccojobs': 'Morocco', 'tunisia': 'Tunisia', 'algeria': 'Algeria', 'japanlife': 'Japan', 'japan': 'Japan', 'japanjobs': 'Japan', 'JapanJobs': 'Japan', 'korea': 'South Korea', 'koreajobs': 'South Korea', 'KoreaJobs': 'South Korea', 'china': 'China', 'chinajobs': 'China', 'shanghai': 'China', 'taiwan': 'Taiwan', 'taiwanjobs': 'Taiwan', 'hongkong': 'Hong Kong', 'trabajos': 'Latam', 'empleos': 'Latam', 'forodeempleo': 'Latam', 'SpainJobs': 'Spain', 'GermanyJobs': 'Germany', 'FranceJobs': 'France', 'ItalyJobs': 'Italy', 'PhilippinesJobs': 'Philippines'}
PAISES_PAYPAL = {'USA', 'United Kingdom', 'Australia', 'Canada', 'India', 'Philippines', 'Germany', 'France', 'Italy', 'Spain', 'Netherlands', 'Sweden', 'Norway', 'Denmark', 'Finland', 'Poland', 'Czech Republic', 'Hungary', 'Greece', 'Turkey', 'Mexico', 'Argentina', 'Colombia', 'Chile', 'Peru', 'Uruguay', 'Brazil', 'Portugal', 'United Arab Emirates', 'Saudi Arabia', 'Qatar', 'Kuwait', 'Oman', 'Bahrain', 'Jordan', 'Lebanon', 'Israel', 'Singapore', 'Malaysia', 'Japan', 'South Korea', 'Hong Kong', 'China', 'Taiwan'}
MERCADO_MAP = {'United Kingdom': 'UK', 'USA': 'USA', 'Canada': 'Canada', 'Australia': 'Australia', 'Germany': 'Germany', 'France': 'France', 'Italy': 'Italy', 'Spain': 'Spain', 'Netherlands': 'Netherlands', 'Sweden': 'Sweden', 'Norway': 'Norway', 'Denmark': 'Denmark', 'Finland': 'Finland', 'Poland': 'Poland', 'India': 'India', 'Philippines': 'Philippines', 'Brazil': 'Latam', 'Mexico': 'Latam', 'Colombia': 'Latam', 'Argentina': 'Latam', 'Chile': 'Latam', 'Peru': 'Latam', 'Uruguay': 'Latam', 'Paraguay': 'Latam', 'Bolivia': 'Latam', 'Ecuador': 'Latam', 'Venezuela': 'Latam', 'Costa Rica': 'Latam', 'Panama': 'Latam', 'Portugal': 'Portugal', 'Turkey': 'Turkey', 'United Arab Emirates': 'Middle East', 'Qatar': 'Middle East', 'Saudi Arabia': 'Middle East', 'Kuwait': 'Middle East', 'Oman': 'Middle East', 'Bahrain': 'Middle East', 'Jordan': 'Middle East', 'Lebanon': 'Middle East', 'Israel': 'Middle East', 'Singapore': 'Singapore', 'Malaysia': 'Malaysia', 'Japan': 'Japan', 'South Korea': 'Korea', 'China': 'China', 'Taiwan': 'Taiwan', 'Hong Kong': 'Hong Kong'}
PRECIO_MAP = {'USA': '$30-50', 'UK': '$25-35', 'Canada': '$30-40', 'Australia': '$25-35', 'Germany': '$25-35', 'France': '$25-35', 'Italy': '$25-30', 'Spain': '$25-30', 'Netherlands': '$30-40', 'Sweden': '$30-40', 'Norway': '$35-45', 'Denmark': '$35-45', 'Finland': '$30-40', 'Poland': '$20-25', 'India': '$20', 'Philippines': '$20', 'Latam': '$20-25', 'Singapore': '$30-40', 'Malaysia': '$20-25', 'Japan': '$25-35', 'Korea': '$25-35', 'China': '$20-30', 'Taiwan': '$20-30', 'Hong Kong': '$30-40', 'Turkey': '$20-25', 'Middle East': '$30-40', 'Portugal': '$25-30'}
CV_KEYWORDS = ['my resume', 'my cv', 'resume feedback', 'review my resume', 'roast my resume', 'fix my resume', 'resume help', 'mi cv', 'mi curriculum', 'revisar mi cv', 'ayuda con mi cv', 'mejorar mi cv', 'meu cv', 'mon cv', 'mein lebenslauf', 'curriculum', 'cv review', 'resume review', 'help with resume', 'help with cv', 'hoja de vida', 'curriculum vitae', 'mejorar curriculum', 'revisar curriculum', 'curriculum feedback']
SUCCESS_KEYWORDS = ['got an offer', 'hired!', 'success story']
DESCARTE_KEYWORDS = ['[for hire]', 'hiring', 'we are hiring', 'job opening', 'remote job', 'position available']

def es_valido_rapido(titulo, cuerpo):
    texto = (titulo + ' ' + cuerpo).lower()
    if any((kw in texto for kw in SUCCESS_KEYWORDS + DESCARTE_KEYWORDS)):
        return False
    return any((kw in texto for kw in CV_KEYWORDS))

def get_pais_y_paypal(sub):
    pais = PAIS_POR_SUBREDDIT.get(sub, 'USA')
    return (pais, pais in PAISES_PAYPAL)

def get_mercado(pais):
    m = MERCADO_MAP.get(pais, 'USA')
    return (m, PRECIO_MAP.get(m, '$30-50'))

def get_cv(d):
    url = d.get('url', '')
    if any((x in url for x in ['i.redd.it', '.jpg', '.png', '.pdf'])):
        return 'IMG'
    if len(d.get('selftext', '')) >= 200:
        return 'TEXTO'
    return 'NO'

def get_score(sub, cv, horas, comentarios):
    s = 3 if cv == 'IMG' else 2 if cv == 'TEXTO' else 0
    if sub in ['resumes', 'resumesupport', 'resume', 'resumehelp']:
        s += 3
    if horas < 6:
        s += 2
    elif horas < 24:
        s += 1
    if comentarios == 0:
        s += 2
    return min(s, 10)

def validar_con_bigmodel(titulo, cuerpo, user, intentos=2):
    prompt = f"Responde SOLO 'SI' o 'NO'. ¿El usuario pide ayuda para mejorar su CV/resume?\nUsuario: u/{user}\nTítulo: {titulo[:200]}\nCuerpo: {cuerpo[:500]}"
    headers = {'Authorization': f'Bearer {BIGMODEL_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': 'glm-4.7-flash', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 5, 'thinking': {'type': 'disabled'}}
    for i in range(intentos):
        try:
            resp = requests.post(BIGMODEL_URL, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                respuesta = resp.json()['choices'][0]['message']['content'].strip().upper()
                if 'SI' in respuesta or 'SÍ' in respuesta:
                    return True
                else:
                    return False
            elif resp.status_code == 429:
                print(f' (HTTP 429 - esperando 30s)', end=' ')
                time.sleep(30)
            else:
                print(f' (HTTP {resp.status_code})', end=' ')
                if i < intentos - 1:
                    time.sleep(10)
        except Exception as e:
            print(f' (Error: {type(e).__name__})', end=' ')
            if i < intentos - 1:
                time.sleep(10)
    return False
session = requests.Session()
session.headers.update({'User-Agent': REDDIT_USER_AGENT})

def refresh_reddit_token():
    r = requests.post('https://www.reddit.com/api/v1/access_token', auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET), data={'grant_type': 'client_credentials'}, headers={'User-Agent': REDDIT_USER_AGENT}, timeout=15)
    r.raise_for_status()
    session.headers['Authorization'] = 'bearer ' + r.json()['access_token']

refresh_reddit_token()
fecha_hoy = datetime.date.today()
OUTPUT_HTML = f'leads_reddit_{fecha_hoy}.html'
CSV_FILE = f'leads_reddit_master.csv'
ahora = datetime.datetime.now(datetime.timezone.utc)
todos = []
seen_usernames = set()
start_time = time.time()
MAX_SECONDS = 4 * 3600
print('=' * 70)
print('Reddit leads collector | official Reddit API (OAuth)')
print('Espera inicial de 60 segundos...')
time.sleep(60)
print(f'{len(SUBREDDITS)} subreddits | Límite 4 horas')
print('Pausa extra de 30s cada 5 subreddits')
print('=' * 70)
contador_subreddits = 0
for sub in SUBREDDITS:
    if time.time() - start_time > MAX_SECONDS:
        print('\n⏰ Tiempo máximo alcanzado. Guardando resultados parciales...')
        break
    if contador_subreddits > 0 and contador_subreddits % 5 == 0:
        print(f'\n🔄 Pausa extra de 30 segundos (llevamos {contador_subreddits} subreddits)...')
        time.sleep(30)
    print(f'\n📌 r/{sub}...', end=' ', flush=True)
    after = None
    encontrados = 0
    while True:
        url = f'https://oauth.reddit.com/r/{sub}/new?limit=100'
        if after:
            url += f'&after={after}'
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 401:
                refresh_reddit_token()
                resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json().get('data', {})
            posts = data.get('children', [])
            if not posts:
                break
            for p in posts:
                d = p.get('data', {})
                horas = (ahora.timestamp() - d.get('created_utc', 0)) / 3600
                if horas > 72:
                    continue
                titulo, cuerpo, user = (d.get('title', ''), d.get('selftext', ''), d.get('author', ''))
                if user in ['[deleted]', '[removed]', '', 'AutoModerator'] or user in seen_usernames:
                    continue
                if not es_valido_rapido(titulo, cuerpo):
                    continue
                print(f'\n  🤖 u/{user[:15]}...', end=' ')
                es_valido = validar_con_bigmodel(titulo, cuerpo, user)
                if not es_valido:
                    print('❌')
                else:
                    pais, paypal_ok = get_pais_y_paypal(sub)
                    mercado, precio = get_mercado(pais)
                    tiene_cv = get_cv(d)
                    coments = d.get('num_comments', 0)
                    score = get_score(sub, tiene_cv, horas, coments)
                    todos.append({'username': user, 'link_dm': f'https://www.reddit.com/message/compose/?to={user}', 'link_post': 'https://www.reddit.com' + d.get('permalink', ''), 'titulo': titulo, 'subreddit': f'r/{sub}', 'horas': round(horas, 1), 'score': score, 'tiene_cv': tiene_cv, 'mercado': mercado, 'precio': precio, 'pais': pais, 'paypal_ok': paypal_ok})
                    seen_usernames.add(user)
                    encontrados += 1
                    print(f'✅ {pais} - {mercado}' + (' 💰' if paypal_ok else ''))
                print(f'  (Pausa 5s)')
                time.sleep(5)
            after = data.get('after')
            if not after:
                break
            pausa_pagina = random.uniform(4, 6)
            print(f'  (Pausa entre páginas: {pausa_pagina:.1f}s)')
            time.sleep(pausa_pagina)
        except Exception as e:
            print(f'\n  ❌ Error: {e}')
            break
    print(f' → {encontrados} leads')
    pausa_sub = random.uniform(5, 7)
    print(f'  (Pausa entre subreddits: {pausa_sub:.1f}s)')
    time.sleep(pausa_sub)
    contador_subreddits += 1
if todos:
    vistos = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                vistos.add(row['username'])
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        fieldnames = ['username', 'subreddit', 'titulo', 'link_post', 'link_dm', 'horas', 'score', 'tiene_cv', 'mercado', 'precio', 'pais', 'paypal_ok', 'fecha_extraccion']
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if os.path.getsize(CSV_FILE) == 0:
            w.writeheader()
        for lead in todos:
            if lead['username'] not in vistos:
                lead['fecha_extraccion'] = str(fecha_hoy)
                w.writerow(lead)
    print(f'\n📂 CSV actualizado: {CSV_FILE}')
    leads_json = json.dumps(todos, ensure_ascii=False)
    html = f"""<!DOCTYPE html>\n<html><head><meta charset="UTF-8"><title>Leads - 600 Subreddits</title>\n<style>body{{font-family:Arial;background:#0a0e1a;color:#e0e0e0;padding:20px}}table{{width:100%;border-collapse:collapse;background:#1a1f2e}}th,td{{padding:8px;border-bottom:1px solid #2a2f3e}}th{{background:#0f1420}}a{{color:#ffd966}}.btn{{background:#2a2f3e;border:none;color:white;padding:4px 8px;border-radius:12px;cursor:pointer}}.contactado td{{background:#1e2a1e}}.descartado td{{background:#2a1e1e}}.cerrado td{{background:#1e2a2a}}</style>\n</head><body><h2>Leads (600 subreddits - pausa 5s entre leads)</h2><p>Total: {len(todos)} | <label><input type="checkbox" id="paypalOnly"> Solo PayPal</label></p>\n<table id="tabla"><thead><tr><th>#</th><th>Usuario</th><th>CV</th><th>H</th><th>Score</th><th>Mercado</th><th>País</th><th>PayPal</th><th>Título</th><th>Post</th><th>DM</th><th>Acciones</th></tr></thead><tbody id="cuerpo"></tbody></table>\n<script>const datos={leads_json}; let estado=JSON.parse(localStorage.getItem('estado')||'{{}}'); function marcar(uid,a){{estado[uid]=a;localStorage.setItem('estado',JSON.stringify(estado));mostrar();}} function mostrar(){{let p=document.getElementById('paypalOnly').checked; let h=''; let i=0; for(let l of datos){{if(p&&l.paypal_ok!=='True')continue; i++; let st=estado[l.username]||'pendiente'; let clase=st==='contactado'?'contactado':(st==='descartado'?'descartado':(st==='cerrado'?'cerrado':'')); h+=`<tr class="${{clase}}"><td>${{i}}</div></td><b>${{l.username}}</b><br><small>${{l.subreddit}}</small></td><td>${{l.tiene_cv}}</div><td>${{l.horas}}h</div><td>${{l.score}}/10</div><td>${{l.mercado}}<br>${{l.precio}}</div><td>${{l.pais}}</div></td>${{l.paypal_ok==='True'?'💰':'❌'}}</div><td>${{l.titulo.substring(0,50)}}...</div><td><a href='${{l.link_post}}' target='_blank'>Post</a></div><td><a href='${{l.link_dm}}' target='_blank'>DM</a></div><td><button class='btn' onclick=marcar('${{l.username}}','contactado')>📞 Contactar</button> <button class='btn' onclick=marcar('${{l.username}}','descartado')>❌ Descartar</button> <button class='btn' onclick=marcar('${{l.username}}','cerrado')>💰 Cerrar</button></td></tr>`;}} document.getElementById('cuerpo').innerHTML=h;}} document.getElementById('paypalOnly').onclick=mostrar; mostrar();</script></body></html>"""
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\n🌐 HTML generado: {OUTPUT_HTML}')
    print(f'\n✅ TOTAL LEADS: {len(todos)} | PayPal: {sum((1 for l in todos if l['paypal_ok']))}')
    try:
        os.system(f'termux-notification --title "Scraper" --content "Terminó. {len(todos)} leads capturados." --sound --vibrate')
    except:
        pass
else:
    print('\n⚠️ No se encontraron leads.')
