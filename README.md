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
| _Auth                          | Auth files for automatic youtube uploads & cookies.txt                                                                                                |
| _Captions                      | Automatic subtitles in here enable easy clipping                                                                                                      |
| _Config                        | Config files for the dvr                                                                                                                              |
| _Logs                          | Logs go in here and optionally can be archived to subfolders after upload                                                                             |
| _Meta                          | Contains the default metadata and thumbnail images to tag the files with when uploading to youtube                                                    |

| _Playlists         | The heart of the DVR the channel is monitored and any videos,shorts,livestreams etc are added as an entry to the channel playlist json which is monitored by the downloaders and uploaders.                                     |

| _PlayWright         | Rumble, Odysee and Bitchute uploaders are based on playwright web automation. This folder stores session videos, session cookies and debug html dumps                                                                                       |

| _DVR/_Live_Comments            | Comments made during livestreams go in here for you to laugh at                                                                                       |
| _DVR/_Live_DownloadQueue       | Livestreams are downloaded in this folder until they are completed then they get moved to _Live_Videos                                               |
| _DVR/_Live_DownloadRecovery    | Second processed copies of livestreams after they finish are stored in here drop into _Live_Videos to upload them to IA & YouTube automatically        |
| _DVR/_Live_Videos              | Any video files placed in here that match the download_timestamp_format get uploaded to Youtube and IA automatically                                 |
| _DVR/_Posted_CommunityMessages | Contains Community_Archive.html which is a complete archive of the community posts including deleted posts                                            |
| _DVR/_Posted_DownloadQueue     | Shorts & Videos are downloaded here when complete they automatically move to _Posted_Videos                                                          |
| _DVR/_Posted_Videos            | Any video files placed in here that match the download_timestamp_format get uploaded to YouTube and IA automatically                                 |

# I WANT DIS! HOW I GET....

Make a container with the image python:alpine

Add 3 mounts 

| Mount Local Path                              | Mount Containter Path | Permissions | Description                                                                                                         |
| --------------------------------------------- | --------------------- |:-----------:| ------------------------------------------------------------------------------------------------------------------- |
| /DreggDVR/DVR_Production                      | /_Dregg_DVR           | Read Only   | Dump the repo code in here this is common to all instances                                                          |
| DreggDVR/DVR_Instances/YOURDREGG/_DVR_Runtime | /_DVR_Runtime         | Write       | Contains the logs, config files and metadata specific to this dvr instence see the example _DVR_Runtime in the repo |
| DreggDVR/DVR_Instances/YOURDREGG/_DVR_Data    | /_DVR_Data            | Write       | Contains the recordings for this dvr instence                                                                       |

Set the start action to

python3 /_Dregg_DVR/main.py

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
5. **Optional ** > Export your cookies.txt with a burner account and dump it in the auth folder https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies
6. ~~run '**ia configure**' within the containers shell to save your archive.org shared secret.~~ Automatically done now yay!

# OPTIONS , WHAT THEY DO!

Here is a quick breakdown of the config files

* **dvr_instances.cfg** (NEW - Required for multi-instance support)
  Master configuration file that defines all DVR instances to run simultaneously. Each instance can monitor a different YouTube channel independently.
* **dvr_accounts.cfg**
  Contains account specific information that is unique to each dvr container
* **dvr_settings.cfg**
  Contains general settings for the dvr features, this file will most likely be the same for all your dvr containers
* **dvr_tasks.cfg**
  defines what features are enabled for the dvr this is usually unique to each dvr container

#### **dvr_accounts.cfg**

| Section        | Value                 | Explanation                                                          |
| -------------- | --------------------- | -------------------------------------------------------------------- |
| YT_Sources     | source                | The primary Youtube source we want to clone
| File_Naming    | live_downloadprefix   | The prefix for livestream video files inserted before the timestamp  |
| File_Naming    | posted_downloadprefix | The prefix for posted video files inserted before the timestamp      |
| IA_Settings    | itemid                | The itemid of your archive.org item where all files will be added to |
| IA_Settings    | user_agent            | The user agent for your instence of this bot                         |
| IA_Credentials | email                 | Your IA Credentials                                                  |
| IA_Credentials | password              | Your IA Credentials                                                  |
| Rumble_Credentials | email              | Your Rumble account email                                             |
| Rumble_Credentials | password           | Your Rumble account password                                          |
| Rumble_Settings    | primary_category   | Primary category for Rumble uploads (e.g., "News & Politics")         |
| Rumble_Settings    | secondary_category | Secondary category for Rumble uploads (e.g., "People & Blogs" optional)       |
| BitChute_Credentials | email            | Your BitChute account email                                           |
| BitChute_Credentials | password         | Your BitChute account password                                        |
| Odysee_Credentials | email             | Your Odysee account email                                             |
| Odysee_Credentials | password          | Your Odysee account password                                          |
| GitHub_Credentials | token              | Your GitHub personal access token for authenticated API access         |
| GitHub_Repo        | owner              | GitHub account/organization name that owns the repository             |
| GitHub_Repo        | repo_name          | Name of the GitHub repository for storing data                        |
| GitHub_Repo        | captions_path      | Path within the repository where captions should be stored            |

