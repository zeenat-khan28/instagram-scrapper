import instaloader
import pandas as pd
import time
import os
import sys
import re
import json
import logging
from datetime import datetime
from functools import wraps
from typing import List, Tuple, Dict, Any

from google import genai
from google.genai import types
from google.api_core.exceptions import ResourceExhausted

# -------------------------------------------------------------------
# 🔧 CONFIGURATION
# -------------------------------------------------------------------

# IMPORTANT: Do NOT hardcode real API keys if you will share this file.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if not GEMINI_API_KEY:
    print("⚠️ No Gemini API key detected – category/location will fall back to heuristic only.")
else:
    print("✅ Gemini API key detected.")

# Scraper settings
MAX_POSTS = int(os.environ.get("MAX_POSTS", "30"))  # posts per profile
SLEEP_DELAY = float(os.environ.get("SLEEP_DELAY", "2.0"))  # delay between posts
MAX_FOLLOWERS_FETCH = int(os.environ.get("MAX_FOLLOWERS_FETCH", "500"))  # safety cap

# Optional scheduling (only used if --schedule is provided via CLI)
DEFAULT_SCHEDULE_MINUTES = int(os.environ.get("SCHEDULE_MINUTES", "0"))

# Optional login via env (session reuse or login)
INSTA_USERNAME = os.environ.get("INSTA_USERNAME", "").strip()
INSTA_PASSWORD = os.environ.get("INSTA_PASSWORD", "").strip()

# Quiet down Instaloader logs a bit
logging.getLogger("instaloader").setLevel(logging.WARNING)

# Regex utils
MENTION_RE = re.compile(r"@([A-Za-z0-9_.]+)")
AD_KEYWORDS = ["#ad", "#sponsored", "#collab", "paid partnership"]


