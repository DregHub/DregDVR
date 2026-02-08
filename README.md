# DregDVR

An automatic YouTube channel archiver & YouTube channel cloner. 

'Am i 4k wecording? Yes im 4k wecording!'

# WOT IT DO ?

Automatically downloads all their YouTube....

- Livestreams

- Livestream Comments (even hidden or removed ones) to a .txt file

- Subtitles (for both live and posted videos\shorts

- Videos

- Shorts

- Community Posts
  
  

**Automatically uploads Their....**

- Livestreams

- Videos

- Shorts

**To....**

- Internet Archive > which is practically unbannable

- Youtube > which will show up in google search results
  
  

All information is pulled from \_Meta\Default.xml

Using fuck all resources with no video transcoding . Can run on a potato

# SO MANY FOLDERS, WHAT FOR ?

| Folder Name                    | Usage                                                                                                                                                 |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| _Auth                          | Auth files for automatic youtube uploads                                                                                                              |
| _Captions                      | Automatic subtitles in here enable easy clipping                                                                                                      |
| _Config                        | Config files for the dvr                                                                                                                              |
| _Logs                          | Logs go in here and optionally can be archived to subfolders after upload                                                                             |
| _Meta                          | Contains the default metadata and thumbnail images to tag the files with when uploading to youtube                                                    |
| _DVR/_Live_Comments            | Comments made during livestreams go in here for you to laugh at                                                                                       |
| _DVR/_Live_CompletedUploads    | After livestreams are downloaded and reuploaded to youtube & IA they go in here                                                                       |
| _DVR/_Live_DownloadQueue       | Livestreams are downloaded in this folder until they are completed then they get moved to _Live_UploadQueue                                           |
| _DVR/_Live_DownloadRecovery    | Second proccessed copies of livestreams after they finish are stored in here drop into _Live_UploadQueue to upload them to IA & YouTube automatically |
| _DVR/_Live_UploadQueue         | Any video files placed in her that match the download_timestamp_format get uploaded to Youtube and IA automatically                                   |
| _DVR/_Posted_CommunityMessages | Contains Community_Archive.html which is a complete archive of the community posts including deleted posts                                            |
| _DVR/_Posted_CompletedUploads  | Shorts & Videos end up here after they are uploaded to YouTube & IA                                                                                   |
| _DVR/_Posted_DownloadQueue     | Shorts & Videos are downloaded here when complete they automatically move to _Posted_UploadQueue                                                      |
| _DVR/_Posted_Playlists         | You can ignore this one, Just 2 csv files for keeping track of what's a new video and what's been uploaded before.                                    |
| _DVR/_Posted_UploadQueue       | Any video files placed in here that match the download_timestamp_format get uploaded to YouTube and IA automatically                                  |

# I WANT DIS! HOW I GET....

### To run on your router, tv, calculator, microwave......

Just make a container with the image 

python:alpine

or

registry-1.docker.io/library/python:alpine

dump the files in the work directory and set the startup to be 

python3 main.py



To run on Windows......

 run the command here and reboot

https://learn.microsoft.com/en-us/windows/wsl/install

download this and install

https://www.docker.com/products/docker-desktop/

Clone the repo into a folder structure like V:\Dregs\SOMEDREG first and fill in your dvr_accounts.cfg with real details

then look at this command and modify it for your system 

- docker run -v V:\Dregs\SOMEDREG:/dvr python:alpine python /dvr/main.py

**command breakdown...**

1. V:\Dregs\SOMEDREG = The folder on the disk for this instance of the dvr, the repo files should already be in here
2. :/dvr = Leave this alone can be the same for multiple dregs
3. python:alpine = the os the container will run only alpine is supported
4. python /dvr/main.py = the command the container will use to start the dregs dvr script

**You need a different folder and container for each dreg you want to record, For example**

1. docker run -v V:\Dregs\PJ:/dvr python:alpine python /dvr/main.py
2. docker run -v V:\Dregs\Gert:/dvr python:alpine python /dvr/main.py
3. docker run -v V:\Dregs\Timmy:/dvr python:alpine python /dvr/main.py



### Then...

After you get the thing running and logs appearing in the logs dir more work...

**You need to customize dvr_accounts.cfg & dvr_tasks.cfg for each Dreg... Each DVR needs...**

1. An internet archive account and page (https://archive.org/create/ upload any file to community videos and configure a video archive, put the details page in dvr_accounts.cfg)
2. A YouTube account with advanced features https://support.google.com/youtube/answer/9891124
3. A Google account with API access see: https://developers.google.com/youtube/v3/quickstart/python#step_1_set_up_your_project_and_credentials
4. oauth2.json and client_secret.json 
   Download client_secret.json from the portal in step 3
   Use the following example on a computer with a browser to generate oauth2.json https://developers.google.com/youtube/v3/guides/uploading_a_video
   Once you have successfully uploaded a video to youtube using the example code above you can rename to YT-client_secret.json , YT-oauth2.json and overwrite the examples in the auth folder
5. ~~run '**ia configure**' within the containers shell to save your archive.org shared secret.~~ Automatically done now yay!

# OPTIONS , WHAT THEY DO!

Here is a quick breakdown of the config files

* **dvr_accounts.cfg**
  Contains account specific information that is unique to each dvr container
* **dvr_settings.cfg**
  Contains general settings for the dvr features, this file will most likely be the same for all your dvr containers
* **dvr_tasks.cfg**
  defines what features are enabled for the dvr this is usually unique to each dvr container

#### **dvr_accounts.cfg**

| Section        | Value                 | Explanation                                                          |
| -------------- | --------------------- | -------------------------------------------------------------------- |
| YT_Sources     | source                | The primary Youtube source we want to clone                          |
| YT_Sources     | caption_source        | The channel to download subtitles from (can be the same)             |
| File_Naming    | live_downloadprefix   | The prefix for livestream video files inserted before the timestamp  |
| File_Naming    | posted_downloadprefix | The prefix for posted video files inserted before the timestamp      |
| IA_Settings    | itemid                | The itemid of your archive.org item where all files will be added to |
| IA_Settings    | user_agent            | The user agent for your instence of this bot                         |
| IA_Credentials | email                 | Your IA Credentials                                                  |
| IA_Credentials | password              | Your IA Credentials                                                  |

#### **dvr_settings.cfg**

| Section             | Value                              | Explanation                                                                                                      |
| ------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| YT_DownloadSettings | download_timestamp_format          | The yt-dlp -o output template usually used to add the timestamp to the filename                                  |
| YT_DownloadSettings | dlp_no_progress_filters            | Defines log filters to skip yt-dlp's progress messages                                                           |
| YT_DownloadSettings | dlp_verbose_downloads              | Provides verbose logging in yt-dlp (Recommended)                                                                 |
| YT_DownloadSettings | dlp_no_progress_downloads          | Hides all progress messages from yt-dlp (Recommended)                                                            |
| YT_DownloadSettings | dlp_keep_fragments_downloads       | Allows keeping fragments no longer needed now that we have the recovery downloader                               |
| YT_DownloadSettings | dlp_max_download_retries           | Mapped to the --retries option for yt-dlp default is 10                                                          |
| YT_DownloadSettings | dlp_max_fragment_retries           | Mapped to the --fragment-retries option for yt-dlp default is 10                                                 |
| YT_DownloadSettings | dlp_truncate_title_after_x_chars   | Trim the title of the source video when its too large                                                            |
| YT_UploadSettings   | upload_file_extensions             | Defines what file extensions the uploader should watch for                                                       |
| Directories         | live_uploadqueue_dir               | The name of the directory is customizable for reasons                                                            |
| Directories         | live_downloadqueue_dir             | The name of the directory is customizable for reasons                                                            |
| Directories         | live_completeduploads_dir          | The name of the directory is customizable for reasons                                                            |
| Directories         | live_downloadrecovery_dir          | The name of the directory is customizable for reasons                                                            |
| Directories         | live_comments_dir                  | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_uploadqueue_dir             | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_downloadqueue_dir           | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_completeduploads_dir        | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_playlists_dir               | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_notices_dir                 | The name of the directory is customizable for reasons                                                            |
| Directories         | metadata_dir                       | The name of the directory is customizable for reasons                                                            |
| Directories         | log_dir                            | The name of the directory is customizable for reasons                                                            |
| Directories         | auth_dir                           | The name of the directory is customizable for reasons                                                            |
| Directories         | bin_dir                            | the ia binary goes in here, we download it for you how handy                                                     |
| dirs_to_create      | dirs_to_create                     | we automatically make["make", "these", "dirs"]                                                                   |
| Logging             | log_archiving                      | Controls log archiving to folders after a livestream or short has been uploaded                                  |
| Log_Filters         | core_log_filter                    | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | captions_log_filter                | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | download_live_log_filter           | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | download_live_recovery_log_filter  | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | download_posted_log_filter         | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | upload_posted_log_filter           | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | download_posted_notices_log_filter | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | upload_live_log_filter             | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | upload_ia_log_filter               | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| Log_Filters         | upload_yt_log_filter               | ["ignore this", "and that", "and the other"] any log message with one of these strings will be ignored neet&tidy |
| General             | required_dependencies              | these get installed & updated automatically on startup                                                           |
| General             | maximum_threads                    | Currently only used for the caption downloader can help speed up initial caption generation                      |

#### **dvr_tasks.cfg**

| Section | Value                          | Explanation                                                                                           |
| ------- | ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Tasks   | container_maintenance_inf_loop | Stops the dvr from loading if set to true, allows you to mess with the terminal                       |
| Tasks   | livestream_download            | Task control for downloading livestreams                                                              |
| Tasks   | livestream_recovery_download   | Task control for downloading a second copy of livestreams after they end                              |
| Tasks   | comments_download              | Task control for downloading comments from livestreams to text files                                  |
| Tasks   | captions_download              | Task control for downloading captions from youtube                                                    |
| Tasks   | posted_videos_download         | Task control for downloading posted videos & shorts                                                   |
| Tasks   | posted_notices_download        | Task control for downloading community posts to _Posted_CommunityMessages\Community_Post_Archive.html |
| Tasks   | livestream_upload              | Task control for uploading of livestreams                                                             |
| Tasks   | posted_videos_upload           | Task control for uploading of posted videos & shorts                                                  |

# CREDITS , WHO TO THANK

https://github.com/yt-dlp/yt-dlp

https://github.com/xenova/chat-downloader

https://github.com/NothingNaN/YoutubeCommunityScraper/

https://github.com/bindestriche/srt_fix

https://archive.org/developers/
