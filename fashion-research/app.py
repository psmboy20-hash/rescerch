"""
패션 리서치 툴 v3 - 통합 버전
- fashion-research UI (랭킹, 원단, 브랜드, 제품, 업데이트)
- arête 벌크 스캔 (카테고리 URL → 제품 일괄 분석)
- 시장 반응 속도 (제조년월 vs 첫 리뷰 차이)
순수 Python 내장 라이브러리 (Flask 불필요)
"""

import json, os, uuid, re, threading, time, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date
from urllib.parse import urlparse, parse_qs

# ─── Windows 비동기 이벤트 루프 설정 ───────────────────────────────
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ─── 전역 상태 ───────────────────────────────────────────────────
BULK_LOG = []
BULK_RUNNING = False
BULK_RESULT = {'meta': [], 'reviews': []}  # 최신 스캔 결과

IG_LOG = []
IG_RUNNING = False
IG_RESULT = {'posts': [], 'keywords': [], 'accounts': []}

YT_LOG = []
YT_RUNNING = False
YT_RESULT = {'videos': []}

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

    market_response = _get_market_response_data()

    data_json = json.dumps({
        'rankings': rankings,
        'brands': brands,
        'settings': settings,
        'products_all': products,
        'fabric_map': fabric_map,
        'last_updated': settings.get('last_updated','없음 (예시 데이터)'),
        'market_response': market_response['items'],
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
            # 민감 필드 마스킹
            for secret_key in ['naver_client_secret', 'instagram_password', 'openai_api_key', 'youtube_api_key']:
                if s.get(secret_key): s[secret_key] = '••••••••'
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

        # ── 벌크 스캔 상태 폴링 ──
        elif path == '/api/bulk/log':
            self.send_json({
                'logs': BULK_LOG,
                'running': BULK_RUNNING,
                'result': BULK_RESULT
            })

        # ── 시장 반응 속도 조회 ──
        elif path == '/api/market-response':
            self.send_json(_get_market_response_data())

        # ── Instagram 분석 로그 폴링 ──
        elif path == '/api/instagram/log':
            self.send_json({'logs': IG_LOG, 'running': IG_RUNNING, 'result': IG_RESULT})

        # ── YouTube 트렌드 로그 폴링 ──
        elif path == '/api/youtube/log':
            self.send_json({'logs': YT_LOG, 'running': YT_RUNNING, 'result': YT_RESULT})

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

        # ── 벌크 스캔 시작 ──
        elif path == '/api/bulk/start':
            global BULK_RUNNING
            if BULK_RUNNING:
                self.send_json({'success': False, 'message': '이미 스캔 중입니다'})
            else:
                category_url = data.get('category_url', '').strip()
                platform     = data.get('platform', '29cm').strip()
                limit        = int(data.get('limit', 20))
                if not category_url:
                    self.send_json({'success': False, 'error': 'category_url이 필요합니다'})
                    return
                t = threading.Thread(
                    target=run_bulk_scan_bg,
                    args=(category_url, platform, limit),
                    daemon=True
                )
                t.start()
                self.send_json({'success': True, 'message': f'벌크 스캔 시작 ({platform}, 최대 {limit}개)'})

        # ── 벌크 결과 → products.json 저장 ──
        elif path == '/api/bulk/save':
            items = data.get('items', [])
            if not items:
                self.send_json({'success': False, 'error': '저장할 항목이 없습니다'})
                return
            added = _save_bulk_to_products(items)
            self.send_json({'success': True, 'added': added})

        # ── Instagram 분석 시작 ──
        elif path == '/api/instagram/start':
            global IG_RUNNING
            if IG_RUNNING:
                self.send_json({'success': False, 'message': '이미 분석 중입니다'})
            else:
                hashtag   = data.get('hashtag', '').strip().lstrip('#')
                max_posts = int(data.get('max_posts', 20))
                if not hashtag:
                    self.send_json({'success': False, 'error': 'hashtag이 필요합니다'})
                    return
                t = threading.Thread(
                    target=run_instagram_bg,
                    args=(hashtag, max_posts),
                    daemon=True
                )
                t.start()
                self.send_json({'success': True, 'message': f'#{hashtag} 분석 시작 (최대 {max_posts}개)'})

        # ── Instagram 결과 → score_instagram 업데이트 ──
        elif path == '/api/instagram/apply':
            pid   = data.get('product_id', '')
            count = int(data.get('count', 0))
            if pid:
                products = load_json(PRODUCTS_FILE)
                for p in products:
                    if p['id'] == pid:
                        p['score_instagram'] = count
                        p['updated_date'] = date.today().isoformat()
                        break
                save_json(PRODUCTS_FILE, products)
                self.send_json({'success': True})
            else:
                self.send_json({'success': False, 'error': 'product_id 필요'})

        # ── YouTube 트렌드 검색 시작 ──
        elif path == '/api/youtube/start':
            global YT_RUNNING
            if YT_RUNNING:
                self.send_json({'success': False, 'message': '이미 검색 중입니다'})
            else:
                keyword     = data.get('keyword', '').strip()
                max_results = int(data.get('max_results', 15))
                get_comments = bool(data.get('get_comments', False))
                if not keyword:
                    self.send_json({'success': False, 'error': 'keyword가 필요합니다'})
                    return
                t = threading.Thread(
                    target=run_youtube_bg,
                    args=(keyword, max_results, get_comments),
                    daemon=True
                )
                t.start()
                self.send_json({'success': True, 'message': f'"{keyword}" YouTube 검색 시작'})

        # ── Settings 저장 (확장) ──
        elif path == '/api/settings':
            s = load_json(SETTINGS_FILE)
            safe_fields = [
                'naver_client_id', 'score_weights',
                'openai_api_key', 'youtube_api_key',
                'instagram_username', 'headless_mode',
                'scrape_delay_min', 'scrape_delay_max', 'max_pages'
            ]
            for f in safe_fields:
                if f in data:
                    s[f] = data[f]
            # secret 필드 마스킹 처리
            if 'naver_client_secret' in data and data['naver_client_secret'] != '••••••••':
                s['naver_client_secret'] = data['naver_client_secret']
            if 'instagram_password' in data and data['instagram_password'] != '••••••••':
                s['instagram_password'] = data['instagram_password']
            save_json(SETTINGS_FILE, s)
            self.send_json({'success': True})

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

# ─── 시장 반응 속도 데이터 계산 ──────────────────────────────────
def _get_market_response_data():
    """제조년월 vs 첫 리뷰 날짜 → 시장 반응 속도(일) 계산"""
    products = load_json(PRODUCTS_FILE)
    result = []
    for p in products:
        mfg = p.get('mfg_date', '')
        history = p.get('review_history', [])
        if not history:
            continue
        # 첫 리뷰 날짜 = review_history 중 가장 이른 날짜 (cnt_29cm 또는 cnt_wconcept > 0)
        first_review_month = None
        for h in sorted(history, key=lambda x: x.get('date','')):
            if h.get('cnt_29cm', 0) > 0 or h.get('cnt_wconcept', 0) > 0 or h.get('naver', 0) > 0:
                first_review_month = h.get('date', '')
                break
        if not first_review_month:
            first_review_month = history[0].get('date', '') if history else ''

        response_days = None
        if mfg and first_review_month:
            try:
                from datetime import datetime as dt
                mfg_clean = mfg.replace('.', '-').replace('/', '-')
                mfg_dt = dt.strptime(mfg_clean[:7], '%Y-%m')
                rev_dt = dt.strptime(first_review_month[:7], '%Y-%m')
                response_days = max(0, (rev_dt - mfg_dt).days)
            except Exception:
                pass

        result.append({
            'id': p.get('id', ''),
            'name': p.get('name', ''),
            'brand_name': p.get('brand_name', ''),
            'category': p.get('category', ''),
            'mfg_date': mfg,
            'first_review_month': first_review_month,
            'response_days': response_days,
            'total_score': round(p.get('total_score', 0), 1),
            'score_29cm': p.get('score_29cm', 0),
            'score_wconcept': p.get('score_wconcept', 0),
            'score_naver': p.get('score_naver', 0),
            'score_instagram': p.get('score_instagram', 0),
            'review_history': p.get('review_history', []),
            'image_url': p.get('image_url', ''),
            'url_29cm': p.get('url_29cm', ''),
            'url_wconcept': p.get('url_wconcept', ''),
        })
    # 응답속도 기준 정렬 (빠른 것 먼저)
    result.sort(key=lambda x: (x['response_days'] is None, x['response_days'] or 9999))
    return {'items': result}


# ─── 벌크 스캔 백그라운드 실행 ───────────────────────────────────
def run_bulk_scan_bg(category_url: str, platform: str, limit: int):
    """백그라운드에서 벌크 스캔 실행 → BULK_LOG / BULK_RESULT 업데이트"""
    global BULK_LOG, BULK_RUNNING, BULK_RESULT
    BULK_LOG = []
    BULK_RUNNING = True
    BULK_RESULT = {'meta': [], 'reviews': [], 'summary': {}}
    log = lambda msg: BULK_LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    log(f"🔍 [{platform}] 카테고리 스캔 시작: {category_url[:60]}...")
    log(f"📋 최대 {limit}개 제품 수집 예정")

    try:
        # scrapers 경로 추가
        import sys, os
        base = os.path.dirname(os.path.abspath(__file__))
        if base not in sys.path:
            sys.path.insert(0, base)

        from scrapers.bulk_scanner import run_bulk_scan
        # bulk_scanner의 callback은 (completed, total, msg) 3인자를 받음
        def _bulk_cb(completed, total, msg):
            log(f"[{completed}/{total}] {msg}")
        meta_df, reviews_df = run_bulk_scan(
            category_url=category_url,
            platform=platform,
            limit=limit,
            progress_callback=_bulk_cb
        )

        if meta_df is not None and not meta_df.empty:
            meta_records = meta_df.to_dict(orient='records')
            # datetime 직렬화
            for r in meta_records:
                for k, v in r.items():
                    if hasattr(v, 'isoformat'):
                        r[k] = v.isoformat()
                    elif v != v:  # NaN check
                        r[k] = None
            BULK_RESULT['meta'] = meta_records

            # 시장 반응 속도 계산
            resp_items = []
            for r in meta_records:
                mfg = r.get('manufacture_date') or ''
                first_rev = r.get('first_review_date') or ''
                response_days = r.get('market_response_days')
                resp_items.append({
                    'name': r.get('name',''),
                    'brand': r.get('brand',''),
                    'platform': r.get('platform',''),
                    'mfg_date': mfg,
                    'first_review_date': first_rev,
                    'response_days': response_days,
                    'review_count': r.get('review_count', 0),
                    'avg_rating': r.get('avg_rating', 0),
                    'url': r.get('url', ''),
                })
            BULK_RESULT['market_response'] = resp_items

            # 요약 통계
            total = len(meta_records)
            avg_reviews = sum(r.get('review_count', 0) or 0 for r in meta_records) / max(total, 1)
            avg_rating  = sum(r.get('avg_rating', 0) or 0 for r in meta_records) / max(total, 1)
            resp_vals = [r['response_days'] for r in resp_items if r['response_days'] is not None]
            avg_resp = sum(resp_vals) / len(resp_vals) if resp_vals else None
            BULK_RESULT['summary'] = {
                'total': total,
                'avg_reviews': round(avg_reviews, 1),
                'avg_rating': round(avg_rating, 2),
                'avg_response_days': round(avg_resp, 1) if avg_resp is not None else None,
            }
            log(f"✅ 완료: {total}개 제품, 평균 리뷰 {avg_reviews:.0f}건, 평균 반응속도 {avg_resp:.0f}일" if avg_resp else f"✅ 완료: {total}개 제품")
        else:
            log("⚠ 수집된 제품이 없습니다. URL 또는 플랫폼을 확인해주세요.")

        if reviews_df is not None and not reviews_df.empty:
            BULK_RESULT['reviews_count'] = len(reviews_df)
            log(f"📝 총 리뷰 {len(reviews_df)}건 수집")

    except ImportError as e:
        log(f"⚠ 스크래퍼 모듈 임포트 실패: {e}")
        log("pip install httpx playwright loguru pandas 실행 후 재시도하세요")
    except Exception as e:
        log(f"❌ 오류: {e}")
        import traceback
        for line in traceback.format_exc().splitlines()[-5:]:
            log(f"   {line}")
    finally:
        BULK_RUNNING = False


# ─── 벌크 결과 → products.json 저장 ───────────────────────────────
def _save_bulk_to_products(items: list) -> int:
    """벌크 스캔 결과를 products.json에 추가 (중복 URL 체크)"""
    products = load_json(PRODUCTS_FILE)
    settings = load_json(SETTINGS_FILE)
    added = 0
    existing_urls = set()
    for p in products:
        if p.get('url_29cm'):     existing_urls.add(p['url_29cm'])
        if p.get('url_wconcept'): existing_urls.add(p['url_wconcept'])

    for item in items:
        url = item.get('url', '')
        if url and url in existing_urls:
            continue  # 이미 있는 제품 skip
        platform = item.get('platform', '')
        new_p = {
            'id': f"p{uuid.uuid4().hex[:8]}",
            'brand_name': item.get('brand', ''),
            'name': item.get('name', ''),
            'category': _guess_category(url, item.get('name', '')),
            'season': '',
            'price': int(item.get('price') or 0),
            'url_29cm':     url if platform == '29cm' else '',
            'url_wconcept': url if platform == 'wconcept' else '',
            'image_url': item.get('image_url', ''),
            'fabric': {'material': '', 'composition': '', 'weight': '', 'origin': ''},
            'mfg_date': item.get('manufacture_date', ''),
            'score_29cm':     int(item.get('review_count', 0)) if platform == '29cm' else 0,
            'score_wconcept': int(item.get('review_count', 0)) if platform == 'wconcept' else 0,
            'score_naver': 0, 'score_instagram': 0,
            'total_score': 0, 'rank': 0, 'rank_all': 0, 'prev_rank': 0,
            'buzz': False,
            'added_date': date.today().isoformat(),
            'updated_date': date.today().isoformat(),
            'review_history': []
        }
        if url: existing_urls.add(url)
        products.append(new_p)
        added += 1

    if added > 0:
        products = calculate_rankings(products, settings)
        save_json(PRODUCTS_FILE, products)
    return added


# ─── Instagram 백그라운드 분석 ────────────────────────────────────
def run_instagram_bg(hashtag: str, max_posts: int):
    global IG_LOG, IG_RUNNING, IG_RESULT
    IG_LOG = []
    IG_RUNNING = True
    IG_RESULT = {'posts': [], 'keywords': [], 'accounts': []}
    log = lambda msg: IG_LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    log(f"📸 #{hashtag} Instagram 분석 시작 (최대 {max_posts}개)")

    try:
        import sys, os
        base = os.path.dirname(os.path.abspath(__file__))
        if base not in sys.path:
            sys.path.insert(0, base)

        # 설정에서 계정 정보 읽기
        settings = load_json(SETTINGS_FILE)
        ig_user = settings.get('instagram_username', 'jellygogo1')
        ig_pass = settings.get('instagram_password', 'tjdan1020123!!')

        # 환경변수 주입 (agent가 os.getenv로 읽음)
        os.environ['INSTAGRAM_USERNAME'] = ig_user
        os.environ['INSTAGRAM_PASSWORD'] = ig_pass
        os.environ['INSTAGRAM_COOKIE_FILE'] = os.path.join(base, 'data', 'instagram_cookies.json')

        from agents.instagram_agent import InstagramAgent
        agent = InstagramAgent(username=ig_user, password=ig_pass)

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        posts = loop.run_until_complete(agent.search_hashtag(hashtag, max_posts=max_posts))
        loop.close()

        log(f"✅ 포스트 {len(posts)}개 수집 완료")

        # 직렬화
        post_dicts = []
        for p in posts:
            d = p.to_dict()
            # screenshot_path 제거 (JSON 직렬화 가능하게)
            d.pop('screenshot_path', None)
            post_dicts.append(d)
        IG_RESULT['posts'] = post_dicts

        # 키워드 추출 (해시태그 기반)
        import re as _re
        kw_counter = {}
        for p in posts:
            tags = _re.findall(r'#(\w+)', p.caption or '')
            for t in tags:
                t_lower = t.lower()
                if t_lower != hashtag.lower():
                    kw_counter[t_lower] = kw_counter.get(t_lower, 0) + 1
        top_kw = sorted(kw_counter.items(), key=lambda x: x[1], reverse=True)[:30]
        IG_RESULT['keywords'] = [{'tag': k, 'count': v} for k, v in top_kw]
        log(f"🏷️ 키워드 {len(top_kw)}개 추출")

        # 계정 분석
        acc_counter = {}
        for p in posts:
            if p.account:
                acc_counter[p.account] = acc_counter.get(p.account, 0) + 1
        top_acc = sorted(acc_counter.items(), key=lambda x: x[1], reverse=True)[:20]
        IG_RESULT['accounts'] = [{'account': a, 'posts': c} for a, c in top_acc]

        # 통계
        total_likes    = sum(p.likes or 0 for p in posts)
        total_comments = sum(p.comments or 0 for p in posts)
        IG_RESULT['summary'] = {
            'total_posts': len(posts),
            'avg_likes':    round(total_likes / max(len(posts), 1), 1),
            'avg_comments': round(total_comments / max(len(posts), 1), 1),
            'video_ratio':  round(sum(1 for p in posts if p.is_video) / max(len(posts), 1) * 100, 1),
        }
        log(f"📊 평균 좋아요 {IG_RESULT['summary']['avg_likes']}, 평균 댓글 {IG_RESULT['summary']['avg_comments']}")

    except ImportError as e:
        log(f"⚠ 모듈 없음: {e} → pip install playwright loguru pandas pillow 실행 필요")
    except Exception as e:
        log(f"❌ 오류: {e}")
        import traceback
        for line in traceback.format_exc().splitlines()[-5:]:
            log(f"   {line}")
    finally:
        IG_RUNNING = False


# ─── YouTube 백그라운드 검색 ──────────────────────────────────────
def run_youtube_bg(keyword: str, max_results: int, get_comments: bool):
    global YT_LOG, YT_RUNNING, YT_RESULT
    YT_LOG = []
    YT_RUNNING = True
    YT_RESULT = {'videos': []}
    log = lambda msg: YT_LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    log(f"🎬 '{keyword}' YouTube 검색 시작 (최대 {max_results}개)")

    try:
        import sys, os
        base = os.path.dirname(os.path.abspath(__file__))
        if base not in sys.path:
            sys.path.insert(0, base)

        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        videos = loop.run_until_complete(agent.search_videos(keyword, max_results=max_results))
        log(f"✅ 영상 {len(videos)}개 수집")

        # 댓글 수집 (요청 시)
        if get_comments and videos:
            log(f"💬 상위 5개 영상 댓글 수집 중...")
            for v in videos[:5]:
                try:
                    comments = loop.run_until_complete(
                        agent.get_video_comments(v.video_url, max_comments=10)
                    )
                    v.top_comments = comments
                    log(f"  댓글 {len(comments)}개 [{v.title[:30]}]")
                except Exception as ce:
                    log(f"  댓글 오류: {ce}")
        loop.close()

        # 직렬화
        YT_RESULT['videos'] = [v.to_dict() for v in videos]

        # 통계
        total_views = sum(v.views or 0 for v in videos)
        YT_RESULT['summary'] = {
            'total': len(videos),
            'total_views': total_views,
            'avg_views': round(total_views / max(len(videos), 1)),
        }
        log(f"📊 총 조회수 {total_views:,}, 평균 {YT_RESULT['summary']['avg_views']:,}")

    except ImportError as e:
        log(f"⚠ 모듈 없음: {e}")
    except Exception as e:
        log(f"❌ 오류: {e}")
        import traceback
        for line in traceback.format_exc().splitlines()[-5:]:
            log(f"   {line}")
    finally:
        YT_RUNNING = False


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
    print("🛍️  패션 리서치 툴 v4 (통합)")
    print(f"📌 http://localhost:{PORT}")
    print("="*50)
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()