#### **dvr_settings.cfg**

| Section             | Value                              | Explanation                                                                                                      |
| ------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| YT_DownloadSettings | download_timestamp_format          | The yt-dlp -o output template usually used to add the timestamp to the filename                                  |
| YT_DownloadSettings | dlp_verbose_downloads              | Provides verbose logging in yt-dlp (Recommended)                                                                 |
| YT_DownloadSettings | dlp_keep_fragments_downloads       | Allows keeping fragments no longer needed now that we have the recovery downloader                               |
| YT_DownloadSettings | dlp_max_download_retries           | Mapped to the --retries option for yt-dlp default is 10                                                          |
| YT_DownloadSettings | dlp_max_fragment_retries           | Mapped to the --fragment-retries option for yt-dlp default is 10                                                 |
| YT_DownloadSettings | dlp_js_runtime                     | JavaScript runtime for yt-dlp to use (default "quickjs" for optimal performance)                                |
| YT_DownloadSettings | dlp_truncate_title_after_x_chars   | Trim the title of the source video when its too large (default 60)                                              |
| YT_DownloadSettings | dlp_subtitle_use_srtfix            | Automatically fix subtitle formatting issues using srt_fix tool (true/false, default true)                       |
| YT_DownloadSettings | dlp_getinfo_timeout_seconds        | Timeout for fetching video info in seconds (default 800)                                                         |
| YT_DownloadSettings | dlp_stall_timeout_seconds          | Timeout for stalled connections in seconds (default 800)                                                         |
| YT_DownloadSettings | dlp_buffer_first_attempt_errors    | Buffer/ignore errors on first download attempt to allow retries (true/false, default true)                       |
| YT_UploadSettings   | upload_file_extensions             | Defines what file extensions the uploader should watch for                                                       |
| YT_UploadSettings   | upload_visibility                  | Valid values are Public Private or Unlisted                                                                      |
| YT_UploadSettings   | upload_category                    | 22 = People & Blogs  https://mixedanalytics.com/blog/list-of-youtube-video-category-ids                          |
| Uploaders           | upload_to_youtube                  | Set to true/false to enable/disable YouTube uploads                                                              |
| Uploaders           | upload_to_ia                       | Set to true/false to enable/disable Internet Archive uploads                                                     |
| Uploaders           | upload_to_rumble                   | Set to true/false to enable/disable Rumble uploads                                                               |
| Uploaders           | upload_to_bitchute                 | Set to true/false to enable/disable BitChute uploads                                                             |
| Uploaders           | upload_to_odysee                   | Set to true/false to enable/disable Odysee uploads                                                               |
| Uploaders           | upload_to_github                   | Set to true/false to enable/disable GitHub caption uploads                                                       |
| Directories         | live_videos_dir               | The name of the directory is customizable for reasons                                                            |
| Directories         | live_downloadqueue_dir             | The name of the directory is customizable for reasons                                                            |
| Directories         | live_completeduploads_dir          | The name of the directory is customizable for reasons                                                            |
| Directories         | live_downloadrecovery_dir          | The name of the directory is customizable for reasons                                                            |
| Directories         | live_comments_dir                  | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_videos_dir             | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_downloadqueue_dir           | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_completeduploads_dir        | The name of the directory is customizable for reasons                                                            |
| Directories         | channel_playlists_dir               | The name of the directory is customizable for reasons                                                            |
| Directories         | posted_notices_dir                 | The name of the directory is customizable for reasons                                                            |
| Directories         | metadata_dir                       | The name of the directory is customizable for reasons                                                            |
| Directories         | log_dir                            | The name of the directory is customizable for reasons                                                            |
| Directories         | auth_dir                           | The name of the directory is customizable for reasons                                                            |
| Directories         | playwright_dir                     | The playwright browser session storage directory                                                                 |
| Directories         | templates_dir                      | Directory containing HTML templates for rendering community posts and comments                                    |
| Directories         | captions_dir                       | Root directory for caption storage                                                                               |
| Directories         | captions_upload_queue_dir          | Subdirectory of captions_dir for captions awaiting upload                                                        |
| Directories         | captions_completed_uploads_dir     | Subdirectory of captions_dir for uploaded captions                                                               |
| Directories         | temp_captions_dir                  | Subdirectory of captions_dir for temporary caption processing                                                    |
| Directories         | runtime_dir                        | Root name for runtime directory (default "_DVR_Runtime")                                                         |
| Directories         | data_dir                           | Root name for data directory (default "_DVR_Data")                                                               |
| Logging             | log_archiving                      | Controls log archiving to folders after a livestream or short has been uploaded                                  |
| General             | required_pip_dependencies          | Python packages that get installed & updated automatically on startup                                             |
| General             | required_apt_dependencies          | System packages that get installed & updated automatically on startup (Linux only)                                |
| General             | maximum_threads                    | Maximum concurrent threads for operations like caption downloading (default 6)                                    |

