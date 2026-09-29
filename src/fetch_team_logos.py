from pathlib import Path

import certifi
import requests

from team_metadata import TEAM_METADATA


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

OUTPUT_DIR = (
    ROOT_DIR
    / "dashboard"
    / "assets"
    / "logos"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def get_logo_url(team_id):
    return (
        "https://cdn.nba.com/"
        f"logos/nba/{team_id}/"
        "primary/D/logo.svg"
    )


def download_logo(
    team_id,
    tricode,
):
    url = get_logo_url(
        team_id
    )

    output_path = (
        OUTPUT_DIR
        / f"{tricode.lower()}.svg"
    )

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent":
                "Mozilla/5.0",
        },
        verify=certifi.where(),
    )

    response.raise_for_status()

    output_path.write_bytes(
        response.content
    )

    print(
        f"{tricode}: "
        f"{output_path}"
    )


def main():
    success = 0
    failed = 0

    for (
        team_id,
        metadata,
    ) in TEAM_METADATA.items():
        tricode = metadata[
            "tricode"
        ]

        try:
            download_logo(
                team_id,
                tricode,
            )

            success += 1

        except Exception as error:
            failed += 1

            print(
                f"FAILED {tricode}: "
                f"{error}"
            )

    print()
    print(
        f"Downloaded: {success}"
    )

    print(
        f"Failed: {failed}"
    )


if __name__ == "__main__":
    main()