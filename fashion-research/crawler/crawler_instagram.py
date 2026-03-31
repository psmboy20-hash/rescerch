"""
인스타그램 해시태그/언급 수 수집기
- 로그인 없이 가능한 공개 엔드포인트 활용
- 실패 시 네이버에서 인스타그램 언급 수 추정
"""

import requests
import re
import time
import random
import json
from urllib.parse import quote

UA_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.90 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def get_ig_hashtag_count(keyword: str) -> dict:
    """
    인스타그램 해시태그 게시물 수 조회
    여러 방법 순서대로 시도

    Returns: {'count': int, 'method': str, 'success': bool}
    """
    tag = keyword.strip().replace(' ', '').replace('#', '')

    # ── 방법 1: Instagram Web App API (비공식 GraphQL) ──
    result = _try_ig_web_api(tag)
    if result['success']:
        return result

    # ── 방법 2: Instagram 모바일 앱 API ──
    result = _try_ig_mobile_api(tag)
    if result['success']:
        return result

    # ── 방법 3: Naver에서 인스타그램 언급 수 추정 ──
    result = _estimate_via_naver(keyword)
    return result


def _try_ig_web_api(tag: str) -> dict:
    """Instagram 웹 비공식 API 시도"""
    try:
        sess = requests.Session()
        sess.headers.update({
            'User-Agent': random.choice(UA_POOL),
            'Accept': '*/*',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Referer': 'https://www.instagram.com/',
            'X-IG-App-ID': '936619743392459',
            'X-Requested-With': 'XMLHttpRequest',
        })

        # 먼저 메인 페이지 방문해서 csrf token / session 획득
        r0 = sess.get('https://www.instagram.com/', timeout=8)
        time.sleep(random.uniform(1.0, 2.0))

        # csrf token 추출
        csrf = re.search(r'"csrf_token":"([^"]+)"', r0.text)
        if csrf:
            sess.headers.update({'X-CSRFToken': csrf.group(1)})

        # 태그 검색 API
        api_url = f'https://www.instagram.com/web/search/topsearch/?context=hashtag&query={quote(tag)}&include_reel=false'
        r1 = sess.get(api_url, timeout=10)

        if r1.status_code == 200:
            data = r1.json()
            hashtags = data.get('hashtags', [])
            for ht in hashtags:
                name = ht.get('hashtag', {}).get('name', '').lower()
                if name == tag.lower():
                    count = ht.get('hashtag', {}).get('media_count', 0)
                    return {'count': int(count), 'method': 'ig_web_api', 'success': True}

        # 태그 페이지 직접 파싱
        time.sleep(random.uniform(1.0, 2.5))
        tag_url = f'https://www.instagram.com/explore/tags/{quote(tag)}/'
        r2 = sess.get(tag_url, timeout=12)

        if r2.status_code == 200:
            # GraphQL 데이터 파싱
            m = re.search(r'"edge_hashtag_to_media"\s*:\s*\{"count"\s*:\s*(\d+)', r2.text)
            if m:
                return {'count': int(m.group(1)), 'method': 'ig_tag_page', 'success': True}
            # 다른 형태
            m = re.search(r'"media_count"\s*:\s*(\d+)', r2.text)
            if m:
                return {'count': int(m.group(1)), 'method': 'ig_tag_page2', 'success': True}

    except Exception as e:
        pass

    return {'count': 0, 'method': 'ig_web_api', 'success': False}


def _try_ig_mobile_api(tag: str) -> dict:
    """Instagram 모바일 API 시도 (앱 User-Agent)"""
    try:
        mobile_ua = "Instagram 278.0.0.16.105 Android (31/12; 420dpi; 1080x2400; Google/google; Pixel 5; redfin; redfin; ko_KR; 463736515)"
        headers = {
            'User-Agent': mobile_ua,
            'Accept': '*/*',
            'Accept-Language': 'ko-KR',
            'X-IG-App-ID': '567067343352427',
            'X-IG-Capabilities': '3brTvwE=',
            'X-IG-Connection-Type': 'WIFI',
        }
        r = requests.get(
            f'https://i.instagram.com/api/v1/tags/{quote(tag)}/info/',
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            count = data.get('media_count', 0)
            if count > 0:
                return {'count': int(count), 'method': 'ig_mobile_api', 'success': True}
    except:
        pass
    return {'count': 0, 'method': 'ig_mobile_api', 'success': False}


def _estimate_via_naver(keyword: str) -> dict:
    """
    네이버 검색에서 인스타그램 언급 수 추정
    정확하지 않지만 상대적 규모 파악 가능
    """
    try:
        query = f'site:instagram.com {keyword}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'ko-KR,ko;q=0.9',
        }
        time.sleep(random.uniform(0.8, 1.5))
        r = requests.get(
            f'https://search.naver.com/search.naver?where=web&query={quote(query)}',
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            m = re.search(r'총\s*<[^>]*>\s*([\d,]+)', r.text)
            if m:
                count = int(m.group(1).replace(',', ''))
                # 인스타그램 해시태그는 네이버 결과의 약 100~500배로 추정
                estimated = count * 200
                return {'count': estimated, 'method': 'naver_estimate', 'success': True, 'estimated': True}
    except:
        pass
    return {'count': 0, 'method': 'failed', 'success': False}