#### **dvr_tasks.cfg**

| Section | Value                          | Explanation                                                                                           |
| ------- | ------------------------------ | ----------------------------------------------------------------------------------------------------- |

| Tasks   | dependency_package_update      | Task control for package dpendencies                                      |
| Tasks   | livestream_download            | Task control for downloading livestreams                                                              |
| Tasks   | livestream_recovery_download   | Task control for downloading a second copy of livestreams after they end                              |
| Tasks   | comments_download              | Task control for downloading comments from livestreams to text files                                  |
| Tasks   | captions_download              | Task control for downloading captions from youtube                                                    |
| Tasks   | captions_upload                | Task control for uploading captions to youtube                                                        |
| Tasks   | comments_republish             | Task control for republishing archived comments from previous livestreams                             |
| Tasks   | posted_videos_download         | Task control for downloading posted videos & shorts                                                   |
| Tasks   | posted_notices_download        | Task control for downloading community posts to _Posted_CommunityMessages\Community_Post_Archive.html |
| Tasks   | livestream_upload              | Task control for uploading of livestreams                                                             |
| Tasks   | posted_videos_upload           | Task control for uploading of posted videos & shorts                                                  |
| Tasks   | update_playlist      | Task control for updating youtube source playlist metadata                                             |


#### **dvr_instances.cfg** (NEW)

Master configuration file for managing multiple simultaneous DVR instances. Each `[DVR_Instance]` section defines one instance that can monitor a different YouTube channel independently.

| Section      | Value                        | Explanation                                                                                                                                                              |
| ------------ | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| DVR_Instance | instance_name                | Name of the instance (will be converted to safe filesystem name). Each instance gets its own runtime and data directories                                               |
| DVR_Instance | dvr_data_in_other_instance   | Set to true to share data directories with another instance instead of creating a new one. Useful for instances that upload to the same queues. (true/false)            |
| DVR_Instance | dvr_data_other_instance_name | Name of the instance whose data directory to use when `dvr_data_in_other_instance=true`. Leave empty if `dvr_data_in_other_instance=false`                             |

**Example Configuration:**
```ini
[DVR_Instance]
instance_name=MainChannel
dvr_data_in_other_instance=false
dvr_data_other_instance_name=

[DVR_Instance]
instance_name=BackupChannel
dvr_data_in_other_instance=false
dvr_data_other_instance_name=

[DVR_Instance]
instance_name=UploadOnly
dvr_data_in_other_instance=true
dvr_data_other_instance_name=MainChannel
```

**Key Features:**
- Each instance creates its own directory structure in `_DVR_Runtime/[InstanceName]` and `_DVR_Data/[InstanceName]`
- Multiple instances run concurrently using asyncio, enabling true parallel operation
- Instances can share data by pointing to another instance's data directory
- Each instance has independent logs, making troubleshooting easier
- Logs for each instance stored in `_DVR_Runtime/[InstanceName]/_Logs/`

**Important Notes:**
- At least one instance must be defined in the config
- Instance names are case-sensitive in the config but will be converted to safe filesystem names
- If `dvr_data_other_instance_name` references a non-existent instance, that instance's directories will be created automatically
- All instances use the same `dvr_settings.cfg` but can have different task enables/disables via `dvr_tasks.cfg` (configure globally)

# CREDITS , WHO TO THANK

https://github.com/yt-dlp/yt-dlp

https://github.com/xenova/chat-downloader

https://github.com/bindestriche/srt_fix

https://archive.org/developers/
