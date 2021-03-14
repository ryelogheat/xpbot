import base64
import glob
import os
import logging
from datetime import datetime
import pyimgbox
import requests
from dotenv import load_dotenv
from ffmpy import FFmpeg
import asyncio
from rich.console import Console
from rich.progress import track
import time

# For more control over rich terminal content, import and construct a Console object.
console = Console()




def get_ss_range(duration, num_of_screenshots):
    first_time_stamp = int(duration) / int(int(num_of_screenshots) + 1)
    list_of_ss_timestamps = []
    for num_screen in range(1, int(num_of_screenshots) + 1):
        multiply_me_screenshots = round(first_time_stamp) * num_screen
        millis = int(str(multiply_me_screenshots).split(".", 1)[0])
        ss_timestamp_n = str(datetime.strptime("%d:%d:%d" % (int((millis / (1000 * 60 * 60)) % 24),
                                                             int((millis / (1000 * 60)) % 60),
                                                             int((millis / 1000) % 60)),
                                               '%H:%M:%S').time())
        list_of_ss_timestamps.append(ss_timestamp_n)

    return list_of_ss_timestamps


def generate_screenshots(upload_media, final_title, ss_timestamp, base_path):
    ff = FFmpeg(inputs={upload_media: '-loglevel panic -ss ' + ss_timestamp},
                outputs={r'{}{} - ({}).png'.format(base_path + "/images/screenshots/", final_title, ss_timestamp.replace(":", ".")): '-frames:v 1 -q:v 10'})
    ff.run()


def upload_screens(img_host, api_key, working_folder, torrent_title):
    console.print(f"Uploading to [chartreuse1]{img_host}[/chartreuse1]", style="Bold Blue")

    thumbs_links_dict = {}  # we keep track of the thumbnail png link & its corresponding web page link here

    # Both imgbb & freeimage are based on Chevereto which the API has us upload 1 image at a time while imgbox uses something custom and we upload a list of images at the same time
    # So if we try and upload to imgbox for every 1 image we end up uploading num_of_screenshots^2 which results in a ton of dupes & temp ban

    if img_host in ('imgbb', 'freeimage', 'imgyukle'):
        for img in track(glob.glob("{}*.png".format(working_folder + "/images/screenshots/")), description="Uploading..."):

            data = {
                'key': api_key,
                'image': base64.b64encode(open(img, "rb").read())  # skipcq: PTC-W0010
            }

            if img_host == "imgbb":
                url = "https://api.imgbb.com/1/upload"
                try:
                    response_test = requests.post(url, data=data)
                    if response_test.ok:
                        response = response_test.json()
                    else:
                        break
                except requests.exceptions.RequestException:
                    logging.error("Failed to upload {file_in_question} to {host_in_question}".format(file_in_question=img, host_in_question=img_host))
                    console.print(f"upload to [bold]{img_host}[/bold] has failed!", style="Red")
                    return "failed"
                # Save the thumb and full page links into a dict
                thumbs_links_dict[response["data"]["medium"]["url"]] = response['data']['url_viewer']

            if img_host == "freeimage":
                url = "https://freeimage.host/api/1/upload"
                try:
                    response_test = requests.post(url, data=data)
                    if response_test.ok:
                        response = response_test.json()
                    else:
                        break
                except requests.exceptions.RequestException:
                    logging.error("Failed to upload {file_in_question} to {host_in_question}".format(file_in_question=img, host_in_question=img_host))
                    console.print(f"upload to [bold]{img_host}[/bold] has failed!", style="Red")
                    return "failed"
                thumbs_links_dict[response['image']['medium']['url']] = response['image']['url_viewer']

            if img_host == "imgyukle":
                # We just replace the dict key "image" to "source" which is what imgyukle requires
                data["source"] = data.pop("image")

                url = "https://imgyukle.com/api/1/upload"
                try:
                    response_test = requests.post(url, data=data)
                    if response_test.ok:
                        response = response_test.json()
                    else:
                        break
                except requests.exceptions.RequestException:
                    logging.error("Failed to upload {file_in_question} to {host_in_question}".format(file_in_question=img, host_in_question=img_host))
                    console.print(f"upload to [bold]{img_host}[/bold] has failed!", style="Red")
                    return "failed"
                thumbs_links_dict[response['image']['medium']['url']] = response['image']['url_viewer']


    # Instead of coding our own solution we'll use the awesome project https://github.com/plotski/pyimgbox to upload to imgbox
    if img_host == "imgbox":
        async def imgbox_upload(list_of_filepath):
            async with pyimgbox.Gallery(title=torrent_title, thumb_width=350) as gallery:
                async for submission in gallery.add(list_of_filepath):
                    if not submission['success']:
                        logging.error(f"{submission['filename']}: {submission['error']}")
                    else:
                        thumbs_links_dict[submission["thumbnail_url"]] = submission["web_url"]
                        if submission["edit_url"] not in edit_url:
                            edit_url.append(submission["edit_url"])

        edit_url = []  # We save the edit url to logfile so we can delete images if needed later
        list_of_images = []  # here is a list of all images we are uploading, we don't need to base64 encode them like we do with Chevereto sites
        for file in os.listdir(working_folder + "/images/screenshots/"):
            list_of_images.append(working_folder + "/images/screenshots/" + file)  # append to dict
        asyncio.run(imgbox_upload(list_of_images))  # call the function that uploads images to imgbox
        logging.info(f"imgbox edit_url: {edit_url[0]}")  # log the edit url

    # return the dict so we can verify the images successfully uploaded and if so then format the links into bbcode
    return thumbs_links_dict




