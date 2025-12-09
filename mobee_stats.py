#!/usr/bin/env python3
"""
Mobee Game Stats Analyzer
Fetches game notifications from Slack and generates statistics
"""

import requests
import re
from collections import defaultdict, Counter
from datetime import datetime
import json
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import os

# Register Roboto fonts for PDF
pdfmetrics.registerFont(TTFont('Roboto', 'fonts/Roboto-Regular.ttf'))
pdfmetrics.registerFont(TTFont('Roboto-Bold', 'fonts/Roboto-Bold.ttf'))
pdfmetrics.registerFont(TTFont('Roboto-Italic', 'fonts/Roboto-Italic.ttf'))
pdfmetrics.registerFont(TTFont('Roboto-BoldItalic', 'fonts/Roboto-BoldItalic.ttf'))

# Register Roboto font family for matplotlib
roboto_path = 'fonts/Roboto-Regular.ttf'
fm.fontManager.addfont(roboto_path)
plt.rcParams['font.family'] = 'Roboto'

# Slack credentials from environment variables
SLACK_TOKEN = os.environ.get('SLACK_TOKEN', '')
CHANNEL_ID = os.environ.get('CHANNEL_ID', '')

def fetch_slack_messages(channel_id, token):
    """Fetch all messages from a Slack channel"""
    messages = []
    cursor = None
    
    url = "https://slack.com/api/conversations.history"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    while True:
        params = {
            "channel": channel_id,
            "limit": 1000  # Max allowed per request
        }
        if cursor:
            params["cursor"] = cursor
            
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if not data.get("ok"):
            print(f"Error fetching messages: {data.get('error')}")
            break
            
        messages.extend(data.get("messages", []))
        
        # Check if there are more messages
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
            
    return messages

def parse_game_notification(text, timestamp=None):
    """Parse a game notification message to extract data"""

    # Check if it's a high score
    is_high_score = "🏆 HIGH SCORE:" in text or "HIGH SCORE:" in text or ":trophy: HIGH SCORE:" in text

    # Extract score
    score_match = re.search(r'(?:HIGH SCORE|Score):\s*(\d+)', text)
    if not score_match:
        return None

    score = int(score_match.group(1))
    
    # Extract location (city, country)
    location_match = re.search(r'\|\s*([^|]+),\s*([^|]+)\s*\|', text)
    city = location_match.group(1).strip() if location_match else "Unknown"
    country = location_match.group(2).strip() if location_match else "Unknown"

    # Extract platform (between country and user code)
    platform_match = re.search(r'\|\s*([^|]+)\s*\|\s*[a-zA-Z0-9]+\s*#', text)
    platform = platform_match.group(1).strip() if platform_match else "Unknown"

    # Extract user code (the short code after the pipe, before #)
    user_match = re.search(r'\|\s*([a-zA-Z0-9]+)\s*#\d+', text)
    user_code = user_match.group(1).strip() if user_match else "Unknown"

    # Extract game number for this user
    game_num_match = re.search(r'#(\d+)', text)
    game_number = int(game_num_match.group(1)) if game_num_match else 0

    # Extract game code
    game_code_match = re.search(r'Code:\s*(MOBEE-[0-9A-Z-]+)', text)
    game_code = game_code_match.group(1) if game_code_match else "Unknown"

    return {
        "is_high_score": is_high_score,
        "score": score,
        "city": city,
        "country": country,
        "platform": platform,
        "user_code": user_code,
        "game_number": game_number,
        "game_code": game_code,
        "timestamp": timestamp
    }

