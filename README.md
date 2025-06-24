# DregDVR
Dreg's DVR... Am i 4k wecording? Yes im 4k wecording!

#WOT IT DO ?

Automatically downloads all their....
	livestreams
	comments on livestreams (even hidden or removed ones) to a .txt file
	shorts & videos

Automatically uploads....
	To internet archive which is practically unbannable
	To youtube (to seed google search results with links to the internet archive page we dont care if this gets taken down)

Using fuck all resources, no video transcoding.

#I WANT DIS! HOW I GET....

If your on windows run the command here and reboot

https://learn.microsoft.com/en-us/windows/wsl/install

download this and install
 
https://www.docker.com/products/docker-desktop/

then look at this command and modify it for your system

docker run -v V:\Dregs\pj:/dvr python:alpine python /dvr/main.py

command brakedown...
V:\Dregs\PJ = The folder on the disk for this instance of the dvr
:/dvr = Leave this alone can be the same for multiple dregs
python:alpine = the os the container will run leave this alone its already slimmed down enough
python /dvr/main.py = the command the container will use to start the dregs dvr script

You need a different folder and container for each dreg you want to record

eg
docker run -v V:\Dregs\PJ:/dvr python:alpine python /dvr/main.py
docker run -v V:\Dregs\Gert:/dvr python:alpine python /dvr/main.py
docker run -v V:\Dregs\Timmy:/dvr python:alpine python /dvr/main.py
etc

You need to customise each ini for each Dreg...
	Each DVR needs...
		1 An internet archive account and page (https://archive.org/create/ upload any file to community videos and configure a video archive, put the details page in the ini file)
		2 A youtube account with advanced features https://support.google.com/youtube/answer/9891124

Additionally
1 google account with API access see: https://developers.google.com/youtube/v3/quickstart/python#step_1_set_up_your_project_and_credentials
Save the oath json as YT-oauth2.json in \_Auth you can duplicate this file across all your Dreg dvr containers.
