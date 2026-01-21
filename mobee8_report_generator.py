#!/usr/bin/env python3
"""
Mobee-8 PDF Report Generator

Reads game data from Upstash Redis and generates a PDF report with:
- Level 1 (7 symbols) and Level 2 (12 symbols) sections
- Score distribution histogram charts
- Daily activity charts with dual Y-axis
- Top players leaderboards with avatars
- Player engagement statistics

Environment variables:
  UPSTASH_REDIS_REST_URL   - Upstash Redis REST URL
  UPSTASH_REDIS_REST_TOKEN - Upstash Redis REST token

Output:
  mobee8_stats_report_YYYY-MM-DD_HH00UTC.pdf
  mobee8_stats.json (data snapshot)
"""

import os
import sys
import json
import io
from datetime import datetime, timezone
from collections import defaultdict
import requests
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib import colors
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Configuration
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL', '')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')
AVATAR_BASE_URL = 'https://mobee-8.trippplecard.games/assets/avatars_320/'
MAX_EVENTS = 10000

# Colors matching the old report style
CHART_COLOR_PRIMARY = '#6c7b95'  # Blue-gray for bars
CHART_COLOR_SECONDARY = '#b8a9c9'  # Light purple for secondary bars
HEADER_COLOR = '#d4a574'  # Orange/tan for section headers

def upstash_command(args):
    """Execute a Redis command via Upstash REST API"""
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        raise ValueError("Missing UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN")

    response = requests.post(
        UPSTASH_URL,
        headers={
            'Authorization': f'Bearer {UPSTASH_TOKEN}',
            'Content-Type': 'application/json'
        },
        json=args
    )

    if not response.ok:
        raise Exception(f"Upstash error: {response.status_code} {response.text}")

    return response.json().get('result')

def avatar_coords_to_url(coords):
    """
    Convert avatar coords "col,row" (0-indexed) to PNG URL.
    Example: "11,5" -> "6-12.png" (row+1, col+1)
    """
    if not coords:
        return None
    try:
        parts = coords.split(',')
        col = int(parts[0])
        row = int(parts[1])
        filename = f"{row + 1}-{col + 1}.png"
        return f"{AVATAR_BASE_URL}{filename}"
    except:
        return None

def download_avatar(url, size=(24, 24)):
    """Download and resize avatar image. Returns RLImage or None."""
    if not url:
        return None
    try:
        response = requests.get(url, timeout=5)
        if response.ok:
            img = Image.open(io.BytesIO(response.content))
            img = img.resize(size, Image.LANCZOS)
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            return RLImage(img_buffer, width=size[0], height=size[1])
    except Exception as e:
        print(f"Avatar download failed for {url}: {e}")
    return None

def get_score_bucket_7(score):
    """Categorize score into distribution bucket for Level 1 (7 symbols)"""
    if score <= 5:
        return '0-5'
    if score <= 10:
        return '6-10'
    if score <= 15:
        return '11-15'
    if score <= 20:
        return '16-20'
    return '20+'

def get_score_bucket_12(score):
    """Categorize score into distribution bucket for Level 2 (12 symbols) - smaller ranges"""
    if score <= 2:
        return '0-2'
    if score <= 5:
        return '3-5'
    if score <= 8:
        return '6-8'
    if score <= 11:
        return '9-11'
    return '12+'

SCORE_BUCKETS_7 = ['0-5', '6-10', '11-15', '16-20', '20+']
SCORE_BUCKETS_12 = ['0-2', '3-5', '6-8', '9-11', '12+']

def format_date(timestamp):
    """Convert timestamp to YYYY-MM-DD"""
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

