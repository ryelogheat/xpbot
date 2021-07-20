import os
import re
import json
import logging
import requests
from distutils import util
from guessit import guessit
from fuzzywuzzy import fuzz
from rich.table import Table
from rich.prompt import Confirm
from rich.console import Console



console = Console()

working_folder = os.path.dirname(os.path.realpath(__file__))

logging.basicConfig(filename=f'{working_folder}/upload_script.log',
                    level=logging.INFO,
                    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')


def search_for_dupes_api(search_site, imdb, torrent_info, tracker_api):
    with open(f'{working_folder}/site_templates/{search_site}.json', "r", encoding="utf-8") as config_file:
        # with open(working_folder + "/site_templates/{}.json".format(search_site), "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    if str(config["dupes"]["request"]) == "POST":
        # POST request (BHD)
        url_dupe_search = str(config["torrents_search"]).format(api_key=tracker_api)
        url_dupe_payload = {'action': 'search', config["translation"]["imdb"]: imdb}
        dupe_check_response = requests.post(url=url_dupe_search, data=url_dupe_payload)
    else:
        # GET request (BLU & ACM)
        url_dupe_search = str(config["dupes"]["url_format"]).format(search_url=str(config["torrents_search"]).format(api_key=tracker_api), imdb=imdb[2:])
        url_dupe_payload = None  # this is here just for the log, its not technically needed
        dupe_check_response = requests.get(url=url_dupe_search)

    logging.info(msg=f'Dupe search request | Method: {str(config["dupes"]["request"])} | URL: {url_dupe_search} | Payload: {url_dupe_payload}')


    if dupe_check_response.status_code != 200:
        logging.error(f"{search_site} returned the status code: {dupe_check_response.status_code}")
        logging.error(f"Dupe check for {search_site} failed, assuming no dupes and continuing upload")
        return False

    # Now that we have the response from tracker(X) we can parse the json and try to identify dupes

    existing_release_types = {}  # We first break down the results into very basic categories like "remux", "encode", "web" etc and store the title + results here
    existing_releases_count = {'bluray_encode': 0, 'bluray_remux': 0, 'webdl': 0, 'webrip': 0, 'hdtv': 0}  # We also log the num each type shows up on site

    for item in dupe_check_response.json()[str(config["dupes"]["parse_json"]["top_lvl"])]:

        if "torrent_details" in config["dupes"]["parse_json"]:
            # BLU & ACM have us go 2 "levels" down to get torrent info -->  [data][attributes][name] = torrent title
            torrent_details = item[str(config["dupes"]["parse_json"]["torrent_details"])]
        else:
            # BHD only has us go down 1 "level" to get torrent info --> [data][name] = torrent title
            torrent_details = item

        torrent_title = str(torrent_details["name"])
        torrent_title_split = torrent_title.replace("-", " ").lower().split(' ')


        # Bluray Encode
        if all(x in torrent_title_split for x in ['bluray']) and any(x in torrent_title_split for x in ['720p', '1080i', '1080p', '2160p']) and any(x in torrent_title_split for x in ['x264', 'x265']):
            existing_release_types[torrent_title] = 'bluray_encode'

        # Bluray Remux
        if all(x in torrent_title_split for x in ['bluray', 'remux']) and any(x in torrent_title_split for x in ['720p', '1080i', '1080p', '2160p']):
            existing_release_types[torrent_title] = 'bluray_remux'

        # WEB-DL
        if all(x in torrent_title_split for x in ['web', 'dl']) and any(x in torrent_title_split for x in ['h.264', 'h264', 'h.265', 'h265', 'hevc']):
            existing_release_types[torrent_title] = "webdl"

        # WEBRip
        if all(x in torrent_title_split for x in ['webrip']) and any(x in torrent_title_split for x in ['h.264', 'h264', 'h.265', 'h265', 'hevc', 'x264', 'x265']):
            existing_release_types[torrent_title] = "webrip"

        # HDTV
        if all(x in torrent_title_split for x in ['hdtv']):
            existing_release_types[torrent_title] = "hdtv"

        # DVD
        if all(x in torrent_title_split for x in ['dvd']):
            existing_release_types[torrent_title] = "dvd"


    # If we are uploading a tv show we should only add the correct season to the existing_release_types dict
    if "s00e00" in torrent_info:
        # We just want the season of whatever we are uploading so we can filter the results later (Most API requests include all the seasons/episodes of a tv show in the response, we don't need all of them)
        season = str(torrent_info["s00e00"])[:-3] if len(torrent_info["s00e00"]) > 3 else str(torrent_info["s00e00"])

        for existing_release_types_key in list(existing_release_types.keys()):
            if season not in existing_release_types_key:  # filter our wrong seasons
                existing_release_types.pop(existing_release_types_key)


    # This just updates a dict with the number of a particular "type" of release exists on site (e.g. "2 bluray_encodes" or "1 bluray_remux" etc)
    for onsite_quality_type in existing_release_types.values():
        existing_releases_count[onsite_quality_type] += 1
    logging.info(msg=f'Results from initial dupe query (all resolution): {existing_releases_count}')


    # If we get no matches when searching via IMDB ID that means this content hasn't been upload in any format, no possibility for dupes
    if len(existing_release_types.keys()) == 0:
        logging.info(msg='Dupe query did not return any releases that we could parse, assuming no dupes exist.')
        return False



    # --------------- Filter the existing_release_types dict to only include correct res & source_type --------------- #
    for their_title in list(existing_release_types.keys()):  # we wrap the dict keys in a "list()" so we can modify (pop) keys from it while the loop is running below
        # use guessit to get details about the release
        their_title_guessit = guessit(their_title)
        their_title_type = existing_release_types[their_title]

        # This next if statement does 2 things:
        #   1. If the torrent title from the API request doesn't have the same resolution as the file being uploaded we pop (remove) it from the dict "existing_release_types"
        #   2. If the API torrent title source type (e.g. bluray_encode) is not the same as the local file then we again pop it from the "existing_release_types" dict
        if ("screen_size" not in their_title_guessit or their_title_guessit["screen_size"] != torrent_info["screen_size"]) or their_title_type != torrent_info["source_type"]:
            existing_releases_count[their_title_type] -= 1
            existing_release_types.pop(their_title)

    logging.info(msg=f'After applying resolution & "source_type" filter: {existing_releases_count}')


    def fuzzy_similarity(our_title, check_against_title):
        check_against_title_original = check_against_title
        # We will remove things like the title & year from the comparison stings since we know they will be exact matches anyways

        # replace DD+ with DDP from both our title and tracker results title to make the dupe check a bit more accurate since some sites like to use DD+ and others DDP but they refer to the same thing
        our_title = re.sub(r'dd\+', 'ddp', str(our_title).lower())
        check_against_title = re.sub(r'dd\+', 'ddp', str(check_against_title).lower())
        content_title = re.sub('[^0-9a-zA-Z]+', ' ', str(torrent_info["title"]).lower())

        if "year" in torrent_info:
            # Also remove the year because that *should* be an exact match, that's not relevant to detecting changes
            if str(int(torrent_info["year"]) + 1) in check_against_title:
                check_against_title_year = str(int(torrent_info["year"]) + 1)  # some releases are occasionally off by 1 year, it's still the same media so it can be used for dupe check
            elif str(int(torrent_info["year"]) - 1) in check_against_title:
                check_against_title_year = str(int(torrent_info["year"]) - 1)
            else:
                check_against_title_year = str(torrent_info["year"])
        else:
            check_against_title_year = ""

        # our_title = str(our_title).replace(torrent_info["resolution"], "").replace(check_against_title_year, "").replace(content_title, "")
        our_title = re.sub(r'[^A-Za-z0-9 ]+', ' ', str(our_title)).lower().replace(torrent_info["screen_size"], "").replace(check_against_title_year, "")
        our_title = " ".join(our_title.split())

        check_against_title = re.sub(r'[^A-Za-z0-9 ]+', ' ', str(check_against_title)).lower().replace(torrent_info["screen_size"], "").replace(check_against_title_year, "")
        check_against_title = " ".join(check_against_title.split())

        token_set_ratio = fuzz.token_set_ratio(our_title.replace(content_title, ''), check_against_title.replace(content_title, ''))
        logging.info(f"'{check_against_title_original}' was flagged with a {str(token_set_ratio)}% dupe probability")


        # Instead of wasting time trying to create a 'low, medium, high' risk system we just have the user enter in a percentage they are comfortable with
        # if a torrent titles vs local title similarity percentage exceeds a limit the user set we immediately quit trying to upload to that site
        # since what the user considers (via token_set_ratio percentage) to be a dupe exists
        return token_set_ratio


    possible_dupes_table = Table(show_header=True, header_style="bold cyan")
    possible_dupes_table.add_column(f"Exceeds Max % ({os.getenv('acceptable_similarity_percentage')}%)", justify="left")
    possible_dupes_table.add_column(f"Possible Dupes ({str(config['source']).upper()})", justify="left")
    possible_dupes_table.add_column("Similarity %", justify="center")


    possible_dupe_with_percentage_dict = {}
    max_dupe_percentage_exceeded = False

    for possible_dupe_title in existing_release_types.keys():
        # If we get a match then run further checks
        possible_dupe_with_percentage_dict[possible_dupe_title] = fuzzy_similarity(our_title=torrent_info["torrent_title"], check_against_title=possible_dupe_title)


    for possible_dupe in sorted(possible_dupe_with_percentage_dict, key=possible_dupe_with_percentage_dict.get, reverse=True):
        mark_as_dupe = bool(possible_dupe_with_percentage_dict[possible_dupe] >= int(os.getenv('acceptable_similarity_percentage')))
        mark_as_dupe_color = "bright_red" if mark_as_dupe else "dodger_blue1"
        mark_as_dupe_percentage_difference_raw_num = possible_dupe_with_percentage_dict[possible_dupe] - int(os.getenv('acceptable_similarity_percentage'))
        mark_as_dupe_percentage_difference = f'{"+" if mark_as_dupe_percentage_difference_raw_num >= 0 else "-"}{abs(mark_as_dupe_percentage_difference_raw_num)}%'

        possible_dupes_table.add_row(f'[{mark_as_dupe_color}]{mark_as_dupe}[/{mark_as_dupe_color}] ({mark_as_dupe_percentage_difference})', possible_dupe, f'{str(possible_dupe_with_percentage_dict[possible_dupe])}%')


        # because we want to show the user every possible dupe (not just the ones that exceed the max percentage) we just mark an outside var True & finish the for loop that adds the table rows
        if not max_dupe_percentage_exceeded:
            max_dupe_percentage_exceeded = mark_as_dupe


    if max_dupe_percentage_exceeded:
        console.print(f"\n[bold red on white] :warning: Detected possible dupe! :warning: [/bold red on white]")
        console.print(possible_dupes_table)
        return True if bool(util.strtobool(os.getenv('auto_mode'))) else not bool(Confirm.ask("\nContinue upload even with possible dupe?"))
    else:
        console.print(f":heavy_check_mark: Yay! No dupes found on [bold]{str(config['source']).upper()}[/bold], continuing the upload process now\n")
        return False
