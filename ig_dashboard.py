import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 🔗 IMPORTANT:
# Change this import to the actual filename where your analyze_profile() lives.
# Example: if your scraper file is called "ved_ai_scraper.py", then do:
# from ved_ai_scraper import analyze_profile
from main import analyze_profile  # <<< CHANGE THIS


# ==============
#  PAGE CONFIG
# ==============
st.set_page_config(
    page_title="Instagram – Analytics",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============
#  DARK THEME
# ============
st.markdown(
    """
<style>
/* Global background */
body {
    background-color: #050816;
}

/* Main App background */
[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at top left, #161a2b 0, #050816 45%, #000000 100%);
    color: #f5f5f5;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #050816 0%, #02030a 100%);
}

/* Cards / containers */
.block-container {
    padding-top: 1.5rem;
}

/* Titles */
h1, h2, h3, h4 {
    color: #f8fafc;
}

/* Metrics */
[data-testid="stMetricValue"] {
    font-size: 26px;
    font-weight: 700;
}

.metric-card {
    background: rgba(15, 23, 42, 0.9);
    border-radius: 16px;
    padding: 16px 18px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.6);
}

.glass-card {
    background: rgba(15, 23, 42, 0.75);
    border-radius: 18px;
    padding: 18px 20px;
    border: 1px solid rgba(148, 163, 184, 0.4);
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.9);
}

/* Pills */
.badge-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 11px;
    margin-right: 6px;
    border: 1px solid rgba(148, 163, 184, 0.6);
}

.badge-green {
    background: rgba(22, 163, 74, 0.15);
    color: #4ade80;
    border-color: rgba(74, 222, 128, 0.7);
}

.badge-purple {
    background: rgba(147, 51, 234, 0.15);
    color: #c4b5fd;
    border-color: rgba(196, 181, 253, 0.7);
}

.badge-blue {
    background: rgba(59, 130, 246, 0.15);
    color: #93c5fd;
    border-color: rgba(147, 197, 253, 0.7);
}

/* Tabs header tweak */
.stTabs [role="tablist"] {
    border-bottom: 1px solid rgba(51, 65, 85, 0.8);
}
.stTabs [role="tab"] {
    color: #9ca3af;
}
.stTabs [aria-selected="true"] {
    border-bottom: 2px solid #38bdf8;
    color: #e5e7eb;
}
</style>
""",
    unsafe_allow_html=True,
)


# ==================
#  SMALL UTILITIES
# ==================
def format_large_number(num):
    """Format big numbers nicely like 1.2K / 3.4M."""
    try:
        num = float(num)
    except Exception:
        return str(num)

    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    else:
        return str(int(num))


def compute_engagement_for_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add engagement and engagement_rate columns to posts DF."""
    if df is None or df.empty:
        return df

    df = df.copy()
    df["engagement"] = df["likes"] + df["comments"]
    return df


# =======================
#  HEADER / HERO SECTION
# =======================
def render_header():
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(
            """
<div style="
    padding: 18px 20px;
    border-radius: 18px;
    background: radial-gradient(circle at top left, #22c55e22 0, #020617 52%);
    border: 1px solid rgba(34, 197, 94, 0.28);
">
    <h1 style="margin-bottom:4px;">Instagram scrapper</h1>
    <p style="margin:0; color:#e5e7eb;">Deep-dive analytics on any public Instagram profile – built on your custom scraper.</p>
</div>
""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
<div style="
    padding: 12px 14px;
    border-radius: 16px;
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(148, 163, 184, 0.4);
    font-size: 13px;
">
    <b>How this UI works:</b><br/>
    • Uses your <code>analyze_profile()</code> backend (Instaloader + Gemini/heuristic)<br/>
    • Reads <b>stats</b>, <b>post-level data</b>, <b>followers/following</b>, and <b>rate-limit info</b><br/>
    • Turns it into a clean dashboard for non-technical users.
</div>
""",
            unsafe_allow_html=True,
        )


# ========================
#  PROFILE + METRICS CARD
# ========================
def render_overview_tab(stats: dict, df: pd.DataFrame, extra: dict):
    st.subheader("Overview")

    # Top strip: handle + badges
    with st.container():
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        top_col1, top_col2 = st.columns([3, 2])
        with top_col1:
            handle = stats.get("username", "unknown")
            name = stats.get("full_name", "")
            st.markdown(f"### @{handle}")
            if name:
                st.markdown(f"**{name}**")

            badge_html = ""
            if stats.get("is_verified"):
                badge_html += '<span class="badge-pill badge-blue">Verified</span>'
            if stats.get("brand_collabs", 0) > 0:
                badge_html += '<span class="badge-pill badge-purple">Brand Collaborations</span>'
            if stats.get("category") and stats["category"] != "Unknown":
                badge_html += f'<span class="badge-pill badge-green">{stats["category"]}</span>'

            if badge_html:
                st.markdown(badge_html, unsafe_allow_html=True)

            bio = (stats.get("bio") or "").strip()
            if bio:
                st.markdown(f"<br/>📝 <i>{bio[:180]}{'...' if len(bio) > 180 else ''}</i>", unsafe_allow_html=True)

        with top_col2:
            location = stats.get("location", "Unknown")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Location (AI/Heuristic)**")
                st.write(location or "Unknown")
            with col_b:
                st.write("**Last Scraped**")
                st.write(datetime.now().strftime("%Y-%m-%d %H:%M"))

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    # KPI metrics row 1
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Followers", format_large_number(stats.get("followers", 0)))
        st.markdown("</div>", unsafe_allow_html=True)

    with m2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Following", format_large_number(stats.get("following", 0)))
        st.markdown("</div>", unsafe_allow_html=True)

    with m3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Total Posts", format_large_number(stats.get("total_posts", 0)))
        st.markdown("</div>", unsafe_allow_html=True)

    with m4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Posts per Week", f"{stats.get('posts_per_week', 0):.2f}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    # KPI metrics row 2
    m5, m6, m7, m8 = st.columns(4)
    with m5:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Avg Likes", format_large_number(stats.get("avg_likes", 0)))
        st.markdown("</div>", unsafe_allow_html=True)

    with m6:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Avg Comments", format_large_number(stats.get("avg_comments", 0)))
        st.markdown("</div>", unsafe_allow_html=True)

    with m7:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Avg Views (Reels)", format_large_number(stats.get("avg_views", 0)))
        st.markdown("</div>", unsafe_allow_html=True)

    with m8:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Engagement Rate", f"{stats.get('engagement_rate', 0):.2f}%")
        st.markdown("</div>", unsafe_allow_html=True)

    # Small text summary
    st.markdown("---")
    st.markdown(
        f"""
**Quick narrative:**

- This dashboard is based on the last **{len(df)} posts** we scraped.
- Engagement rate is averaged per post as: **(likes + comments) / followers × 100**.
- We detected **{stats.get('brand_collabs', 0)}** brand collaboration style posts.
- Rate limiting info and scrape health are visible under the **“Tech & Logs”** tab.
"""
    )


# ==========================
#  CONTENT & HASHTAG ANALYSIS
# ==========================
def render_content_tab(stats: dict, df: pd.DataFrame, extra: dict):
    st.subheader("Content & Hashtags")

    col_left, col_right = st.columns([1.2, 1])

    # Content type distribution (pie)
    with col_left:
        st.markdown("#### Content Mix")
        content_dist = extra.get("content_distribution", {})
        if content_dist:
            fig = px.pie(
                names=list(content_dist.keys()),
                values=list(content_dist.values()),
                hole=0.45,
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
            )
            fig.update_layout(
                template="plotly_dark",
                height=380,
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No content distribution data – maybe no posts were scraped.")

    # Top hashtags
    with col_right:
        st.markdown("#### Top Hashtags")
        top_hashtags = extra.get("top_hashtags", {})
        if top_hashtags:
            tags_df = (
                pd.DataFrame(
                    [{"Hashtag": k, "Count": v} for k, v in top_hashtags.items()]
                )
                .sort_values("Count", ascending=False)
                .head(15)
            )
            fig_ht = px.bar(
                tags_df,
                x="Count",
                y="Hashtag",
                orientation="h",
                template="plotly_dark",
            )
            fig_ht.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_ht, use_container_width=True)
        else:
            st.info("No hashtags detected in the scraped posts.")

    st.markdown("---")

    # Mentions
    st.markdown("#### Frequently Mentioned / Tagged Accounts")
    top_mentions = extra.get("top_mentions", {})
    if top_mentions:
        mentions_df = (
            pd.DataFrame(
                [{"User": k, "Count": v} for k, v in top_mentions.items()]
            )
            .sort_values("Count", ascending=False)
            .head(20)
        )
        col_m1, col_m2 = st.columns([2, 1])
        with col_m1:
            fig_m = px.bar(
                mentions_df,
                x="User",
                y="Count",
                template="plotly_dark",
            )
            fig_m.update_layout(
                xaxis_tickangle=-45,
                height=420,
                margin=dict(l=10, r=10, t=40, b=80),
            )
            st.plotly_chart(fig_m, use_container_width=True)
        with col_m2:
            st.dataframe(
                mentions_df,
                use_container_width=True,
                height=420,
            )
    else:
        st.info("No mentions/tagged accounts were detected.")


# ======================
#  POSTS EXPLORER TAB
# ======================
def render_posts_tab(stats: dict, df: pd.DataFrame):
    st.subheader("Posts Explorer")

    if df is None or df.empty:
        st.info("No posts were scraped – posts table is empty.")
        return

    df = compute_engagement_for_df(df)

    # Controls
    with st.expander("🔎 Filters", expanded=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            content_type_filter = st.multiselect(
                "Content Type",
                options=sorted(df["content_type"].unique()),
                default=list(sorted(df["content_type"].unique())),
            )
        with col_f2:
            min_likes = st.number_input(
                "Minimum Likes",
                min_value=0,
                value=int(df["likes"].median()),
                step=10,
            )
        with col_f3:
            search_text = st.text_input(
                "Search in caption (optional)",
                placeholder="e.g. giveaway, tutorial, vlog",
            )

    filtered = df[df["content_type"].isin(content_type_filter)]
    filtered = filtered[filtered["likes"] >= min_likes]
    if search_text:
        filtered = filtered[
            filtered["caption"].fillna("").str.contains(search_text, case=False)
        ]

    st.markdown(f"**Showing {len(filtered)} posts out of {len(df)} scraped.**")

    # Show top posts by engagement
    top_n = 10
    st.markdown(f"#### Top {top_n} posts by engagement (likes + comments)")
    top_posts = filtered.sort_values("engagement", ascending=False).head(top_n).copy()
    if not top_posts.empty:
        # Add URL column from shortcode
        top_posts["post_url"] = top_posts["shortcode"].apply(
            lambda s: f"https://www.instagram.com/p/{s}/" if s else ""
        )
        display_cols = [
            "post_index",
            "date",
            "content_type",
            "likes",
            "comments",
            "engagement",
            "is_video",
            "video_view_count",
            "post_url",
        ]
        st.dataframe(
            top_posts[display_cols],
            use_container_width=True,
            height=420,
        )
    else:
        st.info("No posts match the current filters.")

    st.markdown("---")

    # Raw table (caption + hashtags, for people who want details)
    with st.expander("📋 Full posts table (technical)", expanded=False):
        st.dataframe(df, use_container_width=True, height=500)


# ======================
#  NETWORK TAB
# ======================
def render_network_tab(stats: dict, extra: dict):
    st.subheader("Network: Followers, Following & Interaction")

    followers_list = extra.get("followers_list", [])
    following_list = extra.get("following_list", [])
    top_mentions = extra.get("top_mentions", {})

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Followers (list fetched)", len(followers_list))
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Following (list fetched)", len(following_list))
        st.markdown("</div>", unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Unique accounts mentioned", len(top_mentions))
        st.markdown("</div>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        with st.expander("👥 Sample of followers list"):
            if followers_list:
                st.write(f"Showing first {min(50, len(followers_list))} usernames:")
                st.write(", ".join(followers_list[:50]))
            else:
                st.info(
                    "Followers list is empty. Either profile is huge, "
                    "or we were not logged in / rate-limited for followers."
                )

    with col_b:
        with st.expander("➡️ Sample of following list"):
            if following_list:
                st.write(f"Showing first {min(50, len(following_list))} usernames:")
                st.write(", ".join(following_list[:50]))
            else:
                st.info(
                    "Following list is empty. Same reasons – auth/limits can block these."
                )


# ======================
#  TECH / LOGS / EXPORTS
# ======================
def render_tech_tab(stats: dict, df: pd.DataFrame, extra: dict, username: str):
    st.subheader("Tech & Logs")

    posts_failed = extra.get("posts_failed", 0)
    total_requests = extra.get("total_requests", 0)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Posts failed during scrape", posts_failed)
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Approx. requests made", total_requests)
        st.markdown("</div>", unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Configured MAX_POSTS", len(df))
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # Engagement timeline if present
    er_timeline = extra.get("er_timeline", [])
    if er_timeline:
        st.markdown("#### Engagement rate over time (per post)")
        tdf = pd.DataFrame(er_timeline)
        fig = px.line(
            tdf,
            x="date",
            y="er_percent",
            markers=True,
            template="plotly_dark",
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Engagement rate (%)",
            height=420,
            margin=dict(l=10, r=10, t=40, b=60),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No engagement timeline data available.")

    st.markdown("---")
    st.markdown("#### Export current view")

    # Export stats + extra as JSON
    combined = {
        "stats": stats,
        "extra": extra,
        "generated_at": datetime.now().isoformat(),
    }
    json_bytes = json.dumps(combined, indent=2, default=str).encode("utf-8")
    st.download_button(
        "📥 Download summary JSON",
        data=json_bytes,
        file_name=f"{username}_summary_from_dashboard.json",
        mime="application/json",
    )

    # Export posts as CSV
    if df is not None and not df.empty:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download posts CSV",
            data=csv_bytes,
            file_name=f"{username}_posts_from_dashboard.csv",
            mime="text/csv",
        )


# ==============
#  MAIN APP
# ==============
def main():
    render_header()

    # Session to hold latest run
    if "analysis" not in st.session_state:
        st.session_state.analysis = None
        st.session_state.last_username = ""

    st.sidebar.markdown("## 🎯 Run Analysis")
    username_input = st.sidebar.text_input(
        "Instagram username (without @)",
        placeholder="e.g. indiainlast24hr",
    )
    run_button = st.sidebar.button("🚀 Analyze Profile", type="primary")

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
**Notes**

- Backend: your custom `analyze_profile()` (Instaloader + Gemini/heuristic).
- Scraping depth: based on `MAX_POSTS` in the scraper code / env.
- Followers & following lists only appear when login/session allows it.
"""
    )

    if run_button:
        if not username_input.strip():
            st.warning("Please enter a username first.")
        else:
            with st.spinner(f"Running backend scraper for @{username_input} ..."):
                # Call your existing Python function
                stats, df, extra = analyze_profile(
                    username_input.strip(),
                    export=True,
                    print_report=False,  # avoid terminal spam in server logs
                )

                if not stats:
                    st.error("Scrape failed or returned empty stats. Check terminal logs.")
                else:
                    st.session_state.analysis = {
                        "stats": stats,
                        "df": df,
                        "extra": extra,
                    }
                    st.session_state.last_username = stats.get("username", username_input)

    # If nothing has been run yet
    if st.session_state.analysis is None:
        st.info("Run an analysis from the left sidebar to see the dashboard.")
        return

    # Use session data
    analysis = st.session_state.analysis
    stats = analysis["stats"]
    df = analysis["df"]
    extra = analysis["extra"]
    username = st.session_state.last_username

    # Tabs
    tab_overview, tab_content, tab_posts, tab_network, tab_tech = st.tabs(
        ["🌌 Overview", "🎨 Content & Hashtags", "📸 Posts Explorer", "🕸 Network", "🛠 Tech & Logs"]
    )

    with tab_overview:
        render_overview_tab(stats, df, extra)

    with tab_content:
        render_content_tab(stats, df, extra)

    with tab_posts:
        render_posts_tab(stats, df)

    with tab_network:
        render_network_tab(stats, extra)

    with tab_tech:
        render_tech_tab(stats, df, extra, username)


if __name__ == "__main__":
    main()
