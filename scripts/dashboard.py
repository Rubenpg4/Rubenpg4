#!/usr/bin/env python3
"""Genera las tarjetas SVG del perfil: actividad, lenguajes y proyectos destacados.

Solo usa la biblioteca estándar. Lee dashboard.config.json y consulta la API
GraphQL de GitHub con GITHUB_TOKEN. Solo cuenta repositorios públicos y propios
(sin forks); un proyecto de la configuración que no sea público no se dibuja.

    GITHUB_TOKEN=... python scripts/dashboard.py --out dist

Cada tarjeta se escribe en versión clara y oscura: <nombre>-light.svg y <nombre>-dark.svg.
"""

import argparse
import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com/graphql"

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "title": "#e6edf3",
        "text": "#9198a1",
        "muted": "#6e7681",
        "accent": "#ff9900",
        "link": "#4493f8",
        "track": "#21262d",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d1d9e0",
        "title": "#1f2328",
        "text": "#59636e",
        "muted": "#818b98",
        "accent": "#e8870a",
        "link": "#0969da",
        "track": "#eff2f5",
    },
}

MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Octicon "repo" (MIT, GitHub).
REPO_ICON = (
    "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z"
)

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      nodes {
        name
        isPrivate
        stargazerCount
        pushedAt
        primaryLanguage { name color }
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-dashboard",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        sys.exit(f"Error de la API de GitHub: {payload['errors']}")
    return payload["data"]["user"]


def number(value):
    return f"{value:,}".replace(",", ".")


def month_year(iso_date):
    year, month = iso_date[:4], int(iso_date[5:7])
    return f"{MONTHS[month - 1]} {year}"


def streaks(days):
    """Racha actual y máxima, en días. Hoy sin actividad todavía no rompe la racha."""
    longest = run = 0
    for _, count in days:
        run = run + 1 if count else 0
        longest = max(longest, run)
    tail = days[:-1] if days and days[-1][1] == 0 else days
    current = 0
    for _, count in reversed(tail):
        if not count:
            break
        current += 1
    return current, longest


def wrap(text, max_chars, max_lines):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) <= max_chars or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return lines