# -------------------------------------------------------------------
# 🔁 BACKOFF DECORATOR FOR ERROR RECOVERY
# -------------------------------------------------------------------
def with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """
    Simple exponential backoff decorator for network-sensitive functions.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    msg = str(e)
                    # If Instagram says "please wait a few minutes", don't spam retries
                    if "Please wait a few minutes before you try again" in msg:
                        print("[!] Instagram is temporarily rate limiting / blocking this IP.")
                        print("    Cannot continue scraping right now for this profile.")
                        break

                    if attempt == max_retries - 1:
                        print(f"[!] {func.__name__} failed after {max_retries} attempts: {e}")
                        raise
                    print(f"[!] {func.__name__} error on attempt {attempt+1}/{max_retries}: {e} "
                          f"– retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    delay *= 2
            if last_error:
                raise last_error
        return wrapper
    return decorator


# -------------------------------------------------------------------
# 🧩 INSTALOADER INSTANCE (AUTH + RATE-LIMIT-FRIENDLY)
# -------------------------------------------------------------------
def get_instaloader_instance() -> instaloader.Instaloader:
    """
    Create and return a configured Instaloader instance.

    - Uses env INSTA_USERNAME / INSTA_PASSWORD if available
    - Reuses session file .instaloader-session-<username> if present
    - Falls back to public (unauthenticated) mode otherwise
    """
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=3,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        ),
    )

    if INSTA_USERNAME:
        session_file = f".instaloader-session-{INSTA_USERNAME}"
        # Try to load existing session
        try:
            if os.path.exists(session_file):
                print(f"📂 Loading existing session for {INSTA_USERNAME}...")
                L.load_session_from_file(INSTA_USERNAME, session_file)
                print("✅ Session loaded (authenticated).")
            elif INSTA_PASSWORD:
                print(f"🔐 Logging in as {INSTA_USERNAME}...")
                L.login(INSTA_USERNAME, INSTA_PASSWORD)
                L.save_session_to_file(session_file)
                print("✅ Logged in & session saved.")
            else:
                print("ℹ️ INSTA_USERNAME set but no session file and no INSTA_PASSWORD – using public mode.")
        except Exception as e:
            print(f"⚠️ Could not login/load session – using public mode: {e}")
    else:
        print("ℹ️ No INSTA_USERNAME – using public (unauthenticated) Instaloader session.")

    return L


# -------------------------------------------------------------------
# 🔧 UTILS – HASHTAGS & MENTIONS
# -------------------------------------------------------------------
def extract_hashtags(caption: str) -> List[str]:
    """
    Extract hashtags from a caption string.
    Returns a list of lowercase hashtag strings without the '#'.
    """
    if not caption:
        return []
    words = caption.split()
    tags = [w[1:].lower() for w in words if w.startswith("#") and len(w) > 1]
    return tags


def extract_mentions_from_caption(caption: str) -> List[str]:
    """
    Extract @mentions from caption text using regex.
    """
    if not caption:
        return []
    return [m.lower() for m in MENTION_RE.findall(caption)]


# -------------------------------------------------------------------
# 🧠 LOCAL HEURISTIC FOR CATEGORY + LOCATION (NO GEMINI / GEMINI FAILS)
# -------------------------------------------------------------------
def heuristic_category_location(bio: str, captions: List[str]) -> Dict[str, str]:
    """
    Simple rule-based inference for category + location
    when Gemini is not available or quota is exhausted.
    """
    text = (bio or "") + " " + " ".join(captions or [])
    text_lower = text.lower()

    category = "Unknown (heuristic)"

    if any(k in text_lower for k in ["poetry", "poet", "shayari", "urdu"]):
        category = "Poetry / Writing"
    elif any(k in text_lower for k in ["fitness", "gym", "workout", "coach", "trainer"]):
        category = "Fitness"
    elif any(k in text_lower for k in ["travel", "wanderlust", "trip", "tourism"]):
        category = "Travel"
    elif any(k in text_lower for k in ["food", "chef", "recipe", "baking", "restaurant"]):
        category = "Food"
    elif any(k in text_lower for k in ["fashion", "style", "outfit", "ootd", "makeup", "beauty"]):
        category = "Fashion / Beauty"
    elif any(k in text_lower for k in ["developer", "coding", "programmer", "software", "tech"]):
        category = "Tech / Developer"
    elif any(k in text_lower for k in ["photography", "photographer", "camera", "portrait"]):
        category = "Photography"
    elif any(k in text_lower for k in ["music", "singer", "songwriter", "producer", "dj"]):
        category = "Music / Artist"

    location = "Unknown (heuristic)"
    known_locations = {
        "mumbai": "Mumbai, India",
        "bombay": "Mumbai, India",
        "pune": "Pune, India",
        "bangalore": "Bengaluru, India",
        "bengaluru": "Bengaluru, India",
        "delhi": "Delhi, India",
        "new delhi": "New Delhi, India",
        "hyderabad": "Hyderabad, India",
        "chennai": "Chennai, India",
        "kolkata": "Kolkata, India",
        "karachi": "Karachi, Pakistan",
        "lahore": "Lahore, Pakistan",
        "islamabad": "Islamabad, Pakistan",
        "dubai": "Dubai, UAE",
        "london": "London, UK",
        "new york": "New York, USA",
        "los angeles": "Los Angeles, USA",
        "toronto": "Toronto, Canada",
        "vancouver": "Vancouver, Canada",
        "sydney": "Sydney, Australia",
        "melbourne": "Melbourne, Australia",
        "paris": "Paris, France",
    }

    for key, loc in known_locations.items():
        if key in text_lower:
            location = loc
            break

    return {"category": category, "location": location}


# -------------------------------------------------------------------
# 🤖 GEMINI – CATEGORY & LOCATION INFERENCE (WITH CLEAN FALLBACK)
# -------------------------------------------------------------------
def infer_category_and_location(bio: str, captions: List[str], api_key: str) -> Dict[str, str]:
    """
    Uses Gemini to infer 'category' and 'location' from bio + recent captions.
    Falls back to heuristic on any error.
    """
    captions = captions or []

    if not api_key:
        print("ℹ️ No Gemini API key – using local heuristic for category/location.")
        return heuristic_category_location(bio, captions)

    captions_text = " || ".join(captions[:5]) if captions else ""
    prompt = f"""
    Analyze the following Instagram profile data:
    BIO: {bio}
    RECENT POST CAPTIONS: {captions_text}

    Task:
    1. Identify the 'Category' or Niche (e.g., Fitness, Travel, Food, Tech, Fashion, Meme).
    2. Identify the 'Location' (City, Country) where the creator is likely based. If uncertain, say 'Unknown'.

    Return ONLY a JSON string with keys 'category' and 'location'.
    """

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )

        if hasattr(response, "text") and response.text:
            return json.loads(response.text)

        print("⚠️ Gemini returned empty response – using local heuristic.")
        return heuristic_category_location(bio, captions)

    except ResourceExhausted:
        print("⚠️ Gemini quota exhausted – using local heuristic for category/location.")
        return heuristic_category_location(bio, captions)

    except Exception:
        print("⚠️ Gemini error – using local heuristic for category/location.")
        return heuristic_category_location(bio, captions)


# -------------------------------------------------------------------
# 🧮 CORE ANALYSIS LOGIC
# -------------------------------------------------------------------
@with_backoff(max_retries=3, base_delay=2.0)
def load_profile(L: instaloader.Instaloader, username: str) -> instaloader.Profile:
    return instaloader.Profile.from_username(L.context, username)


def analyze_profile(
    username: str,
    export: bool = True,
    print_report: bool = True,
) -> Tuple[Dict[str, Any], pd.DataFrame, Dict[str, Any]]:
    """
    Scrape an Instagram profile and compute analytics.

    Returns:
      stats: dict of profile-level metrics (for comparison, display)
      df:    per-post DataFrame
      extra: dict with hashtags, mentions, ER timeline, export paths, followers list, etc.
    """

    if username.startswith("@"):
        username = username[1:]

    print(f"\n🚀 STARTING ANALYSIS FOR: @{username}")
    L = get_instaloader_instance()

    # 1. Load Profile
    try:
        profile = load_profile(L, username)
    except Exception as e:
        print(f"[-] Error loading profile '{username}': {e}")
        return {}, pd.DataFrame(), {}

    print(f"✅ Loaded Profile: {profile.full_name} (@{profile.username})")
    print(f"   Followers: {profile.followers:,} | Posts: {profile.mediacount:,}")
    print(f"... Fetching last {MAX_POSTS} posts for @{username} ...")

    # 2. Scrape Posts (with light rate limiting)
    posts_data: List[Dict[str, Any]] = []
    total_requests = 0
    failed_posts = 0

    try:
        posts = profile.get_posts()
        for i, post in enumerate(posts):
            if i >= MAX_POSTS:
                break

            try:
                likes = getattr(post, "likes", 0) or 0
                comments = getattr(post, "comments", 0) or 0
                is_video = bool(getattr(post, "is_video", False))

                try:
                    video_views = getattr(post, "video_view_count", 0) if is_video else 0
                except Exception:
                    video_views = 0

                caption = post.caption if post.caption else ""
                date_local = post.date_local

                typename = getattr(post, "typename", "")
                if typename == "GraphImage":
                    content_type = "Photo"
                elif typename == "GraphVideo":
                    content_type = "Video/Reel"
                elif typename == "GraphSidecar":
                    content_type = "Carousel"
                else:
                    content_type = "Unknown"

                mentions = set(extract_mentions_from_caption(caption))
                try:
                    for m in getattr(post, "caption_mentions", []):
                        mentions.add(m.username.lower())
                except Exception:
                    pass
                try:
                    for u in getattr(post, "tagged_users", []):
                        mentions.add(u.username.lower())
                except Exception:
                    pass

                text_lower = caption.lower()
                is_brand_collab = any(k in text_lower for k in AD_KEYWORDS)

                posts_data.append(
                    {
                        "post_index": i + 1,
                        "shortcode": getattr(post, "shortcode", ""),
                        "date": date_local,
                        "likes": likes,
                        "comments": comments,
                        "is_video": is_video,
                        "video_view_count": video_views,
                        "caption": caption,
                        "hashtags": extract_hashtags(caption),
                        "mentions": list(mentions),
                        "content_type": content_type,
                        "is_brand_collab": is_brand_collab,
                    }
                )

                total_requests += 1

                if (i + 1) % 5 == 0:
                    print(f"   ... scraped {i+1} posts")

                # 🔁 Light rate limiting: short sleep every post, longer break every 20 posts
                if SLEEP_DELAY > 0:
                    if (i + 1) % 20 == 0:
                        print("   ⏸️ Taking a longer break to avoid rate limits...")
                        time.sleep(SLEEP_DELAY * 3)
                    else:
                        time.sleep(SLEEP_DELAY)

            except instaloader.exceptions.TooManyRequestsException as tre:
                print(f"[!] Too many requests while scraping posts: {tre}")
                print("    Stopping post scraping early to avoid hard block.")
                failed_posts += 1
                break
            except instaloader.exceptions.ConnectionException as ce:
                print(f"[!] Connection issue while scraping posts: {ce}")
                failed_posts += 1
                time.sleep(30)
                continue
            except Exception as e:
                print(f"[!] Skipping one post due to error: {e}")
                failed_posts += 1
                continue

    except Exception as e:
        print(f"[-] Warning during post scraping: {e}")

    df = pd.DataFrame(posts_data)

    # 3. Compute Metrics
    stats: Dict[str, Any] = {
        "username": profile.username,
        "full_name": profile.full_name,
        "bio": profile.biography or "",
        "followers": profile.followers,
        "following": profile.followees,
        "total_posts": profile.mediacount,
        "is_verified": profile.is_verified,
        "avg_likes": 0.0,
        "avg_comments": 0.0,
        "avg_views": 0.0,
        "engagement_rate": 0.0,
        "viral_percentage": 0.0,
        "posts_per_week": 0.0,
        "brand_collabs": 0,
    }

    extra: Dict[str, Any] = {
        "top_hashtags": {},
        "top_mentions": {},
        "content_distribution": {},
        "er_timeline": [],
        "posts_failed": failed_posts,
        "total_requests": total_requests,
    }

    if not df.empty:
        stats["avg_likes"] = float(df["likes"].mean())
        stats["avg_comments"] = float(df["comments"].mean())

        video_df = df[df["is_video"] == True]
        if not video_df.empty:
            stats["avg_views"] = float(video_df["video_view_count"].mean())
        else:
            stats["avg_views"] = 0.0

        followers_count = stats["followers"]
        if followers_count > 0:
            df["engagement"] = df["likes"] + df["comments"]
            df["engagement_rate_post"] = df["engagement"] / followers_count * 100.0
            stats["engagement_rate"] = float(df["engagement_rate_post"].mean())

            if not video_df.empty:
                video_df = video_df.copy()
                video_df["engagement"] = video_df["likes"] + video_df["comments"]
                video_df["engagement_rate_post"] = (
                    video_df["engagement"] / followers_count * 100.0
                )
                avg_video_eng = video_df["engagement_rate_post"].mean()
                viral_videos = video_df[video_df["engagement_rate_post"] > 3 * avg_video_eng]
                stats["viral_percentage"] = (
                    len(viral_videos) / len(video_df) * 100.0 if len(video_df) > 0 else 0.0
                )
            else:
                stats["viral_percentage"] = 0.0
        else:
            stats["engagement_rate"] = 0.0
            stats["viral_percentage"] = 0.0

        if len(df) > 1:
            date_range_days = (df["date"].max() - df["date"].min()).days
            if date_range_days > 0:
                weeks = date_range_days / 7.0
                stats["posts_per_week"] = len(df) / weeks
            else:
                stats["posts_per_week"] = 0.0

        stats["brand_collabs"] = int(df["is_brand_collab"].sum())

        all_hashtags: List[str] = []
        for hs in df["hashtags"]:
            all_hashtags.extend(hs)
        if all_hashtags:
            hashtags_series = pd.Series(all_hashtags)
            top_hashtags_series = hashtags_series.value_counts().head(20)
            extra["top_hashtags"] = top_hashtags_series.to_dict()

        all_mentions: List[str] = []
        for ms in df["mentions"]:
            all_mentions.extend(ms)
        if all_mentions:
            mentions_series = pd.Series(all_mentions)
            top_mentions_series = mentions_series.value_counts().head(20)
            extra["top_mentions"] = top_mentions_series.to_dict()

        content_dist_series = df["content_type"].value_counts(normalize=True) * 100.0
        extra["content_distribution"] = content_dist_series.to_dict()

        er_timeline = []
        if "engagement_rate_post" in df.columns:
            df_sorted = df.sort_values("date")
            for _, row in df_sorted.iterrows():
                er_timeline.append(
                    {
                        "date": row["date"].strftime("%Y-%m-%d"),
                        "post_index": int(row["post_index"]),
                        "er_percent": float(round(row["engagement_rate_post"], 3)),
                    }
                )
        extra["er_timeline"] = er_timeline

    else:
        print("[-] No posts could be scraped. Some metrics will be zero.")

    # ===== Followers & following lists (AUTH REQUIRED) =====
    followers_list: List[str] = []
    following_list: List[str] = []

    # Only even try if we are logged in
    if L.context.username:
        try:
            print("🔎 Fetching followers list (may be capped)...")
            for idx, f in enumerate(profile.get_followers()):
                followers_list.append(f.username)
                if idx + 1 >= MAX_FOLLOWERS_FETCH:
                    print(f"   ⏸️ Reached MAX_FOLLOWERS_FETCH={MAX_FOLLOWERS_FETCH}, stopping.")
                    break
        except Exception as e:
            print(f"⚠️ Could not fetch followers list: {e}")

        try:
            print("🔎 Fetching following list (followees, capped)...")
            for idx, f in enumerate(profile.get_followees()):
                following_list.append(f.username)
                if idx + 1 >= MAX_FOLLOWERS_FETCH:
                    print(f"   ⏸️ Reached MAX_FOLLOWERS_FETCH={MAX_FOLLOWERS_FETCH}, stopping.")
                    break
        except Exception as e:
            print(f"⚠️ Could not fetch following list: {e}")
    else:
        print("ℹ️ Not logged in – cannot fetch followers/following lists. "
              "Set INSTA_USERNAME and use a saved session.")

    extra["followers_list"] = followers_list
    extra["following_list"] = following_list

    # 4. Category + Location (Gemini + heuristic)
    captions = [p["caption"] for p in posts_data] if posts_data else []
    print("🤖 Inferring category and location (Gemini + heuristic)...")
    ai_res = infer_category_and_location(stats["bio"], captions, GEMINI_API_KEY)
    stats["category"] = ai_res.get("category", "Unknown")
    stats["location"] = ai_res.get("location", "Unknown")

    # ----------------------------------------------------------------
    # 5. Export Options: everything into a per-user folder + logs
    # ----------------------------------------------------------------
    base_name = stats["username"] or username or "profile"
    output_dir = os.path.join(os.getcwd(), base_name)
    os.makedirs(output_dir, exist_ok=True)

    posts_csv = os.path.join(output_dir, f"{base_name}_posts.csv")
    profile_csv = os.path.join(output_dir, f"{base_name}_profile_summary.csv")
    profile_json = os.path.join(output_dir, f"{base_name}_profile_summary.json")
    profile_xlsx = os.path.join(output_dir, f"{base_name}_profile_summary.xlsx")
    posts_log = os.path.join(output_dir, f"{base_name}_posts_log.jsonl")

    followers_log = os.path.join(output_dir, f"{base_name}_followers.jsonl")
    following_log = os.path.join(output_dir, f"{base_name}_following.jsonl")
    interactions_log = os.path.join(output_dir, f"{base_name}_interactions_summary.json")

    if export:
        # Posts CSV (per-post structured data)
        df.to_csv(posts_csv, index=False)

        # Posts log file – JSONL (1 JSON object per line for every post)
        try:
            with open(posts_log, "w", encoding="utf-8") as f:
                for p in posts_data:
                    p_serializable = dict(p)
                    if isinstance(p_serializable.get("date"), datetime):
                        p_serializable["date"] = p_serializable["date"].isoformat()
                    else:
                        p_serializable["date"] = str(p_serializable.get("date"))
                    f.write(json.dumps(p_serializable, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"⚠️ Could not write posts log file ({posts_log}): {e}")

        # Followers JSONL
        try:
            with open(followers_log, "w", encoding="utf-8") as f:
                for uname in followers_list:
                    f.write(json.dumps({"username": uname}, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"⚠️ Could not write followers log file ({followers_log}): {e}")

        # Following JSONL
        try:
            with open(following_log, "w", encoding="utf-8") as f:
                for uname in following_list:
                    f.write(json.dumps({"username": uname}, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"⚠️ Could not write following log file ({following_log}): {e}")

        # Interactions summary (top interacted users = top_mentions)
        try:
            interactions_summary = {
                "username": stats["username"],
                "generated_at": datetime.now().isoformat(),
                "top_mentions": extra.get("top_mentions", {}),
                "posts_failed": failed_posts,
                "total_requests": total_requests,
            }
            with open(interactions_log, "w", encoding="utf-8") as f:
                json.dump(interactions_summary, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Could not write interactions summary file ({interactions_log}): {e}")

        # Profile summary (CSV / JSON / Excel)
        profile_df = pd.DataFrame(
            [
                {
                    "Profile Name": stats["full_name"],
                    "Username": stats["username"],
                    "Bio": stats["bio"],
                    "Location": stats["location"],
                    "Category": stats["category"],
                    "Followers": stats["followers"],
                    "Following": stats["following"],
                    "Total Posts": stats["total_posts"],
                    "Is Verified": stats["is_verified"],
                    "Avg Likes": round(stats["avg_likes"], 1),
                    "Avg Comments": round(stats["avg_comments"], 1),
                    "Avg Views (Reels)": round(stats["avg_views"], 1),
                    "Engagement Rate %": round(stats["engagement_rate"], 3),
                    "Viral Video %": round(stats["viral_percentage"], 2),
                    "Brand Collaborations (Recent)": stats["brand_collabs"],
                    "Posts Per Week": round(stats["posts_per_week"], 2),
                    "Scraping Date": datetime.now().strftime("%Y-%m-%d"),
                }
            ]
        )
        profile_df.to_csv(profile_csv, index=False)
        profile_df.to_json(profile_json, orient="records", indent=2)
        try:
            profile_df.to_excel(profile_xlsx, index=False)
        except Exception as e:
            print(f"⚠️ Could not write Excel file ({profile_xlsx}): {e}")

    # ----------------------------------------------------------------
    # 6. Print Final Report (line by line)
    # ----------------------------------------------------------------
    if print_report:
        print("\n========================================")
        print(f"📊 REPORT: @{stats['username']}")
        print(f"Name: {stats['full_name']}")
        print("========================================")

        print(f"📝 Bio: {stats['bio'].replace(chr(10), ' ')}")
        print(f"📍 Location (AI/Heuristic): {stats['location']}")
        print(f"🏷️  Category (AI/Heuristic): {stats['category']}")
        print("--------------------")
        print(f"👥 Followers: {stats['followers']:,}")
        print(f"👉 Following: {stats['following']:,}")
        print(f"📝 Total Posts: {stats['total_posts']:,}")
        print(f"✅ Verified: {stats['is_verified']}")
        print()
        print(f"👍 Avg Likes: {stats['avg_likes']:.1f}")
        print(f"💬 Avg Comments: {stats['avg_comments']:.1f}")
        print(f"🎥 Avg Views (Reels): {stats['avg_views']:.1f}")
        print()
        print(f"🚀 Engagement Rate: {stats['engagement_rate']:.3f}%")
        print(f"🔥 Viral Video %: {stats['viral_percentage']:.2f}%")
        print(f"🤝 Brand Collaborations (recent sample): {stats['brand_collabs']}")
        print(f"📅 Posts Per Week: {stats['posts_per_week']:.2f}")
        print(f"📆 Scraping Date: {datetime.now().strftime('%Y-%m-%d')}")
        print(f"📉 Posts failed during scrape: {failed_posts}")
        print(f"📡 Total requests (approx): {total_requests}")
        print("========================================")

        if extra["content_distribution"]:
            print("\n📺 Content Type Distribution (% of recent posts):")
            for ctype, pct in extra["content_distribution"].items():
                print(f"  - {ctype}: {pct:.1f}%")
        else:
            print("\n📺 Content Type Distribution: No posts.")

        if extra["top_hashtags"]:
            print("\n#️⃣ Top Hashtags:")
            for tag, freq in extra["top_hashtags"].items():
                print(f"  #{tag}: {freq} times")
        else:
            print("\n#️⃣ Top Hashtags: None detected.")

        if extra["top_mentions"]:
            print("\n👤 Frequently Mentioned / Tagged Accounts:")
            for user, freq in extra["top_mentions"].items():
                print(f"  @{user}: {freq} times")
        else:
            print("\n👤 Frequently Mentioned / Tagged Accounts: None detected.")

        if extra["er_timeline"]:
            print("\n📈 Engagement Rate Over Time (most recent posts):")
            for item in extra["er_timeline"][-10:]:
                print(
                    f"  {item['date']} (Post #{item['post_index']}): "
                    f"{item['er_percent']:.3f}%"
                )
        else:
            print("\n📈 Engagement Rate Over Time: No data.")

        print("\n📂 Exported Files (inside folder):")
        print(f"  Folder: {output_dir}")
        print(f"  - Posts CSV: {posts_csv}")
        print(f"  - Posts Log (JSONL): {posts_log}")
        print(f"  - Followers Log (JSONL): {followers_log}")
        print(f"  - Following Log (JSONL): {following_log}")
        print(f"  - Interactions Summary (JSON): {interactions_log}")
        print(f"  - Profile CSV: {profile_csv}")
        print(f"  - Profile JSON: {profile_json}")
        if os.path.exists(profile_xlsx):
            print(f"  - Profile Excel: {profile_xlsx}")
        print("\n[+] Analysis complete.\n")

    # Attach export paths to extra
    extra["output_dir"] = output_dir
    extra["posts_csv"] = posts_csv
    extra["posts_log"] = posts_log
    extra["followers_log"] = followers_log
    extra["following_log"] = following_log
    extra["interactions_log"] = interactions_log
    extra["profile_csv"] = profile_csv
    extra["profile_json"] = profile_json
    extra["profile_xlsx"] = profile_xlsx

    return stats, df, extra


# -------------------------------------------------------------------
# 🔁 MULTI-PROFILE COMPARISON & OPTIONAL SCHEDULING
# -------------------------------------------------------------------
def analyze_multiple_profiles(usernames: List[str], schedule_minutes: int = 0):
    """
    Analyze multiple profiles sequentially.
    If schedule_minutes > 0, repeats the whole batch periodically.
    """

    def run_once():
        summaries = []
        for i, uname in enumerate(usernames):
            print(f"\n====== [{i+1}/{len(usernames)}] {uname} ======")
            stats, df, extra = analyze_profile(uname, export=True, print_report=True)
            if stats:
                summaries.append(stats)
            time.sleep(SLEEP_DELAY)

        if summaries:
            summary_df = pd.DataFrame(summaries)
            cols = [
                "username",
                "full_name",
                "followers",
                "following",
                "total_posts",
                "avg_likes",
                "avg_comments",
                "avg_views",
                "engagement_rate",
                "viral_percentage",
                "posts_per_week",
                "category",
                "location",
            ]
            cols = [c for c in cols if c in summary_df.columns]
            print("\n📊 Comparison Summary (key metrics):")
            print(summary_df[cols].to_string(index=False))

            summary_df.to_csv("profiles_comparison.csv", index=False)
            summary_df.to_json("profiles_comparison.json", orient="records", indent=2)
            try:
                summary_df.to_excel("profiles_comparison.xlsx", index=False)
            except Exception as e:
                print(f"⚠️ Could not write profiles_comparison.xlsx: {e}")
            print("\n📂 Comparison exports:")
            print("  - profiles_comparison.csv")
            print("  - profiles_comparison.json")
            if os.path.exists("profiles_comparison.xlsx"):
                print("  - profiles_comparison.xlsx")

    if schedule_minutes > 0:
        while True:
            print(f"\n⏰ Scheduled run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            run_once()
            print(f"\n⏳ Sleeping for {schedule_minutes} minutes before next run...")
            time.sleep(schedule_minutes * 60)
    else:
        run_once()


# -------------------------------------------------------------------
# 🏁 CLI ENTRYPOINT
# -------------------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]
    schedule_minutes = 0
    usernames: List[str] = []

    if not args:
        entered = input("Enter Instagram Username (or multiple separated by spaces): ").strip()
        if entered:
            usernames = entered.split()
        else:
            print("No username provided.")
            sys.exit(0)
    else:
        if "--schedule" in args:
            idx = args.index("--schedule")
            if idx + 1 < len(args):
                try:
                    schedule_minutes = int(args[idx + 1])
                except ValueError:
                    print("⚠️ Invalid schedule minutes value; ignoring scheduling.")
                    schedule_minutes = 0
                filtered = []
                for i, a in enumerate(args):
                    if i in (idx, idx + 1):
                        continue
                    filtered.append(a)
                usernames = filtered
            else:
                print("⚠️ --schedule provided without minutes. Ignoring scheduling.")
                usernames = [a for a in args if a != "--schedule"]
        else:
            usernames = args

    if not usernames:
        print("No usernames provided.")
        sys.exit(0)

    if len(usernames) == 1 and schedule_minutes == 0:
        analyze_profile(usernames[0], export=True, print_report=True)
    else:
        analyze_multiple_profiles(usernames, schedule_minutes=schedule_minutes)
