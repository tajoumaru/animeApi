# SPDX-License-Identifier: MIT

from typing import Any, Union

import requests as req
from alive_progress import alive_bar  # type: ignore
from bs4 import BeautifulSoup, Tag
from fake_useragent import FakeUserAgent  # type: ignore
from generator.const import pprint
from generator.prettyprint import Platform, Status

fua = FakeUserAgent(browsers=["chrome"])
rand_fua: str = f"{fua.random}"  # type: ignore


class OtakOtaku:
    """OtakOtaku anime data scraper"""

    def __init__(self) -> None:
        """Initiate the class"""
        self.headers = {
            "authority": "otakotaku.com",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "cookie": "lang=id",
            "dnt": "1",
            "referer": "https://otakotaku.com/anime/view/1/yahari-ore-no-seishun-love-comedy-wa-machigatteiru",
            "sec-ch-ua": '"Chromium";v="116", " Not)A;Brand";v="24", "Microsoft Edge";v="116"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "user-agent": rand_fua,
            "x-requested-with": "XMLHttpRequest",
            "Content-Encoding": "gzip",
        }
        pprint.print(
            Platform.OTAKOTAKU,
            Status.READY,
            "OtakOtaku anime data scraper ready to use",
        )

    def _get(self, url: str) -> Union[req.Response, None]:
        """
        Get the response from the url

        :param url: The url to get the response
        :type url: str
        :return: The response from the url
        :rtype: Union[req.Response, None]
        """
        response = req.get(url, headers=self.headers, timeout=15)
        try:
            response.raise_for_status()
            return response
        except Exception as err:
            pprint.print(Platform.OTAKOTAKU, Status.ERR, f"Error: {err}")
            return None

    def get_latest_anime(self) -> int:
        """
        Get latest anime from the website

        :return: The latest anime id
        :rtype: int
        """
        url = "https://otakotaku.com/anime/feed"
        response = self._get(url)
        if not response:
            raise ConnectionError("Failed to connect to otakotaku.com")
        soup = BeautifulSoup(response.text, "html.parser")
        link = soup.find("div", class_="anime-img")
        if not isinstance(link, Tag):
            pprint.print(Platform.OTAKOTAKU, Status.ERR, "Failed to get latest anime")
            return 0
        link = link.find("a")
        if not isinstance(link, Tag):
            pprint.print(Platform.OTAKOTAKU, Status.ERR, "Failed to get latest anime")
            return 0
        href = link.get("href")
        if not href:
            pprint.print(Platform.OTAKOTAKU, Status.ERR, "Failed to get latest anime")
            return 0
        if isinstance(href, list):
            href = href[0]
        anime_id = href.rstrip("/").split("/")[-2]
        pprint.print(Platform.OTAKOTAKU, Status.PASS, f"Latest anime id: {anime_id}")
        return int(anime_id)

    def _get_data(self, anime_id: int) -> Union[dict[str, Any], None]:
        """
        Get anime data

        :param anime_id: The anime id
        :type anime_id: int
        :return: The anime data
        :rtype: Union[dict[str, Any], None]
        """
        response = self._get(
            f"https://otakotaku.com/api/anime/view/{anime_id}/yahari-ore-no-seishun-love-comedy-wa-machigatteiru"
        )
        if not response:
            raise ConnectionError("Failed to connect to otakotaku.com")
        json_: dict[str, Any] = response.json()
        if not json_:
            return None
        data: dict[str, Any] = json_["data"]
        mal: Union[str, int, None] = data.get("`mal_id_anime", None)
        if mal:
            mal = int(mal)
        apla = data.get("ap_id_anime", None)
        if apla:
            apla = int(apla)
        anidb = data.get("anidb_id_anime", None)
        if anidb:
            anidb = int(anidb)
        ann = data.get("ann_id_anime", None)
        if ann:
            ann = int(ann)
        title = data["judul_anime"]
        title = title.replace("&quot;", '"')
        result: dict[str, Union[str, int, None]] = {
            "otakotaku": int(data["id_anime"]),
            "title": title,
            "myanimelist": mal,
            "animeplanet": apla,
            "anidb": anidb,
            "animenewsnetwork": ann,
        }
        return result

    def get_anime(self) -> list[dict[str, Any]]:
        """
        Get complete anime data

        :return: The anime data
        :rtype: list[dict[str, Any]]
        """
        anime_list: list[dict[str, Any]] = []

        pprint.print(Platform.OTAKOTAKU, Status.INFO, "Starting anime data collection")

        latest_id = self.get_latest_anime()
        if not latest_id:
            raise ConnectionError("Failed to connect to otakotaku.com")

        # Get all anime data from 1 to latest_id
        with alive_bar(latest_id, title="Getting OtakOtaku data", spinner=None) as bar:  # type: ignore
            for anime_id in range(1, latest_id + 1):
                data_index = self._get_data(anime_id)
                if not data_index:
                    pprint.print(
                        Platform.OTAKOTAKU,
                        Status.ERR,
                        f"Failed to get data index for anime id: {anime_id},"
                        " data may be empty or invalid",
                    )
                    bar()
                    continue
                anime_list.append(data_index)
                bar()

        anime_list.sort(key=lambda x: x["title"])  # type: ignore

        pprint.print(
            Platform.OTAKOTAKU, Status.PASS, f"Total anime data: {len(anime_list)}"
        )

        return anime_list

    @staticmethod
    def convert_list_to_dict(data: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """
        Convert list to dict

        :param data: The list to convert
        :type data: list[dict[str, Any]]
        :return: The converted list
        :rtype: dict[str, dict[str, Any]]
        """
        result: dict[str, dict[str, Any]] = {}
        for item in data:
            result[str(item["otakotaku"])] = item
        return result
