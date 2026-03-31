"""
패션 리서치 툴 v2 - 상세 페이지 + 리뷰 추이 + 원단 분석
순수 Python 내장 라이브러리 (Flask 불필요)
"""

import json, os, uuid, re, threading, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date
from urllib.parse import urlparse, parse_qs

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, 'data')
RANKINGS_DIR= os.path.join(DATA_DIR, 'rankings')
TEMPLATE_FILE = os.path.join(BASE_DIR, 'templates', 'index.html')

PRODUCTS_FILE = os.path.join(DATA_DIR, 'products.json')
BRANDS_FILE   = os.path.join(DATA_DIR, 'brands.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')

os.makedirs(RANKINGS_DIR, exist_ok=True)

# ─── 데이터 헬퍼 ─────────────────────────────────────────────────
def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [] if path.endswith(('products.json','brands.json')) else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── 버즈 감지 ────────────────────────────────────────────────────
def detect_buzz(product):
    """최근 2개월 리뷰 수 비교 → 2배 이상이면 버즈"""
    history = product.get('review_history', [])
    if len(history) < 2:
        return False
    prev = history[-2]
    curr = history[-1]
    prev_total = prev.get('naver',0) + prev.get('instagram',0)
    curr_total = curr.get('naver',0) + curr.get('instagram',0)
    return curr_total >= prev_total * 1.8 and prev_total > 0

# ─── 랭킹 계산 ───────────────────────────────────────────────────
def calculate_rankings(products, settings):
    weights = settings.get('score_weights', {
        'score_29cm': 0.30, 'score_wconcept': 0.30,
        'score_naver': 0.20, 'score_instagram': 0.20
    })
    keys = ['score_29cm','score_wconcept','score_naver','score_instagram']
    max_vals = {}
    for k in keys:
        vals = [p.get(k,0) for p in products if p.get(k,0)>0]
        max_vals[k] = max(vals) if vals else 1

    for p in products:
        p['total_score'] = sum(
            (p.get(k,0)/max_vals[k]*100)*weights.get(k,0.25) for k in keys
        )
        p['buzz'] = detect_buzz(p)

    for cat in ['denim','shirt','tshirt']:
        cats = sorted([p for p in products if p.get('category')==cat],
                      key=lambda x: x.get('total_score',0), reverse=True)
        for i,p in enumerate(cats,1):
            p['rank'] = i
    for i,p in enumerate(sorted(products, key=lambda x:x.get('total_score',0), reverse=True),1):
        p['rank_all'] = i
    return products

# ─── 페이지 렌더 ─────────────────────────────────────────────────
def render_page():
    products  = load_json(PRODUCTS_FILE)
    brands    = load_json(BRANDS_FILE)
    settings  = load_json(SETTINGS_FILE)
    products  = calculate_rankings(products, settings)

    rankings = {}
    for cat in ['denim','shirt','tshirt']:
        rankings[cat] = sorted([p for p in products if p.get('category')==cat],
                               key=lambda x:x.get('rank',999))[:50]
    rankings['all'] = sorted(products, key=lambda x:x.get('rank_all',999))[:50]

    # 원단 분석용 데이터
    fabric_map = {}
    for p in products:
        mat = (p.get('fabric') or {}).get('material','기타')
        if mat not in fabric_map:
            fabric_map[mat] = []
        fabric_map[mat].append({
            'id': p['id'], 'brand_name': p.get('brand_name',''),
            'name': p.get('name',''), 'price': p.get('price',0),
            'category': p.get('category',''), 'season': p.get('season',''),
            'composition': (p.get('fabric') or {}).get('composition',''),
            'total_score': round(p.get('total_score',0),1)
        })

    data_json = json.dumps({
        'rankings': rankings,
        'brands': brands,
        'settings': settings,
        'products_all': products,
        'fabric_map': fabric_map,
        'last_updated': settings.get('last_updated','없음 (예시 데이터)')
    }, ensure_ascii=False)

    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    injection = f'<script id="__sd__">window.__DATA__={data_json};</script>'
    html = html.replace('</head>', injection + '\n</head>', 1)
    return html

