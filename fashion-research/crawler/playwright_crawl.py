"""
Playwright 기반 크롤러 v2
- 실제 Chrome headless → JS 완전 렌더링
- 브라우저 싱글톤 재사용 (속도 최적화)
- API 인터셉트 + DOM 추출 이중 구조
- 수집 항목: 제품명·브랜드·가격·이미지·시즌·제조년월·원산지·소재·리뷰수
"""

import re, json, threading
from bs4 import BeautifulSoup

_lock = threading.Lock()
_browser = None
_playwright_inst = None

# ════════════════════════════════════════════════════════
#  브라우저 싱글톤
# ════════════════════════════════════════════════════════
def get_browser():
    global _browser, _playwright_inst
    with _lock:
        if _browser is None or not _browser.is_connected():
            try:
                from playwright.sync_api import sync_playwright
                _playwright_inst = sync_playwright().start()
                _browser = _playwright_inst.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--lang=ko-KR',
                    ]
                )
            except Exception as e:
                raise RuntimeError(
                    f'Playwright 실행 실패: {e}\n'
                    f'해결: 터미널에서 "playwright install chromium" 실행 후 재시작'
                )
    return _browser

def close_browser():
    global _browser, _playwright_inst
    with _lock:
        try:
            if _browser: _browser.close()
        except: pass
        try:
            if _playwright_inst: _playwright_inst.stop()
        except: pass
        _browser = None
        _playwright_inst = None

# ════════════════════════════════════════════════════════
#  공통 추출 유틸
# ════════════════════════════════════════════════════════
def _safe_int(v):
    try: return int(str(v).replace(',','').replace(' ','').strip())
    except: return 0

