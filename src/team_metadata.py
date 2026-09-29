from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

LOGO_DIR = (
    ROOT_DIR
    / "dashboard"
    / "assets"
    / "logos"
)


def logo_path(tricode):
    return str(
        LOGO_DIR
        / f"{tricode.lower()}.svg"
    )


TEAM_METADATA = {
    1610612737: {
        "name": "Atlanta Hawks",
        "tricode": "ATL",
        "primary_color": "#E03A3E",
        "secondary_color": "#C1D32F",
        "chart_color": "#FF5A5F",
        "logo": logo_path("ATL"),
    },

    1610612738: {
        "name": "Boston Celtics",
        "tricode": "BOS",
        "primary_color": "#007A33",
        "secondary_color": "#BA9653",
        "chart_color": "#2ECC71",
        "logo": logo_path("BOS"),
    },

    1610612739: {
        "name": "Cleveland Cavaliers",
        "tricode": "CLE",
        "primary_color": "#860038",
        "secondary_color": "#FDBB30",
        "chart_color": "#F6C344",
        "logo": logo_path("CLE"),
    },

    1610612740: {
        "name": "New Orleans Pelicans",
        "tricode": "NOP",
        "primary_color": "#0C2340",
        "secondary_color": "#C8102E",
        "chart_color": "#4DA3FF",
        "logo": logo_path("NOP"),
    },

    1610612741: {
        "name": "Chicago Bulls",
        "tricode": "CHI",
        "alternate_chart_color": "#F3F4F6",
        "primary_color": "#CE1141",
        "secondary_color": "#000000",
        "chart_color": "#FF3B5C",
        "logo": logo_path("CHI"),
    },

    1610612742: {
        "name": "Dallas Mavericks",
        "tricode": "DAL",
        "primary_color": "#00538C",
        "secondary_color": "#B8C4CA",
        "chart_color": "#48A9E6",
        "logo": logo_path("DAL"),
    },

    1610612743: {
        "name": "Denver Nuggets",
        "tricode": "DEN",
        "primary_color": "#0E2240",
        "secondary_color": "#FEC524",
        "chart_color": "#FEC524",
        "logo": logo_path("DEN"),
    },

    1610612744: {
        "name": "Golden State Warriors",
        "tricode": "GSW",
        "primary_color": "#1D428A",
        "secondary_color": "#FFC72C",
        "chart_color": "#FFC72C",
        "logo": logo_path("GSW"),
    },

    1610612745: {
        "name": "Houston Rockets",
        "tricode": "HOU",
        "primary_color": "#CE1141",
        "secondary_color": "#000000",
        "chart_color": "#FF3B5C",
        "logo": logo_path("HOU"),
    },

    1610612746: {
        "name": "Los Angeles Clippers",
        "tricode": "LAC",
        "primary_color": "#C8102E",
        "secondary_color": "#1D428A",
        "chart_color": "#FF3B5C",
        "logo": logo_path("LAC"),
    },

    1610612747: {
        "name": "Los Angeles Lakers",
        "tricode": "LAL",
        "primary_color": "#552583",
        "secondary_color": "#FDB927",
        "chart_color": "#C79CFF",
        "logo": logo_path("LAL"),
    },

    1610612748: {
        "name": "Miami Heat",
        "tricode": "MIA",
        "primary_color": "#98002E",
        "secondary_color": "#F9A01B",
        "chart_color": "#FF4D6D",
        "logo": logo_path("MIA"),
    },

    1610612749: {
        "name": "Milwaukee Bucks",
        "tricode": "MIL",
        "primary_color": "#00471B",
        "secondary_color": "#EEE1C6",
        "chart_color": "#2ECC71",
        "logo": logo_path("MIL"),
    },

    1610612750: {
        "name": "Minnesota Timberwolves",
        "tricode": "MIN",
        "primary_color": "#0C2340",
        "secondary_color": "#78BE20",
        "chart_color": "#78BE20",
        "logo": logo_path("MIN"),
    },

    1610612751: {
        "name": "Brooklyn Nets",
        "tricode": "BKN",
        "primary_color": "#000000",
        "secondary_color": "#FFFFFF",
        "chart_color": "#D1D5DB",
        "logo": logo_path("BKN"),
    },

    1610612752: {
        "name": "New York Knicks",
        "tricode": "NYK",
        "primary_color": "#006BB6",
        "secondary_color": "#F58426",
        "chart_color": "#3DA5FF",
        "logo": logo_path("NYK"),
    },

    1610612753: {
        "name": "Orlando Magic",
        "tricode": "ORL",
        "primary_color": "#0077C0",
        "secondary_color": "#C4CED4",
        "chart_color": "#42B4FF",
        "logo": logo_path("ORL"),
    },

    1610612754: {
        "name": "Indiana Pacers",
        "tricode": "IND",
        "primary_color": "#002D62",
        "secondary_color": "#FDBB30",
        "chart_color": "#FDBB30",
        "logo": logo_path("IND"),
    },

    1610612755: {
        "name": "Philadelphia 76ers",
        "tricode": "PHI",
        "primary_color": "#006BB6",
        "secondary_color": "#ED174C",
        "chart_color": "#46A5FF",
        "logo": logo_path("PHI"),
    },

    1610612756: {
        "name": "Phoenix Suns",
        "tricode": "PHX",
        "primary_color": "#1D1160",
        "secondary_color": "#E56020",
        "chart_color": "#FF8C42",
        "logo": logo_path("PHX"),
    },

    1610612757: {
        "name": "Portland Trail Blazers",
        "tricode": "POR",
        "primary_color": "#E03A3E",
        "secondary_color": "#000000",
        "chart_color": "#FF5A5F",
        "logo": logo_path("POR"),
    },

    1610612758: {
        "name": "Sacramento Kings",
        "tricode": "SAC",
        "primary_color": "#5A2D81",
        "secondary_color": "#63727A",
        "chart_color": "#B388FF",
        "logo": logo_path("SAC"),
    },

    1610612759: {
        "name": "San Antonio Spurs",
        "tricode": "SAS",
        "primary_color": "#C4CED4",
        "secondary_color": "#000000",
        "chart_color": "#D8DEE4",
        "logo": logo_path("SAS"),
    },

    1610612760: {
        "name": "Oklahoma City Thunder",
        "tricode": "OKC",
        "primary_color": "#007AC1",
        "secondary_color": "#EF3B24",
        "chart_color": "#45B8FF",
        "logo": logo_path("OKC"),
    },

    1610612761: {
        "name": "Toronto Raptors",
        "tricode": "TOR",
        "primary_color": "#CE1141",
        "secondary_color": "#000000",
        "chart_color": "#FF3B5C",
        "logo": logo_path("TOR"),
    },

    1610612762: {
        "name": "Utah Jazz",
        "tricode": "UTA",
        "primary_color": "#002B5C",
        "secondary_color": "#F9A01B",
        "chart_color": "#F9A01B",
        "logo": logo_path("UTA"),
    },

    1610612763: {
        "name": "Memphis Grizzlies",
        "tricode": "MEM",
        "primary_color": "#5D76A9",
        "secondary_color": "#12173F",
        "chart_color": "#8EA8DB",
        "logo": logo_path("MEM"),
    },

    1610612764: {
        "name": "Washington Wizards",
        "tricode": "WAS",
        "primary_color": "#002B5C",
        "secondary_color": "#E31837",
        "chart_color": "#4DA3FF",
        "logo": logo_path("WAS"),
    },

    1610612765: {
        "name": "Detroit Pistons",
        "tricode": "DET",
        "primary_color": "#C8102E",
        "secondary_color": "#1D42BA",
        "chart_color": "#FF3B5C",
        "logo": logo_path("DET"),
    },

    1610612766: {
        "name": "Charlotte Hornets",
        "tricode": "CHA",
        "primary_color": "#1D1160",
        "secondary_color": "#00788C",
        "chart_color": "#38CBD8",
        "logo": logo_path("CHA"),
    },
}


def get_team_metadata(
    team_id,
):
    if team_id in TEAM_METADATA:
        return TEAM_METADATA[
            team_id
        ]

    return {
        "name": f"Team {team_id}",
        "tricode": str(team_id),
        "primary_color": "#6B7280",
        "secondary_color": "#9CA3AF",
        "chart_color": "#9CA3AF",
        "logo": None,
    }