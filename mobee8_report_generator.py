#!/usr/bin/env python3
"""
Mobee-8 PDF Report Generator

Reads game data from Upstash Redis and generates a PDF report with:
- Level 1 (7 symbols) and Level 2 (12 symbols) sections
- Avatar images embedded in leaderboards
- Score distribution, daily activity charts
- Top players by score and by games played

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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib import colors
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Configuration
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL', '')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')
AVATAR_BASE_URL = 'https://mobee-8.trippplecard.games/assets/avatars_320/'
MAX_EVENTS = 10000

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

def get_score_bucket(score):
    """Categorize score into distribution bucket"""
    if score <= 5:
        return '0-5'
    if score <= 10:
        return '6-10'
    if score <= 15:
        return '11-15'
    if score <= 20:
        return '16-20'
    return '20+'

def format_date(timestamp):
    """Convert timestamp to YYYY-MM-DD"""
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

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
    score_distribution = {'0-5': 0, '6-10': 0, '11-15': 0, '16-20': 0, '20+': 0}
    daily_map = {}  # date -> {games, players set}
    player_stats = {}  # playerId -> {games, totalScore, scores[], lastAvatar, lastSeen}
    total_games = 0
    total_score = 0
    max_score = 0

    for event in events:
        date_key = format_date(event.get('endedAt') or event.get('startedAt', 0))

        if date_key not in daily_map:
            daily_map[date_key] = {'games': 0, 'players': set()}

        scores = event.get('scores', {})
        avatars = event.get('avatars', {})
        ended_at = event.get('endedAt') or event.get('startedAt', 0)

        for player_id, score in scores.items():
            total_games += 1
            total_score += score
            max_score = max(max_score, score)

            unique_players.add(player_id)
            score_distribution[get_score_bucket(score)] += 1

            daily_map[date_key]['games'] += 1
            daily_map[date_key]['players'].add(player_id)

            if player_id not in player_stats:
                player_stats[player_id] = {
                    'games': 0,
                    'totalScore': 0,
                    'scores': [],
                    'lastAvatar': None,
                    'lastSeen': 0
                }

            player_stats[player_id]['games'] += 1
            player_stats[player_id]['totalScore'] += score
            player_stats[player_id]['scores'].append(score)

            avatar = avatars.get(player_id)
            if ended_at > player_stats[player_id]['lastSeen']:
                player_stats[player_id]['lastSeen'] = ended_at
                if avatar:
                    player_stats[player_id]['lastAvatar'] = avatar

    # Build daily stats (last 60 days)
    daily_stats = []
    for date, data in sorted(daily_map.items()):
        daily_stats.append({
            'date': date,
            'games': data['games'],
            'unique_players': len(data['players'])
        })
    daily_stats = daily_stats[-60:]

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
            try:
                meta = upstash_command(['HGETALL', f'mobee8:player:{player_id}'])
                if meta:
                    meta_dict = {}
                    for j in range(0, len(meta), 2):
                        meta_dict[meta[j]] = meta[j + 1]
                    avatar_coords = meta_dict.get('avatar')
                    name = meta_dict.get('name')
            except:
                pass

            top_by_score.append({
                'playerId': player_id,
                'score': score,
                'avatarCoords': avatar_coords,
                'name': name
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

    return {
        'variant': variant_key,
        'total_games': total_games,
        'unique_players': len(unique_players),
        'avg_score': round(total_score / total_games, 1) if total_games > 0 else 0,
        'max_score': max_score,
        'score_distribution': score_distribution,
        'daily_stats': daily_stats,
        'top_players_by_score': top_by_score,
        'top_players_by_games': top_by_games
    }

def create_chart(daily_stats, title, output_path):
    """Create a daily activity chart and save as PNG"""
    if not daily_stats:
        return None

    dates = [d['date'][-5:] for d in daily_stats]  # MM-DD
    games = [d['games'] for d in daily_stats]

    fig, ax = plt.subplots(figsize=(6, 2))
    ax.bar(range(len(dates)), games, color='#3498db', alpha=0.8)
    ax.set_title(title, fontsize=10)
    ax.set_ylabel('Games', fontsize=8)

    # Show only some x-labels to avoid crowding
    step = max(1, len(dates) // 10)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)], rotation=45, fontsize=7)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    return output_path

def create_pdf_report(data_7, data_12, output_file):
    """Generate PDF report with both variants"""

    doc = SimpleDocTemplate(
        output_file,
        pagesize=letter,
        topMargin=0.4*inch,
        bottomMargin=0.4*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName='Times-Roman',
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=1
    )

    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontName='Times-Bold',
        fontSize=14,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=8,
        spaceBefore=12
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName='Times-Bold',
        fontSize=11,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=4,
        spaceBefore=6
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=10,
        leading=12
    )

    # Title
    now = datetime.now(timezone.utc)
    elements.append(Paragraph("<b>MOBEE-8 GAME STATISTICS REPORT</b>", title_style))
    elements.append(Paragraph(f"<i>Generated: {now.strftime('%B %d, %Y %H:%M UTC')}</i>", normal_style))
    elements.append(Spacer(1, 0.2*inch))

    # Combined summary
    total_games = data_7['total_games'] + data_12['total_games']
    total_players = len(set(
        [p['playerId'] for p in data_7.get('top_players_by_games', [])] +
        [p['playerId'] for p in data_12.get('top_players_by_games', [])]
    ))

    elements.append(Paragraph("<b>COMBINED SUMMARY</b>", heading_style))
    summary_data = [
        ['Total Games:', str(total_games), 'Level 1 Games:', str(data_7['total_games'])],
        ['Unique Players:', str(data_7['unique_players'] + data_12['unique_players']), 'Level 2 Games:', str(data_12['total_games'])]
    ]
    summary_table = Table(summary_data, colWidths=[1.5*inch, 1*inch, 1.5*inch, 1*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#34495e')),
        ('FONTNAME', (1, 0), (1, -1), 'Times-Bold'),
        ('FONTNAME', (3, 0), (3, -1), 'Times-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.15*inch))

    # Add variant sections
    for data, level_name, symbol_count in [
        (data_7, 'LEVEL 1', '7 Symbols'),
        (data_12, 'LEVEL 2', '12 Symbols')
    ]:
        elements.append(Paragraph(f"<b>{level_name} ({symbol_count})</b>", section_style))

        # Stats row
        stats_data = [
            ['Games:', str(data['total_games']), 'Players:', str(data['unique_players']),
             'Avg Score:', str(data['avg_score']), 'Max:', str(data['max_score'])]
        ]
        stats_table = Table(stats_data, colWidths=[0.7*inch, 0.6*inch, 0.7*inch, 0.6*inch, 0.8*inch, 0.5*inch, 0.5*inch, 0.5*inch])
        stats_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (2, 0), (2, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (4, 0), (4, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (6, 0), (6, 0), colors.HexColor('#34495e')),
            ('FONTNAME', (1, 0), (1, 0), 'Times-Bold'),
            ('FONTNAME', (3, 0), (3, 0), 'Times-Bold'),
            ('FONTNAME', (5, 0), (5, 0), 'Times-Bold'),
            ('FONTNAME', (7, 0), (7, 0), 'Times-Bold'),
        ]))
        elements.append(stats_table)
        elements.append(Spacer(1, 0.1*inch))

        # Score Distribution
        elements.append(Paragraph("<b>Score Distribution</b>", heading_style))
        dist_data = [['Range', 'Games', '%']]
        for range_label in ['0-5', '6-10', '11-15', '16-20', '20+']:
            count = data['score_distribution'].get(range_label, 0)
            pct = (count / data['total_games'] * 100) if data['total_games'] > 0 else 0
            dist_data.append([range_label, str(count), f"{pct:.1f}%"])

        dist_table = Table(dist_data, colWidths=[0.8*inch, 0.8*inch, 0.6*inch])
        dist_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(dist_table)
        elements.append(Spacer(1, 0.1*inch))

        # Top Players by Score (with avatars)
        elements.append(Paragraph("<b>Top 10 by High Score</b>", heading_style))
        score_data = [['#', '', 'Player', 'Score']]
        for i, player in enumerate(data['top_players_by_score'][:10]):
            avatar_url = avatar_coords_to_url(player.get('avatarCoords'))
            avatar_img = download_avatar(avatar_url) or ''
            name = player.get('name') or player['playerId'][:8]
            score_data.append([
                str(i + 1),
                avatar_img,
                name,
                str(player['score'])
            ])

        score_table = Table(score_data, colWidths=[0.3*inch, 0.4*inch, 1.5*inch, 0.6*inch])
        score_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(score_table)
        elements.append(Spacer(1, 0.1*inch))

        # Top Players by Games (with avatars)
        elements.append(Paragraph("<b>Top 10 by Games Played</b>", heading_style))
        games_data = [['#', '', 'Player', 'Games', 'Avg']]
        for i, player in enumerate(data['top_players_by_games'][:10]):
            avatar_url = avatar_coords_to_url(player.get('avatarCoords'))
            avatar_img = download_avatar(avatar_url) or ''
            games_data.append([
                str(i + 1),
                avatar_img,
                player['playerId'][:8],
                str(player['games']),
                str(player['avgScore'])
            ])

        games_table = Table(games_data, colWidths=[0.3*inch, 0.4*inch, 1.2*inch, 0.5*inch, 0.5*inch])
        games_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(games_table)
        elements.append(Spacer(1, 0.2*inch))

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
    print(f"Top Score (7 symbols): {data_7['top_players_by_score'][0]['playerId'] if data_7['top_players_by_score'] else 'N/A'} - {data_7['top_players_by_score'][0]['score'] if data_7['top_players_by_score'] else 0}")
    print(f"Top Score (12 symbols): {data_12['top_players_by_score'][0]['playerId'] if data_12['top_players_by_score'] else 'N/A'} - {data_12['top_players_by_score'][0]['score'] if data_12['top_players_by_score'] else 0}")
    print(f"Total Games: {data_7['total_games'] + data_12['total_games']}")

    return pdf_file

if __name__ == '__main__':
    main()
