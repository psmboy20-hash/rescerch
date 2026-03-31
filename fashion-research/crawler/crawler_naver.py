"""
네이버 블로그 리뷰 수 크롤러
- 네이버 검색 API (무료) 사용
- API 키 없을 경우 웹 크롤링 fallback
"""

import requests
import os
import time
import json
import re

# 네이버 검색 API 설정 (settings.json에서 로드)
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')

NAVER_API_HEADERS_TEMPLATE = {
    "X-Naver-Client-Id": "",
    "X-Naver-Client-Secret": "",
}


def search_naver_blog(query: str, client_id: str = None, client_secret: str = None) -> int:
    """
    네이버 블로그 검색으로 특정 키워드의 리뷰/언급 수 조회

    Args:
        query: 검색어 (브랜드명 + 제품명)
        client_id: 네이버 API 클라이언트 ID
        client_secret: 네이버 API 클라이언트 시크릿

    Returns:
        검색된 블로그 게시물 수 (추정치)
    """
    cid = client_id or NAVER_CLIENT_ID
    csec = client_secret or NAVER_CLIENT_SECRET

    if cid and csec:
        return _search_via_api(query, cid, csec)
    else:
        return _search_via_scraping(query)


def _search_via_api(query: str, client_id: str, client_secret: str) -> int:
    """네이버 검색 API로 블로그 검색"""
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {
        "query": query,
        "display": 1,
        "start": 1,
        "sort": "sim"
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('total', 0)
        else:
            print(f"[네이버 API 오류] {resp.status_code}: {resp.text}")
            return 0
    except Exception as e:
        print(f"[네이버 API 오류] {e}")
        return 0


def _search_via_scraping(query: str) -> int:
    """API 키 없을 때 웹 크롤링으로 대략적인 수 조회"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    try:
        # 네이버 블로그 검색 URL
        search_url = f"https://search.naver.com/search.naver?where=blog&query={requests.utils.quote(query)}"
        time.sleep(1.5)

        resp = requests.get(search_url, headers=headers, timeout=10)

        if resp.status_code != 200:
            return 0

        # 검색 결과 수 파싱 (대략적)
        match = re.search(r'총\s*([\d,]+)건', resp.text)
        if match:
            count_str = match.group(1).replace(',', '')
            return int(count_str)

        # 결과 카드 수로 추정
        result_items = re.findall(r'class="[^"]*blog_item[^"]*"', resp.text)
        return len(result_items) * 100  # 페이지당 10개 * 추정 10페이지

    except Exception as e:
        print(f"[네이버 스크래핑 오류] {e}")
        return 0


def batch_search(products: list, client_id: str = None, client_secret: str = None) -> list:
    """
    여러 제품의 네이버 블로그 리뷰 수를 일괄 조회

    Args:
        products: [{'id': str, 'brand_name': str, 'name': str}]

    Returns:
        [{'id': str, 'score_naver': int}]
    """
    results = []

    for product in products:
        query = f"{product.get('brand_name', '')} {product.get('name', '')} 후기"
        score = search_naver_blog(query, client_id, client_secret)

        results.append({
            'id': product['id'],
            'score_naver': min(score, 9999)  # 상한선
        })

        # API 호출 간격
        time.sleep(0.5)

    return results
