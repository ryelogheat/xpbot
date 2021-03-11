# UNIT3D_auto_upload
Automatically parse, rename, and upload torrents to trackers using the UNIT3D codebase
### Supported sites:
* BHD - [**Beyond-HD**](https://beyond-hd.me)
* BLU - [**Blutopia**](https://blutopia.xyz)
* ACM - [**AsianCinema**](https://asiancinema.me/)


<!-- Basic setup -->
# Basic setup:
1. Clone / download this repository
2. Install necessary packages ```pip3 install -r requirements.txt```
3. Rename `config.env.sample` to `config.env`
4. Fill out the required values in `config.env`
5. Ensure you have [mediainfo](https://mediaarea.net/en/MediaInfo/Download/Ubuntu) & [ffmpeg](https://ffmpeg.org/download.html) installed on your system
6. Run the script using [Python3](https://www.python.org/downloads/)
   
   <br /> 
   
**Things to note:**
1. We use TMDB API for all things media related (Title, Year, External IDs, etc)
2. If you provide the IMDB ID via ```-imdb```, you must include the 'tt' that precedes the numerical ID
3. If you're trying to pass in a file as an arg, you may find autocomplete isn't working. Do this to fix it
    * (What I mean by autocomplete is when you double hit *Tab*, and the filename/folder gets automatically filled in)
    * ```chmod u+x auto_upload.py```
    * run script using ```./auto_upload.py -t etc -p /path/to/file/autocompletes.now```
4. A folder called ``temp_upload`` will be created which will store the files:
    * ```description.txt``` ```mediainfo.txt``` ```*.torrent```
5. **Raw Blu-rays are not currently supported**
    * BDInfo is required for Blu-ray discs which requires Docker etc
    * Support will be added soon
    


<!-- config.env -->
# Args / user input
**Do not include *commas* or *double quotes* with your args**
* ```-t``` | *Trackers* | Required
   * This is how you specify which site you upload to
   * e.g. ```python3 auto_upload.py -t BHD BLU```
<br></br> 
* ```-p``` | *Path* | Optional
  * Use this to specify which file or folder you want to upload
   * e.g. ```python3 auto_upload.py -t ABC -p /home/user/Videos/file.mkv```
<br></br> 
* ```-tmdb``` | [*TMDB*](https://www.themoviedb.org/) | Optional
   * Manually provide the **TMDB** instead of relying on script API
   * It's recommended to use this arg if ```auto_mode=true``` but that's not a requirement
   * e.g. ```python3 auto_upload.py -t ABC -tmdb 278```
<br></br> 
* ```-imdb``` | [*IMDB*](https://www.imdb.com/) | Optional
   * You can use the **IMDB ID** to get the **TMDB ID** through the **TMDB API** ```/find/{external_id}``` endpoint
   * Do not forget to include the **tt** that proceeds the numerical part
   * e.g. ```python3 auto_upload.py -t ABC -imdb tt0111161```
<br></br> 
* ```-anon``` | *Anonymous* | Optional   
   * No input needed after the arg, just pass in ```-anon``` and the upload will be uploaded anonymously
   * ```python3 auto_upload.py -t ABC -anon```
<br></br> 
* ```-e``` | *Edition* | Optional
   * This is typically auto extracted from the filename but in the rare case when the encoder doesn't include that info in the filename
   * e.g. ```python3 auto_upload.py -t ABC -e Criterion Collection -anon```
<br></br> 
* ```-d``` | *Description* | Optional
   * **This only works if ```auto_mode=False```** 
   * No input needed after the arg  
   * This will simply pause the script before uploading and give you a chance to open description.txt to edit it before uploading
   * e.g. ```python3 auto_upload.py -t ABC -e```
   


<!-- config.env -->
# config.env
1. **API keys**
    * You have to provide an API key for each site you plan on uploading to
    * **TMDB API Key is required**, TMDB is integral to this script
<br />  
<br />
      
2. **Image Hosts**
    * These are used for screenshots, currently 3 are supported
    * Set the order that we follow for image uploads (if a host fails or is unreachable we can fallback to the next host specified)
    1. [imgbb](https://api.imgbb.com/) - **API Key required**
    2. [imgyukle](https://imgyukle.com/page/resim-yukleme-api) - **API Key required**)
    3. [freeimage](https://freeimage.host/page/api) - **API Key required**
    4. [imgbox](https://imgbox.com/) - **No API Key needed** - (thanks to [pyimgbox](https://github.com/plotski/pyimgbox))
    * For example your order might look something like this (imgbox disabled in this example)
      ```
      img_host_1=freeimage
      img_host_2=imgbb
      img_host_3=imgyukle
      img_host_3=
      ```
<br />
<br />

3. **Number of screenshots**
    * Pretty self explanatory, set this to however many screenshots you want taken & uploaded
        * ```num_of_screenshots=6```  
   <br /> 
   <br />     
          
4. **Selecting media for uploading**
    * You can either set a **upload_dir_path** or use the **-path** argument
    1. **upload_dir_path:** set the full path to a folder which contains a single file or folder (e.g. season pack), and it will be uploaded automatically upon script execution
        * ```upload_dir_path=/home/user/videos/upload_me/```
    2. **-path argument:** If you leave **upload_dir_path** blank then you have to supply the **-path** argument followed by the path to the media you want to upload (video file or folder)
        * ```python3 auto_upload.py -t ABC -path /home/user/videos/upload_me/test.mkv```
   <br />
   <br />
   <br />
5. **Post Processing**
    * After a successful upload we can move the .torrent file & actual media file/folder to a location you specify
    * **Leave blank to disable any movement**
    1. **dot_torrent_move_location:** specify the full path to where you want the .torrent file moved after uploading
        * this could be used with an AutoWatch directory to automatically start seeding
    2. **media_move_location:** path to location where you want media file/folder moved to after uploading
        * again this could be used with AutoTools to automatically start seeding after uploading
     
    **Torrent client & watch directories:**
    1. **Transmission**: open **settings.json** & append the following lines 
       ```
       "watch-dir": "/path/to/folder/to/watch/",
       "watch-dir-enabled": true
       ```
    2. **rtorrent/ruTorrent**: open **rtorrent.rc** and add the following line (might already exist)
       ```
       schedule = watch_directory,5,5,"load.start=/path/to/folder/to/watch/*.torrent,d.delete_tied="
       ```
    3. **Deluge**: TODO
       ```
       fill me out later
       ```
   <br /> 
   <br /> 
6. **Dupe check**
    * *Use at your own risk*
    * Set ```check_dupes=``` to ```true``` if you want to use this   
      *  Using fuzzywuzzy we compare a stripped down version of the title we generate to the results we get from the site search API
      *  We remove the title, year, resolution before comparing similarity (we filter out results that don't match the resolution of the local file)
    * Set a maximum similarity percentage (don't include percentage symbol) at ```acceptable_similarity_percentage=```
      * ```acceptable_similarity_percentage``` only works if ```check_dupes=true```
      * **100% dupe matches** will always cancel the upload no matter what ```acceptable_similarity_percentage``` is set to
      * (Higher = Riskier)
     
    <details>
      <summary>examples of filename & percent differences</summary>
  
        Ex Machina 2015 1080p UHD Bluray DTS 5.1 HDR x265-D-Z0N3
        Ex Machina 2014 1080p UHD BluRay DTS HDR x265 D-Z0N3
        100%
        -----
        Atomic Blonde 2017 1080p UHD Bluray DD+ 7.1 HDR x265-NCmt
        Atomic Blonde 2017 1080p UHD BluRay DD+7.1 HDR x265 - HQMUX
        84%
        -----
        Get Him to the Greek 2010 1080p Bluray DTS-HD MA 5.1 AVC Remux-EPSiLON
        Get Him to the Greek 2010 Unrated BluRay 1080p DTS-HD MA 5.1 AVC REMUX-FraMeSToR
        88%
        -----
        Knives Out 2019 1080p UHD Bluray DD+ 7.1 HDR x265-D-Z0N3
        Knives Out 2019 REPACK 1080p UHD BluRay DDP 7.1 HDR x265-SA89
        89%
    </details>
   <br /> 
   <br /> 
   
7. **Auto Mode (silent mode)**
   * Set this to ```true``` to run without any human interaction
     * This will parse the filename & auto select the *right* TMDB ID
     * If minor issues are found (e.g. the filename year is off by 1) it will deal with it and upload anyways 
     * Note that you are responsible for following **all** tracker rules and should manually double check all automatic uploads 
   <br /> 
   * Set this to ```false``` to have a more interactive & hands on experience **(recommended)**
      * If issues are found (e.g. source can't be auto-detected) you'll be prompted for user input that we can use
      * You'll be shown status updates continually & will have a chance to review/approve the final upload data
      * You'll be shown the exact POST data/file payload before its uploaded for your review/approval 
   
   <br />
   <br />

8. **auto_mode_force**
    * This works in tandem with **auto_mode**, if ```auto_mode=false``` then this won't work
    * If your torrent has minor issues like we can't auto-detect the *audio_channels*, this will force the upload without that info
        * e.g. If **pymediainfo** / **ffprobe** / **regex** can not detect the audio_codec this will simply omit the *audio_codec* from the torrent title and finish the upload
    * **If missing, these can be skipped:**
        * `audio_codec` `audio_channels` `video_codec (maybe)`

   <br />
   <br />


9. **Live / Draft**
   * This only applies to **BHD** since they are the only supported site that has a **Drafts** page
   * It's recommended to set this to ```False``` for your first few uploads, so you can verify everything is to your liking



<!-- Usage Examples -->
# Usage Examples
1. Upload to **Beyond-HD** & **Blutopia** with movie file in **/home/user/Videos/movie.title.year.bluray.1080p.etc.mkv**
    * ```python3 auto_upload.py -t BHD BLU -path /home/user/Videos/movie.title.year.bluray.1080p.etc.mkv```
2. Upload movie **anonymously** to **AsianCinema** with manually specified **TMDB** & **IMDB** IDs
    * ```python3 auto_upload.py -t acm -p /home/user/Videos/movie.title.year.bluray.1080p.etc.mkv -imdb tt6751668 -tmdb 496243 -anon```


<!-- ROADMAP -->
# Planned features
   1. Add support for raw Blu-ray Disc uploads
   2. Integrate ***trumping*** & ***co-existing*** rules
      * **Trumping**: An *Extended, Dolby Vision Remux* should trump an *Extended, HDR10 Remux* **(assuming DV remux has HDR10 fallback)**
      * **Co-Existing**: Both *Extended* & *Theatrical* Remuxs can co-exist 
   3. Add support for a "queue" that can upload all files / folders in specific location 
   4. *fast resume* for rtorrent





