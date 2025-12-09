#!/usr/bin/env python3
"""
Generate PDF report for Mobee Game Statistics
"""

import json
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime

def create_pdf_report(stats_file, output_file):
    """Create a single-page PDF report from stats JSON"""

    # Load statistics
    with open(stats_file, 'r') as f:
        stats = json.load(f)

    # Create PDF
    doc = SimpleDocTemplate(
        output_file,
        pagesize=letter,
        topMargin=0.4*inch,
        bottomMargin=0.4*inch,
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
        fontName='Times-Roman',
        fontSize=16,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=1  # Center
    )

    # Normal text style
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=10,
        leading=12
    )

    # Heading style
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName='Times-Bold',
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
        ['Average Score:', f"{stats['avg_score']:.2f}", 'Highest Score:', str(stats['max_score'])],
        ['High Score Games:', str(stats['high_score_games']), 'Lowest Score:', str(stats['min_score'])]
    ]

    overall_table = Table(overall_data, colWidths=[1.7*inch, 0.8*inch, 1.5*inch, 0.8*inch])
    overall_table.setStyle(TableStyle([
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
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(dist_table)
    elements.append(Spacer(1, 0.1*inch))

    # Two column layout for remaining sections
    # Top Players
    elements.append(Paragraph("<b>TOP PLAYERS</b>", heading_style))

    # Top 5 by games and by score side by side
    player_data = [['By Games Played', 'Games', 'By High Score', 'Score']]
    for i in range(5):
        by_games = stats['top_players_by_games'][i] if i < len(stats['top_players_by_games']) else ['', []]
        by_score = stats['top_players_by_score'][i] if i < len(stats['top_players_by_score']) else ['', 0]

        games_player = by_games[0]
        games_count = len(by_games[1]) if isinstance(by_games[1], list) else 0
        score_player = by_score[0]
        score_value = by_score[1]

        player_data.append([
            games_player,
            str(games_count),
            score_player,
            str(score_value)
        ])

    player_table = Table(player_data, colWidths=[1.5*inch, 0.6*inch, 1.5*inch, 0.6*inch])
    player_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(player_table)
    elements.append(Spacer(1, 0.1*inch))

    # Platform Stats
    elements.append(Paragraph("<b>TOP PLATFORMS</b>", heading_style))
    platform_data = [['Platform', 'Games', 'Avg Score', 'Max']]
    sorted_platforms = sorted(stats['platform_scores'].items(), key=lambda x: x[1]['count'], reverse=True)
    for platform, data in sorted_platforms[:5]:
        platform_data.append([
            platform,
            str(data['count']),
            f"{data['avg']:.1f}",
            str(data['max'])
        ])

    platform_table = Table(platform_data, colWidths=[2.0*inch, 0.8*inch, 1.0*inch, 0.6*inch])
    platform_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(platform_table)
    elements.append(Spacer(1, 0.1*inch))

    # Engagement and Location side by side
    elements.append(Paragraph("<b>ENGAGEMENT & LOCATION INSIGHTS</b>", heading_style))

    eng = stats['engagement']
    location_data = sorted(stats['location_scores'].items(), key=lambda x: x[1]['avg'], reverse=True)

    combined_data = [['Player Engagement', 'Count', 'Top Countries', 'Avg Score']]
    combined_data.append([
        'One-time Players',
        str(eng['one_time_players']),
        location_data[0][0] if location_data else '',
        f"{location_data[0][1]['avg']:.1f}" if location_data else ''
    ])
    combined_data.append([
        'Returning Players',
        str(eng['returning_players']),
        location_data[1][0] if len(location_data) > 1 else '',
        f"{location_data[1][1]['avg']:.1f}" if len(location_data) > 1 else ''
    ])
    combined_data.append([
        'Super Engaged (10+)',
        str(eng['super_engaged']),
        location_data[2][0] if len(location_data) > 2 else '',
        f"{location_data[2][1]['avg']:.1f}" if len(location_data) > 2 else ''
    ])

    combined_table = Table(combined_data, colWidths=[1.8*inch, 0.7*inch, 1.3*inch, 0.8*inch])
    combined_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(combined_table)
    elements.append(Spacer(1, 0.1*inch))

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
        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
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
    print(f"PDF report generated: {output_file}")

if __name__ == "__main__":
    create_pdf_report("mobee_stats.json", "mobee_stats_report.pdf")
