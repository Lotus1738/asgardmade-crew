"""
AsgardMade Pantheon — Weekly P&L Email Report
Sends a dark-themed HTML email every Sunday at 8am via Gmail SMTP.

Requires:
    GMAIL_USER=trendingmoneyai@gmail.com
    GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail app password (NOT main password)
    REPORT_EMAIL=...                          # optional, defaults to GMAIL_USER
"""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
REPORT_TO = os.getenv("REPORT_EMAIL") or GMAIL_USER


# ─── HTML builder ─────────────────────────────────────────────────────────────

def build_weekly_html_report(stats: dict) -> str:
    """
    Build a dark-themed HTML email with the weekly P&L.

    Expected stats keys:
        week_revenue      float
        week_profit       float
        week_sales        int
        new_designs       int
        top_niches        list[dict]   each: {niche, revenue, units}
        top_listings      list[dict]   each: {title, sales, revenue}
        total_listings    int
        pending_approvals int
        ideas_researched  int
        designs_created   int
        listings_published int
        upcoming_events   list[str]    optional
    """
    now = datetime.now()
    week_start = (now - timedelta(days=7)).strftime("%b %d")
    week_end = now.strftime("%b %d, %Y")

    # ── metric cards ──────────────────────────────────────────────────────────
    week_revenue = stats.get("week_revenue", 0.0)
    week_profit = stats.get("week_profit", 0.0)
    week_sales = stats.get("week_sales", 0)
    new_designs = stats.get("new_designs", 0)

    def card(label: str, value: str, sub: str = "") -> str:
        return f"""
        <td style="padding:0 8px;">
          <div style="background:#13101c;border:1px solid #2a2040;border-radius:10px;
                      padding:20px 24px;text-align:center;min-width:120px;">
            <div style="color:#c9a84c;font-size:26px;font-weight:700;letter-spacing:-0.5px;">{value}</div>
            <div style="color:#a89bc4;font-size:12px;margin-top:4px;text-transform:uppercase;
                        letter-spacing:1px;">{label}</div>
            {f'<div style="color:#5a5070;font-size:11px;margin-top:2px;">{sub}</div>' if sub else ''}
          </div>
        </td>"""

    # ── top niches table ──────────────────────────────────────────────────────
    top_niches = stats.get("top_niches", [])
    niche_rows = ""
    for i, n in enumerate(top_niches[:5]):
        bg = "#0f0d18" if i % 2 == 0 else "#13101c"
        niche_rows += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 16px;color:#d4cce8;font-size:13px;">{n.get('niche','—').title()}</td>
          <td style="padding:10px 16px;color:#c9a84c;font-size:13px;text-align:right;">${n.get('revenue',0):.2f}</td>
          <td style="padding:10px 16px;color:#a89bc4;font-size:13px;text-align:right;">{n.get('units',0)} units</td>
        </tr>"""
    if not niche_rows:
        niche_rows = '<tr><td colspan="3" style="padding:14px 16px;color:#5a5070;font-size:13px;text-align:center;">No sales data yet this week</td></tr>'

    # ── top listings ──────────────────────────────────────────────────────────
    top_listings = stats.get("top_listings", [])
    listing_rows = ""
    for i, lst in enumerate(top_listings[:3]):
        bg = "#0f0d18" if i % 2 == 0 else "#13101c"
        listing_rows += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 16px;color:#d4cce8;font-size:13px;">{lst.get('title','—')}</td>
          <td style="padding:10px 16px;color:#c9a84c;font-size:13px;text-align:right;">{lst.get('sales',0)} sales</td>
          <td style="padding:10px 16px;color:#a89bc4;font-size:13px;text-align:right;">${lst.get('revenue',0):.2f}</td>
        </tr>"""
    if not listing_rows:
        listing_rows = '<tr><td colspan="3" style="padding:14px 16px;color:#5a5070;font-size:13px;text-align:center;">No listing data yet</td></tr>'

    # ── agent activity ────────────────────────────────────────────────────────
    ideas_researched = stats.get("ideas_researched", 0)
    designs_created = stats.get("designs_created", 0)
    listings_published = stats.get("listings_published", 0)
    pending_approvals = stats.get("pending_approvals", 0)
    total_listings = stats.get("total_listings", 0)

    activity_rows = f"""
    <tr style="background:#0f0d18;">
      <td style="padding:9px 16px;color:#a89bc4;font-size:13px;">🔍 Ideas Researched</td>
      <td style="padding:9px 16px;color:#d4cce8;font-size:13px;text-align:right;">{ideas_researched}</td>
    </tr>
    <tr style="background:#13101c;">
      <td style="padding:9px 16px;color:#a89bc4;font-size:13px;">🎨 Designs Created</td>
      <td style="padding:9px 16px;color:#d4cce8;font-size:13px;text-align:right;">{designs_created}</td>
    </tr>
    <tr style="background:#0f0d18;">
      <td style="padding:9px 16px;color:#a89bc4;font-size:13px;">🛍️ Listings Published</td>
      <td style="padding:9px 16px;color:#d4cce8;font-size:13px;text-align:right;">{listings_published}</td>
    </tr>
    <tr style="background:#13101c;">
      <td style="padding:9px 16px;color:#a89bc4;font-size:13px;">📋 Pending Approvals</td>
      <td style="padding:9px 16px;color:#d4cce8;font-size:13px;text-align:right;">{pending_approvals}</td>
    </tr>
    <tr style="background:#0f0d18;">
      <td style="padding:9px 16px;color:#a89bc4;font-size:13px;">🏪 Total Live Listings</td>
      <td style="padding:9px 16px;color:#d4cce8;font-size:13px;text-align:right;">{total_listings}</td>
    </tr>"""

    # ── upcoming events ───────────────────────────────────────────────────────
    upcoming_events = stats.get("upcoming_events", [])
    if upcoming_events:
        event_items = "".join(
            f'<li style="margin-bottom:6px;color:#d4cce8;">{e}</li>'
            for e in upcoming_events[:4]
        )
        events_section = f"""
        <div style="margin-top:24px;">
          <h3 style="color:#c9a84c;font-size:14px;font-weight:600;
                     text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;">
            📅 Upcoming Seasonal Opportunities (Next 4 Weeks)
          </h3>
          <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.7;">
            {event_items}
          </ul>
        </div>"""
    else:
        events_section = ""

    # ── assemble full email ───────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>AsgardMade Weekly Report</title>
