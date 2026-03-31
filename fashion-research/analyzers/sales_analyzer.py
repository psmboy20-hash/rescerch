"""
analyzers/sales_analyzer.py
판매 추이 분석 엔진 - Pandas + Plotly 시각화
핵심: 리뷰 날짜 기반 판매 추이 + 제조년월 vs 첫 리뷰 시장 반응 속도
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from loguru import logger
from scrapers.base_scraper import ProductMeta


# ── 색상 팔레트 (ARÊTE 브랜드 컬러) ────────────────────────────
COLORS = {
    "primary": "#1A1A2E",
    "secondary": "#16213E",
    "accent": "#E94560",
    "gold": "#C9A84C",
    "light": "#F5F5F0",
    "gray": "#8B8B8B",
    "positive": "#27AE60",
    "negative": "#E74C3C",
    "neutral": "#F39C12",
}

PLOTLY_TEMPLATE = {
    "layout": {
        "paper_bgcolor": "#FAFAFA",
        "plot_bgcolor": "#FFFFFF",
        "font": {"family": "Pretendard, Apple SD Gothic Neo, sans-serif", "color": COLORS["primary"]},
        "colorway": [COLORS["accent"], COLORS["gold"], COLORS["positive"], COLORS["gray"]],
    }
}


class SalesAnalyzer:
    """리뷰 데이터 기반 판매 추이 분석기"""

    def __init__(self, reviews_df: pd.DataFrame, meta: ProductMeta = None):
        self.raw_df = reviews_df.copy()
        self.meta = meta
        self.df = self._preprocess(reviews_df)

    def _preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """데이터 전처리"""
        if df.empty:
            return df
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.sort_values("date")
        df["year_month"] = df["date"].dt.to_period("M").astype(str)
        df["year_week"] = df["date"].dt.to_period("W").astype(str)
        df["year"] = df["date"].dt.year
        df["month"] = df["date"].dt.month
        df["day_of_week"] = df["date"].dt.day_name()
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0)
        return df

    # ── 1. 월별 판매 추이 차트 ─────────────────────────────────
    def plot_monthly_trend(self) -> go.Figure:
        """월별 리뷰(판매) 추이 + 누적 곡선"""
        if self.df.empty:
            return self._empty_fig("데이터 없음")

        monthly = self.df.groupby("year_month").agg(
            count=("review_id", "count"),
            avg_rating=("rating", "mean"),
        ).reset_index()
        monthly["cumulative"] = monthly["count"].cumsum()

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=("📈 월별 판매량(리뷰 수)", "📊 누적 판매 곡선"),
            vertical_spacing=0.12,
        )

        # 월별 바 차트
        fig.add_trace(
            go.Bar(
                x=monthly["year_month"],
                y=monthly["count"],
                name="월별 리뷰 수",
                marker_color=COLORS["accent"],
                text=monthly["count"],
                textposition="outside",
            ),
            row=1, col=1,
        )

        # 평균 별점 라인
        fig.add_trace(
            go.Scatter(
                x=monthly["year_month"],
                y=monthly["avg_rating"],
                name="평균 별점",
                mode="lines+markers",
                yaxis="y2",
                line=dict(color=COLORS["gold"], width=2),
                marker=dict(size=6),
            ),
            row=1, col=1,
        )

        # 누적 곡선
        fig.add_trace(
            go.Scatter(
                x=monthly["year_month"],
                y=monthly["cumulative"],
                name="누적 판매",
                fill="tozeroy",
                fillcolor=f"rgba(233,69,96,0.15)",
                line=dict(color=COLORS["accent"], width=2.5),
            ),
            row=2, col=1,
        )

        # 제조년월 수직선 추가
        if self.meta and self.meta.manufacture_date:
            for row in [1, 2]:
                fig.add_vline(
                    x=self.meta.manufacture_date,
                    line_dash="dash",
                    line_color=COLORS["gold"],
                    annotation_text=f"🏭 제조: {self.meta.manufacture_date}",
                    annotation_position="top right",
                    row=row, col=1,
                )

        # 첫 리뷰 수직선
        if self.meta and self.meta.first_review_date:
            first_ym = self.meta.first_review_date[:7]
            for row in [1, 2]:
                fig.add_vline(
                    x=first_ym,
                    line_dash="dot",
                    line_color=COLORS["positive"],
                    annotation_text=f"⭐ 첫 리뷰",
                    annotation_position="top left",
                    row=row, col=1,
                )

        fig.update_layout(
            title=f"📦 {self.meta.name if self.meta else '제품'} - 월별 판매 추이",
            height=600,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        return fig

    # ── 2. 주별 판매 추이 차트 ─────────────────────────────────
    def plot_weekly_trend(self) -> go.Figure:
        """주별 리뷰 추이 + 7일 이동평균"""
        if self.df.empty:
            return self._empty_fig("데이터 없음")

        weekly = self.df.groupby("year_week").size().reset_index(name="count")
        weekly["ma7"] = weekly["count"].rolling(window=4, min_periods=1).mean()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=weekly["year_week"],
            y=weekly["count"],
            name="주별 리뷰",
            marker_color=COLORS["primary"],
            opacity=0.7,
        ))
        fig.add_trace(go.Scatter(
            x=weekly["year_week"],
            y=weekly["ma7"],
            name="4주 이동평균",
            line=dict(color=COLORS["accent"], width=2.5),
        ))

        fig.update_layout(
            title="📅 주별 판매 추이 (4주 이동평균)",
            height=400,
            xaxis_title="주간",
            yaxis_title="리뷰 수",
        )
        return fig

    # ── 3. 시장 반응 속도 분석 ─────────────────────────────────
    def plot_market_response(self) -> go.Figure:
        """제조년월 → 첫 리뷰 반응 속도 게이지 차트"""
        if not self.meta:
            return self._empty_fig("메타데이터 없음")

        days = self.meta.market_response_days
        if days is None:
            return self._empty_fig("제조년월 또는 첫 리뷰 날짜 없음")

        # 기준: 30일 이내 = 우수, 30~60 = 보통, 60+ = 느림
        color = COLORS["positive"] if days <= 30 else COLORS["neutral"] if days <= 60 else COLORS["negative"]
        grade = "🟢 매우 빠름" if days <= 30 else "🟡 보통" if days <= 60 else "🔴 느림"

        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=days,
            title={"text": f"시장 반응 속도<br><sub>{grade}</sub>", "font": {"size": 18}},
            number={"suffix": "일", "font": {"size": 36, "color": color}},
            gauge={
                "axis": {"range": [0, 180], "tickwidth": 1},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 30], "color": "rgba(39,174,96,0.2)"},
                    {"range": [30, 60], "color": "rgba(243,156,18,0.2)"},
                    {"range": [60, 180], "color": "rgba(231,76,60,0.2)"},
                ],
                "threshold": {
                    "line": {"color": COLORS["accent"], "width": 4},
                    "thickness": 0.75,
                    "value": days,
                },
            },
        ))
        fig.update_layout(
            title=f"🏭 제조: {self.meta.manufacture_date} → ⭐ 첫 리뷰: {self.meta.first_review_date}",
            height=350,
        )
        return fig

    # ── 4. 별점 분포 ───────────────────────────────────────────
    def plot_rating_distribution(self) -> go.Figure:
        """별점 분포 도넛 차트"""
        if self.df.empty:
            return self._empty_fig("데이터 없음")

        rating_counts = self.df["rating"].value_counts().sort_index(ascending=False)
        labels = [f"⭐ {r}점" for r in rating_counts.index]

        fig = go.Figure(go.Pie(
            labels=labels,
            values=rating_counts.values,
            hole=0.5,
            marker_colors=[COLORS["positive"], COLORS["gold"], COLORS["neutral"], COLORS["gray"], COLORS["negative"]],
            textinfo="label+percent",
        ))
        avg = self.df["rating"].mean()
        fig.update_layout(
            title=f"⭐ 별점 분포 (평균 {avg:.2f}점)",
            height=380,
            annotations=[{"text": f"{avg:.1f}", "font_size": 28, "showarrow": False}],
        )
        return fig

    # ── 5. 옵션별 분석 ─────────────────────────────────────────
    def plot_option_analysis(self) -> go.Figure:
        """옵션(사이즈/컬러)별 리뷰 분포"""
        if self.df.empty or "option" not in self.df.columns:
            return self._empty_fig("옵션 데이터 없음")

        option_counts = self.df["option"].value_counts().head(15)
        if option_counts.empty:
            return self._empty_fig("옵션 데이터 없음")

        fig = go.Figure(go.Bar(
            x=option_counts.values,
            y=option_counts.index,
            orientation="h",
            marker_color=COLORS["accent"],
            text=option_counts.values,
            textposition="outside",
        ))
        fig.update_layout(
            title="👗 옵션별 판매 분포 (Top 15)",
            height=max(300, len(option_counts) * 30),
            xaxis_title="리뷰 수",
            yaxis_title="옵션",
        )
        return fig

    # ── 6. 키워드 히트맵 ───────────────────────────────────────
    def plot_keyword_heatmap(self, keywords: list[str]) -> go.Figure:
        """월별 × 키워드 언급 히트맵"""
        if self.df.empty or not keywords:
            return self._empty_fig("키워드 없음")

        months = sorted(self.df["year_month"].unique())
        matrix = []
        for kw in keywords:
            row = []
            for m in months:
                sub = self.df[self.df["year_month"] == m]
                count = sub["text"].str.contains(kw, case=False, na=False).sum()
                row.append(count)
            matrix.append(row)

        fig = go.Figure(go.Heatmap(
            z=matrix,
            x=months,
            y=keywords,
            colorscale="RdYlGn",
            text=[[str(v) for v in row] for row in matrix],
            texttemplate="%{text}",
        ))
        fig.update_layout(
            title="🔍 키워드 언급 히트맵 (월별)",
            height=max(300, len(keywords) * 35),
        )
        return fig

    # ── 7. 요약 통계 ───────────────────────────────────────────
    def get_summary_stats(self) -> dict:
        if self.df.empty:
            return {}

        stats = {
            "총 리뷰 수": len(self.df),
            "평균 별점": round(self.df["rating"].mean(), 2),
            "5점 비율": f"{(self.df['rating'] == 5).mean() * 100:.1f}%",
            "1-2점 비율": f"{(self.df['rating'] <= 2).mean() * 100:.1f}%",
            "최초 리뷰일": str(self.df["date"].min().date()),
            "최근 리뷰일": str(self.df["date"].max().date()),
            "분석 기간": f"{(self.df['date'].max() - self.df['date'].min()).days}일",
            "포토리뷰 비율": f"{self.df['has_photo'].mean() * 100:.1f}%" if "has_photo" in self.df.columns else "N/A",
        }

        if self.meta:
            stats["제조년월"] = self.meta.manufacture_date or "미확인"
            stats["시장반응속도"] = f"{self.meta.market_response_days}일" if self.meta.market_response_days else "계산불가"
            stats["제품명"] = self.meta.name
            stats["브랜드"] = self.meta.brand

        # 피크 월 (가장 많이 팔린 달)
        monthly = self.df.groupby("year_month").size()
        if not monthly.empty:
            stats["최고 판매월"] = monthly.idxmax()
            stats["최고 판매월 리뷰수"] = int(monthly.max())

        return stats

    # ── 8. 벌크 비교 차트 ─────────────────────────────────────
    @staticmethod
    def plot_bulk_comparison(meta_df: pd.DataFrame) -> go.Figure:
        """여러 제품 시장 반응 속도 비교"""
        if meta_df.empty:
            return SalesAnalyzer._static_empty_fig("데이터 없음")

        df = meta_df.dropna(subset=["market_response_days"]).copy()
        df = df.sort_values("market_response_days")

        fig = go.Figure(go.Bar(
            x=df["name"].str[:20] + "...",
            y=df["market_response_days"],
            marker_color=[
                COLORS["positive"] if d <= 30 else COLORS["neutral"] if d <= 60 else COLORS["negative"]
                for d in df["market_response_days"]
            ],
            text=[f"{d}일" for d in df["market_response_days"]],
            textposition="outside",
        ))
        fig.update_layout(
            title="🏆 제품별 시장 반응 속도 비교 (제조→첫리뷰)",
            height=500,
            xaxis_title="제품명",
            yaxis_title="반응일수 (낮을수록 좋음)",
            xaxis={"tickangle": -45},
        )
        return fig

    @staticmethod
    def _static_empty_fig(msg: str) -> go.Figure:
        fig = go.Figure()
        fig.add_annotation(text=msg, x=0.5, y=0.5, showarrow=False, font=dict(size=18))
        fig.update_layout(height=300)
        return fig

    def _empty_fig(self, msg: str) -> go.Figure:
        return SalesAnalyzer._static_empty_fig(msg)
