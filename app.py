from flask import Flask, render_template, request, jsonify
from muzzy_bhai import InstagramAnalyticsScraper
from datetime import datetime
import json
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        username = request.json.get('username')
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        # Initialize scraper
        scraper = InstagramAnalyticsScraper()
        
        # Scrape profile data
        analytics = scraper.scrape_profile(username, max_posts=30)
        
        if not analytics:
            return jsonify({'error': f'Could not fetch data for @{username}'}), 404
        
        # Save the data for reference
        os.makedirs('data', exist_ok=True)
        filename = f"data/{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(analytics, f, indent=2, ensure_ascii=False, default=str)
        
        return jsonify(analytics)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
