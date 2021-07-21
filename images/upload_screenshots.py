import os
import sys
import base64
import asyncio
import logging
import pyimgbox
import requests
from ffmpy import FFmpeg
from datetime import datetime
from dotenv import load_dotenv
from rich.progress import track
from rich.console import Console

# For more control over rich terminal content, import and construct a Console object.
console = Console()


def get_ss_range(duration, num_of_screenshots):
    list_of_ss_timestamps = []
    # Now start a loop that will run for the num_of_screenshots & create evenly split timestamps at which to take screenshots
    first_time_stamp = int(duration) / int(int(num_of_screenshots) + 1)
    for num_screen in range(1, int(num_of_screenshots) + 1):
        millis = round(first_time_stamp) * num_screen
        list_of_ss_timestamps.append(str(datetime.strptime("%d:%d:%d" % (int((millis / (1000 * 60 * 60)) % 24), int((millis / (1000 * 60)) % 60), int((millis / 1000) % 60)), '%H:%M:%S').time()))
    # Return the list that contains timestamps at which we'll take screenshots next
    return list_of_ss_timestamps


def upload_screens(img_host, img_host_api, image_path, torrent_title):
    # ptpimg does all for us to upload multiple images at the same time but to simplify things & allow for simple "backup hosts"/upload failures we instead upload 1 image at a time
    #
    # Both imgbb & freeimage are based on Chevereto which the API has us upload 1 image at a time while imgbox uses something custom and we upload a list of images at the same time
    #
    # Annoyingly pyimgbox requires every upload be apart of a "gallery", This is fine if you're uploading a list of multiple images at the same time
    #  but because of the way we deal with "backup" image hosts/upload failures its not realistic to pass a list of all the images to imgbox at the same time.
    #  so instead we just upload 1 image at a time to imgbox (also creates 1 gallery per image)

    if img_host == 'ptpimg':
        try:
            import ptpimg_uploader
            ptp_img_upload = ptpimg_uploader.upload(api_key=os.getenv('ptpimg_api_key'), files_or_urls=[image_path], timeout=5)
            # Make sure the response we get from ptpimg is a list
            assert type(ptp_img_upload) == list
            # assuming it is, we can then get the img url, format it into bbcode & return it

            # Pretty sure ptpimg doesn't compress/host multiple 'versions' of the same image so we use the direct image link for both parts of the bbcode (url & img)
            return True, f'[url={ptp_img_upload[0]}][img=350x350]{ptp_img_upload[0]}[/img][/url]'

        except ImportError:
            logging.error(msg='cant upload to ptpimg without this pip package: https://pypi.org/project/ptpimg-uploader/')
            console.print(f"\nInstall required pip package: [bold]ptpimg_uploader[/bold] to enable ptpimg uploads\n", style='Red', highlight=False)
            return False
        except AssertionError:
            logging.error(msg='ptpimg uploaded an image but returned something unexpected (should be a list)')
            console.print(f"\nUnexpected response from ptpimg upload (should be a list). No image link found\n", style='Red', highlight=False)
            return False
        except Exception:
            logging.error(msg='ptpimg upload failed, double check the ptpimg API Key & try again.')
            console.print(f"\nptpimg upload failed. double check the [bold]ptpimg_api_key[/bold] in [bold]config.env[/bold]\n", style='Red', highlight=False)
            return False

    if img_host in ('imgbb', 'freeimage'):
        # Get the correct image host url/json key
        available_image_host_urls = {'imgbb': 'https://api.imgbb.com/1/upload', 'freeimage': 'https://freeimage.host/api/1/upload'}
        parent_key = 'data' if img_host == 'imgbb' else 'image'

        # Load the img_host_url, api key & img encoded in base64 into a dict called 'data' & post it
        image_host_url = available_image_host_urls[img_host]
        data = {'key': img_host_api, 'image': base64.b64encode(open(image_path, "rb").read())}
        try:
            img_upload_request = requests.post(url=image_host_url, data=data)
            if img_upload_request.ok:
                img_upload_response = img_upload_request.json()
                # When you upload an image you get a few links back, you get 'medium', 'thumbnail', 'url', 'url_viewer' and we only need max 2 so we set the order/list to try and get the ones we want
                possible_image_types = ['medium', 'thumb']
                try:
                    for img_type in possible_image_types:
                        if img_type in img_upload_response[parent_key]:
                            if 'delete_url' in img_upload_response:
                                logging.info(f'{img_host} delete url for {image_path}: {img_upload_response["delete_url"]}')
                            return True, f'[url={img_upload_response[parent_key]["url_viewer"]}][img=350x350]{img_upload_response[parent_key][img_type]["url"]}[/img][/url]'
                        else:
                            return True, f'[url={img_upload_response[parent_key]["url_viewer"]}][img=350x350]{img_upload_response[parent_key]["url"]}[/img][/url]'

                except KeyError as key_error:
                    logging.error(f'{img_host} json KeyError: {key_error}')
                    return False
            else:
                logging.error(f'{img_host} upload failed. JSON Response: {img_upload_request.json()}')
                console.print(f"{img_host} upload failed. Status code: [bold]{img_upload_request.status_code}[/bold]", style='red3', highlight=False)
                return False
        except requests.exceptions.RequestException:
            logging.error(f"Failed to upload {image_path} to {img_host}")
            console.print(f"upload to [bold]{img_host}[/bold] has failed!", style="Red")
            return False

    # Instead of coding our own solution we'll use the awesome project https://github.com/plotski/pyimgbox to upload to imgbox
    if img_host == "imgbox":
        async def imgbox_upload(filepaths):
            async with pyimgbox.Gallery(title=torrent_title, thumb_width=350) as gallery:
                async for submission in gallery.add(filepaths):
                    if not submission['success']:
                        logging.error(f"{submission['filename']}: {submission['error']}")
                        return False
                    else:
                        logging.info(f'imgbox edit url for {image_path}: {submission["edit_url"]}')
                        return True, f'[url={submission["web_url"]}][img=350x350]{submission["thumbnail_url"]}[/img][/url]'

        if os.path.getsize(image_path) >= 10485760:  # Bytes
            logging.error('Screenshot size is over imgbox limit of 10MB, Trying another host (if available)')
            return False

        if sys.version_info < (3, 7):
            logging.critical(f'Required Python version to use pyimgbox is: 3.7+ You currently are on {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
            return False

        imgbox_asyncio_upload = asyncio.run(imgbox_upload(filepaths=[image_path]))
        if imgbox_asyncio_upload:
            return True, imgbox_asyncio_upload[1]

        # # Python 3.7+ version
        # asyncio.run(imgbox_upload(filepaths=[image_path]))  # call the function that uploads images to imgbox
        #
        # # Python <= 3.6 friendly alternative
        # loop = asyncio.get_event_loop()
        # loop.run_until_complete(imgbox_upload(list_of_images))


def take_upload_screens(duration, upload_media_import, torrent_title_import, base_path, discord_url):
    logging.basicConfig(filename=f'{base_path}/upload_script.log', level=logging.INFO, format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')

    # Open the config file
    load_dotenv(f"{base_path}config.env")
    num_of_screenshots = os.getenv("num_of_screenshots")

    logging.info(f"Using {upload_media_import} to generate screenshots")
    console.print(f'\nTaking [chartreuse1]{str(num_of_screenshots)}[/chartreuse1] screenshots', style="Bold Blue")

    enabled_img_hosts_list = []
    # ---------------------- check if 'num_of_screenshots=0' or not set ---------------------- #
    if num_of_screenshots == "0" or not bool(num_of_screenshots):
        logging.error(f'num_of_screenshots is {"not set" if not bool(num_of_screenshots) else f"set to {num_of_screenshots}"}, continuing without screenshots.')
        console.print(f'\nnum_of_screenshots is {"not set" if not bool(num_of_screenshots) else f"set to {num_of_screenshots}"}\n', style='bold red')
    else:
        # ---------------------- verify at least 1 image-host is set/enabled ---------------------- #
        enabled_img_host_num_loop = 0
        while bool(os.getenv(f'img_host_{enabled_img_host_num_loop + 1}')):
            enabled_img_hosts_list.append(os.getenv(f'img_host_{enabled_img_host_num_loop + 1}'))
            enabled_img_host_num_loop += 1
        # now check if the loop ^^ found any enabled image hosts
        if not bool(enabled_img_host_num_loop):
            logging.error('All image-hosts are disabled/not set (try setting "img_host_1=imgbox" in config.env)')
            console.print(f'\nNo image-hosts are enabled, maybe try setting [dodger_blue2][bold]img_host_1=imgbox[/bold][/dodger_blue2] in [dodger_blue2]config.env[/dodger_blue2]\n', style='bold red')

        # -------------------- verify an API key is set for 'enabled_img_hosts' -------------------- #
        for img_host_api_check in enabled_img_hosts_list:
            # Check if an API key is set for the image host
            if not bool(os.getenv(f'{img_host_api_check}_api_key')):
                logging.error(f"Can't upload to {img_host_api_check} without an API key")
                console.print(f"\nCan't upload to [bold]{img_host_api_check}[/bold] without an API key\n", style='red3', highlight=False)
                # If the api key is missing then remove the img_host from the 'enabled_img_hosts_list' list
                enabled_img_hosts_list.remove(img_host_api_check)
        # log the leftover enabled image hosts
        logging.info(f"Image host order we will try & upload to: {enabled_img_hosts_list}")

    # -------------------------- Check if any img_hosts are still in the 'enabled_img_hosts_list' list -------------------------- #
    # if no image_hosts are left then we show the user an error that we will continue the upload with screenshots & return back to auto_upload.py
    if not bool(enabled_img_hosts_list):
        with open(f"{base_path}/temp_upload/bbcode_images.txt", "w") as no_images:
            no_images.write("[b][color=#FF0000][size=22]None[/size][/color][/b]")
            no_images.close()
        logging.error(f"Continuing upload without screenshots")
        console.print(f'Continuing without screenshots\n', style='chartreuse1')
        return

    # ##### Now that we've verified that at least 1 imghost is available & has an api key etc we can try & upload the screenshots ##### #

    # Figure out where exactly to take screenshots by evenly dividing up the length of the video
    ss_timestamps_list = []
    screenshots_to_upload_list = []
    for ss_timestamp in track(get_ss_range(duration=duration, num_of_screenshots=num_of_screenshots), description="Taking screenshots..."):
        # Save the ss_ts to the 'ss_timestamps_list' list
        ss_timestamps_list.append(ss_timestamp)
        screenshots_to_upload_list.append(f'{base_path}/images/screenshots/{torrent_title_import} - ({ss_timestamp.replace(":", ".")}).png')
        # Now with each of those timestamps we can take a screenshot and update the progress bar
        FFmpeg(inputs={upload_media_import: f'-loglevel panic -ss {ss_timestamp}'}, outputs={f'{base_path}/images/screenshots/{torrent_title_import} - ({ss_timestamp.replace(":", ".")}).png': '-frames:v 1 -q:v 10'}).run()
    console.print('Finished taking screenshots!\n', style='sea_green3')
    # log the list of screenshot timestamps
    logging.info(f'Taking screenshots at the following timestamps {ss_timestamps_list}')

    # ---------------------------------------------------------------------------------------- #

    console.print(f"Image host order: [chartreuse1]{' [bold blue]:arrow_right:[/bold blue] '.join(enabled_img_hosts_list)}[/chartreuse1]", style="Bold Blue")
    successfully_uploaded_image_count = 0
    for ss_to_upload in track(screenshots_to_upload_list, description="Uploading screenshots..."):
        # This is how we fall back to a second host if the first fails
        for img_host in enabled_img_hosts_list:

            # call the function that uploads the screenshot
            upload_image = upload_screens(img_host=img_host, img_host_api=os.getenv(f'{img_host}_api_key'), image_path=ss_to_upload, torrent_title=torrent_title_import)

            # If the upload function returns True, we add it to bbcode_images.txt
            if upload_image:
                with open(f"{base_path}/temp_upload/bbcode_images.txt", "a") as append_bbcode_txt:
                    append_bbcode_txt.write(f"{upload_image[1]} ")
                successfully_uploaded_image_count += 1
                # Since the image uploaded successfully, we need to break now so we don't reupload to the backup image host (if exists)
                break

    # Depending on the image upload outcome we print a success or fail message showing the user what & how many images failed/succeeded
    if len(screenshots_to_upload_list) == successfully_uploaded_image_count:
        console.print(f'Uploaded {successfully_uploaded_image_count}/{len(screenshots_to_upload_list)} screenshots', style='sea_green3', highlight=False)
        logging.info(f'Successfully uploaded {successfully_uploaded_image_count}/{len(screenshots_to_upload_list)} screenshots')
    else:
        console.print(f'{len(screenshots_to_upload_list) - successfully_uploaded_image_count}/{len(screenshots_to_upload_list)} screenshots failed to upload', style='bold red', highlight=False)
        logging.error(f'{len(screenshots_to_upload_list) - successfully_uploaded_image_count}/{len(screenshots_to_upload_list)} screenshots failed to upload')
