"""
app.py
ARÊTE Fashion Intelligence Dashboard - Streamlit 메인 앱
실행: streamlit run app.py
"""
import asyncio
import sys

# Windows에서 Playwright + Streamlit 호환 설정 (필수!)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── 페이지 설정 ────────────────────────────────────────────────
st.set_page_config(
    page_title="ARÊTE Fashion Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 커스텀 CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=Pretendard:wght@300;400;500;600&display=swap');

:root {
    --primary: #1A1A2E;
    --accent: #E94560;
    --gold: #C9A84C;
    --bg: #FAFAF8;
    --card: #FFFFFF;
}

.stApp { background: var(--bg); }

.main-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 2.8rem;
    font-weight: 300;
    color: var(--primary);
    letter-spacing: 0.15em;
    text-align: center;
    padding: 1rem 0 0.3rem;
}
.sub-title {
    font-family: 'Pretendard', sans-serif;
    font-size: 0.85rem;
    color: #888;
    text-align: center;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    margin-bottom: 2rem;
}

.metric-card {
    background: white;
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    border-left: 4px solid var(--accent);
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    margin-bottom: 1rem;
}
.metric-value { font-size: 2rem; font-weight: 600; color: var(--primary); }
.metric-label { font-size: 0.8rem; color: #888; letter-spacing: 0.1em; }

.section-header {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.4rem;
    color: var(--primary);
    border-bottom: 1px solid var(--gold);
    padding-bottom: 0.5rem;
    margin: 1.5rem 0 1rem;
}

.badge {
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 500;
    margin: 0.2rem;
}
.badge-red { background: #FEE2E2; color: #DC2626; }
.badge-green { background: #D1FAE5; color: #059669; }
.badge-gold { background: #FEF3C7; color: #D97706; }

.stButton > button {
    background: var(--primary) !important;
    color: white !important;
    border-radius: 8px !important;
    border: none !important;
    padding: 0.5rem 1.5rem !important;
    font-family: 'Pretendard', sans-serif !important;
    letter-spacing: 0.05em !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: var(--accent) !important;
    transform: translateY(-1px) !important;
}
</style>
""", unsafe_allow_html=True)


# ── 헤더 ───────────────────────────────────────────────────────
st.markdown('<div class="main-title">🏛️ ARÊTE</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Fashion Intelligence Dashboard</div>', unsafe_allow_html=True)

# ── 사이드바 네비게이션 ────────────────────────────────────────
with st.sidebar:
    st.image("https://via.placeholder.com/200x60/1A1A2E/C9A84C?text=ARÊTE", width=200)
    st.markdown("---")

    page = st.selectbox(
        "🗂️ 메뉴",
        [
            "🏠 홈 대시보드",
            "🔍 단일 제품 분석",
            "📦 카테고리 벌크 스캔",
            "📤 CSV 데이터 분석",
            "📺 YouTube 트렌드",
            "📸 Instagram 분석",
            "🤖 AI 제품 브리핑",
            "🔧 디렉터 플러그인",
            "⚙️ 설정",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("**API 상태**")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    st.markdown(f"{'🟢 OpenAI' if openai_key and openai_key != 'sk-xxx' else '🔴 OpenAI (미설정)'}")
    st.markdown(f"{'🟢 YouTube' if os.getenv('YOUTUBE_API_KEY') else '⚪ YouTube (선택)'}")
    st.markdown("---")
    st.caption("ARÊTE © 2024 | Internal Use Only")


# ════════════════════════════════════════════════════════════════
# 1. 홈 대시보드
# ════════════════════════════════════════════════════════════════
if page == "🏠 홈 대시보드":
    st.markdown('<div class="section-header">📊 분석 현황</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""<div class="metric-card">
            <div class="metric-value">0</div>
            <div class="metric-label">분석된 제품</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown("""<div class="metric-card">
            <div class="metric-value" style="color:#E94560">0</div>
            <div class="metric-label">수집된 리뷰</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown("""<div class="metric-card">
            <div class="metric-value" style="color:#C9A84C">-</div>
            <div class="metric-label">평균 반응 속도</div>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown("""<div class="metric-card">
            <div class="metric-value">0</div>
            <div class="metric-label">AI 브리핑 생성</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-header">🚀 빠른 시작</div>', unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.info("**🔍 단일 제품 분석**\n\n제품 URL을 입력하면 전체 리뷰를 자동 수집하고 판매 추이를 분석합니다.")
    with col_b:
        st.info("**📦 카테고리 벌크 스캔**\n\n카테고리 URL로 상위 100개 제품을 일괄 분석합니다.")
    with col_c:
        st.info("**📤 CSV 업로드**\n\n기존 리뷰 데이터를 CSV로 업로드해 즉시 분석을 시작합니다.")

    st.markdown('<div class="section-header">📋 최근 분석 기록</div>', unsafe_allow_html=True)
    export_dir = "./exports"
    if os.path.exists(export_dir):
        files = sorted(
            [f for f in os.listdir(export_dir) if f.endswith((".csv", ".xlsx"))],
            reverse=True,
        )[:10]
        if files:
            for f in files:
                fpath = os.path.join(export_dir, f)
                size = os.path.getsize(fpath) // 1024
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
                st.markdown(f"📄 `{f}` · {size}KB · {mtime}")
        else:
            st.caption("아직 분석 기록이 없습니다. 왼쪽 메뉴에서 분석을 시작해보세요!")
    else:
        st.caption("아직 분석 기록이 없습니다.")


# ════════════════════════════════════════════════════════════════
# 2. 단일 제품 분석
# ════════════════════════════════════════════════════════════════
elif page == "🔍 단일 제품 분석":
    st.markdown('<div class="section-header">🔍 단일 제품 분석</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        product_url = st.text_input(
            "제품 URL 입력",
            placeholder="https://www.29cm.co.kr/products/12345 또는 https://www.wconcept.co.kr/product/...",
        )
    with col2:
        platform = st.selectbox("플랫폼", ["자동 감지", "29cm", "wconcept", "musinsa"])

    # 자동 플랫폼 감지
    def detect_platform(url: str) -> str:
        if "29cm" in url:
            return "29cm"
        elif "wconcept" in url:
            return "wconcept"
        elif "musinsa" in url:
            return "musinsa"
        return "29cm"

    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        start_btn = st.button("🚀 분석 시작", type="primary")

    if start_btn and product_url:
        detected = detect_platform(product_url) if platform == "자동 감지" else platform
        st.info(f"**플랫폼:** {detected} | **URL:** {product_url}")

        with st.spinner(f"🔄 [{detected}] 리뷰 전수 수집 중... (수백 건 시 수 분 소요)"):
            try:
                from scrapers.bulk_scanner import run_single_scrape
                meta, reviews_df = run_single_scrape(product_url, detected)

                st.session_state["meta"] = meta
                st.session_state["reviews_df"] = reviews_df
                st.success(f"✅ 수집 완료: {meta.name} | 리뷰 {meta.review_count}건")
            except Exception as e:
                st.error(f"❌ 오류: {e}")
                st.stop()

    # 결과 표시
    if "reviews_df" in st.session_state and not st.session_state["reviews_df"].empty:
        meta = st.session_state.get("meta")
        reviews_df = st.session_state["reviews_df"]

        from analyzers.sales_analyzer import SalesAnalyzer
        analyzer = SalesAnalyzer(reviews_df, meta)
        stats = analyzer.get_summary_stats()

        # 핵심 지표
        st.markdown('<div class="section-header">📊 핵심 지표</div>', unsafe_allow_html=True)
        cols = st.columns(4)
        key_metrics = ["총 리뷰 수", "평균 별점", "제조년월", "시장반응속도"]
        for i, key in enumerate(key_metrics):
            with cols[i]:
                val = stats.get(key, "-")
                st.metric(key, val)

        # 차트들
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 월별 추이", "📅 주별 추이", "⚡ 반응속도", "⭐ 별점", "👗 옵션"])
        with tab1:
            st.plotly_chart(analyzer.plot_monthly_trend(), use_container_width=True)
        with tab2:
            st.plotly_chart(analyzer.plot_weekly_trend(), use_container_width=True)
        with tab3:
            st.plotly_chart(analyzer.plot_market_response(), use_container_width=True)
        with tab4:
            st.plotly_chart(analyzer.plot_rating_distribution(), use_container_width=True)
        with tab5:
            st.plotly_chart(analyzer.plot_option_analysis(), use_container_width=True)

        # 리뷰 데이터 테이블
        st.markdown('<div class="section-header">📋 리뷰 원본 데이터</div>', unsafe_allow_html=True)
        search_kw = st.text_input("🔍 키워드 검색", placeholder="원단, 사이즈, 불만...")
        filtered_df = reviews_df
        if search_kw:
            filtered_df = reviews_df[reviews_df["text"].str.contains(search_kw, case=False, na=False)]
        st.dataframe(filtered_df, use_container_width=True, height=400)

        # 다운로드
        csv = filtered_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 CSV 다운로드", csv, f"reviews_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")


# ════════════════════════════════════════════════════════════════
# 3. 카테고리 벌크 스캔
# ════════════════════════════════════════════════════════════════
elif page == "📦 카테고리 벌크 스캔":
    st.markdown('<div class="section-header">📦 카테고리 벌크 스캐너</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        cat_url = st.text_input("카테고리 URL", placeholder="https://www.wconcept.co.kr/Category/...")
    with col2:
        bulk_platform = st.selectbox("플랫폼", ["29cm", "wconcept", "musinsa"])
    with col3:
        bulk_limit = st.number_input("제품 수", min_value=5, max_value=100, value=30)

    if st.button("🚀 벌크 스캔 시작"):
        progress = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total, url):
            pct = int(current / total * 100)
            progress.progress(pct)
            status_text.text(f"[{current}/{total}] {url[:60]}...")

        with st.spinner("🔄 카테고리 벌크 스캔 중..."):
            try:
                from scrapers.bulk_scanner import run_bulk_scan
                meta_df, reviews_df = run_bulk_scan(cat_url, bulk_platform, bulk_limit, update_progress)
                st.session_state["bulk_meta_df"] = meta_df
                st.session_state["bulk_reviews_df"] = reviews_df
                st.success(f"✅ 완료: {len(meta_df)}개 제품, {len(reviews_df)}개 리뷰 수집")
            except Exception as e:
                st.error(f"❌ {e}")

    if "bulk_meta_df" in st.session_state:
        meta_df = st.session_state["bulk_meta_df"]
        reviews_df = st.session_state.get("bulk_reviews_df", pd.DataFrame())

        st.markdown('<div class="section-header">📊 벌크 분석 결과</div>', unsafe_allow_html=True)

        from analyzers.sales_analyzer import SalesAnalyzer
        st.plotly_chart(SalesAnalyzer.plot_bulk_comparison(meta_df), use_container_width=True)

        st.dataframe(meta_df, use_container_width=True)
        csv = meta_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 제품 메타 CSV", csv, "bulk_meta.csv", "text/csv")


# ════════════════════════════════════════════════════════════════
# 4. CSV 데이터 분석
# ════════════════════════════════════════════════════════════════
elif page == "📤 CSV 데이터 분석":
    st.markdown('<div class="section-header">📤 CSV 데이터 업로드 분석</div>', unsafe_allow_html=True)

    st.info("""
    **CSV 필수 컬럼**: `date` (YYYY-MM-DD), `rating` (숫자), `text` (리뷰 내용)
    **선택 컬럼**: `option` (사이즈/컬러), `has_photo` (True/False), `helpful` (숫자)
    """)

    uploaded_file = st.file_uploader("CSV 파일 선택", type=["csv"])
    if uploaded_file:
        df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
        st.success(f"✅ {len(df)}행 로드 완료")

        # 메타 정보 입력
        with st.expander("📋 제품 메타 정보 입력 (선택)"):
            col1, col2 = st.columns(2)
            with col1:
                csv_product_name = st.text_input("제품명")
                csv_brand = st.text_input("브랜드명")
            with col2:
                csv_mfg_date = st.text_input("제조년월 (YYYY-MM)", placeholder="2024-03")
                csv_first_review = st.text_input("첫 리뷰 날짜 (YYYY-MM-DD)")

        from scrapers.base_scraper import ProductMeta
        from analyzers.sales_analyzer import SalesAnalyzer

        meta = ProductMeta(
            platform="csv",
            product_id="uploaded",
            url="",
            name=csv_product_name or "업로드 제품",
            brand=csv_brand or "",
            manufacture_date=csv_mfg_date or None,
            first_review_date=csv_first_review or None,
        )

        analyzer = SalesAnalyzer(df, meta)
        stats = analyzer.get_summary_stats()

        cols = st.columns(4)
        for i, (k, v) in enumerate(list(stats.items())[:4]):
            with cols[i]:
                st.metric(k, v)

        tab1, tab2, tab3, tab4 = st.tabs(["📈 월별", "📅 주별", "⭐ 별점", "👗 옵션"])
        with tab1:
            st.plotly_chart(analyzer.plot_monthly_trend(), use_container_width=True)
        with tab2:
            st.plotly_chart(analyzer.plot_weekly_trend(), use_container_width=True)
        with tab3:
            st.plotly_chart(analyzer.plot_rating_distribution(), use_container_width=True)
        with tab4:
            st.plotly_chart(analyzer.plot_option_analysis(), use_container_width=True)

        # 키워드 히트맵
        st.markdown('<div class="section-header">🔍 키워드 히트맵</div>', unsafe_allow_html=True)
        keyword_input = st.text_input("키워드 입력 (쉼표 구분)", "원단,사이즈,핏,컬러,품질,배송")
        if keyword_input:
            kws = [k.strip() for k in keyword_input.split(",")]
            st.plotly_chart(analyzer.plot_keyword_heatmap(kws), use_container_width=True)


# ════════════════════════════════════════════════════════════════
# 5. YouTube 트렌드
# ════════════════════════════════════════════════════════════════
elif page == "📺 YouTube 트렌드":
    st.markdown('<div class="section-header">📺 YouTube 트렌드 분석</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        yt_keyword = st.text_input("검색 키워드", placeholder="아우터 코디, 오버사이즈 자켓...")
    with col2:
        yt_max = st.number_input("최대 결과", 5, 50, 20)
    with col3:
        yt_sort = st.selectbox("정렬", ["relevance", "date", "viewCount"])

    if st.button("🔍 YouTube 검색"):
        with st.spinner("🔄 YouTube 검색 중..."):
            try:
                from agents.youtube_agent import YouTubeAgent
                agent = YouTubeAgent()
                yt_df = agent.run_search(yt_keyword, yt_max)
                st.session_state["yt_df"] = yt_df
                st.success(f"✅ {len(yt_df)}개 영상 수집")
            except Exception as e:
                st.error(f"❌ {e}")

    if "yt_df" in st.session_state:
        yt_df = st.session_state["yt_df"]

        # 조회수 TOP 차트
        fig = px.bar(
            yt_df.head(10),
            x="title",
            y="views",
            color="channel",
            title="🏆 조회수 TOP 10",
            labels={"title": "영상 제목", "views": "조회수"},
        )
        fig.update_xaxes(tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

        # 데이터 테이블
        st.dataframe(
            yt_df[["rank", "title", "channel", "views", "upload_date", "duration"]],
            use_container_width=True,
        )

        csv = yt_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 CSV 다운로드", csv, "youtube_trends.csv", "text/csv")


# ════════════════════════════════════════════════════════════════
# 6. Instagram 분석
# ════════════════════════════════════════════════════════════════
elif page == "📸 Instagram 분석":
    st.markdown('<div class="section-header">📸 Instagram 해시태그 분석</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        ig_hashtag = st.text_input("해시태그", placeholder="#오버사이즈 또는 오버사이즈")
    with col2:
        ig_max = st.number_input("최대 게시물", 5, 50, 20)

    if st.button("🔍 Instagram 분석"):
        with st.spinner("🔄 Instagram 분석 중..."):
            try:
                from agents.instagram_agent import InstagramAgent
                agent = InstagramAgent()
                ig_df = agent.run_hashtag_search(ig_hashtag, ig_max)
                st.session_state["ig_df"] = ig_df

                # 키워드 추출
                keywords = agent.extract_keywords_from_captions(ig_df)
                st.session_state["ig_keywords"] = keywords
                st.success(f"✅ {len(ig_df)}개 게시물 수집")
            except Exception as e:
                st.error(f"❌ {e}")

    if "ig_df" in st.session_state:
        ig_df = st.session_state["ig_df"]
        keywords = st.session_state.get("ig_keywords", [])

        if keywords:
            kw_df = pd.DataFrame(keywords, columns=["hashtag", "count"]).head(20)
            fig = px.bar(kw_df, x="hashtag", y="count", title="🔥 관련 해시태그 TOP 20", color="count",
                        color_continuous_scale="reds")
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        # 컬럼 존재 여부 확인 후 표시
        display_cols = [c for c in ["hashtag", "account", "likes", "comments", "posted_at", "caption"] if c in ig_df.columns]
        if display_cols:
            st.dataframe(ig_df[display_cols], use_container_width=True)
        else:
            st.dataframe(ig_df, use_container_width=True)

        # 스크린샷 갤러리
        screenshots = ig_df["screenshot_path"].dropna().tolist()
        if screenshots:
            st.markdown('<div class="section-header">📸 스크린샷 갤러리</div>', unsafe_allow_html=True)
            cols = st.columns(3)
            for i, path in enumerate(screenshots[:6]):
                if os.path.exists(path):
                    with cols[i % 3]:
                        st.image(path, use_column_width=True)


# ════════════════════════════════════════════════════════════════
# 7. AI 제품 브리핑
# ════════════════════════════════════════════════════════════════
elif page == "🤖 AI 제품 브리핑":
    st.markdown('<div class="section-header">🤖 GPT-4o 제품 개발 브리핑</div>', unsafe_allow_html=True)

    if not os.getenv("OPENAI_API_KEY"):
        st.error("⚠️ OpenAI API 키가 설정되지 않았습니다. .env 파일에 OPENAI_API_KEY를 입력하세요.")
        st.stop()

    data_source = st.radio("데이터 소스", ["세션 데이터 사용", "CSV 업로드"])
    reviews_df = pd.DataFrame()
    meta = None

    if data_source == "세션 데이터 사용":
        if "reviews_df" in st.session_state:
            reviews_df = st.session_state["reviews_df"]
            meta = st.session_state.get("meta")
            st.success(f"✅ {len(reviews_df)}건 리뷰 데이터 로드됨")
        else:
            st.warning("⚠️ 먼저 '단일 제품 분석'에서 데이터를 수집하세요.")
    else:
        uploaded = st.file_uploader("리뷰 CSV", type=["csv"])
        if uploaded:
            reviews_df = pd.read_csv(uploaded, encoding="utf-8-sig")

    director_notes = st.text_area(
        "📝 디렉터 메모 (선택)",
        placeholder="예: 3월 생산분은 원단을 두꺼운 것으로 변경할 예정. 특히 키 170 이상 불만 고객 의견에 집중해줘.",
        height=100,
    )
    season = st.text_input("대상 시즌", placeholder="2024 F/W, 2025 S/S")

    if st.button("🤖 AI 브리핑 생성") and not reviews_df.empty:
        with st.spinner("🔄 GPT-4o 분석 중..."):
            from analyzers.ai_analyzer import summarize_reviews, generate_product_brief
            product_name = meta.name if meta else "제품"
            review_analysis = summarize_reviews(reviews_df, product_name)

            meta_dict = meta.to_dict() if meta else {}
            briefing = generate_product_brief(meta_dict, review_analysis, director_notes, season)

        st.markdown("---")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(briefing)
        with col2:
            st.markdown("**📊 리뷰 분석 요약**")
            if "positives" in review_analysis:
                st.markdown("**✅ 긍정 포인트**")
                for p in review_analysis.get("positives", []):
                    st.markdown(f"- {p}")
            if "negatives" in review_analysis:
                st.markdown("**❌ 개선 포인트**")
                for n in review_analysis.get("negatives", []):
                    st.markdown(f"- {n}")
            if "keywords" in review_analysis:
                st.markdown("**🔑 핵심 키워드**")
                st.markdown(" | ".join([f"`{k}`" for k in review_analysis.get("keywords", [])]))

        st.download_button("📥 브리핑 다운로드", briefing, "product_briefing.md", "text/markdown")


# ════════════════════════════════════════════════════════════════
# 8. 디렉터 플러그인
# ════════════════════════════════════════════════════════════════
elif page == "🔧 디렉터 플러그인":
    st.markdown('<div class="section-header">🔧 디렉터 커스텀 로직 플러그인</div>', unsafe_allow_html=True)

    from plugins.director_plugins import list_plugins, run_plugin, add_custom_plugin

    plugins = list_plugins()
    st.markdown("**📋 등록된 플러그인**")
    for p in plugins:
        col1, col2 = st.columns([3, 7])
        with col1:
            st.markdown(f"`{p['name']}`")
        with col2:
            st.markdown(p["description"])

    st.markdown("---")

    # 플러그인 실행
    if "reviews_df" in st.session_state:
        selected_plugin = st.selectbox("플러그인 선택", [p["name"] for p in plugins])

        # 플러그인별 파라미터
        plugin_kwargs = {}
        if selected_plugin == "체형_불만_필터":
            st.markdown("**필터 설정**")
            col1, col2 = st.columns(2)
            with col1:
                h_min = st.number_input("키 최소 (cm)", value=160)
            with col2:
                h_max = st.number_input("키 최대 (cm)", value=175)
            plugin_kwargs = {"height_range": (h_min, h_max + 1)}
        elif selected_plugin == "생산월_원단분석":
            prod_month = st.text_input("생산월 (YYYY-MM)", value="2024-01")
            plugin_kwargs = {"production_month": prod_month}

        if st.button("▶ 플러그인 실행"):
            reviews_df = st.session_state["reviews_df"]
            result = run_plugin(selected_plugin, reviews_df, **plugin_kwargs)
            if isinstance(result, pd.DataFrame):
                st.success(f"✅ {len(result)}건 추출")
                st.dataframe(result, use_container_width=True)
                csv = result.to_csv(index=False, encoding="utf-8-sig")
                st.download_button("📥 CSV 다운로드", csv, f"{selected_plugin}_result.csv", "text/csv")
            elif isinstance(result, dict):
                st.json(result)
    else:
        st.warning("⚠️ 먼저 리뷰 데이터를 수집하세요.")

    # 커스텀 플러그인 추가
    st.markdown("---")
    st.markdown('<div class="section-header">➕ 새 플러그인 추가</div>', unsafe_allow_html=True)

    new_name = st.text_input("플러그인 이름")
    new_desc = st.text_input("설명")
    new_code = st.text_area(
        "Python 코드",
        height=200,
        value="""def run(reviews_df, **kwargs):
    # reviews_df: pandas DataFrame (date, rating, option, text 컬럼 포함)
    # kwargs: 추가 파라미터
    
    # 예시: 3점 이하 리뷰만 추출
    result = reviews_df[reviews_df['rating'] <= 3]
    return result
""",
    )
    if st.button("💾 플러그인 저장"):
        if new_name and new_desc and new_code:
            success = add_custom_plugin(new_name, new_desc, new_code)
            if success:
                st.success(f"✅ '{new_name}' 플러그인 등록 완료!")
                st.rerun()
            else:
                st.error("❌ 플러그인 등록 실패. 코드를 확인하세요.")


# ════════════════════════════════════════════════════════════════
# 9. 설정
# ════════════════════════════════════════════════════════════════
elif page == "⚙️ 설정":
    st.markdown('<div class="section-header">⚙️ 환경 설정</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🔑 API 키 설정**")
        openai_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
        yt_key = st.text_input("YouTube API Key (선택)", type="password", value=os.getenv("YOUTUBE_API_KEY", ""))
        if st.button("💾 저장"):
            env_content = f"OPENAI_API_KEY={openai_key}\nYOUTUBE_API_KEY={yt_key}\n"
            with open(".env", "w") as f:
                f.write(env_content)
            st.success("✅ .env 파일 저장 완료. 앱을 재시작하세요.")

    with col2:
        st.markdown("**🌐 스크래핑 설정**")
        headless = st.checkbox("헤드리스 모드 (브라우저 숨김)", value=True)
        delay_min = st.slider("최소 딜레이 (초)", 0.5, 5.0, 1.5)
        delay_max = st.slider("최대 딜레이 (초)", 1.0, 10.0, 3.5)
        max_pages = st.number_input("최대 리뷰 페이지", 1, 999, 999)

        if st.button("⚙️ 스크래핑 설정 저장"):
            with open(".env", "a") as f:
                f.write(f"\nHEADLESS_MODE={'true' if headless else 'false'}")
                f.write(f"\nSCRAPE_DELAY_MIN={delay_min}")
                f.write(f"\nSCRAPE_DELAY_MAX={delay_max}")
                f.write(f"\nMAX_PAGES={max_pages}")
            st.success("✅ 저장 완료")

    st.markdown("---")
    st.markdown("**📦 Playwright 브라우저 설치**")
    st.code("py -3.11 -m playwright install chromium", language="bash")
    st.markdown("**▶ 앱 실행 명령어**")
    st.code("py -3.11 -m streamlit run app.py", language="bash")

    st.markdown("---")
    st.markdown("**🔑 Instagram 세션 관리**")
    col_ig1, col_ig2 = st.columns(2)
    with col_ig1:
        ig_user = st.text_input("Instagram ID", value=os.getenv("INSTAGRAM_USERNAME", ""))
        ig_pass = st.text_input("Instagram PW", type="password", value=os.getenv("INSTAGRAM_PASSWORD", ""))
        if st.button("💾 저장 + 쿠키 갱신"):
            # .env 업데이트
            import re as _re
            env_path = ".env"
            env_text = open(env_path).read() if os.path.exists(env_path) else ""
            for key, val in [("INSTAGRAM_USERNAME", ig_user), ("INSTAGRAM_PASSWORD", ig_pass)]:
                if key in env_text:
                    env_text = _re.sub(rf'{key}=.*', f'{key}={val}', env_text)
                else:
                    env_text += f"\n{key}={val}"
            with open(env_path, "w") as f:
                f.write(env_text)
            # 기존 쿠키 삭제 (재로그인 강제)
            cookie_file = "./exports/instagram_cookies.json"
            if os.path.exists(cookie_file):
                os.remove(cookie_file)
            st.success("✅ 저장 완료. 다음 Instagram 분석 시 새로 로그인합니다.")
    with col_ig2:
        cookie_exists = os.path.exists("./exports/instagram_cookies.json")
        st.markdown(f"**세션 쿠키:** {'🟢 저장됨 (로그인 유지)' if cookie_exists else '⚪ 없음 (로그인 필요)'}")
        if cookie_exists and st.button("🗑️ 쿠키 삭제 (재로그인)"):
            os.remove("./exports/instagram_cookies.json")
            st.success("✅ 쿠키 삭제. 다음 실행 시 재로그인합니다.")
            st.rerun()