# ─── HTTP 핸들러 ─────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get('Content-Length',0))
        if length:
            raw = self.rfile.read(length)
            try: return json.loads(raw.decode('utf-8'))
            except: return {}
        return {}

    def do_GET(self):
        path = urlparse(self.path).path.rstrip('/')

        if path in ('','/'): self.send_html(render_page())

        elif path == '/api/products':
            self.send_json(load_json(PRODUCTS_FILE))

        elif path == '/api/brands':
            self.send_json(load_json(BRANDS_FILE))

        elif path == '/api/settings':
            s = load_json(SETTINGS_FILE)
            if s.get('naver_client_secret'): s['naver_client_secret'] = '••••••••'
            self.send_json(s)

        # 제품 상세
        elif re.match(r'^/api/products/[^/]+$', path):
            pid = path.split('/')[-1]
            products = load_json(PRODUCTS_FILE)
            p = next((x for x in products if x['id']==pid), None)
            if p: self.send_json(p)
            else: self.send_json({'error':'not found'},404)

        # 업데이트 로그 폴링
        elif path == '/api/update/log':
            self.send_json({'logs': UPDATE_LOG, 'running': UPDATE_RUNNING})

        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path.rstrip('/')
        data = self.read_body()

        if path == '/api/products/add':
            products = load_json(PRODUCTS_FILE)
            new_p = {
                'id': f"p{uuid.uuid4().hex[:8]}",
                'brand_id': data.get('brand_id',''),
                'brand_name': data.get('brand_name',''),
                'name': data.get('name',''),
                'category': data.get('category','all'),
                'season': data.get('season',''),
                'price': int(data.get('price',0)),
                'url_29cm': data.get('url_29cm',''),
                'url_wconcept': data.get('url_wconcept',''),
                'image_url': data.get('image_url',''),
                'fabric': data.get('fabric', {'material':'','composition':'','weight':'','origin':''}),
                'mfg_date': data.get('mfg_date',''),
                'score_29cm': int(data.get('score_29cm',0)),
                'score_wconcept': int(data.get('score_wconcept',0)),
                'score_naver': int(data.get('score_naver',0)),
                'score_instagram': int(data.get('score_instagram',0)),
                'total_score': 0, 'rank': 0, 'rank_all': 0, 'prev_rank': 0,
                'buzz': False,
                'added_date': date.today().isoformat(),
                'updated_date': date.today().isoformat(),
                'review_history': []
            }
            products.append(new_p)
            save_json(PRODUCTS_FILE, products)
            self.send_json({'success':True,'product':new_p})

        elif path == '/api/brands/add':
            brands = load_json(BRANDS_FILE)
            new_b = {
                'id': f"b{uuid.uuid4().hex[:8]}",
                'name': data.get('name',''), 'name_en': data.get('name_en',''),
                'concept': data.get('concept',[]),
                'platform_29cm': data.get('platform_29cm',False),
                'platform_wconcept': data.get('platform_wconcept',False),
                'active': True
            }
            brands.append(new_b)
            save_json(BRANDS_FILE, brands)
            self.send_json({'success':True,'brand':new_b})

        # 리뷰 히스토리 추가
        elif re.match(r'^/api/products/[^/]+/review$', path):
            pid = path.split('/')[-2]
            products = load_json(PRODUCTS_FILE)
            for p in products:
                if p['id'] == pid:
                    if 'review_history' not in p: p['review_history'] = []
                    entry = {
                        'date': data.get('date', date.today().strftime('%Y-%m')),
                        'naver': int(data.get('naver',0)),
                        'instagram': int(data.get('instagram',0)),
                        'cnt_29cm': int(data.get('cnt_29cm',0)),
                        'cnt_wconcept': int(data.get('cnt_wconcept',0))
                    }
                    # 같은 날짜면 업데이트
                    existing = [i for i,h in enumerate(p['review_history']) if h['date']==entry['date']]
                    if existing: p['review_history'][existing[0]] = entry
                    else: p['review_history'].append(entry)
                    p['review_history'].sort(key=lambda x:x['date'])
                    p['score_naver'] = entry['naver']
                    p['score_instagram'] = entry['instagram']
                    p['score_29cm'] = entry['cnt_29cm']
                    p['score_wconcept'] = entry['cnt_wconcept']
                    p['updated_date'] = date.today().isoformat()
                    save_json(PRODUCTS_FILE, products)
                    self.send_json({'success':True})
                    return
            self.send_json({'success':False,'error':'not found'},404)

        elif path == '/api/parse-url':
            url = data.get('url','').strip()
            if not url:
                self.send_json({'success':False,'error':'URL이 비어있습니다'})
                return
            try:
                from crawler.auto_crawl import crawl_29cm_product, crawl_wconcept_product
                if '29cm.co.kr' in url:
                    d = crawl_29cm_product(url)
                    d['platform'] = '29cm'
                    d['url_29cm'] = url
                    d['url_wconcept'] = ''
                    # 카테고리 자동 추론 (URL 경로 기반)
                    d['category'] = _guess_category(url, d.get('name',''))
                elif 'wconcept.co.kr' in url:
                    d = crawl_wconcept_product(url)
                    d['platform'] = 'wconcept'
                    d['url_29cm'] = ''
                    d['url_wconcept'] = url
                    d['category'] = _guess_category(url, d.get('name',''))
                else:
                    self.send_json({'success':False,'error':'29cm 또는 W컨셉 URL만 지원합니다'})
                    return
                self.send_json(d)
            except Exception as e:
                self.send_json({'success':False,'error':str(e)})

        elif path == '/api/update/manual':
            # 동기 업데이트 (레거시 호환)
            try:
                count = run_update()
                self.send_json({'success':True,'message':f'업데이트 완료: {count}개 제품'})
            except Exception as e:
                self.send_json({'success':False,'error':str(e)})

        elif path == '/api/update/start':
            # 비동기 백그라운드 업데이트 시작
            if UPDATE_RUNNING:
                self.send_json({'success':False,'message':'이미 업데이트 중입니다'})
            else:
                t = threading.Thread(target=run_update, daemon=True)
                t.start()
                self.send_json({'success':True,'message':'업데이트 시작됨 (백그라운드)'})

        # 단일 제품 온디맨드 크롤링
        elif re.match(r'^/api/products/[^/]+/crawl$', path):
            pid = path.split('/')[-2]
            if UPDATE_RUNNING:
                self.send_json({'success':False,'message':'이미 업데이트 중입니다'})
            else:
                t = threading.Thread(target=run_single_product_update, args=(pid,), daemon=True)
                t.start()
                self.send_json({'success':True,'message':f'{pid} 크롤링 시작'})

        elif path == '/api/settings':
            s = load_json(SETTINGS_FILE)
            if 'naver_client_id' in data: s['naver_client_id'] = data['naver_client_id']
            if 'naver_client_secret' in data and data['naver_client_secret'] != '••••••••':
                s['naver_client_secret'] = data['naver_client_secret']
            if 'score_weights' in data: s['score_weights'] = data['score_weights']
            save_json(SETTINGS_FILE, s)
            self.send_json({'success':True})

        else:
            self.send_response(404); self.end_headers()

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip('/')
        m = re.match(r'^/api/products/([^/]+)$', path)
        if m:
            pid = m.group(1)
            products = [p for p in load_json(PRODUCTS_FILE) if p['id']!=pid]
            save_json(PRODUCTS_FILE, products)
            self.send_json({'success':True}); return
        m = re.match(r'^/api/brands/([^/]+)$', path)
        if m:
            bid = m.group(1)
            brands = [b for b in load_json(BRANDS_FILE) if b['id']!=bid]
            save_json(BRANDS_FILE, brands)
            self.send_json({'success':True}); return
        self.send_response(404); self.end_headers()

    def do_PUT(self):
        path = urlparse(self.path).path.rstrip('/')
        data = self.read_body()
        m = re.match(r'^/api/products/([^/]+)$', path)
        if m:
            pid = m.group(1)
            products = load_json(PRODUCTS_FILE)
            for p in products:
                if p['id'] == pid:
                    for k in ['name','brand_name','category','season','price',
                              'url_29cm','url_wconcept','image_url','fabric',
                              'score_29cm','score_wconcept','score_naver','score_instagram']:
                        if k in data: p[k] = data[k]
                    p['updated_date'] = date.today().isoformat()
                    save_json(PRODUCTS_FILE, products)
                    self.send_json({'success':True,'product':p}); return
            self.send_json({'success':False,'error':'not found'},404); return
        self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.end_headers()

