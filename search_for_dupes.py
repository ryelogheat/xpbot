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
    # to handle torrents with HDR and DV, we keep a separate dictionary to keep tracker of hdr. non-hdr and dv releases
    # the reason to go for a separate map is because in `existing_release_types` the keys are torrent titles and that is not possible for hdr based filtering
    # note that for hdr filtering we are not bothered about the different formats (PQ10, HDR, HLG etc), Since its rare to see a show release in multiple formats.
    # although not impossible. (moonknight had PQ10 and HDR versions)
    hdr_format_types = { 'hdr': [], 'dv_hdr': [], 'dv': [], 'normal': []}
    
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
        
        # HDR
        if any(x in torrent_title_split for x in ['hdr', 'hdr10', 'hdr10+', 'hdr10plus', 'pq10', 'hlg', 'wcg']):
            hdr_format_types['hdr'].append(torrent_title)
        
        # DV
        if any(x in torrent_title_split for x in ['dv', 'dovi', 'dolbyvision']):
            hdr_format_types['dv'].append(torrent_title)
        
        # Non-HDR
        if all(x not in torrent_title_split for x in ['dv', 'dovi', 'dolbyvision', 'hdr', 'hdr10', 'hdr10+', 'hdr10plus', 'pq10', 'hlg', 'wcg']):
            hdr_format_types['normal'].append(torrent_title)
        
        # DV HDR
        if any(x in torrent_title_split for x in ['dv', 'dovi', 'dolbyvision']) and any(x in torrent_title_split for x in ['hdr', 'hdr10', 'hdr10+', 'hdr10plus', 'pq10', 'hlg', 'wcg']):
            hdr_format_types['dv_hdr'].append(torrent_title)

    logging.info(f'[DupeCheck] Existing release types based on hdr formats identified from tracker {search_site} are {hdr_format_types}')

    # This just updates a dict with the number of a particular "type" of release exists on site (e.g. "2 bluray_encodes" or "1 bluray_remux" etc)
    for onsite_quality_type in existing_release_types.values():
        existing_releases_count[onsite_quality_type] += 1
    for hdr_format in hdr_format_types.keys():
        existing_releases_count[hdr_format] = len(hdr_format_types[hdr_format])
    logging.info(msg=f'Results from initial dupe query (all resolution): {existing_releases_count}')



    # If we get no matches when searching via IMDB ID that means this content hasn't been upload in any format, no possibility for dupes
    if len(existing_release_types.keys()) == 0:
        logging.info(msg='Dupe query did not return any releases that we could parse, assuming no dupes exist.')
        return False
    
    our_format = "normal"
    if "dv" in torrent_info:
        our_format = "dv_hdr" if "hdr" in torrent_info else "dv"
    elif "hdr" in torrent_info:
        our_format = "hdr"
    
    logging.info(f'[DupeCheck] Eliminating releases based on HDR Format. We are tring to upload: "{our_format}". All other formats will be ignored.')
    for item in hdr_format_types.keys():
        if item != our_format:
            for their_title in hdr_format_types[item]:
                if their_title in existing_release_types and their_title not in hdr_format_types[our_format]:
                    their_title_type = existing_release_types[their_title]
                    existing_releases_count[their_title_type] -= 1
                    existing_release_types.pop(their_title)
            existing_releases_count[item] = 0
            hdr_format_types[item] = []
    logging.info(msg=f'[DupeCheck] After applying "HDR Format" filter: {existing_releases_count}')

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



    # Movies (mostly blurays) are usually a bit more flexible with dupe/trump rules due to editions, regions, etc
    # TV Shows (mostly web) are usually only allowed 1 "version" onsite & we also need to consider individual episode uploads when a season pack exists etc
    # for those reasons ^^ we place this dict here that we will use to generate the Table we show the user of possible dupes
    possible_dupe_with_percentage_dict = {}  # By keeping it out of the fuzzy_similarity() func/loop we are able to directly insert/modify data into it when dealing with tv show dupes/trumps below

    # If we are uploading a tv show we should only add the correct season to the existing_release_types dict
    if "s00e00" in torrent_info:
        # First check if what the user is uploading is a full season or not
        is_full_season = bool(len(torrent_info["s00e00"]) == 3)

        # We just want the season of whatever we are uploading so we can filter the results later (Most API requests include all the seasons/episodes of a tv show in the response, we don't need all of them)
        season_num = torrent_info["s00e00"] if is_full_season else str(torrent_info["s00e00"])[:-3]
        episode_num = str(torrent_info["s00e00"])[3:]
        logging.info(msg=f'Filtering out results that are not from the same season being uploaded ({season_num})')

        # Loop through the results & discard everything that is not from the correct season
        number_of_discarded_seasons = 0
        for existing_release_types_key in list(existing_release_types.keys()):

            if season_num not in existing_release_types_key:  # filter our wrong seasons
                existing_release_types.pop(existing_release_types_key)
                number_of_discarded_seasons += 1
                continue


            # at this point we've filtered out all the different resolutions/types/seasons
            #  so now we check each remaining title to see if its a season pack or individual episode
            extracted_season_episode_from_title = list(filter(lambda x: x.startswith(season_num), existing_release_types_key.split(" ")))[0]
            if len(extracted_season_episode_from_title) == 3:
                logging.info(msg=f'Found a season pack for {season_num} on {search_site}')
                # TODO maybe mark the season pack as a 100% dupe or consider expanding dupe Table to allow for error messages to inform the user


                # If a full season pack is onsite then in almost all cases individual episodes from that season are not allowed to be uploaded anymore
                #   check to see if that's ^^ happening, if it is then we will log it and if 'auto_mode' is enabled we also cancel the upload
                #   if 'auto_mode=false' then we prompt the user & let them decide
                if not is_full_season:


                    if bool(util.strtobool(os.getenv('auto_mode'))):
                        # possible_dupe_with_percentage_dict[existing_release_types_key] = 100
                        logging.critical(msg=f'Canceling upload to {search_site} because uploading a full season pack is already available: {existing_release_types_key}')
                        return True


                    # if this is an interactive upload then we can prompt the user & let them choose if they want to cancel or continue the upload
                    logging.error(msg="Almost all trackers don't allow individual episodes to be uploaded after season pack is released")
                    console.print(f"\n[bold red on white] :warning: Need user input! :warning: [/bold red on white]")
                    console.print(f"You're trying to upload an [bold red]Individual Episode[/bold red] [bold]({torrent_info['title']} {torrent_info['s00e00']})[/bold] to {search_site}",  highlight=False)
                    console.print(f"A [bold red]Season Pack[/bold red] is already available: {existing_release_types_key}", highlight=False)
                    console.print("Most sites [bold red]don't allow[/bold red] individual episode uploads when the season pack is available")
                    console.print('---------------------------------------------------------')
                    if not bool(Confirm.ask("Ignore and continue upload?", default=False)):
                        return True


            # now we just need to make sure the episode we're trying to upload is not already on site
            number_of_discarded_episodes = 0
            if extracted_season_episode_from_title != torrent_info['s00e00']:
                number_of_discarded_episodes += 1
                existing_release_types.pop(existing_release_types_key)

            logging.info(msg=f'Filtered out: {number_of_discarded_episodes} results for having different episode numbers (looking for {episode_num})')


        logging.info(msg=f'Filtered out: {number_of_discarded_seasons} results for not being the right season ({season_num})')


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
        console.print(f"\n\n[bold red on white] :warning: Detected possible dupe! :warning: [/bold red on white]")
        console.print(possible_dupes_table)
        return True if bool(util.strtobool(os.getenv('auto_mode'))) else not bool(Confirm.ask("\nContinue upload even with possible dupe?"))
    else:
        console.print(f":heavy_check_mark: Yay! No dupes found on [bold]{str(config['source']).upper()}[/bold], continuing the upload process now\n")
        return False