</head>
<body style="margin:0;padding:0;background:#07050a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#07050a;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0"
               style="max-width:600px;width:100%;background:#0a0810;
                      border:1px solid #1e1830;border-radius:14px;overflow:hidden;">

          <!-- HEADER -->
          <tr>
            <td style="background:linear-gradient(135deg,#13101c 0%,#1a1228 100%);
                       padding:32px 36px;border-bottom:1px solid #2a2040;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <div style="color:#c9a84c;font-size:22px;font-weight:700;letter-spacing:-0.3px;">
                      ⚡ ASGARDMADE
                    </div>
                    <div style="color:#6b5f8a;font-size:12px;margin-top:4px;letter-spacing:2px;
                                text-transform:uppercase;">Pantheon Intelligence</div>
                  </td>
                  <td align="right">
                    <div style="color:#a89bc4;font-size:13px;">Weekly P&amp;L Report</div>
                    <div style="color:#5a5070;font-size:12px;margin-top:3px;">{week_start} – {week_end}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- METRIC CARDS -->
          <tr>
            <td style="padding:28px 36px 0;">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  {card("Revenue", f"${week_revenue:.2f}", "this week")}
                  {card("Profit", f"${week_profit:.2f}", "net")}
                  {card("Sales", str(week_sales), "orders")}
                  {card("New Listings", str(new_designs), "published")}
                </tr>
              </table>
            </td>
          </tr>

          <!-- TOP NICHES -->
          <tr>
            <td style="padding:28px 36px 0;">
              <h3 style="color:#c9a84c;font-size:14px;font-weight:600;
                         text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;">
                🏆 Top Niches by Revenue
              </h3>
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="border-radius:8px;overflow:hidden;border:1px solid #1e1830;">
                <tr style="background:#1a1228;">
                  <th style="padding:10px 16px;color:#6b5f8a;font-size:11px;font-weight:600;
                             text-align:left;text-transform:uppercase;letter-spacing:1px;">Niche</th>
                  <th style="padding:10px 16px;color:#6b5f8a;font-size:11px;font-weight:600;
                             text-align:right;text-transform:uppercase;letter-spacing:1px;">Revenue</th>
                  <th style="padding:10px 16px;color:#6b5f8a;font-size:11px;font-weight:600;
                             text-align:right;text-transform:uppercase;letter-spacing:1px;">Units</th>
                </tr>
                {niche_rows}
              </table>
            </td>
          </tr>

          <!-- TOP LISTINGS -->
          <tr>
            <td style="padding:24px 36px 0;">
              <h3 style="color:#c9a84c;font-size:14px;font-weight:600;
                         text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;">
                🛍️ Top 3 Listings by Sales
              </h3>
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="border-radius:8px;overflow:hidden;border:1px solid #1e1830;">
                <tr style="background:#1a1228;">
                  <th style="padding:10px 16px;color:#6b5f8a;font-size:11px;font-weight:600;
                             text-align:left;text-transform:uppercase;letter-spacing:1px;">Listing</th>
                  <th style="padding:10px 16px;color:#6b5f8a;font-size:11px;font-weight:600;
                             text-align:right;text-transform:uppercase;letter-spacing:1px;">Sales</th>
                  <th style="padding:10px 16px;color:#6b5f8a;font-size:11px;font-weight:600;
                             text-align:right;text-transform:uppercase;letter-spacing:1px;">Revenue</th>
                </tr>
                {listing_rows}
              </table>
            </td>
          </tr>

          <!-- AGENT ACTIVITY -->
          <tr>
            <td style="padding:24px 36px 0;">
              <h3 style="color:#c9a84c;font-size:14px;font-weight:600;
                         text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;">
                🤖 Agent Activity Summary
              </h3>
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="border-radius:8px;overflow:hidden;border:1px solid #1e1830;">
                {activity_rows}
              </table>
            </td>
          </tr>

          <!-- UPCOMING EVENTS -->
          {f'<tr><td style="padding:0 36px;">{events_section}</td></tr>' if events_section else ''}

          <!-- FOOTER -->
          <tr>
            <td style="padding:28px 36px 32px;margin-top:8px;
                       border-top:1px solid #1e1830;margin-top:28px;">
              <p style="color:#3d3558;font-size:11px;text-align:center;margin:0;letter-spacing:1px;
                        text-transform:uppercase;">
                Powered by PANTHEON &nbsp;·&nbsp; AsgardMade Autonomous Commerce System
              </p>
              <p style="color:#2a2040;font-size:11px;text-align:center;margin:8px 0 0;">
                This report was generated automatically every Sunday at 8:00 AM.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return html


# ─── Sender ───────────────────────────────────────────────────────────────────

async def send_weekly_report(stats: dict) -> bool:
    """
    Build and send the weekly HTML email via Gmail SMTP.
    Returns True on success, False on any failure.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[GMAIL] GMAIL_USER or GMAIL_APP_PASSWORD not set — skipping weekly report")
        return False

    recipient = REPORT_TO or GMAIL_USER
    subject = f"AsgardMade Weekly Report — {datetime.now().strftime('%b %d, %Y')}"

    html = build_weekly_html_report(stats)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, recipient, msg.as_string())
        print(f"[GMAIL] Weekly report sent to {recipient}")
        return True
    except Exception as e:
        print(f"[GMAIL] Send failed: {type(e).__name__}: {e}")
        return False