# ─── 카테고리 자동 추론 ───────────────────────────────────────────
def _guess_category(url: str, name: str) -> str:
    """URL과 제품명에서 카테고리 추론"""
    combined = (url + ' ' + name).lower()
    if any(k in combined for k in ['denim','데님','jeans','진','청바지','청팬츠']):
        return 'denim'
    if any(k in combined for k in ['shirt','셔츠','blouse','블라우스']):
        return 'shirt'
    if any(k in combined for k in ['tshirt','t-shirt','반팔','나시','sleeveless','크롭']):
        return 'tshirt'
    return 'all'

# ─── 업데이트 (자동 크롤링 풀 통합) ────────────────────────────────
UPDATE_LOG = []          # 실시간 로그 버퍼 (UI에서 폴링 가능)
UPDATE_RUNNING = False   # 업데이트 실행 상태 플래그

def run_update():
    global UPDATE_LOG, UPDATE_RUNNING
    UPDATE_LOG = []
    UPDATE_RUNNING = True
    log = lambda msg: UPDATE_LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    products = load_json(PRODUCTS_FILE)
    settings = load_json(SETTINGS_FILE)
    today = date.today().isoformat()
    month = date.today().strftime('%Y-%m')
    nid   = settings.get('naver_client_id','')
    nsec  = settings.get('naver_client_secret','')

    log(f"총 {len(products)}개 제품 크롤링 시작")

    for p in products:
        brand = p.get('brand_name','')
        name  = p.get('name','')
        log(f"▶ {brand} - {name}")

        # ── 29cm 상세 파싱 ──
        if p.get('url_29cm'):
            try:
                from crawler.auto_crawl import crawl_29cm_product
                d = crawl_29cm_product(p['url_29cm'])
                if d['success']:
                    if d.get('image_url'): p['image_url'] = d['image_url']
                    if d.get('fabric',{}).get('composition'): p['fabric'] = d['fabric']
                    elif d.get('fabric',{}).get('material'): p.setdefault('fabric',{})['material'] = d['fabric']['material']
                    if d.get('season'): p['season'] = d['season']
                    if d.get('mfg_date'): p['mfg_date'] = d['mfg_date']
                    if d.get('price') and not p.get('price'): p['price'] = d['price']
                    if d.get('review_count_29cm'): p['score_29cm'] = d['review_count_29cm']
                    log(f"  ✅ 29cm: 리뷰 {d.get('review_count_29cm',0)}건 | 시즌 {d.get('season','—')} | 소재 {d.get('fabric',{}).get('composition','—')[:30]}")
                else:
                    log(f"  ⚠ 29cm 파싱 실패: {d['error']}")
            except Exception as e:
                log(f"  ⚠ 29cm 오류: {e}")

        # ── W컨셉 상세 파싱 ──
        if p.get('url_wconcept'):
            try:
                from crawler.auto_crawl import crawl_wconcept_product
                d = crawl_wconcept_product(p['url_wconcept'])
                if d['success']:
                    if d.get('image_url') and not p.get('image_url'): p['image_url'] = d['image_url']
                    if d.get('fabric',{}).get('composition') and not p.get('fabric',{}).get('composition'):
                        p['fabric'] = d['fabric']
                    if d.get('season') and not p.get('season'): p['season'] = d['season']
                    if d.get('mfg_date') and not p.get('mfg_date'): p['mfg_date'] = d['mfg_date']
                    if d.get('review_count_wconcept'): p['score_wconcept'] = d['review_count_wconcept']
                    log(f"  ✅ W컨셉: 리뷰 {d.get('review_count_wconcept',0)}건")
                else:
                    log(f"  ⚠ W컨셉 파싱 실패: {d['error']}")
            except Exception as e:
                log(f"  ⚠ W컨셉 오류: {e}")

        # ── 네이버 블로그 수 ──
        if brand and name:
            try:
                from crawler.auto_crawl import crawl_naver_blog_count
                query = f"{brand} {name} 후기"
                count = crawl_naver_blog_count(query, nid, nsec)
                if count > 0:
                    p['score_naver'] = count
                    log(f"  📝 네이버 블로그 {count:,}건")
                else:
                    log(f"  ⚠ 네이버 결과 없음 (기존 유지)")
            except Exception as e:
                log(f"  ⚠ 네이버 오류: {e}")

        # ── 인스타그램 해시태그 수 ──
        if brand:
            try:
                from crawler.crawler_instagram import get_ig_hashtag_count
                tag = f"{brand}{name}".replace(' ','')
                r = get_ig_hashtag_count(tag)
                if not r['success'] or r['count'] == 0:
                    # 브랜드명만으로 재시도
                    r = get_ig_hashtag_count(brand)
                if r['count'] > 0:
                    p['score_instagram'] = r['count']
                    est = ' (추정)' if r.get('estimated') else ''
                    log(f"  📸 인스타그램 {r['count']:,}건{est} [{r['method']}]")
                else:
                    log(f"  ⚠ 인스타그램 조회 실패 (로그인 필요할 수 있음)")
            except Exception as e:
                log(f"  ⚠ 인스타그램 오류: {e}")

        # ── 리뷰 히스토리 스냅샷 저장 ──
        if 'review_history' not in p: p['review_history'] = []
        existing = [i for i,h in enumerate(p['review_history']) if h.get('date')==month]
        entry = {
            'date': month,
            'naver': p.get('score_naver',0),
            'instagram': p.get('score_instagram',0),
            'cnt_29cm': p.get('score_29cm',0),
            'cnt_wconcept': p.get('score_wconcept',0)
        }
        if existing: p['review_history'][existing[0]] = entry
        else: p['review_history'].append(entry)
        p['review_history'].sort(key=lambda x:x['date'])
        p['updated_date'] = today

    products = calculate_rankings(products, settings)
    save_json(PRODUCTS_FILE, products)
    save_json(os.path.join(RANKINGS_DIR, f"{today}.json"), {'date':today,'products':products})
    settings['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_json(SETTINGS_FILE, settings)
    log(f"✅ 완료 — {len(products)}개 제품 업데이트")
    UPDATE_RUNNING = False
    return len(products)

def run_single_product_update(pid):
    """단일 제품 온디맨드 크롤링"""
    global UPDATE_LOG, UPDATE_RUNNING
    UPDATE_LOG = []
    UPDATE_RUNNING = True
    log = lambda msg: UPDATE_LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    products = load_json(PRODUCTS_FILE)
    settings = load_json(SETTINGS_FILE)
    today = date.today().isoformat()
    month = date.today().strftime('%Y-%m')
    nid   = settings.get('naver_client_id','')
    nsec  = settings.get('naver_client_secret','')

    p = next((x for x in products if x['id'] == pid), None)
    if not p:
        UPDATE_LOG.append("⚠ 제품을 찾을 수 없습니다")
        UPDATE_RUNNING = False
        return

    brand = p.get('brand_name','')
    name  = p.get('name','')
    log(f"▶ [{pid}] {brand} - {name} 크롤링 시작")

    if p.get('url_29cm'):
        try:
            from crawler.auto_crawl import crawl_29cm_product
            d = crawl_29cm_product(p['url_29cm'])
            if d['success']:
                if d['image_url']: p['image_url'] = d['image_url']
                if d.get('fabric',{}).get('composition'): p['fabric'] = d['fabric']
                if d.get('season'): p['season'] = d['season']
                log(f"  ✅ 29cm 파싱 성공")
            else:
                log(f"  ⚠ 29cm 파싱 실패: {d['error']}")
        except Exception as e:
            log(f"  ⚠ 29cm 오류: {e}")

    if p.get('url_wconcept'):
        try:
            from crawler.auto_crawl import crawl_wconcept_product
            d = crawl_wconcept_product(p['url_wconcept'])
            if d['success']:
                if d['image_url'] and not p.get('image_url'): p['image_url'] = d['image_url']
                if d.get('fabric',{}).get('composition') and not p.get('fabric',{}).get('composition'): p['fabric'] = d['fabric']
                log(f"  ✅ W컨셉 파싱 성공")
            else:
                log(f"  ⚠ W컨셉 파싱 실패: {d['error']}")
        except Exception as e:
            log(f"  ⚠ W컨셉 오류: {e}")

    if brand and name:
        try:
            from crawler.auto_crawl import crawl_naver_blog_count
            query = f"{brand} {name} 후기"
            count = crawl_naver_blog_count(query, nid, nsec)
            if count > 0:
                p['score_naver'] = count
                log(f"  📝 네이버 블로그 {count:,}건")
            else:
                log(f"  ⚠ 네이버 결과 없음 (기존 유지)")
        except Exception as e:
            log(f"  ⚠ 네이버 오류: {e}")

    if brand:
        try:
            from crawler.crawler_instagram import get_ig_hashtag_count
            tag = f"{brand}{name}".replace(' ','')
            r = get_ig_hashtag_count(tag)
            if not r['success'] or r['count'] == 0:
                r = get_ig_hashtag_count(brand)
            if r['count'] > 0:
                p['score_instagram'] = r['count']
                est = ' (추정)' if r.get('estimated') else ''
                log(f"  📸 인스타그램 {r['count']:,}건{est} [{r['method']}]")
            else:
                log(f"  ⚠ 인스타그램 조회 실패")
        except Exception as e:
            log(f"  ⚠ 인스타그램 오류: {e}")

    if 'review_history' not in p: p['review_history'] = []
    existing = [i for i,h in enumerate(p['review_history']) if h.get('date')==month]
    entry = {
        'date': month,
        'naver': p.get('score_naver',0),
        'instagram': p.get('score_instagram',0),
        'cnt_29cm': p.get('score_29cm',0),
        'cnt_wconcept': p.get('score_wconcept',0)
    }
    if existing: p['review_history'][existing[0]] = entry
    else: p['review_history'].append(entry)
    p['review_history'].sort(key=lambda x:x['date'])
    p['updated_date'] = today

    products = calculate_rankings(products, settings)
    save_json(PRODUCTS_FILE, products)
    log(f"✅ [{pid}] 크롤링 완료")
    UPDATE_RUNNING = False

def scheduler():
    while True:
        if datetime.now().hour==0 and datetime.now().minute==0:
            try: run_update()
            except: pass
            time.sleep(61)
        time.sleep(30)

if __name__ == '__main__':
    try:
        p = load_json(PRODUCTS_FILE)
        s = load_json(SETTINGS_FILE)
        if p: save_json(PRODUCTS_FILE, calculate_rankings(p, s))
    except: pass

    threading.Thread(target=scheduler, daemon=True).start()
    PORT = 5000
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print("="*50)
    print("🛍️  패션 리서치 툴 v2")
    print(f"📌 http://localhost:{PORT}")
    print("="*50)
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()