def _extract_fabric(text: str) -> dict:
    fab = {'material':'', 'composition':'', 'weight':'', 'origin':''}

    # 혼용률
    for pat in [
        r'혼용률\s*[:\-]?\s*([가-힣a-zA-Z\s]+\d+%(?:\s*[,·/]\s*[가-힣a-zA-Z\s]+\d+%)*)',
        r'소재\s*[:\-]?\s*([가-힣a-zA-Z\s]+\d+%(?:\s*[,·/]\s*[가-힣a-zA-Z\s]+\d+%)*)',
        r'((?:면|폴리에스터|나일론|레이온|린넨|울|캐시미어|아크릴|모달|텐셀|'
        r'cotton|polyester|nylon|rayon|linen|wool)\s*\d+%'
        r'(?:[,·/ ]*[가-힣a-zA-Z\s]+\d+%)*)',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m: fab['composition'] = m.group(1).strip()[:150]; break

    # 소재명
    for pat in [
        r'소재명\s*[:\-]?\s*([가-힣a-zA-Z]+)',
        r'원단명?\s*[:\-]?\s*([가-힣a-zA-Z]+)',
        r'\b(데님|린넨|면|코튼|캐시미어|울|나일론|폴리에스터|레이온|모달|텐셀'
        r'|시폰|새틴|벨벳|트위드|플리스|니트|저지|스웨이드|코듀로이)\b',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m: fab['material'] = m.group(1).strip(); break

    # 원산지
    for pat in [
        r'원산지\s*[:\-]?\s*([가-힣a-zA-Z\s]+?)(?:\n|,|\.|·|\s{2}|$)',
        r'생산국\s*[:\-]?\s*([가-힣a-zA-Z\s]+?)(?:\n|,|\.|·|\s{2}|$)',
        r'Made\s+in\s+([A-Za-z가-힣\s]+?)(?:\n|,|\.|·|\s{2}|$)',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m: fab['origin'] = m.group(1).strip()[:50]; break

    # 중량
    m = re.search(r'(\d+\s*(?:oz|g/m²|수))', text, re.IGNORECASE)
    if m: fab['weight'] = m.group(1).strip()

    return fab

def _extract_season(text: str) -> str:
    """다양한 시즌 표기 패턴 인식"""
    patterns = [
        r'\b(SS|FW|AW|RE|PF|PRE)\s*(\d{2,4})\b',   # SS25, FW2025
        r'\b(\d{2,4})\s*(SS|FW|AW|S/S|F/W)\b',       # 25SS, 2025 S/S
        r'\b(봄여름|봄/여름)\s*(\d{2,4})\b',
        r'\b(가을겨울|가을/겨울)\s*(\d{2,4})\b',
    ]
    season_map = {'봄여름':'SS','봄/여름':'SS','가을겨울':'FW','가을/겨울':'FW',
                  'S/S':'SS','F/W':'FW','AW':'FW'}
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            g1, g2 = m.group(1).upper(), m.group(2).upper()
            s = season_map.get(g1, g1)
            yr = g2[-2:] if len(g2) == 4 else g2
            # 순서 판단: SS25 vs 25SS
            if re.match(r'\d', g1):  # g1이 숫자면 연도
                yr = g1[-2:] if len(g1) == 4 else g1
                s = season_map.get(g2, g2)
            return f"{s}{yr}"
    return ''

def _extract_mfg_date(text: str) -> str:
    """제조년월 추출"""
    patterns = [
        r'제조년월\s*[:\-]?\s*(\d{4}[\.\-/년]\s*\d{1,2})',
        r'제조일자\s*[:\-]?\s*(\d{4}[\.\-/년]\s*\d{1,2})',
        r'제조\s*[:\-]?\s*(\d{4}[\.\-/년]\s*\d{1,2})',
        r'(\d{4}년\s*\d{1,2}월)',
        r'(\d{4}\.\d{2})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # 정규화: 2024.03 → 2024.03
            raw = re.sub(r'년\s*', '.', raw)
            raw = re.sub(r'월', '', raw).strip('.')
            return raw
    return ''


# ════════════════════════════════════════════════════════
#  29cm 크롤러
# ════════════════════════════════════════════════════════
def crawl_29cm_product(url: str) -> dict:
    result = {
        'success': False, 'name':'', 'price':0, 'image_url':'', 'brand':'',
        'fabric':{'material':'','composition':'','weight':'','origin':''},
        'season':'', 'mfg_date':'',
        'review_count_29cm': 0,
        'error':''
    }
    captured = {}  # API 인터셉트 데이터

    try:
        browser = get_browser()
        ctx = browser.new_context(locale='ko-KR', extra_http_headers={'Accept-Language':'ko-KR,ko;q=0.9'})
        page = ctx.new_page()

        # ── API 인터셉트 ──
        def on_response(resp):
            try:
                u = resp.url
                if resp.status != 200: return
                ct = resp.headers.get('content-type','')
                if 'json' not in ct: return
                # 29cm 내부 API 패턴
                if 'api.29cm.co.kr' in u or ('29cm.co.kr' in u and '/api/' in u):
                    body = resp.json()
                    # 데이터 탐색: 여러 래퍼 구조 처리
                    candidate = body
                    for key in ['data','item','product','result','content']:
                        sub = body.get(key)
                        if isinstance(sub, dict):
                            candidate = sub
                            break
                    # 제품 데이터 확인
                    if candidate.get('itemName') or candidate.get('itemNo') or candidate.get('productNo'):
                        captured.update(candidate)
            except: pass

        page.on('response', on_response)
        page.goto(url, wait_until='domcontentloaded', timeout=25000)

        # 네트워크 완료 대기 (동적 로딩)
        try: page.wait_for_load_state('networkidle', timeout=10000)
        except: pass

        # ── 1순위: API 인터셉트 데이터 ──
        if captured:
            result['name']  = captured.get('itemName') or captured.get('productName') or ''
            result['brand'] = captured.get('brandName') or captured.get('brand') or ''
            pv = captured.get('consumerPrice') or captured.get('salePrice') or captured.get('price') or 0
            if pv: result['price'] = _safe_int(pv)
            for ik in ['listImageUrl','frontImageUrl','mainImageUrl','imageUrl']:
                v = captured.get(ik,'')
                if v: result['image_url'] = v; break
            # 리뷰 수
            rv = captured.get('reviewCount') or captured.get('reviewTotalCount') or captured.get('reviewCnt') or 0
            result['review_count_29cm'] = _safe_int(rv)
            # 시즌
            for sk in ['season','seasonCode','seasonName']:
                sv = captured.get(sk,'')
                if sv: result['season'] = _extract_season(str(sv)) or str(sv); break
            # 원단 (상세 HTML 안에 있음)
            for dk in ['frontDetail','detailContent','materialInfo','productInfo','description','itemDetail']:
                dv = captured.get(dk,'')
                if dv:
                    dt = BeautifulSoup(str(dv), 'html.parser').get_text(' ')
                    fab = _extract_fabric(dt)
                    if fab['composition'] or fab['material']:
                        result['fabric'] = fab
                        break
                    if not result['mfg_date']:
                        result['mfg_date'] = _extract_mfg_date(dt)

        # ── 2순위: 렌더링된 DOM ──
        full_text = ''
        try: full_text = page.inner_text('body')
        except: pass

        # 제품명
        if not result['name']:
            for sel in ['[class*="ProductName"]','[class*="productName"]',
                        '[class*="product-name"]','h1','h2']:
                try:
                    el = page.locator(sel).first
                    t = el.inner_text().strip()
                    if t and len(t) > 2: result['name'] = t; break
                except: pass

        # 브랜드
        if not result['brand']:
            for sel in ['[class*="BrandName"]','[class*="brandName"]',
                        'a[class*="brand"]','[class*="brand-name"]']:
                try:
                    t = page.locator(sel).first.inner_text().strip()
                    if t: result['brand'] = t; break
                except: pass

        # 가격
        if not result['price'] and full_text:
            for sel in ['[class*="Price"]','[class*="price"]','[class*="Amount"]']:
                try:
                    els = page.locator(sel).all()[:5]
                    for el in els:
                        t = el.inner_text().replace(',','').replace('원','')
                        nums = re.findall(r'\d{4,}', t)
                        for n in nums:
                            v = int(n)
                            if 5000 <= v <= 5000000:
                                result['price'] = v; break
                        if result['price']: break
                except: pass

        # 리뷰 수 (DOM)
        if not result['review_count_29cm'] and full_text:
            for pat in [r'리뷰\s*[(\[]?\s*([\d,]+)', r'([\d,]+)\s*개\s*리뷰',
                        r'review\s*[:\-]?\s*([\d,]+)']:
                m = re.search(pat, full_text, re.IGNORECASE)
                if m:
                    result['review_count_29cm'] = _safe_int(m.group(1)); break

        # 소재·시즌·제조년월·원산지 (DOM 전체 텍스트)
        if full_text:
            if not result['fabric']['composition']:
                fab = _extract_fabric(full_text)
                if fab['composition'] or fab['material']:
                    result['fabric'] = fab
            if not result['season']:
                result['season'] = _extract_season(full_text)
            if not result['mfg_date']:
                result['mfg_date'] = _extract_mfg_date(full_text)
            # 원산지 보완
            if not result['fabric']['origin']:
                result['fabric']['origin'] = _extract_fabric(full_text).get('origin','')

        # 이미지 (og: 메타)
        if not result['image_url']:
            try:
                v = page.locator('meta[property="og:image"]').get_attribute('content',timeout=3000)
                if v: result['image_url'] = v
            except: pass

        result['success'] = True
        ctx.close()

    except RuntimeError as e:
        result['error'] = str(e)
    except Exception as e:
        result['error'] = f'크롤링 오류: {e}'

    return result


# ════════════════════════════════════════════════════════
#  W컨셉 크롤러
# ════════════════════════════════════════════════════════
def crawl_wconcept_product(url: str) -> dict:
    result = {
        'success': False, 'name':'', 'price':0, 'image_url':'', 'brand':'',
        'fabric':{'material':'','composition':'','weight':'','origin':''},
        'season':'', 'mfg_date':'',
        'review_count_wconcept': 0,
        'error':''
    }
    captured = {}

    try:
        browser = get_browser()
        ctx = browser.new_context(locale='ko-KR')
        page = ctx.new_page()

        def on_response(resp):
            try:
                u = resp.url
                if resp.status != 200: return
                if 'json' not in resp.headers.get('content-type',''): return
                if 'api.wconcept' in u or ('wconcept.co.kr' in u and '/api/' in u):
                    body = resp.json()
                    candidate = body
                    for key in ['data','product','item','result','content']:
                        sub = body.get(key)
                        if isinstance(sub, dict):
                            candidate = sub; break
                    if candidate.get('productName') or candidate.get('productNo'):
                        captured.update(candidate)
            except: pass

        page.on('response', on_response)
        page.goto(url, wait_until='domcontentloaded', timeout=25000)
        try: page.wait_for_load_state('networkidle', timeout=10000)
        except: pass

        if captured:
            result['name']  = captured.get('productName') or captured.get('name','')
            result['brand'] = captured.get('brandName') or captured.get('brand','')
            pv = captured.get('salePrice') or captured.get('consumerPrice') or captured.get('price') or 0
            if pv: result['price'] = _safe_int(pv)
            for ik in ['mainImageUrl','listImageUrl','frontImageUrl','imageUrl']:
                v = captured.get(ik,'')
                if v: result['image_url'] = v; break
            rv = captured.get('reviewCount') or captured.get('reviewTotalCount') or captured.get('reviewCnt') or 0
            result['review_count_wconcept'] = _safe_int(rv)
            for sk in ['season','seasonCode','seasonName']:
                sv = captured.get(sk,'')
                if sv: result['season'] = _extract_season(str(sv)) or str(sv); break
            for dk in ['detailContent','productInfo','materialInfo','description']:
                dv = captured.get(dk,'')
                if dv:
                    dt = BeautifulSoup(str(dv), 'html.parser').get_text(' ')
                    fab = _extract_fabric(dt)
                    if fab['composition'] or fab['material']:
                        result['fabric'] = fab; break

        full_text = ''
        try: full_text = page.inner_text('body')
        except: pass

        if not result['name']:
            for sel in ['[class*="productName"]','[class*="ProductName"]',
                        '[class*="product-name"]','h1','h2']:
                try:
                    t = page.locator(sel).first.inner_text().strip()
                    if t and len(t) > 2: result['name'] = t; break
                except: pass

        if not result['brand']:
            for sel in ['[class*="brandName"]','[class*="BrandName"]','[class*="brand"]']:
                try:
                    t = page.locator(sel).first.inner_text().strip()
                    if t and len(t) > 1: result['brand'] = t; break
                except: pass

        if not result['price'] and full_text:
            for sel in ['[class*="price"]','[class*="Price"]','[class*="amount"]']:
                try:
                    els = page.locator(sel).all()[:5]
                    for el in els:
                        t = el.inner_text().replace(',','').replace('원','')
                        nums = re.findall(r'\d{4,}', t)
                        for n in nums:
                            v = int(n)
                            if 5000 <= v <= 5000000:
                                result['price'] = v; break
                        if result['price']: break
                except: pass

        if not result['review_count_wconcept'] and full_text:
            for pat in [r'리뷰\s*[(\[]?\s*([\d,]+)', r'([\d,]+)\s*개\s*리뷰']:
                m = re.search(pat, full_text, re.IGNORECASE)
                if m: result['review_count_wconcept'] = _safe_int(m.group(1)); break

        if full_text:
            if not result['fabric']['composition']:
                fab = _extract_fabric(full_text)
                if fab['composition'] or fab['material']:
                    result['fabric'] = fab
            if not result['season']:
                result['season'] = _extract_season(full_text)
            if not result['mfg_date']:
                result['mfg_date'] = _extract_mfg_date(full_text)
            if not result['fabric']['origin']:
                result['fabric']['origin'] = _extract_fabric(full_text).get('origin','')

        if not result['image_url']:
            try:
                v = page.locator('meta[property="og:image"]').get_attribute('content',timeout=3000)
                if v: result['image_url'] = v
            except: pass

        result['success'] = True
        ctx.close()

    except RuntimeError as e:
        result['error'] = str(e)
    except Exception as e:
        result['error'] = f'크롤링 오류: {e}'

    return result


# ════════════════════════════════════════════════════════
#  네이버 블로그 언급량 (Playwright DOM 직접 읽기)
# ════════════════════════════════════════════════════════
def crawl_naver_blog_count_pw(query: str, client_id: str='', client_secret: str='') -> int:
    """Playwright로 네이버 블로그 검색결과 수 추출"""
    # 1순위: 네이버 공식 API
    if client_id and client_secret:
        try:
            import requests
            r = requests.get(
                'https://openapi.naver.com/v1/search/blog.json',
                headers={'X-Naver-Client-Id': client_id, 'X-Naver-Client-Secret': client_secret},
                params={'query': query, 'display': 1},
                timeout=8
            )
            if r.status_code == 200:
                return r.json().get('total', 0)
        except: pass

    # 2순위: Playwright로 검색결과 페이지 읽기
    try:
        from urllib.parse import quote
        browser = get_browser()
        ctx = browser.new_context(locale='ko-KR')
        page = ctx.new_page()
        page.goto(
            f'https://search.naver.com/search.naver?where=blog&query={quote(query)}',
            wait_until='domcontentloaded', timeout=15000
        )
        try: page.wait_for_load_state('networkidle', timeout=5000)
        except: pass

        # 검색 결과 수 텍스트 추출
        full = page.inner_text('body')
        ctx.close()

        # 패턴들: "블로그 1~10 / 32,150건" 또는 "총 32,150건"
        for pat in [
            r'1[~\-]\d+\s*/\s*([\d,]+)\s*건',
            r'총\s*([\d,]+)\s*건',
            r'"totalCount"\s*:\s*(\d+)',
            r'([\d,]+)\s*건의\s*블로그',
        ]:
            m = re.search(pat, full)
            if m: return int(m.group(1).replace(',',''))
        return 0
    except: return 0


# ════════════════════════════════════════════════════════
#  인스타그램 언급량 (추정 방식)
# ════════════════════════════════════════════════════════
def crawl_instagram_count_pw(keyword: str) -> dict:
    """
    인스타그램 해시태그 수 추정
    - Instagram 로그인 차단 대응: 네이버·구글 검색량으로 추정
    - estimated: True 표시
    """
    from urllib.parse import quote
    tag = keyword.replace(' ','').replace('#','')
    result = {'count': 0, 'estimated': True, 'method': ''}

    # 1단계: 인스타그램 직접 시도 (로그인 없이 가끔 됨)
    try:
        browser = get_browser()
        ctx = browser.new_context(locale='ko-KR')
        page = ctx.new_page()
        page.goto(f'https://www.instagram.com/explore/tags/{quote(tag)}/',
                  wait_until='domcontentloaded', timeout=12000)
        try: page.wait_for_load_state('networkidle', timeout=5000)
        except: pass
        full = page.inner_text('body')
        ctx.close()

        # 게시물 수 패턴
        for pat in [r'([\d,.]+)\s*(?:만\s*)?게시물', r'([\d,]+)\s*posts']:
            m = re.search(pat, full, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(',','').replace('.','')
                if '만' in pat or '만' in full[m.start():m.end()+2]:
                    count = int(float(raw.replace('만','')) * 10000)
                else:
                    count = int(raw)
                if count > 0:
                    result = {'count': count, 'estimated': False, 'method': 'instagram_direct'}
                    return result
    except: pass

    # 2단계: 네이버 검색에서 인스타 게시물 수 추정
    try:
        browser = get_browser()
        ctx = browser.new_context(locale='ko-KR')
        page = ctx.new_page()
        page.goto(
            f'https://search.naver.com/search.naver?where=post&query={quote(keyword+" site:instagram.com")}',
            wait_until='domcontentloaded', timeout=12000
        )
        full = page.inner_text('body')
        ctx.close()
        for pat in [r'1[~\-]\d+\s*/\s*([\d,]+)\s*건', r'총\s*([\d,]+)\s*건']:
            m = re.search(pat, full)
            if m:
                est = int(m.group(1).replace(',','')) * 120
                result = {'count': est, 'estimated': True, 'method': 'naver_estimate'}
                return result
    except: pass

    # 3단계: 구글 검색 추정
    try:
        browser = get_browser()
        ctx = browser.new_context(locale='ko-KR')
        page = ctx.new_page()
        page.goto(
            f'https://www.google.com/search?q=site:instagram.com+{quote("#"+tag)}',
            wait_until='domcontentloaded', timeout=12000
        )
        full = page.inner_text('body')
        ctx.close()
        m = re.search(r'약\s*([\d,]+)\s*개', full)
        if not m: m = re.search(r'([\d,]+)\s*results', full, re.IGNORECASE)
        if m:
            est = int(m.group(1).replace(',','')) * 80
            result = {'count': est, 'estimated': True, 'method': 'google_estimate'}
            return result
    except: pass

    return result
