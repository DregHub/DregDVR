# DregDVR

An automatic YouTube channel archiver & YouTube channel cloner. 

'Am i 4k wecording? Yes im 4k wecording!'

# WOT IT DO ?

Automatically downloads all their YouTube....

> Livestreams
> Livestream Comments (even hidden or removed ones) to a .txt file
> Subtitles (for both live and posted videos\shorts
> Videos
> Shorts
> Community Posts to 

Automatically uploads....

> Their Livestreams, Videos, Shorts
> To internet archive > which is practically unbannable
> To youtube          > which will show up in google search results
>
> All video information is pulled from \_Meta\Default.xml

Using fuck all resources, no video transcoding, can run on a potato


# SO MANY FOLDERS, WHAT FOR ?

| Folder Name               | Usage                                                        |
| ------------------------- | ------------------------------------------------------------ |
| _Auth                     | Auth files for automatic youtube uploads                     |
| _Captions                 | Automatic subtitles in here enable easy clipping             |
| _Config                   | Config files for the dvr                                     |
| _Live_Comments            | Comments made during livestreams go in here for you to laugh at |
| _Live_CompletedUploads    | After livestreams are downloaded and reuploaded to youtube & IA they go in here |
| _Live_DownloadQueue       | Livestreams are downloaded in this folder until they are completed then they get moved to _Live_UploadQueue |
| _Live_DownloadRecovery    | Second proccessed copies of livestreams after they finish are stored in here drop into _Live_UploadQueue to upload them to IA & Youtube automatically |
| _Live_UploadQueue         | Any video files placed in her that match the download_timestamp_format get uploaded to Youtube and IA automatically |
| _Logs                     | Logs go in here and optionally can be archived to subfolders after upload |
| _Meta                     | Contains the default metadata and thumbnail images to tag the files with when uploading to youtube |
| _Posted_CommunityMessages | Contains Community_Archive.html which is a complete archive of the community posts including deleted posts |
| _Posted_CompletedUploads  | Shorts & Videos end up here after they are uploaded to Youtube & IA |
| _Posted_DownloadQueue     | Shorts & Videos are downloaded here when complete they automatically move to _Posted_UploadQueue |
| _Posted_Playlists         | You can ignore this one, Just 2 csv files for keeping track of what's a new video and what's been uploaded before. |
| _Posted_UploadQueue       | Any video files placed in her that match the download_timestamp_format get uploaded to Youtube and IA automatically |


# I WANT DIS! HOW I GET....

If your on windows run the command here and reboot

https://learn.microsoft.com/en-us/windows/wsl/install

download this and install

https://www.docker.com/products/docker-desktop/

Clone the repo into a folder structure like V:\Dregs\SOMEDREG first and fill in your config.cfg with real details

then look at this command and modify it for your system docker run -v V:\Dregs\SOMEDREG:/dvr python:alpine python /dvr/main.py

command brakedown...

> V:\Dregs\SOMEDREG = The folder on the disk for this instance of the dvr, the repo files should already be in here
> :/dvr = Leave this alone can be the same for multiple dregs
> python:alpine = the os the container will run only alpine is supported
> python /dvr/main.py = the command the container will use to start the dregs dvr script

You need a different folder and container for each dreg you want to recordeg

> eg
> docker run -v V:\Dregs\PJ:/dvr python:alpine python /dvr/main.py
> docker run -v V:\Dregs\Gert:/dvr python:alpine python /dvr/main.py
> docker run -v V:\Dregs\Timmy:/dvr python:alpine python /dvr/main.py
> etc

1. You need to customise dvr_accounts.cfg & dvr_tasks.cfg for each Dreg... Each DVR needs...
   An internet archive account and page (https://archive.org/create/ upload any file to community videos and configure a video archive, put the details page in the ini file)
2. A youtube account with advanced features https://support.google.com/youtube/answer/9891124
3. Additionally 1 google account with API access see: https://developers.google.com/youtube/v3/quickstart/python#step_1_set_up_your_project_and_credentials
4. Save the oath json as YT-oauth2.json in \_Auth you can duplicate this file across all your Dreg dvr containers.
5. to run 'ia configure' within the containers shell to save your archive.org shared secret.


# OPTIONS , WHAT THEY DO!

Here is a quick breakdown of the config files

* dvr_accounts.cfg
  Contains account specific information that is unique to each dvr container
* dvr_settings.cfg
  Contains general settings for the dvr features, this file will most likely be the same for all your dvr containers
* dvr_tasks.cfg
  defines what features are enabled for the dvr this is usually unique to each dvr container

#### dvr_accounts.cfg


| Section | Value | Explanation |
| --------- | ------- | ------------- |
| YT_Sources | source | The primary Youtube source we want to clone |
| YT_Sources | caption_source | The channel to download subtitles from (can be the same |
| File_Naming | live_downloadprefix | The prefix for livestream video files inserted before the timestamp |
| File_Naming | posted_downloadprefix | The prefix for posted video files inserted before the timestamp |
| IA_Settings | itemid | The itemid of your archive.org item where all files will be added to |
| IA_Credentials | email | Your IA Credentials, You will still need to run "ia configure" on each container once |
| IA_Credentials | password | Your IA Credentials, You will still need to run "ia configure" on each container once |

#### dvr_settings.cfg

| Section             | Value                              | Explanation                                                  |
| ------------------- | ---------------------------------- | ------------------------------------------------------------ |
| YT_DownloadSettings | download_timestamp_format          | The yt-dlp -o output template usually used to add the timestamp to the filename |
| YT_DownloadSettings | dlp_no_progress_filters            | Defines log filters to skip yt-dlp's progress messages       |
| YT_DownloadSettings | dlp_verbose_downloads              | Provides verbose logging in yt-dlp (Recommended)             |
| YT_DownloadSettings | dlp_no_progress_downloads          | Hides all progress messages from yt-dlp (Recommended)        |
| YT_DownloadSettings | dlp_keep_fragments_downloads       | Allows keeping fragments no longer needed now that we have the recovery downloader |
| YT_DownloadSettings | dlp_max_download_retries           | Mapped to the --retries option for yt-dlp default is 10      |
| YT_DownloadSettings | dlp_max_fragment_retries           | Mapped to the --fragment-retries option for yt-dlp default is 10 |
| YT_DownloadSettings | dlp_truncate_title_after_x_chars   | Trim the title of the source video when its too large        |
| YT_UploadSettings   | upload_file_extensions             | Defines what file extensions the uploader should watch for   |
| Directories         | live_uploadqueue_dir               | The name of the directory is customizable for reasons        |
| Directories         | live_downloadqueue_dir             | The name of the directory is customizable for reasons        |
| Directories         | live_completeduploads_dir          | The name of the directory is customizable for reasons        |
| Directories         | live_downloadrecovery_dir          | The name of the directory is customizable for reasons        |
| Directories         | live_comments_dir                  | The name of the directory is customizable for reasons        |
| Directories         | posted_uploadqueue_dir             | The name of the directory is customizable for reasons        |
| Directories         | posted_downloadqueue_dir           | The name of the directory is customizable for reasons        |
| Directories         | posted_completeduploads_dir        | The name of the directory is customizable for reasons        |
| Directories         | posted_playlists_dir               | The name of the directory is customizable for reasons        |
| Directories         | posted_notices_dir                 | The name of the directory is customizable for reasons        |
| Directories         | metadata_dir                       | The name of the directory is customizable for reasons        |
| Directories         | log_dir                            | The name of the directory is customizable for reasons        |
| Directories         | auth_dir                           | The name of the directory is customizable for reasons        |
| Directories         | bin_dir                            | the ia binary goes in here, we download it for you how handy |
| dirs_to_create      | dirs_to_create                     | we automatically make["make", "these", "dirs"]               |
| Logging             | disable_log_archiving              | Controls log archiving to folders after a livestream or short has been uploaded |
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
| General             | required_dependencies              | these get installed & updated automatically on startup       |
| General             | maximum_threads                    | Currently only used for the caption downloader can help speed up initial caption generation |

#### dvr_tasks.cfg
| Section | Value                                  | Explanation                                                  |
| ------- | -------------------------------------- | ------------------------------------------------------------ |
| Tasks   | disable_container_maintenance_inf_loop | Stops the dvr from loading if set to false, allows you to mess with the terminal |
| Tasks   | disable_livestream_download            | Turn off downloading livestreams                             |
| Tasks   | disable_livestream_recovery_download   | Turn off downloading a second copy of livestreams after they end |
| Tasks   | disable_comments_download              | Turns off downloading comments from livestreams to text files |
| Tasks   | disable_captions_download              | Turns off downloading captions from youtube                  |
| Tasks   | disable_posted_videos_download         | Turns off downloading posted videos & shorts                 |
| Tasks   | disable_posted_notices_download        | Turns off downloading community posts to _Posted_CommunityMessages\Community_Post_Archive.html |
| Tasks   | disable_livestream_upload              | Turns off uploading of livestreams                           |
| Tasks   | disable_posted_videos_upload           | Turns off uploading of posted videos & shorts                |

# CREDITS , WHO TO THANK

https://github.com/yt-dlp/yt-dlp

https://github.com/xenova/chat-downloader

https://github.com/NothingNaN/YoutubeCommunityScraper/