def take_upload_screens(duration, upload_media_import, torrent_title_import, base_path, discord_url):
    logging.basicConfig(filename=base_path + 'upload_script.log',
                        level=logging.INFO,
                        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')

    # Open the config

    load_dotenv(f"{base_path}config.env")
    num_of_screenshots = os.getenv("num_of_screenshots")

    console.print(f'\n\n[bold]Taking [chartreuse1]{str(num_of_screenshots)}[/chartreuse1] screenshots[/bold]', style="Bold Blue")
    # Update discord channel
    if discord_url:
        time.sleep(.5)
        requests.request("POST", discord_url, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=f'content='f'Number of Screenshots: **{num_of_screenshots}**')

    logging.info("Using {} to generate screenshots".format(upload_media_import))
    # Verify that num_of_screenshots is not set to 0
    if num_of_screenshots == "0":
        with open(base_path + "/temp_upload/bbcode_images.txt", "w") as no_images:
            no_images.write("[b][color=#FF0000][size=22]N/A[/size][/color][/b]")
            no_images.close()
        logging.error('num_of_screenshots is set to 0, continuing without screenshots')
        return "num_of_screenshots is set to 0, continuing without screenshots"

    # Verify that at least 1 image host is enabled so we don't waste time taking unneeded screenshots
    upload_to_host_dict = {}
    for host in range(1, 5):  # current number of image hosts available (4)
        if len(os.getenv('img_host_{}'.format(host))) != 0:
            if len(os.getenv('{host_site}_api_key'.format(host_site=os.getenv('img_host_{}'.format(host))))) == 0:
                console.print(f"Can't upload to '{os.getenv('img_host_{}'.format(host))}' without an API key", style='Red', highlight=False)
                logging.error("Can't upload to '{}' without an API key".format(os.getenv('img_host_{}'.format(host))))
            else:
                # Save the site & api key to upload_to_host_dict
                upload_to_host_dict[os.getenv('img_host_{}'.format(host))] = os.getenv('{host_site}_api_key'.format(host_site=os.getenv('img_host_{}'.format(host))))

    if len(upload_to_host_dict) == 0:
        with open(base_path + "/temp_upload/bbcode_images.txt", "w") as no_images:
            no_images.write("[b][color=#FF0000][size=22]N/A[/size][/color][/b]")
            no_images.close()

        logging.info("All image hosts are disabled by the user so we'll upload the torrent without screenshots")
        return "All image hosts are disabled by the user so we'll upload the torrent without screenshots"

    # We only generate screenshots if a valid image host is enabled/available
    ss_number_range = 0
    # first figure out where exactly to take screenshots by evenly dividing up the length of the video
    for timestamp in track(get_ss_range(duration=duration, num_of_screenshots=num_of_screenshots), description="Taking screenshots.."):
        # Now with each of those timestamps we can take a screenshot and update the progress bar
        generate_screenshots(upload_media=upload_media_import, final_title=torrent_title_import, ss_timestamp=timestamp, base_path=base_path)
        ss_number_range += 1
        logging.info("Taking a screenshot at {}".format(timestamp))
    print("\n")


    # As to not keep opening and closing bbcode_images.txt we instead open it now, put in the header and then write in each images bbcode then finally close after the loop
    with open(base_path + "/temp_upload/bbcode_images.txt", "w") as write_bbcode_description_txt:

        # Now we start the actual upload process
        for host_site, host_api in upload_to_host_dict.items():
            # Call the function that actually uploads the images
            upload_status = upload_screens(img_host=host_site, api_key=host_api, working_folder=base_path, torrent_title=torrent_title_import)
            # Check "thumbs_links_dict" to verify images have uploaded and we have all the links necessary to format BBCODE

            # if upload_status is equal to "failed" then we simply skip everything below and instead move on to the next host until none are available
            if upload_status != "failed":

                if int(len(upload_status.items())) == int(num_of_screenshots):
                    logging.info("All {num_of_imgs} images have been upload to {host}".format(num_of_imgs=num_of_screenshots, host=host_site))
                    # This means all the screenshots have been uploaded and we can move on
                    for thumbnail_png, web_url in upload_status.items():
                        write_bbcode_description_txt.write("[url={web_url}][img=350x350]{img_url}[/img][/url]".format(web_url=web_url, img_url=thumbnail_png) + " ")

                        # If 50% or more of the screenshots specified get uploaded we can move on (Modify the threshold below to percentage that works for you)
                elif int(len(upload_status.items())) >= int(int(num_of_screenshots) / 2):
                    for thumbnail_png, web_url in upload_status.items():
                        write_bbcode_description_txt.write("[url={web_url}][img=350x350]{img_url}[/img][/url]".format(web_url=web_url, img_url=thumbnail_png) + " ")

                        # All images BBCODE has been written in so now we add the closing tags and quit this script since everything is done
                logging.info("We've uploaded {num_of_uploaded_imgs} to {image_host}".format(num_of_uploaded_imgs=len(upload_status.items()), image_host=host_site))
                write_bbcode_description_txt.close()
                # Update discord channel
                if discord_url:
                    time.sleep(.5)
                    requests.request("POST", discord_url, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=f'content='f'Uploaded all images to: **{host_site}**')

                return "All images uploaded successfully"

            print("Upload to {first_choice} has failed! Going to try the backup now".format(first_choice=host_site))
            logging.error("Upload to {first_choice} has failed".format(first_choice=host_site))

        # If we haven't quit yet then that means we tried all hosts and none of them worked so now we move on with what we have
        logging.error("We were unable to upload to any of the enabled image hosts, so we are going to finish the torrent upload without images")
        write_bbcode_description_txt.write("\n[/center]")
        write_bbcode_description_txt.close()
        # Update discord channel
        if discord_url:
            requests.request("POST", discord_url, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=f'content='f'Image upload failed, continuing without them')
        return "We were unable to upload to any of the enabled image hosts, so we are going to finish the torrent upload without images"
