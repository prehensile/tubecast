import subprocess
from bs4 import BeautifulSoup as bs
from flask import Flask, Response, url_for, render_template, abort
import requests
import urlparse 
import sys
import re
import os

app = Flask(__name__)
app.debug = True

@app.route('/')
def index():
    return render_template( "index.html" )

@app.route('/stream/<path:path>')
def stream( path ):
    
    path_components = path.split("/")
    if len(path_components) < 1:
        #TODO: more detailed error throwing
        abort(400)

    youtube_id = path_components[0]
    if not re.match( r'[a-zA-Z0-9_-]{11}', youtube_id ):
        #TODO: more detailed error throwing
        abort(400)

    ff_path = os.path.realpath(__file__)
    ff_path = os.path.join( ff_path, ".heroku/vendor/ffmpeg/bin/ffmpeg")

    yt_args = [ "youtube-dl", "-f", "140", "-q", "--output", "-", youtube_id ]
    ff_args = [ ff_path, "-i", "-", "-loglevel", "quiet", "-acodec", "copy", "-f", "adts", "-" ]

    yt_proc = subprocess.Popen( yt_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
    ff_proc = subprocess.Popen( ff_args, stdin=yt_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
    
    def stream( proc ):
        buf_size = 1024
        while True:
            d = proc.stdout.read( buf_size )
            yield d
            if len(d) < buf_size:
                break

    return Response( stream( ff_proc ), mimetype='audio/mp4' )

def parse_playlist( playlist_id ):

    feed_url = "http://gdata.youtube.com/feeds/api/playlists/" + playlist_id
    r = requests.get( feed_url )
    soup = bs( r.text )

    channel_out = {}
    items_out = []

    feed = soup.find("feed")
    
    channel_out["self_url"] = url_for( "feed", path=playlist_id, _external=True )
    
    channel_out["title"] = feed.find("title").string
    channel_out["link"] = feed.find( "link", rel="alternate" ).attrs["href"]
    channel_out["description"] = feed.find("subtitle").string
    channel_out["last_updated"] = feed.find("updated").string
    channel_out["author"] = feed.find("author")

    for entry_tag in soup.find_all( "entry" ):

        this_item = {}

        # extract a few things from the item xml
        media_group = entry_tag.find( "media:group" )
        media_player = media_group.find( "media:player" )
        player_url = media_player.attrs[ "url" ]
        
        # get youtube item id from player url
        parsed = urlparse.urlparse( player_url )
        qd = urlparse.parse_qs( parsed.query )
        yt_id = "%s" % qd["v"][0]
        
        # construct item dict
        this_item["title"] = entry_tag.find("title").string
        this_item["pub_date"] = entry_tag.find("published").string
        this_item["guid"] = entry_tag.find("id").string
        this_item["content"] = entry_tag.find("content").string
        
        this_item["link"] = entry_tag.find( "link", rel="alternate" ).attrs["href"]
        this_item["media_url"] = url_for( "stream", path=yt_id, _external=True )

        this_item["author"] = entry_tag.find("author")
        this_item["categories"] = entry_tag.find_all("category")

        this_item["duration"] = media_group.find( "media:content" ).attrs["duration"]
        this_item["description"] = media_group.find( "media:description" ).string
        
        items_out.append( this_item )

    return channel_out, items_out

@app.route('/feed/<path:path>')
def feed( path ):
    path_components = path.split("/")
    if len(path_components) < 1:
        abort(400)

    playlist_id = path_components[0]
    if not re.match( r'[a-zA-Z0-9_-]+', playlist_id ):
        #TODO: better validation
        abort(400)

    try:
        channel, items = parse_playlist( playlist_id )
    except Exception:
        #TODO: better error handling
        abort(500)
    
    return render_template( "feed.xml", channel=channel, items=items )

if __name__ == '__main__':
    if len(sys.argv) > 1:
        playlist_id = sys.argv[1]
        channel, items = parse_playlist( playlist_id )
        print channel
        print items
    else:
        app.run()
