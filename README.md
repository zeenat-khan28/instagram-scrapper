# instagram-scraper

# 📊 Advanced Instagram Analytics Scraper & Dashboard

This is a **full-stack Instagram analytics system** that scrapes public Instagram profiles, computes insightful engagement metrics, and presents everything in a **beautiful Streamlit dashboard**. Checkout the website here https://instagram--scraper.streamlit.app/.

It combines:

* ⚡ **Python + Instaloader** (data scraping)
* 📈 **Pandas + analytics layer** (processing)
* 🤖 **Gemini AI + heuristic fallback** (category & location inference)
* 🌙 **Dark mode dashboard** (Streamlit + Plotly)

This project includes:

* A **backend** that fetches real Instagram data
* A **frontend dashboard** that converts data into clean, human-readable insights
* A **rate-limit–safe system** with sessions, backoff, and smart error handling

Perfect for:

* Influencer analytics
* Market research
* Brand social intelligence
* Academic / internship / portfolio projects

## ✨ Features

### 📥 Scraping Engine (Instaloader-based)

* Recent posts (up to configurable limit)
* Likes, comments, reels views
* Content type detection (Photo / Video / Carousel)
* Captions, hashtags, mentions
* Followers & following lists (if authenticated)
* Shortcodes for direct post links

### 📊 Analytics Engine

* Avg likes, comments, views
* Engagement rate per post + overall
* Posting frequency (Posts/week)
* Viral video detection (3× baseline rule)
* Top hashtags + top mentions
* Content distribution (%)
* Interaction summary (JSON)
* Export of all datasets

### 🤖 AI Insights (Gemini 2.0 Flash)

* Predicts **category/niche** (e.g., Travel, Fitness, Tech)
* Predicts **location** from bio + captions
* Full fallback system using **rule-based heuristics** when:

  * Gemini quota exceeds
  * API fails
  * No API key is provided

### 🛡 Rate Limit Recovery System

A unique approach used in this project:

* Exponential backoff wrapper (`@with_backoff`)
* Larger sleep every few posts
* Automatic pause on "Please wait a few minutes" errors
* Session reuse for minimal login activity

> This lets the scraper survive even under strong IP restrictions.

### 🎨 Streamlit Dashboard (Dark Mode)

* Modern dark UI with colored metrics
* Tabs:

  * Overview
  * Content Insights
  * Engagement Insights
  * Top Posts
  * Hashtag Analysis
  * Interaction Network
  * Downloads (CSV/JSON)
* Interactive charts (Plotly)
* Data explorer
* Downloads for all datasets

## 📁 Project Structure

```
.
├── scraper.py              # Backend: scraping + analytics + exports
├── ig_dashboard.py         # Dark-themed Streamlit dashboard
├── requirements.txt        # Packages required to run the project
├── .gitignore              # Hides sessions, creds, venv, local data
└── README.md               # Documentation (this file)
```

Outputs (auto-generated per profile):

```
<username>/
    <username>_posts.csv
    <username>_posts_log.jsonl
    <username>_followers.jsonl
    <username>_following.jsonl
    <username>_profile_summary.csv
    <username>_profile_summary.json
    <username>_profile_summary.xlsx
    <username>_interactions_summary.json
```

---

## 🔧 Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/zeenat-khan28/instagram-scrapper.git
cd instagram-scrapper
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate           # Mac/Linux
venv\Scripts\activate              # Windows
```

### 3. Install all dependencies

```bash
pip install -r requirements.txt
```

---

## 🔐 Environment Variables

Create a `.env` file or export variables in the terminal.

### Gemini API (Optional but recommended)

```
GEMINI_API_KEY=your_key_here
```

### Instagram login (Optional)

For followers/following + fewer rate limits:

```
INSTA_USERNAME=your_burner_username
INSTA_PASSWORD=your_burner_password
```

> Use a **burner Instagram account**, not your main one.
> Instagram rate-limits aggressively, so using a secondary account is safer.


## ▶️ Running the Scraper (CLI)

Scrape any public profile:

```bash
python scraper.py virat.kohli
```

Scrape multiple profiles:

```bash
python scraper.py user1 user2 user3
```

This generates:

* CSV files
* JSON summaries
* Followers/following lists
* Engagement timeline
* Console report


## 🚀 Running the Dashboard (Recommended)

Start the Streamlit dashboard:

```bash
streamlit run ig_dashboard.py
```

Then open:

```
http://localhost:8501
```

### Dashboard Screenshots (optional section for GitHub)

Add images to `/images/`:

* Dashboard Home
* Content Insights
* Engagement Insights
* Top Posts

## 🛡 Rate Limit Handling (Your Unique Feature)

This project implements a **multi-layer, interview-safe rate-limit strategy**:

### 1. Exponential Backoff Decorator

```python
@with_backoff(max_retries=3, base_delay=2.0)
def load_profile(...):
```

Automatically retries with delays:

* 2s → 4s → 8s

### 2. Intelligent Sleep Strategy

* Sleep after each post
* Longer sleep every 20 posts
* Immediately stop if Instagram shows:

  ```
  "Please wait a few minutes before you try again"
  ```

### 3. Session File Reuse

Instaloader saves:

```
.instaloader-session-<username>
```

This prevents frequent logins → fewer bans.

### 4. User-Agent spoofing

Pretends to be a normal Chrome browser.

### Result:

**You can scrape more profiles without getting IP banned.**

---

## 📝 Output Example (Readable Format)

For each profile:

```
Bio: Fitness coach | Mumbai 🇮🇳
Category: Fitness
Location: Mumbai, India

Avg Likes: 1,928
Avg Comments: 112
Engagement Rate: 7.34%
Posts Per Week: 1.8

Top Hashtags:
#fitness 12 times
#workout 9 times
#motivation 5 times

Top Posts:
- Feb 2024: 18.3k likes
- Dec 2023: 15.1k likes
```


## ⚠️ Limitations

* Cannot scrape private profiles (unless burner account follows them)
* Instagram anti-bot changes may break scraping in the future
* High-volume scraping still risks temporary soft-bans

## 📜 License

MIT License (free for personal + commercial use)

## ⭐ How to Support

If you like the project:

* ⭐ Star the repository
* 📌 Use it in your own projects
* 🤝 Contribute improvements

## 🙌 Credits

Built using:

* Instaloader
* Streamlit
* Plotly
* Gemini AI
* pandas