def format_date_display(date_str):
    """Convert YYYY-MM-DD to readable format like 'Tuesday, January 21, 2026'"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return dt.strftime('%A, %B %d, %Y')

def fetch_variant_data(variant_key):
    """
    Fetch and aggregate data for a single variant (7 or 12).
    Returns dict with stats, top_by_score, top_by_games.
    """
    print(f"Fetching data for variant {variant_key}...")

    # Fetch events
    events_raw = upstash_command(['LRANGE', f'mobee8:events:{variant_key}', 0, MAX_EVENTS - 1])
    events = []
    if events_raw:
        for e in events_raw:
            try:
                events.append(json.loads(e))
            except:
                pass

    print(f"  Events loaded: {len(events)}")

    # Aggregate stats from events
    unique_players = set()
    # Use different buckets for Level 1 vs Level 2
    if variant_key == '7':
        score_distribution = {b: 0 for b in SCORE_BUCKETS_7}
        get_bucket = get_score_bucket_7
    else:
        score_distribution = {b: 0 for b in SCORE_BUCKETS_12}
        get_bucket = get_score_bucket_12
    score_histogram = defaultdict(int)  # Individual scores for histogram
    daily_map = {}  # date -> {games, players set}
    player_stats = {}  # playerId -> {games, totalScore, scores[], lastAvatar, lastSeen, highScore}
    country_stats = defaultdict(int)  # country -> games count
    city_stats = defaultdict(int)  # city -> games count
    total_games = 0
    total_score = 0
    max_score = 0
    all_scores = []

    for event in events:
        date_key = format_date(event.get('endedAt') or event.get('startedAt', 0))

        if date_key not in daily_map:
            daily_map[date_key] = {'games': 0, 'players': set()}

        scores = event.get('scores', {})
        avatars = event.get('avatars', {})
        locations = event.get('locations', {})  # {playerId: {country, city}}
        ended_at = event.get('endedAt') or event.get('startedAt', 0)

        for player_id, score in scores.items():
            total_games += 1
            total_score += score
            max_score = max(max_score, score)
            all_scores.append(score)
            score_histogram[score] += 1

            unique_players.add(player_id)
            score_distribution[get_bucket(score)] += 1

            daily_map[date_key]['games'] += 1
            daily_map[date_key]['players'].add(player_id)

            if player_id not in player_stats:
                player_stats[player_id] = {
                    'games': 0,
                    'totalScore': 0,
                    'scores': [],
                    'lastAvatar': None,
                    'lastSeen': 0,
                    'highScore': 0
                }

            player_stats[player_id]['games'] += 1
            player_stats[player_id]['totalScore'] += score
            player_stats[player_id]['scores'].append(score)
            player_stats[player_id]['highScore'] = max(player_stats[player_id]['highScore'], score)

            avatar = avatars.get(player_id)
            if ended_at > player_stats[player_id]['lastSeen']:
                player_stats[player_id]['lastSeen'] = ended_at
                if avatar:
                    player_stats[player_id]['lastAvatar'] = avatar

            # Track location stats
            loc = locations.get(player_id, {})
            country = loc.get('country')
            city = loc.get('city')
            if country and country != "Unknown":
                country_stats[country] += 1
            if city and city != "Unknown":
                city_stats[city] += 1

    # Build daily stats (last 30 days)
    daily_stats = []
    for date, data in sorted(daily_map.items()):
        daily_stats.append({
            'date': date,
            'games': data['games'],
            'unique_players': len(data['players'])
        })
    daily_stats = daily_stats[-30:]

    # Fetch top scores from ZSET
    top_by_score = []
    zset_result = upstash_command(['ZREVRANGE', f'mobee8:highscores:{variant_key}', 0, 19, 'WITHSCORES'])
    if zset_result:
        for i in range(0, len(zset_result), 2):
            player_id = zset_result[i]
            score = int(float(zset_result[i + 1]))

            # Fetch player metadata
            avatar_coords = None
            name = None
            country = None
            city = None
            try:
                meta = upstash_command(['HGETALL', f'mobee8:player:{player_id}'])
                if meta:
                    meta_dict = {}
                    for j in range(0, len(meta), 2):
                        meta_dict[meta[j]] = meta[j + 1]
                    avatar_coords = meta_dict.get('avatar')
                    name = meta_dict.get('name')
                    country = meta_dict.get('country')
                    city = meta_dict.get('city')
            except:
                pass

            top_by_score.append({
                'playerId': player_id,
                'score': score,
                'avatarCoords': avatar_coords or player_stats.get(player_id, {}).get('lastAvatar'),
                'name': name,
                'country': country,
                'city': city
            })

    # Top by games played (from event aggregation)
    top_by_games = []
    sorted_by_games = sorted(player_stats.items(), key=lambda x: x[1]['games'], reverse=True)[:15]
    for player_id, stats in sorted_by_games:
        avg_score = round(stats['totalScore'] / stats['games'], 1) if stats['games'] > 0 else 0
        top_by_games.append({
            'playerId': player_id,
            'games': stats['games'],
            'avgScore': avg_score,
            'avatarCoords': stats['lastAvatar']
        })

    # Calculate engagement stats
    one_time_players = sum(1 for p in player_stats.values() if p['games'] == 1)
    returning_players = sum(1 for p in player_stats.values() if p['games'] > 1)
    super_engaged = sum(1 for p in player_stats.values() if p['games'] >= 10)

    # Calculate median score
    median_score = 0
    if all_scores:
        sorted_scores = sorted(all_scores)
        n = len(sorted_scores)
        median_score = sorted_scores[n // 2] if n % 2 == 1 else (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2

    # Top countries and cities
    top_countries = sorted(country_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    top_cities = sorted(city_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        'variant': variant_key,
        'total_games': total_games,
        'unique_players': len(unique_players),
        'avg_score': round(total_score / total_games, 2) if total_games > 0 else 0,
        'median_score': round(median_score, 2),
        'max_score': max_score,
        'min_score': min(all_scores) if all_scores else 0,
        'score_distribution': score_distribution,
        'score_histogram': dict(score_histogram),
        'daily_stats': daily_stats,
        'top_players_by_score': top_by_score,
        'top_players_by_games': top_by_games,
        'engagement': {
            'one_time': one_time_players,
            'returning': returning_players,
            'super_engaged': super_engaged
        },
        'top_countries': top_countries,
        'top_cities': top_cities
    }

def create_score_histogram(score_histogram, max_score, title, output_path, x_max=30):
    """Create a score distribution histogram chart with integer Y-axis"""
    if not score_histogram:
        return None

    scores = list(range(0, max(max_score + 1, x_max + 1)))
    counts = [score_histogram.get(s, 0) for s in scores]

    fig, ax = plt.subplots(figsize=(6, 2.5))
    ax.bar(scores, counts, color=CHART_COLOR_PRIMARY, alpha=0.85, width=0.8)
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xlabel('Score', fontsize=9)
    ax.set_ylabel('Number of Games', fontsize=9)
    ax.set_xlim(-0.5, x_max + 0.5)
    ax.tick_params(axis='both', labelsize=8)

    # Integer Y-axis ticks only
    max_count = max(counts) if counts else 1
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.set_ylim(0, max_count * 1.1 if max_count > 0 else 1)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    return output_path

def create_daily_activity_chart(daily_stats, title, output_path):
    """Create a daily activity chart with dual Y-axis (games and unique players)"""
    if not daily_stats or len(daily_stats) < 2:
        return None

    dates = [d['date'][-5:] for d in daily_stats]  # MM-DD format
    games = [d['games'] for d in daily_stats]
    players = [d['unique_players'] for d in daily_stats]

    fig, ax1 = plt.subplots(figsize=(6, 2.5))

    # Games bars
    x = np.arange(len(dates))
    width = 0.8
    ax1.bar(x, games, width, color=CHART_COLOR_PRIMARY, alpha=0.85, label='Games Played')
    ax1.set_ylabel('Games Played', fontsize=9)
    ax1.tick_params(axis='y', labelsize=8)
    ax1.set_ylim(0, max(games) * 1.1 if games else 10)

    # Unique players line on secondary axis
    ax2 = ax1.twinx()
    ax2.bar(x, players, width * 0.4, color=CHART_COLOR_SECONDARY, alpha=0.7, label='Unique Players')
    ax2.set_ylabel('Unique Players', fontsize=9)
    ax2.tick_params(axis='y', labelsize=8)
    ax2.set_ylim(0, max(players) * 1.3 if players else 10)

    # X-axis
    step = max(1, len(dates) // 8)
    ax1.set_xticks(x[::step])
    ax1.set_xticklabels([dates[i] for i in range(0, len(dates), step)], rotation=45, fontsize=7)
    ax1.set_xlabel('Date', fontsize=9)

    ax1.set_title(title, fontsize=11, fontweight='bold')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    return output_path

def create_top_players_chart(top_players, title, output_path, value_key='games'):
    """Create horizontal bar chart for top players"""
    if not top_players:
        return None

    players = [p['playerId'][:8] for p in top_players[:10]]
    values = [p.get(value_key, 0) for p in top_players[:10]]

    # Reverse for display (highest at top)
    players = players[::-1]
    values = values[::-1]

    fig, ax = plt.subplots(figsize=(5, 2.5))
    y_pos = np.arange(len(players))

    ax.barh(y_pos, values, color=CHART_COLOR_SECONDARY, alpha=0.85)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(players, fontsize=8)
    ax.set_xlabel('Number of Games' if value_key == 'games' else 'Score', fontsize=9)
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.tick_params(axis='x', labelsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    return output_path

def create_pdf_report(data_7, data_12, output_file):
    """Generate PDF report with both variants - styled like the old report"""

    doc = SimpleDocTemplate(
        output_file,
        pagesize=letter,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
        leftMargin=0.6*inch,
        rightMargin=0.6*inch
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom styles matching old report
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=1
    )

    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=12
    )

    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=13,
        textColor=colors.HexColor('#c4956a'),  # Orange/tan like old report
        spaceAfter=8,
        spaceBefore=16
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=6,
        spaceBefore=10
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=12
    )

    # Title
    now = datetime.now(timezone.utc)
    elements.append(Paragraph("<b>MOBEE-8 GAME STATISTICS REPORT</b>", title_style))
    elements.append(Paragraph(f"Generated: {now.strftime('%B %d, %Y')}", date_style))
    elements.append(Spacer(1, 0.15*inch))

    # ========== OVERALL STATISTICS ==========
    total_games = data_7['total_games'] + data_12['total_games']
    total_players = data_7['unique_players'] + data_12['unique_players']
    combined_avg = 0
    combined_median = 0
    combined_max = max(data_7['max_score'], data_12['max_score'])
    combined_min = min(data_7.get('min_score', 0), data_12.get('min_score', 0))

    if total_games > 0:
        combined_avg = round((data_7['avg_score'] * data_7['total_games'] + data_12['avg_score'] * data_12['total_games']) / total_games, 2)
        combined_median = round((data_7['median_score'] + data_12['median_score']) / 2, 2)

    elements.append(Paragraph("<b>OVERALL STATISTICS</b>", section_style))

    # Stats grid like old report
    overall_data = [
        ['Total Games Played:', f"<b>{total_games}</b>", 'Unique Players:', f"<b>{total_players}</b>"],
        ['Average Score:', f"<b>{combined_avg}</b>", 'Median Score:', f"<b>{combined_median}</b>"],
        ['Highest Score:', f"<b>{combined_max}</b>", 'Lowest Score:', f"<b>{combined_min}</b>"],
        ['Level 1 Games:', f"<b>{data_7['total_games']}</b>", 'Level 2 Games:', f"<b>{data_12['total_games']}</b>"],
    ]

    # Convert to Paragraphs for bold support
    overall_table_data = []
    for row in overall_data:
        overall_table_data.append([
            Paragraph(row[0], normal_style),
            Paragraph(row[1], normal_style),
            Paragraph(row[2], normal_style),
            Paragraph(row[3], normal_style)
        ])

    overall_table = Table(overall_table_data, colWidths=[1.6*inch, 0.9*inch, 1.6*inch, 0.9*inch])
    overall_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(overall_table)
    elements.append(Spacer(1, 0.2*inch))

    # ========== LEVEL 1 SECTION ==========
    elements.append(Paragraph("<b>LEVEL 1 (7 SYMBOLS)</b>", section_style))
    elements.append(Spacer(1, 0.1*inch))

    # Level 1 stats summary
    l1_stats_data = [
        ['Games:', f"<b>{data_7['total_games']}</b>", 'Players:', f"<b>{data_7['unique_players']}</b>",
         'Avg Score:', f"<b>{data_7['avg_score']}</b>", 'Max:', f"<b>{data_7['max_score']}</b>"]
    ]
    l1_stats_table_data = [[Paragraph(cell, normal_style) for cell in l1_stats_data[0]]]
    l1_stats_table = Table(l1_stats_table_data, colWidths=[0.7*inch, 0.5*inch, 0.7*inch, 0.5*inch, 0.8*inch, 0.5*inch, 0.5*inch, 0.5*inch])
    l1_stats_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(l1_stats_table)
    elements.append(Spacer(1, 0.1*inch))

    # Level 1 Score Distribution
    elements.append(Paragraph("<b>Score Distribution</b>", heading_style))
    dist_data_7 = [['Range', 'Games', 'Percentage']]
    for range_label in SCORE_BUCKETS_7:
        count = data_7['score_distribution'].get(range_label, 0)
        pct = (count / data_7['total_games'] * 100) if data_7['total_games'] > 0 else 0
        dist_data_7.append([range_label, str(count), f"{pct:.1f}%"])

    dist_table_7 = Table(dist_data_7, colWidths=[1*inch, 1*inch, 1*inch])
    dist_table_7.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(dist_table_7)
    elements.append(Spacer(1, 0.1*inch))

    # Level 1 histogram (x_max=30 for 7-symbol games)
    hist_chart_7 = create_score_histogram(
        data_7.get('score_histogram', {}),
        data_7['max_score'],
        'Level 1 Score Distribution',
        '/tmp/score_histogram_7.png',
        x_max=30
    )
    if hist_chart_7:
        elements.append(RLImage(hist_chart_7, width=5*inch, height=2*inch))
    elements.append(Spacer(1, 0.1*inch))

    # Level 1 High Score Leaderboard
    elements.append(Paragraph("<b>High Score Leaderboard (Top 10)</b>", heading_style))
    score_data_7 = [['Rank', '', 'Player', 'Score']]
    for i, player in enumerate(data_7['top_players_by_score'][:10]):
        avatar_url = avatar_coords_to_url(player.get('avatarCoords'))
        avatar_img = download_avatar(avatar_url) or ''
        name = player.get('name') or player['playerId'][:8]
        score_data_7.append([str(i + 1), avatar_img, name, str(player['score'])])

    score_table_7 = Table(score_data_7, colWidths=[0.5*inch, 0.4*inch, 2*inch, 0.7*inch])
    score_table_7.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(score_table_7)
    elements.append(Spacer(1, 0.1*inch))

    # Level 1 Top Players by Games
    elements.append(Paragraph("<b>Top Players by Games Played</b>", heading_style))
    games_data_7 = [['Rank', '', 'Player', 'Games', 'Avg']]
    for i, player in enumerate(data_7['top_players_by_games'][:10]):
        avatar_url = avatar_coords_to_url(player.get('avatarCoords'))
        avatar_img = download_avatar(avatar_url) or ''
        games_data_7.append([str(i + 1), avatar_img, player['playerId'][:8], str(player['games']), str(player['avgScore'])])

    games_table_7 = Table(games_data_7, colWidths=[0.5*inch, 0.4*inch, 1.5*inch, 0.7*inch, 0.7*inch])
    games_table_7.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(games_table_7)

    # ========== LEVEL 2 SECTION ==========
    elements.append(PageBreak())
    elements.append(Paragraph("<b>LEVEL 2 (12 SYMBOLS)</b>", section_style))
    elements.append(Spacer(1, 0.1*inch))

    # Level 2 stats summary
    l2_stats_data = [
        ['Games:', f"<b>{data_12['total_games']}</b>", 'Players:', f"<b>{data_12['unique_players']}</b>",
         'Avg Score:', f"<b>{data_12['avg_score']}</b>", 'Max:', f"<b>{data_12['max_score']}</b>"]
    ]
    l2_stats_table_data = [[Paragraph(cell, normal_style) for cell in l2_stats_data[0]]]
    l2_stats_table = Table(l2_stats_table_data, colWidths=[0.7*inch, 0.5*inch, 0.7*inch, 0.5*inch, 0.8*inch, 0.5*inch, 0.5*inch, 0.5*inch])
    l2_stats_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(l2_stats_table)
    elements.append(Spacer(1, 0.1*inch))

    # Level 2 Score Distribution (smaller buckets for harder level)
    elements.append(Paragraph("<b>Score Distribution</b>", heading_style))
    dist_data_12 = [['Range', 'Games', 'Percentage']]
    for range_label in SCORE_BUCKETS_12:
        count = data_12['score_distribution'].get(range_label, 0)
        pct = (count / data_12['total_games'] * 100) if data_12['total_games'] > 0 else 0
        dist_data_12.append([range_label, str(count), f"{pct:.1f}%"])

    dist_table_12 = Table(dist_data_12, colWidths=[1*inch, 1*inch, 1*inch])
    dist_table_12.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(dist_table_12)
    elements.append(Spacer(1, 0.1*inch))

    # Level 2 histogram (x_max=15 for 12-symbol games - scores are lower)
    hist_chart_12 = create_score_histogram(
        data_12.get('score_histogram', {}),
        data_12['max_score'],
        'Level 2 Score Distribution',
        '/tmp/score_histogram_12.png',
        x_max=15
    )
    if hist_chart_12:
        elements.append(RLImage(hist_chart_12, width=5*inch, height=2*inch))
    elements.append(Spacer(1, 0.1*inch))

    # Level 2 High Score Leaderboard
    elements.append(Paragraph("<b>High Score Leaderboard (Top 10)</b>", heading_style))
    score_data_12 = [['Rank', '', 'Player', 'Score']]
    for i, player in enumerate(data_12['top_players_by_score'][:10]):
        avatar_url = avatar_coords_to_url(player.get('avatarCoords'))
        avatar_img = download_avatar(avatar_url) or ''
        name = player.get('name') or player['playerId'][:8]
        score_data_12.append([str(i + 1), avatar_img, name, str(player['score'])])

    score_table_12 = Table(score_data_12, colWidths=[0.5*inch, 0.4*inch, 2*inch, 0.7*inch])
    score_table_12.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(score_table_12)
    elements.append(Spacer(1, 0.1*inch))

    # Level 2 Top Players by Games
    elements.append(Paragraph("<b>Top Players by Games Played</b>", heading_style))
    games_data_12 = [['Rank', '', 'Player', 'Games', 'Avg']]
    for i, player in enumerate(data_12['top_players_by_games'][:10]):
        avatar_url = avatar_coords_to_url(player.get('avatarCoords'))
        avatar_img = download_avatar(avatar_url) or ''
        games_data_12.append([str(i + 1), avatar_img, player['playerId'][:8], str(player['games']), str(player['avgScore'])])

    games_table_12 = Table(games_data_12, colWidths=[0.5*inch, 0.4*inch, 1.5*inch, 0.7*inch, 0.7*inch])
    games_table_12.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(games_table_12)

    # ========== DAILY STATISTICS ==========
    elements.append(PageBreak())
    elements.append(Paragraph("<b>DAILY STATISTICS (LAST 30 DAYS)</b>", section_style))

    # Combined daily stats
    combined_daily = {}
    for d in data_7.get('daily_stats', []):
        if d['date'] not in combined_daily:
            combined_daily[d['date']] = {'games': 0, 'players': 0}
        combined_daily[d['date']]['games'] += d['games']
        combined_daily[d['date']]['players'] += d['unique_players']
    for d in data_12.get('daily_stats', []):
        if d['date'] not in combined_daily:
            combined_daily[d['date']] = {'games': 0, 'players': 0}
        combined_daily[d['date']]['games'] += d['games']
        combined_daily[d['date']]['players'] += d['unique_players']

    daily_list = [{'date': k, 'games': v['games'], 'unique_players': v['players']}
                  for k, v in sorted(combined_daily.items())][-30:]

    # Daily stats table
    daily_table_data = [['Date', 'Games', 'Unique Players']]
    for d in daily_list:
        daily_table_data.append([
            format_date_display(d['date']),
            str(d['games']),
            str(d['unique_players'])
        ])

    daily_table = Table(daily_table_data, colWidths=[2.8*inch, 1*inch, 1.2*inch])
    daily_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(daily_table)
    elements.append(Spacer(1, 0.2*inch))

    # Daily activity chart
    daily_chart = create_daily_activity_chart(
        daily_list,
        'Daily Activity (Last 30 Days)',
        '/tmp/daily_activity.png'
    )
    if daily_chart:
        elements.append(RLImage(daily_chart, width=5.5*inch, height=2.3*inch))

    # ========== PLAYER ENGAGEMENT ==========
    elements.append(Paragraph("<b>PLAYER ENGAGEMENT</b>", section_style))

    total_unique = data_7['unique_players'] + data_12['unique_players']
    one_time = data_7['engagement']['one_time'] + data_12['engagement']['one_time']
    returning = data_7['engagement']['returning'] + data_12['engagement']['returning']
    super_engaged = data_7['engagement']['super_engaged'] + data_12['engagement']['super_engaged']

    engagement_data = [
        ['Category', 'Count', 'Percentage'],
        ['One-time Players', str(one_time), f"{one_time/total_unique*100:.1f}%" if total_unique > 0 else "0%"],
        ['Returning Players', str(returning), f"{returning/total_unique*100:.1f}%" if total_unique > 0 else "0%"],
        ['Super Engaged (10+)', str(super_engaged), f"{super_engaged/total_unique*100:.1f}%" if total_unique > 0 else "0%"],
    ]

    engagement_table = Table(engagement_data, colWidths=[1.8*inch, 1*inch, 1*inch])
    engagement_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(engagement_table)

    # ========== LEVEL BREAKDOWN ==========
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("<b>LEVEL BREAKDOWN</b>", section_style))

    level_data = [
        ['Level', 'Games', 'Players', 'Avg Score', 'Max Score'],
        ['Level 1 (7 symbols)', str(data_7['total_games']), str(data_7['unique_players']),
         str(data_7['avg_score']), str(data_7['max_score'])],
        ['Level 2 (12 symbols)', str(data_12['total_games']), str(data_12['unique_players']),
         str(data_12['avg_score']), str(data_12['max_score'])],
    ]

    level_table = Table(level_data, colWidths=[1.6*inch, 0.9*inch, 0.9*inch, 1*inch, 1*inch])
    level_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(level_table)

    # Build PDF
    doc.build(elements)
    print(f"PDF report generated: {output_file}")
    return output_file

def main():
    """Main entry point"""
    print("Mobee-8 Report Generator")
    print("=" * 40)

    # Check credentials
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        print("ERROR: Missing UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN")
        sys.exit(1)

    # Fetch data for both variants
    data_7 = fetch_variant_data('7')
    data_12 = fetch_variant_data('12')

    # Save JSON snapshot
    now = datetime.now(timezone.utc)
    json_file = 'mobee8_stats.json'
    with open(json_file, 'w') as f:
        json.dump({
            'generated_at': now.isoformat(),
            'level_1': data_7,
            'level_2': data_12
        }, f, indent=2)
    print(f"JSON snapshot saved: {json_file}")

    # Generate PDF
    pdf_file = f"mobee8_stats_report_{now.strftime('%Y-%m-%d_%H00UTC')}.pdf"
    create_pdf_report(data_7, data_12, pdf_file)

    # Also save as latest.pdf for easy access
    create_pdf_report(data_7, data_12, 'mobee8_stats_report.pdf')

    # Print highlights for Slack message
    print("\n" + "=" * 40)
    print("HIGHLIGHTS FOR SLACK:")
    top_7 = data_7['top_players_by_score'][0] if data_7['top_players_by_score'] else {'playerId': 'N/A', 'score': 0}
    top_12 = data_12['top_players_by_score'][0] if data_12['top_players_by_score'] else {'playerId': 'N/A', 'score': 0}
    print(f"Top Score (Level 1): {top_7['playerId']} - {top_7['score']}")
    print(f"Top Score (Level 2): {top_12['playerId']} - {top_12['score']}")
    print(f"Total Games: {data_7['total_games'] + data_12['total_games']}")

    return pdf_file

if __name__ == '__main__':
    main()