def card(width, height, title, body, t):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">
<title id="title">{escape(title)}</title>
<style>
  text {{ font-family: {FONT}; }}
  .mono {{ font-family: {MONO}; }}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t['bg']}" stroke="{t['border']}"/>
{body}
</svg>
"""


def header(label, t):
    return (
        f'<rect x="24" y="23" width="4" height="14" rx="1" fill="{t["accent"]}"/>'
        f'<text x="36" y="35" font-size="14" font-weight="600" fill="{t["title"]}">{escape(label)}</text>'
    )


def stats_card(user, repo_count, t):
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    days = [(d["date"], d["contributionCount"]) for w in calendar["weeks"] for d in w["contributionDays"]]
    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in calendar["weeks"]]
    current, longest = streaks(days)

    parts = [header("Actividad · últimos 12 meses", t)]
    parts.append(
        f'<text x="24" y="92" font-size="38" font-weight="700" fill="{t["title"]}">{number(calendar["totalContributions"])}</text>'
        f'<text x="24" y="114" font-size="12" fill="{t["text"]}">contribuciones</text>'
    )
    cells = [
        ("Commits", number(collection["totalCommitContributions"])),
        ("Pull requests", number(collection["totalPullRequestContributions"])),
        ("Issues", number(collection["totalIssueContributions"])),
        ("Repos públicos", number(repo_count)),
        ("Racha actual", f"{current} d"),
        ("Racha máxima", f"{longest} d"),
    ]
    for i, (label, value) in enumerate(cells):
        x = 188 + (i % 3) * 96
        y = 72 if i < 3 else 118
        parts.append(
            f'<text x="{x}" y="{y}" font-size="20" font-weight="600" fill="{t["title"]}">{escape(value)}</text>'
            f'<text x="{x}" y="{y + 17}" font-size="11" fill="{t["muted"]}">{escape(label)}</text>'
        )

    parts.append(f'<text x="24" y="166" font-size="11" fill="{t["muted"]}">Contribuciones por semana</text>')
    top, height, left, span = 176, 28, 24, 432
    step = span / max(len(weekly), 1)
    peak = max(weekly) or 1
    for i, count in enumerate(weekly):
        h = max(2, round(height * count / peak))
        fill = t["accent"] if count else t["track"]
        parts.append(
            f'<rect x="{left + i * step:.1f}" y="{top + height - h}" width="{max(step - 2, 1):.1f}" height="{h}" rx="1" fill="{fill}"/>'
        )
    return card(480, 224, "Actividad en GitHub", "\n".join(parts), t)


def language_totals(repos, excluded):
    totals = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in excluded:
                continue
            size, color = totals.get(name, (0, edge["node"]["color"]))
            totals[name] = (size + edge["size"], color)
    ranked = sorted(totals.items(), key=lambda item: item[1][0], reverse=True)
    total = sum(size for _, (size, _) in ranked) or 1
    top = [(name, size / total, color) for name, (size, color) in ranked[:7]]
    rest = sum(size for _, (size, _) in ranked[7:])
    if rest:
        top.append(("Otros", rest / total, None))
    return top


def languages_card(languages, t):
    parts = [header("Lenguajes · repos públicos", t)]
    parts.append(
        '<clipPath id="bar"><rect x="24" y="54" width="432" height="10" rx="5"/></clipPath>'
        f'<rect x="24" y="54" width="432" height="10" rx="5" fill="{t["track"]}"/>'
    )
    x = 24.0
    segments = []
    for _, share, color in languages:
        width = 432 * share
        segments.append(f'<rect x="{x:.2f}" y="54" width="{width + 0.5:.2f}" height="10" fill="{color or t["muted"]}"/>')
        x += width
    parts.append(f'<g clip-path="url(#bar)">{"".join(segments)}</g>')

    for i, (name, share, color) in enumerate(languages):
        x = 24 if i < 4 else 252
        y = 100 + (i % 4) * 28
        parts.append(
            f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{color or t["muted"]}"/>'
            f'<text x="{x + 18}" y="{y}" font-size="13" fill="{t["title"]}">{escape(name)}</text>'
            f'<text x="{x + 204}" y="{y}" font-size="12" text-anchor="end" class="mono" fill="{t["text"]}">{share * 100:.1f}%</text>'
        )
    parts.append(f'<text x="24" y="206" font-size="11" fill="{t["muted"]}">Por volumen de código · sin forks</text>')
    return card(480, 224, "Lenguajes más usados", "\n".join(parts), t)


def project_card(project, repo, t):
    parts = [
        f'<path transform="translate(24 22)" d="{REPO_ICON}" fill="{t["text"]}"/>',
        f'<text x="48" y="35" font-size="16" font-weight="600" fill="{t["link"]}">{escape(project["title"])}</text>',
    ]
    if repo["stargazerCount"]:
        parts.append(
            f'<text x="456" y="35" font-size="12" text-anchor="end" fill="{t["text"]}">★ {repo["stargazerCount"]}</text>'
        )
    for i, line in enumerate(wrap(project["description"], 66, 3)):
        parts.append(f'<text x="24" y="{64 + i * 19}" font-size="13" fill="{t["text"]}">{escape(line)}</text>')

    x = 24
    for tag in project.get("tags", []):
        width = round(len(tag) * 6.4 + 20)
        if x + width > 456:
            break
        parts.append(
            f'<rect x="{x}" y="122" width="{width}" height="20" rx="10" fill="{t["track"]}"/>'
            f'<text x="{x + width / 2}" y="136" font-size="11" text-anchor="middle" fill="{t["title"]}">{escape(tag)}</text>'
        )
        x += width + 6

    footer = f'actualizado {month_year(repo["pushedAt"])}'
    language = repo["primaryLanguage"]
    if language:
        parts.append(
            f'<circle cx="29" cy="164" r="5" fill="{language["color"] or t["muted"]}"/>'
            f'<text x="40" y="168" font-size="12" fill="{t["text"]}">{escape(language["name"])}</text>'
        )
        footer_x = 40 + round(len(language["name"]) * 7 + 10)
    else:
        footer_x = 24
    parts.append(f'<text x="{footer_x}" y="168" font-size="12" fill="{t["muted"]}">{"· " if language else ""}{footer}</text>')
    return card(480, 188, project["title"], "\n".join(parts), t)


def write(path, content):
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"  {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--config", type=Path, default=ROOT / "dashboard.config.json")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Falta GITHUB_TOKEN.")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    user = fetch(config["user"], token)

    excluded = set(config.get("exclude_repos", []))
    repos = {r["name"]: r for r in user["repositories"]["nodes"] if not r["isPrivate"] and r["name"] not in excluded}
    languages = language_totals(repos.values(), set(config.get("exclude_languages", [])))

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Generando tarjetas en {args.out}")
    for theme, t in THEMES.items():
        write(args.out / f"stats-{theme}.svg", stats_card(user, len(repos), t))
        write(args.out / f"languages-{theme}.svg", languages_card(languages, t))
        for project in config.get("projects", []):
            repo = repos.get(project["repo"])
            if repo is None:
                print(f"  aviso: {project['repo']} no es un repo público propio; se omite", file=sys.stderr)
                continue
            write(args.out / f"project-{project['repo'].lower()}-{theme}.svg", project_card(project, repo, t))


if __name__ == "__main__":
    main()
