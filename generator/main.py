import json
import sys
import traceback
from time import time
from typing import Any

from alive_progress import alive_bar  # type: ignore

from datadump import DataDump
from prettyprint import Platform, PrettyPrint, Status

pprint = PrettyPrint()


def get_anime_offline_database() -> list[dict[str, Any]]:
    """Get info from manami-project/anime-offline-database"""
    pprint.print(
        Platform.ANIMEOFFLINEDATABASE,
        Status.READY,
        "anime-offline-database ready to use",
    )
    ddump = DataDump(
        url="https://raw.githubusercontent.com/manami-project/anime-offline-database/master/anime-offline-database-minified.json",
        file_name="aod",
        file_type="json",
    )
    content: dict[str, Any] = ddump.dumper()
    data: list[dict[str, Any]] = content["data"]
    pprint.print(
        Platform.ANIMEOFFLINEDATABASE,
        Status.PASS,
        "anime-offline-database data retrieved successfully",
    )
    return data


def get_arm() -> list[dict[str, Any]]:
    pprint.print(
        Platform.ARM,
        Status.READY,
        "ARM ready to use",
    )
    ddump = DataDump(
        url="https://raw.githubusercontent.com/kawaiioverflow/arm/master/arm.json",
        file_name="arm",
        file_type="json",
    )
    data: list[dict[str, Any]] = ddump.dumper()
    pprint.print(
        Platform.ARM,
        Status.PASS,
        "ARM data retrieved successfully",
    )
    return data


def get_anitrakt() -> list[dict[str, Any]]:
    pprint.print(
        Platform.ANITRAKT,
        Status.READY,
        "AniTrakt ready to use",
    )
    base_url = "https://raw.githubusercontent.com/ryuuganime/aniTrakt-IndexParser/main/db/"
    ddump_tv = DataDump(
        url=f"{base_url}tv.json",
        file_name="anitrakt_tv",
        file_type="json",
    )
    data_tv: list[dict[str, Any]] = ddump_tv.dumper()
    pprint.print(
        Platform.ANITRAKT,
        Status.PASS,
        "AniTrakt data for TV retrieved successfully",
    )

    ddump_movie = DataDump(
        url=f"{base_url}movies.json",
        file_name="anitrakt_movie",
        file_type="json",
    )
    data_movie: list[dict[str, Any]] = ddump_movie.dumper()
    pprint.print(
        Platform.ANITRAKT,
        Status.PASS,
        "AniTrakt data for Movie retrieved successfully",
    )
    with alive_bar(len(data_movie),
                   title="Fixing AniTrakt data for movie",
                   spinner=None) as bar:  # type: ignore
        for index, item in enumerate(data_movie):
            item["season"] = None
            data_movie[index] = item
            bar()  # type: ignore
    data = data_tv + data_movie
    with open("database/raw/anitrakt.json", "w", encoding="utf-8") as file:
        json.dump(data, file)
    pprint.print(
        Platform.ANITRAKT,
        Status.PASS,
        "Completely compiled AniTrakt data",
    )
    return data


def get_silveryasha() -> list[dict[str, Any]]:
    pprint.print(
        Platform.SILVERYASHA,
        Status.READY,
        "Silveryasha ready to use",
    )
    ddump = DataDump(
        url="https://db.silveryasha.web.id/ajax/anime/dtanime",
        file_name="silveryasha",
        file_type="json",
    )
    data_: dict[str, Any] = ddump.dumper()
    data: list[dict[str, Any]] = data_["data"]
    pprint.print(
        Platform.SILVERYASHA,
        Status.PASS,
        "Silveryasha data retrieved successfully",
    )
    return data


def main() -> None:
    """Main function"""
    try:
        start_time = time()
        pprint.print(Platform.SYSTEM, Status.READY, "Generator ready to use")
        get_anime_offline_database()
        get_arm()
        get_anitrakt()
        get_silveryasha()
        end_time = time()
        pprint.print(
            Platform.SYSTEM,
            Status.INFO,
            f"Generator finished in {end_time - start_time:.2f} seconds",
        )
    except KeyboardInterrupt:
        pprint.print(Platform.SYSTEM, Status.ERR, "Stopped by user")
    except Exception as err:
        pprint.print(Platform.SYSTEM, Status.ERR, f"Error: {err}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        pprint.print(Platform.SYSTEM, Status.INFO, "Exiting...")
        sys.exit(0)