def analyze_games(games):
    """Analyze game data and generate statistics"""
    
    if not games:
        return None
    
    # Basic counts
    total_games = len(games)
    unique_players = len(set(g["user_code"] for g in games))
    high_score_games = sum(1 for g in games if g["is_high_score"])
    
    # Score statistics
    scores = [g["score"] for g in games]
    avg_score = sum(scores) / len(scores)
    sorted_scores = sorted(scores)
    median_score = sorted_scores[len(sorted_scores)//2] if len(sorted_scores) % 2 == 1 else (sorted_scores[len(sorted_scores)//2-1] + sorted_scores[len(sorted_scores)//2]) / 2
    max_score = max(scores)
    min_score = min(scores)
    
    # Location statistics
    city_counts = Counter(g["city"] for g in games)
    country_counts = Counter(g["country"] for g in games)

    # Platform statistics
    platform_counts = Counter(g["platform"] for g in games)
    platform_scores = defaultdict(list)
    for game in games:
        platform_scores[game["platform"]].append(game["score"])

    # Player statistics
    player_games = defaultdict(list)
    player_high_scores = defaultdict(int)
    player_high_score_info = {}  # Track location, platform, timestamp for high score
    player_most_common_city = {}  # Track most common city for each player
    player_cities = defaultdict(set)
    player_city_counts = defaultdict(lambda: defaultdict(int))
    player_platforms = defaultdict(set)

    for game in games:
        player_games[game["user_code"]].append(game["score"])
        if game["score"] > player_high_scores[game["user_code"]]:
            player_high_scores[game["user_code"]] = game["score"]
            player_high_score_info[game["user_code"]] = {
                "location": f"{game['city']}, {game['country']}",
                "platform": game["platform"],
                "timestamp": game.get("timestamp", "N/A")
            }
        player_cities[game["user_code"]].add(game["city"])
        player_city_counts[game["user_code"]][game["city"]] += 1
        player_platforms[game["user_code"]].add(game["platform"])

    # Determine most common city for each player
    for player, cities in player_city_counts.items():
        player_most_common_city[player] = max(cities.items(), key=lambda x: x[1])[0]

    # Engagement metrics
    one_time_players = sum(1 for scores in player_games.values() if len(scores) == 1)
    returning_players = sum(1 for scores in player_games.values() if len(scores) > 1)
    super_engaged = sum(1 for scores in player_games.values() if len(scores) >= 10)

    # Location diversity
    location_scores = defaultdict(list)
    for game in games:
        location_scores[game["country"]].append(game["score"])

    # Daily statistics
    daily_stats = defaultdict(lambda: {"games": 0, "players": set()})
    for game in games:
        if game.get("timestamp"):
            date = datetime.fromtimestamp(game["timestamp"]).strftime("%Y-%m-%d")
            daily_stats[date]["games"] += 1
            daily_stats[date]["players"].add(game["user_code"])

    # Convert to sortable list
    daily_data = []
    for date, data in sorted(daily_stats.items()):
        daily_data.append({
            "date": date,
            "games": data["games"],
            "unique_players": len(data["players"])
        })
    
    # Top players by games played
    top_players_by_games = sorted(
        player_games.items(), 
        key=lambda x: len(x[1]), 
        reverse=True
    )[:10]
    
    # Top players by high score
    top_players_by_score = sorted(
        player_high_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    # Score distribution
    score_ranges = {
        "0-5": 0,
        "6-10": 0,
        "11-15": 0,
        "16-20": 0,
        "20+": 0
    }
    
    for score in scores:
        if score <= 5:
            score_ranges["0-5"] += 1
        elif score <= 10:
            score_ranges["6-10"] += 1
        elif score <= 15:
            score_ranges["11-15"] += 1
        elif score <= 20:
            score_ranges["16-20"] += 1
        else:
            score_ranges["20+"] += 1
    
    return {
        "total_games": total_games,
        "unique_players": unique_players,
        "high_score_games": high_score_games,
        "avg_score": avg_score,
        "median_score": median_score,
        "max_score": max_score,
        "min_score": min_score,
        "city_counts": dict(city_counts),
        "country_counts": dict(country_counts),
        "platform_counts": dict(platform_counts),
        "platform_scores": {k: {"count": len(v), "avg": sum(v)/len(v), "max": max(v)} for k, v in platform_scores.items()},
        "location_scores": {k: {"count": len(v), "avg": sum(v)/len(v)} for k, v in location_scores.items()},
        "engagement": {
            "one_time_players": one_time_players,
            "returning_players": returning_players,
            "super_engaged": super_engaged
        },
        "player_cities": {k: len(v) for k, v in player_cities.items()},
        "player_platforms": {k: len(v) for k, v in player_platforms.items()},
        "player_most_common_city": player_most_common_city,
        "player_high_score_info": player_high_score_info,
        "top_players_by_games": top_players_by_games,
        "top_players_by_score": top_players_by_score,
        "score_distribution": score_ranges,
        "daily_stats": daily_data
    }

def print_stats(stats):
    """Print formatted statistics"""
    
    print("\n" + "="*60)
    print("MOBEE GAME STATISTICS")
    print("="*60)
    
    print("\n📊 OVERALL STATS")
    print(f"Total Games Played: {stats['total_games']}")
    print(f"Unique Players: {stats['unique_players']}")
    print(f"High Score Games: {stats['high_score_games']}")
    print(f"Total Play Time: {stats['total_games']} minutes")
    
    print("\n🎯 SCORE STATS")
    print(f"Average Score: {stats['avg_score']:.2f}")
    print(f"Highest Score: {stats['max_score']}")
    print(f"Lowest Score: {stats['min_score']}")
    
    print("\n📈 SCORE DISTRIBUTION")
    for range_label, count in stats['score_distribution'].items():
        percentage = (count / stats['total_games']) * 100
        print(f"{range_label:8} : {count:4} games ({percentage:5.1f}%)")
    
    print("\n🌍 LOCATION STATS")
    print("\nBy City:")
    for city, count in sorted(stats['city_counts'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / stats['total_games']) * 100
        print(f"  {city:20} : {count:4} games ({percentage:5.1f}%)")
    
    print("\nBy Country:")
    for country, count in sorted(stats['country_counts'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / stats['total_games']) * 100
        print(f"  {country:20} : {count:4} games ({percentage:5.1f}%)")
    
    print("\n🏆 TOP 10 PLAYERS BY GAMES PLAYED")
    for i, (player, scores) in enumerate(stats['top_players_by_games'], 1):
        avg = sum(scores) / len(scores)
        print(f"{i:2}. {player:10} : {len(scores):4} games (avg: {avg:.2f})")
    
    print("\n🥇 TOP 10 PLAYERS BY HIGH SCORE")
    for i, (player, high_score) in enumerate(stats['top_players_by_score'], 1):
        print(f"{i:2}. {player:10} : {high_score:2} points")

    # Platform statistics
    print("\n📱 PLATFORM STATS")
    platform_data = [(platform, data) for platform, data in stats['platform_scores'].items()]
    platform_data.sort(key=lambda x: x[1]['count'], reverse=True)
    for platform, data in platform_data[:10]:
        percentage = (data['count'] / stats['total_games']) * 100
        print(f"  {platform:20} : {data['count']:4} games ({percentage:5.1f}%) | avg: {data['avg']:.2f} | max: {data['max']}")

    # Engagement insights
    print("\n👥 PLAYER ENGAGEMENT")
    eng = stats['engagement']
    print(f"One-time Players    : {eng['one_time_players']:3} ({eng['one_time_players']/stats['unique_players']*100:5.1f}%)")
    print(f"Returning Players   : {eng['returning_players']:3} ({eng['returning_players']/stats['unique_players']*100:5.1f}%)")
    print(f"Super Engaged (10+) : {eng['super_engaged']:3} ({eng['super_engaged']/stats['unique_players']*100:5.1f}%)")

    # Top countries by average score
    print("\n🌎 TOP COUNTRIES BY AVERAGE SCORE")
    country_data = [(country, data) for country, data in stats['location_scores'].items() if data['count'] >= 5]
    country_data.sort(key=lambda x: x[1]['avg'], reverse=True)
    for country, data in country_data[:10]:
        print(f"  {country:20} : avg {data['avg']:5.2f} ({data['count']:3} games)")

    # Multi-location and multi-platform players
    multi_location_players = [(player, count) for player, count in stats['player_cities'].items() if count > 1]
    multi_location_players.sort(key=lambda x: x[1], reverse=True)
    if multi_location_players:
        print("\n🌍 TOP TRAVELERS (Multiple Cities)")
        for player, city_count in multi_location_players[:10]:
            print(f"  {player:10} : {city_count} cities")

    multi_platform_players = [(player, count) for player, count in stats['player_platforms'].items() if count > 1]
    multi_platform_players.sort(key=lambda x: x[1], reverse=True)
    if multi_platform_players:
        print("\n📲 TOP CROSS-PLATFORM PLAYERS")
        for player, platform_count in multi_platform_players[:10]:
            print(f"  {player:10} : {platform_count} platforms")

    print("\n" + "="*60)

def create_charts(stats, games):
    """Create histogram charts and return them as Image objects"""
    charts = {}

    # Set style for all charts
    plt.style.use('seaborn-v0_8-darkgrid')

    # 1. Score Distribution Histogram
    fig, ax = plt.subplots(figsize=(6, 3))
    scores = [g["score"] for g in games]
    ax.hist(scores, bins=range(0, 32, 2), color='#667eea', edgecolor='white', alpha=0.8)
    ax.set_xlabel('Score', fontsize=10)
    ax.set_ylabel('Number of Games', fontsize=10)
    ax.set_title('Score Distribution', fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()

    # Save to bytes
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    charts['score_dist'] = Image(img_buffer, width=4*inch, height=2*inch)
    plt.close()

    # 2. Games Played by Player (Top 15)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    top_players = sorted(stats['top_players_by_games'][:15], key=lambda x: len(x[1]))
    players = [p[0] for p in top_players]
    game_counts = [len(p[1]) for p in top_players]

    ax.barh(players, game_counts, color='#764ba2', alpha=0.8)
    ax.set_xlabel('Number of Games', fontsize=10)
    ax.set_ylabel('Player', fontsize=9)
    ax.set_title('Top 15 Players by Games Played', fontsize=12, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    charts['games_by_player'] = Image(img_buffer, width=4.5*inch, height=3*inch)
    plt.close()

    # 3. Platform Distribution - Games Played
    fig, ax = plt.subplots(figsize=(6, 3))
    platforms = sorted(stats['platform_scores'].items(), key=lambda x: x[1]['count'], reverse=True)[:10]
    platform_names = [p[0][:20] for p in platforms]  # Truncate long names
    platform_counts = [p[1]['count'] for p in platforms]

    colors_list = plt.cm.viridis([i/len(platform_names) for i in range(len(platform_names))])
    ax.bar(range(len(platform_names)), platform_counts, color=colors_list, alpha=0.8)
    ax.set_xticks(range(len(platform_names)))
    ax.set_xticklabels(platform_names, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Number of Games', fontsize=10)
    ax.set_title('Top 10 Platforms by Games Played', fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    charts['platform_games'] = Image(img_buffer, width=4*inch, height=2*inch)
    plt.close()

    # 4. Platform Distribution - Unique Players
    fig, ax = plt.subplots(figsize=(6, 3))
    # Count unique players per platform
    platform_players = defaultdict(set)
    for game in games:
        platform_players[game['platform']].add(game['user_code'])

    platforms = sorted(platform_players.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    platform_names = [p[0][:20] for p in platforms]
    player_counts = [len(p[1]) for p in platforms]

    colors_list = plt.cm.plasma([i/len(platform_names) for i in range(len(platform_names))])
    ax.bar(range(len(platform_names)), player_counts, color=colors_list, alpha=0.8)
    ax.set_xticks(range(len(platform_names)))
    ax.set_xticklabels(platform_names, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Unique Players', fontsize=10)
    ax.set_title('Top 10 Platforms by Unique Players', fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    charts['platform_players'] = Image(img_buffer, width=4*inch, height=2*inch)
    plt.close()

    # 5. Daily Activity Chart (if we have daily data) - Bar charts
    if stats.get('daily_stats') and len(stats['daily_stats']) > 0:
        from datetime import timedelta

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4), sharex=True)

        # Get last 30 days worth of data, filling in missing days with zeros
        if len(stats['daily_stats']) > 0:
            # Get the most recent date
            last_date = datetime.strptime(stats['daily_stats'][-1]['date'], "%Y-%m-%d")

            # Create dict for easy lookup
            daily_dict = {d['date']: d for d in stats['daily_stats']}

            # Generate last 30 days
            daily_data = []
            for i in range(29, -1, -1):  # 30 days, counting backwards
                date = last_date - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                if date_str in daily_dict:
                    daily_data.append(daily_dict[date_str])
                else:
                    daily_data.append({
                        "date": date_str,
                        "games": 0,
                        "unique_players": 0
                    })

        dates = [d['date'] for d in daily_data]
        games_per_day = [d['games'] for d in daily_data]
        players_per_day = [d['unique_players'] for d in daily_data]

        # Games per day - Bar chart
        ax1.bar(range(len(dates)), games_per_day, color='#667eea', alpha=0.8, edgecolor='white', linewidth=0.5)
        ax1.set_ylabel('Games Played', fontsize=10)
        ax1.set_title('Daily Activity (Last 30 Days)', fontsize=12, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)

        # Unique players per day - Bar chart
        ax2.bar(range(len(dates)), players_per_day, color='#764ba2', alpha=0.8, edgecolor='white', linewidth=0.5)
        ax2.set_ylabel('Unique Players', fontsize=10)
        ax2.set_xlabel('Date', fontsize=10)
        ax2.grid(axis='y', alpha=0.3)

        # Set x-axis labels
        ax2.set_xticks(range(len(dates)))
        ax2.set_xticklabels(dates, rotation=45, ha='right', fontsize=7)
        # Show every 5th date to avoid crowding
        for i, label in enumerate(ax2.xaxis.get_ticklabels()):
            if i % 5 != 0:
                label.set_visible(False)

        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
        img_buffer.seek(0)
        charts['daily_activity'] = Image(img_buffer, width=5.5*inch, height=3*inch)
        plt.close()

    return charts

def create_pdf_report(stats, output_file, games=None):
    """Create a multi-page PDF report with charts from stats"""

    # Generate charts if games data is provided
    charts = None
    if games:
        charts = create_charts(stats, games)

    # Create PDF
    doc = SimpleDocTemplate(
        output_file,
        pagesize=letter,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch
    )

    # Container for the 'Flowable' objects
    elements = []

    # Create custom style with Times New Roman, 12pt
    styles = getSampleStyleSheet()

    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName='Roboto',
        fontSize=16,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=1  # Center
    )

    # Normal text style
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Roboto',
        fontSize=10,
        leading=12
    )

    # Heading style
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName='Roboto-Bold',
        fontSize=11,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=4,
        spaceBefore=6
    )

    # Title
    title = Paragraph("<b>MOBEE GAME STATISTICS REPORT</b>", title_style)
    elements.append(title)

    # Date
    date_text = Paragraph(f"<i>Generated: {datetime.now().strftime('%B %d, %Y')}</i>", normal_style)
    elements.append(date_text)
    elements.append(Spacer(1, 0.15*inch))

    # Overall Stats Section
    elements.append(Paragraph("<b>OVERALL STATISTICS</b>", heading_style))

    overall_data = [
        ['Total Games Played:', str(stats['total_games']), 'Unique Players:', str(stats['unique_players'])],
        ['Average Score:', f"{stats['avg_score']:.2f}", 'Median Score:', f"{stats['median_score']:.2f}"],
        ['Highest Score:', str(stats['max_score']), 'Lowest Score:', str(stats['min_score'])],
        ['High Score Games:', str(stats['high_score_games']), '', '']
    ]

    overall_table = Table(overall_data, colWidths=[1.7*inch, 0.8*inch, 1.5*inch, 0.8*inch])
    overall_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#34495e')),
        ('FONTNAME', (1, 0), (1, -1), 'Roboto-Bold'),
        ('FONTNAME', (3, 0), (3, -1), 'Roboto-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(overall_table)
    elements.append(Spacer(1, 0.1*inch))

    # Score Distribution
    elements.append(Paragraph("<b>SCORE DISTRIBUTION</b>", heading_style))
    dist_data = [['Range', 'Games', 'Percentage']]
    for range_label, count in stats['score_distribution'].items():
        percentage = (count / stats['total_games']) * 100
        dist_data.append([range_label, str(count), f"{percentage:.1f}%"])

    dist_table = Table(dist_data, colWidths=[1.2*inch, 1.2*inch, 1.2*inch])
    dist_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(dist_table)
    elements.append(Spacer(1, 0.15*inch))

    # Add charts if available
    if charts:
        # Score Distribution Chart
        elements.append(charts['score_dist'])
        elements.append(Spacer(1, 0.15*inch))

    # High Score Leaderboard (TOP 15)
    elements.append(Paragraph("<b>HIGH SCORE LEADERBOARD (TOP 15)</b>", heading_style))
    leaderboard_data = [['Rank', 'Player', 'Score', 'Platform', 'Location']]
    for i in range(15):
        if i < len(stats['top_players_by_score']):
            player, score = stats['top_players_by_score'][i]
            info = stats.get('player_high_score_info', {}).get(player, {})
            location = info.get('location', 'Unknown')[:25]
            platform = info.get('platform', 'Unknown')[:15]
            leaderboard_data.append([
                str(i+1),
                player,
                str(score),
                platform,
                location
            ])

    leaderboard_table = Table(leaderboard_data, colWidths=[0.4*inch, 0.8*inch, 0.5*inch, 1.2*inch, 1.4*inch])
    leaderboard_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        # Highlight top 3
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFD700')),  # Gold
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#C0C0C0')),  # Silver
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#CD7F32')),  # Bronze
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(leaderboard_table)
    elements.append(Spacer(1, 0.15*inch))

    if charts:
        # Daily Statistics Table and Daily Activity Chart (table first, then chart)
        if stats.get('daily_stats') and len(stats['daily_stats']) > 0:
            elements.append(Paragraph("<b>DAILY STATISTICS (LAST 30 DAYS)</b>", heading_style))
            daily_table_data = [['Date', 'Games', 'Unique Players']]
            recent_days = stats['daily_stats'][-30:]  # Last 30 days

            for day in recent_days:
                date_obj = datetime.strptime(day['date'], "%Y-%m-%d")
                formatted_date = date_obj.strftime("%A, %B %d, %Y")
                daily_table_data.append([
                    formatted_date,
                    str(day['games']),
                    str(day['unique_players'])
                ])

            daily_table = Table(daily_table_data, colWidths=[2.5*inch, 0.8*inch, 1.0*inch])
            daily_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            elements.append(daily_table)
            elements.append(Spacer(1, 0.15*inch))

            # Daily Activity Chart immediately after table
            if 'daily_activity' in charts:
                elements.append(charts['daily_activity'])
                elements.append(Spacer(1, 0.15*inch))

    # Top 15 Players by Games Played Table (table first, then chart)
    elements.append(Paragraph("<b>TOP 15 PLAYERS BY GAMES PLAYED</b>", heading_style))

    # Build location string with city/country/platform for each player
    player_location_info = {}
    for game in games:
        player = game["user_code"]
        if player not in player_location_info:
            player_location_info[player] = defaultdict(lambda: {"count": 0, "platform": None})

        key = f"{game['city']}, {game['country']}"
        player_location_info[player][key]["count"] += 1
        if not player_location_info[player][key]["platform"]:
            player_location_info[player][key]["platform"] = game["platform"]

    player_games_data = [['Rank', 'Games', 'Name', 'City/Country/Platform']]
    for i in range(15):
        if i < len(stats['top_players_by_games']):
            player, scores = stats['top_players_by_games'][i]

            # Get most common location for this player
            if player in player_location_info:
                most_common_loc = max(player_location_info[player].items(), key=lambda x: x[1]["count"])
                location = most_common_loc[0]  # "City, Country"
                platform = most_common_loc[1]["platform"]
                location_str = f"{location} / {platform}"[:35]
            else:
                location_str = "Unknown"

            player_games_data.append([
                str(i+1),
                str(len(scores)),
                player,
                location_str
            ])

    games_table = Table(player_games_data, colWidths=[0.4*inch, 0.6*inch, 0.9*inch, 2.4*inch])
    games_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(games_table)
    elements.append(Spacer(1, 0.15*inch))

    # Games by Player Chart immediately after table
    if charts:
        elements.append(charts['games_by_player'])
        elements.append(Spacer(1, 0.15*inch))

    # Platform Stats Table (table first, then charts)
    elements.append(Paragraph("<b>TOP PLATFORMS</b>", heading_style))
    platform_data = [['Platform', 'Games', 'Avg Score', 'Max']]
    sorted_platforms = sorted(stats['platform_scores'].items(), key=lambda x: x[1]['count'], reverse=True)
    for platform, data in sorted_platforms[:10]:
        platform_data.append([
            platform,
            str(data['count']),
            f"{data['avg']:.1f}",
            str(data['max'])
        ])

    platform_table = Table(platform_data, colWidths=[2.0*inch, 0.8*inch, 0.9*inch, 0.6*inch])
    platform_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(platform_table)
    elements.append(Spacer(1, 0.15*inch))

    # Platform Charts immediately after table
    if charts:
        elements.append(charts['platform_games'])
        elements.append(Spacer(1, 0.1*inch))
        elements.append(charts['platform_players'])
        elements.append(Spacer(1, 0.15*inch))

    # Player Engagement - Separate table
    elements.append(Paragraph("<b>PLAYER ENGAGEMENT</b>", heading_style))
    eng = stats['engagement']
    engagement_data = [['Category', 'Count', 'Percentage']]
    engagement_data.append(['One-time Players', str(eng['one_time_players']), f"{(eng['one_time_players']/stats['unique_players']*100):.1f}%"])
    engagement_data.append(['Returning Players', str(eng['returning_players']), f"{(eng['returning_players']/stats['unique_players']*100):.1f}%"])
    engagement_data.append(['Super Engaged (10+)', str(eng['super_engaged']), f"{(eng['super_engaged']/stats['unique_players']*100):.1f}%"])

    engagement_table = Table(engagement_data, colWidths=[2.0*inch, 1.0*inch, 1.3*inch])
    engagement_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(engagement_table)
    elements.append(Spacer(1, 0.15*inch))

    # Top Countries by Games and Average Score - Separate table
    elements.append(Paragraph("<b>TOP COUNTRIES</b>", heading_style))
    countries_data = [['Country', 'Games', 'Avg Score']]
    sorted_countries = sorted(stats['location_scores'].items(), key=lambda x: x[1]['count'], reverse=True)
    for country, data in sorted_countries[:10]:
        if data['count'] >= 5:  # Only show countries with 5+ games
            countries_data.append([
                country,
                str(data['count']),
                f"{data['avg']:.2f}"
            ])

    countries_table = Table(countries_data, colWidths=[2.0*inch, 1.0*inch, 1.3*inch])
    countries_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(countries_table)
    elements.append(Spacer(1, 0.15*inch))

    # Top Cities
    elements.append(Paragraph("<b>TOP CITIES BY GAMES PLAYED</b>", heading_style))
    city_data = [['City', 'Games', 'City', 'Games']]
    sorted_cities = sorted(stats['city_counts'].items(), key=lambda x: x[1], reverse=True)
    for i in range(0, min(10, len(sorted_cities)), 2):
        city1 = sorted_cities[i] if i < len(sorted_cities) else ('', 0)
        city2 = sorted_cities[i+1] if i+1 < len(sorted_cities) else ('', 0)
        city_data.append([
            city1[0],
            str(city1[1]),
            city2[0],
            str(city2[1])
        ])

    city_table = Table(city_data, colWidths=[1.8*inch, 0.5*inch, 1.8*inch, 0.5*inch])
    city_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Roboto'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Roboto-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(city_table)

    # Build PDF
    doc.build(elements)
    print(f"\n✅ PDF report generated: {output_file}")

def main():
    print("Fetching messages from Slack...")
    messages = fetch_slack_messages(CHANNEL_ID, SLACK_TOKEN)
    print(f"Retrieved {len(messages)} messages")

    print("\nParsing game notifications...")
    games = []
    for msg in messages:
        text = msg.get("text", "")
        if "Score:" in text or "HIGH SCORE:" in text:
            timestamp = float(msg.get("ts", 0))
            parsed = parse_game_notification(text, timestamp)
            if parsed and parsed["score"] <= 30:  # Ignore scores over 30
                games.append(parsed)
    
    print(f"Found {len(games)} game notifications")
    
    if not games:
        print("No game data found!")
        return
    
    print("\nAnalyzing game data...")
    stats = analyze_games(games)
    
    # Print statistics
    print_stats(stats)
    
    # Save raw data to JSON
    with open("mobee_games_raw.json", "w") as f:
        json.dump(games, f, indent=2)
    print("\n✅ Raw game data saved to mobee_games_raw.json")

    # Save stats to JSON
    with open("mobee_stats.json", "w") as f:
        # Convert tuples to lists for JSON serialization
        stats_copy = stats.copy()
        stats_copy['top_players_by_games'] = [[p, scores] for p, scores in stats['top_players_by_games']]
        stats_copy['top_players_by_score'] = [[p, score] for p, score in stats['top_players_by_score']]
        json.dump(stats_copy, f, indent=2)
    print("✅ Statistics saved to mobee_stats.json")

    # Generate PDF report with charts
    create_pdf_report(stats, "mobee_stats_report.pdf", games)

if __name__ == "__main__":
    main()
