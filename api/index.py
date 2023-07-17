import json
from datetime import datetime
from typing import Any, Union

import flask

app = flask.Flask(__name__)


def platform_id_content(platform: str, platform_id: int) -> dict[str, Any]:
    with open(f"database/{platform}_object.json", "r") as f:
        data = json.loads(f.read())
    return data[str(platform_id)]


@app.route("/", methods=["GET"])
def index():
    # redirect user to GitHub repo
    return flask.redirect("https://github.com/nattadasu/animeApi")


@app.route("/status", methods=["GET"])
@app.route("/heartbeat", methods=["GET"])
def status():
    with open("api/status.json", "r") as f:
        return flask.jsonify(json.loads(f.read()))


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return flask.send_from_directory("api", "favicon.ico")  # type: ignore


@app.route("/updated", methods=["GET"])
def updated():
    with open("api/status.json", "r") as f:
        updated_time = json.loads(f.read())["updated"]["timestamp"]
    formatted_time = datetime.utcfromtimestamp(
        updated_time).strftime("%m/%d/%Y %H:%M:%S UTC")
    return flask.Response(f"Updated on {formatted_time}", mimetype="text/plain")


@app.route("/robots.txt", methods=["GET"])
def robots():
    with open("api/robots.txt", "r") as f:
        return flask.Response(f.read(), mimetype="text/plain", status=200)


@app.route("/trakt/<media_type>/<media_id>", methods=["GET"])
@app.route("/trakt/<media_type>/<media_id>/seasons/<season_id>", methods=["GET"])
@app.route("/trakt/<media_type>/<media_id>/season/<season_id>", methods=["GET"])
def trakt_exclusive_route(media_type: str, media_id: int, season_id: Union[int, None] = None):
    with open(f"database/trakt_object.json", "r") as f:
        data = json.loads(f.read())
    try:
        if not media_type.endswith("s"):
            media_type_ = media_type + "s"
        else:
            media_type_ = media_type
        if season_id is None:
            return flask.jsonify(data[f"{media_type_}/{media_id}"])
        return flask.jsonify(data[f"{media_type_}/{media_id}/seasons/{season_id}"])
    except KeyError:
        return flask.jsonify({
            "error": "Not found",
            "code": 404,
            "message": f"Media type {media_type} with ID {media_id} {'and season ID ' + str(season_id) + ' ' if season_id is not None else ''}not found"
        }), 404


@app.route("/<platform>", methods=["GET"])
@app.route("/<platform>()", methods=["GET"])
def platform_array(platform: str = "animeapi"):
    # get current route
    route = flask.request.path
    platform = platform.lower()
    if not route.endswith("()") and platform != "animeapi":
        platform = platform + "_object"
    if platform == "syobocal":
        platform = "shoboi"
    return flask.jsonify({
        "error": "File too large",
        "code": 413,
        "message": f"To bypass this, prefer to download from GitHub raw directly. Your path is: https://raw.githubusercontent.com/nattadasu/animeApi/v3/database/{platform}.json"
    }), 413

@app.route("/<platform>/<platform_id>.json", methods=["GET"])
@app.route("/<platform>/<platform_id>", methods=["GET"])
def platform_id(platform: str, platform_id: int):
    platform = platform.lower()
    if platform == "syobocal":
        platform = "shoboi"
    data = platform_id_content(platform, platform_id)
    return flask.jsonify(data)


# general error handler
@app.errorhandler(Exception)
def handle_error(err: Exception):
    err_split = str(err).split(":")
    get_code = err_split[0].split(" ")
    data = {
        "error": " ".join(err_split[-1:]).strip(),
        "code": int(get_code[0]),
    }
    return flask.jsonify(data), int(get_code[0])
