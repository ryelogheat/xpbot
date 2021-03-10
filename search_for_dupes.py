import json
import os
import logging
import requests
from rich.console import Console
from rich.table import Table
import re
from fuzzywuzzy import fuzz

console = Console()

working_folder = os.path.dirname(os.path.realpath(__file__))

logging.basicConfig(filename='{}/upload_script.log'.format(working_folder),
                    level=logging.INFO,
                    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')


def search_for_dupes_api(search_site, imdb, torrent_info, tracker_api):
    with open(working_folder + "/site_templates/{}.json".format(search_site), "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    if str(config["dupes"]["request"]) == "POST":
        # POST request (BHD)
        url = str(config["torrents_search"]).format(api_key=tracker_api)
        payload = {'action': 'search', config["translation"]["imdb"]: imdb}
        response = requests.request("POST", url, data=payload)

    else:
        # GET request (BLU & ACM)
        url = str(config["dupes"]["url_format"]).format(search_url=str(config["torrents_search"]).format(api_key=tracker_api), imdb=imdb)
        response = requests.request("GET", url)

    if response.status_code != 200:
        logging.error(f"{search_site} returned the status code: {response.status_code}")
        logging.info(f"Dupe check for {search_site} failed, assuming no dupes and continuing upload")
        return "no_dupes"

    # Now that we have the response from tracker(X) we can parse the json and try to identify dupes
    # print(json.dumps(response.json(), indent=4, sort_keys=True))
    existing_release_types = {}  # We first break down the results into very basic categories like "remux", "encode", "web" etc and store the title + results here


    for item in response.json()[str(config["dupes"]["parse_json"]["top_lvl"])]:

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
        if len(torrent_info["s00e00"]) > 3:
            # This is an episode (since a len of 3 would only leave room for 'S01' not 'S01E01' etc)
            season = str(torrent_info["s00e00"])[:-3]
        else:
            season = str(torrent_info["s00e00"])


        for existing_release_types_key in list(existing_release_types.keys()):
            if season not in existing_release_types_key:
                del existing_release_types[existing_release_types_key]





        # TODO add support for "editions", copy regex from auto_upload script. If any custom edition is found and it does not appear in any of the releases on site, we can consider it OK to upload

    unique_release_types = set(existing_release_types.values())
    for release_type in unique_release_types:
        # console.print("{}:".format(release_type), style="bold magenta")
        num_of_existing_releases = 0
        for key, val in existing_release_types.items():
            if release_type == val:
                num_of_existing_releases += 1
        #         print("{}".format(key))
        # console.print("{}\n".format(num_of_existing_releases), style="bold red")

    # print("\n\n")
    # print(existing_release_types.keys())

    # If we get no matches when searching via IMDB ID that means this content hasn't been upload in any format, no possibility for dupes
    if len(existing_release_types.keys()) == 0:
        return "no_dupes"

    # print("test\n\n")


    def fuzzy_similarity(our_title, check_against_title):
        check_against_title_original = check_against_title
        # We will remove things like the title & year from the comparison stings since we know they will be exact matches anyways

        # replace DD+ with DDP from both our title and tracker results title to make the dupe check a bit more accurate since some sites like to use DD+ and others DDP but they refer to the same thing
        our_title = re.sub(r'dd\+', 'ddp', str(our_title).lower())
        check_against_title = re.sub(r'dd\+', 'ddp', str(check_against_title).lower())

        content_title = re.sub('[^0-9a-zA-Z]+', ' ', str(torrent_info["title"]).lower())
        # content_title = " ".join(content_title.split())

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

        # check_against_title = str(check_against_title).replace(torrent_info["resolution"], "").replace(check_against_title_year, "").replace(content_title, "")
        check_against_title = re.sub(r'[^A-Za-z0-9 ]+', ' ', str(check_against_title)).lower().replace(torrent_info["screen_size"], "").replace(check_against_title_year, "")
        check_against_title = " ".join(check_against_title.split())

        # print("Our Title:        {}".format(our_title.replace(content_title, '')))
        # print("Check Against:    {}".format(check_against_title.replace(content_title, '')))

        token_set_ratio = fuzz.token_set_ratio(our_title.replace(content_title, ''), check_against_title.replace(content_title, ''))
        logging.info(f"'{check_against_title_original}' was flagged with a {str(token_set_ratio)}% dupe probability")

        # Instead of wasting time trying to create a 'low, medium, high' risk system we just have the user enter in a percentage they are comfortable with
        # if a torrent titles vs local title similarity percentage exceeds a limit the user set we immediately quit trying to upload to that site
        # since what the user considers (via token_set_ratio percentage) to be a dupe exists
        if token_set_ratio >= int(os.getenv('acceptable_similarity_percentage')):
            # When we return this dict we pass it back into auto_upload.py to show the user the torrent on site that triggered the dupe fail & its percentage
            return {check_against_title_original: token_set_ratio}


        # 94% (BLU) =  (bluray dts hd ma 5 1 avc remux tdd)
        #              (bluray remux avc dts hd ma 5 1 pmp)

        # 94% (BHD) =  (bluray dts hd ma 5 1 avc remux tdd)
        #         (bluray dts hd ma 5 1 avc remux framestor)

    possible_dupes = Table(show_header=True, header_style="bold cyan")
    possible_dupes.add_column(f"Possible Dupes ({str(config['source']).upper()})", justify="center")


    for i in ['bluray_disc', 'bluray_remux', 'bluray_encode', 'webdl', 'webrip', 'dvd', 'hdtv']:
        if i in torrent_info["source_type"]:
            # console.print("Possible dupes:", style="bold magenta")
            for key, val in existing_release_types.items():
                if val == i and torrent_info["screen_size"] in key:
                    # if torrent_info["screen_size"] in key:
                    possible_dupes.add_row(f"{key}")

                    # If we get a match then run further checks
                    dupe_dict_return = fuzzy_similarity(our_title=torrent_info["torrent_title"], check_against_title=key)
                    if dupe_dict_return is not None:  # Not every loop will end up adding a "dupe" to this dict so we make sure its not empty first
                        logging.error(f"{str(list(dupe_dict_return.values())[0])}% is higher then the maximum similarity percentage ({os.getenv('acceptable_similarity_percentage')}%) allowed by the user ")
                        return dupe_dict_return
