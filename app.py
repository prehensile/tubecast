import subprocess
from bs4 import BeautifulSoup as bs
from flask import Flask, Response, url_for, render_template, abort
import requests
import urlparse 
import sys, os
import re
import datetime, time
from email import utils

app = Flask(__name__)
app.debug = True
app.config['MIME_TYPE'] = "audio/aac-adts"
#mimetype = "audio/m4a"

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

    # construct path to heroku vended ffmpeg first...
    ff_path = os.path.dirname(os.path.realpath(__file__))
    ff_path = os.path.join( ff_path, ".heroku/vendor/ffmpeg/bin/ffmpeg")
    ## ...fall back to assuming it's in the system path
    if not os.path.exists( ff_path ):
        ff_path = "ffmpeg"

    yt_args = [ "youtube-dl", "-f", "140", "-q", "--output", "-", youtube_id ]
    ff_args = [ ff_path, "-loglevel", "quiet", "-i", "-", "-vn", "-acodec", "libfaac", "-f", "adts", "-" ]
    #ff_args = [ ff_path, "-i", "-", "-acodec", "copy", "-vn", "-f", "adts", "-" ]
    #ff_args = [ ff_path, "-i", "-", "-acodec", "copy", "-vn", "-f", "mp4", "-movflags", "frag_keyframe", "-frag_size", "1024", "-" ]
    filename = "%s.aac" % youtube_id
    # filename = "%s.adts" % youtube_id

    print " ".join(yt_args)
    print " ".join(ff_args)

    def stream():
        yt_proc = None
        ff_proc = None
        try:
            yt_proc = subprocess.Popen( yt_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
            ff_proc = subprocess.Popen( ff_args, stdin=yt_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
        except:
            pass
        buf_size = 1024
        finished = False
        streamed = 0
        if (yt_proc is not None) and (ff_proc is not None):
            print "-> begin streaming..."
            while not finished:
                d = ff_proc.stdout.read( buf_size )
                yield d
                streamed += len(d)
                if len(d) < buf_size:
                    finished = True
        if ff_proc is not None:
            print "--> kill ffmpeg"
            ff_proc.wait()
            #ff_proc.terminate()
        if yt_proc is not None:
            print "--> kill youtube-dl"
            #yt_proc.terminate()
            yt_proc.wait()
        print "-> stream ended. Streamed %d bytes." % streamed

    return Response( stream(),
                        mimetype=mimetype,
                        headers={"Content-Disposition":
                                    "attachment;filename=%s"%filename} )
def format_duration( seconds ):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%d:%02d:%02d" % (h, m, s)    

def format_date( datestring ):
    # 2008-12-24T00:46:17.000Z
    dt = datetime.datetime.strptime( datestring, "%Y-%m-%dT%H:%M:%S.%fZ" )
    return utils.formatdate( time.mktime(dt.timetuple()) )

def parse_playlist( playlist_id ):

    feed_url = "http://gdata.youtube.com/feeds/api/playlists/" + playlist_id
    r = requests.get( feed_url )
    soup = bs( r.text )

    channel_out = {}
    items_out = []

    feed = soup.find("feed")
    
    channel_author = feed.find("author")

    channel_out["self_url"] = url_for( "feed", path=playlist_id, _external=True )
    channel_out["title"] = feed.find("title").string
    channel_out["link"] = feed.find( "link", rel="alternate" ).attrs["href"]
    channel_out["description"] = feed.find("subtitle").string
    channel_out["last_updated"] = format_date( feed.find("updated").string )
    channel_out["author"] = channel_author
    channel_out["author_name"] = channel_author.find("name").text

    for entry_tag in soup.find_all( "entry" ):

        this_item = {}

        # extract a few things from the item xml
        media_group = entry_tag.find( "media:group" )
        media_player = media_group.find( "media:player" )
        player_url = media_player.attrs[ "url" ]
        item_author = entry_tag.find("author")
        item_duration = media_group.find( "media:content" ).attrs["duration"]
        
        # get youtube item id from player url
        parsed = urlparse.urlparse( player_url )
        qd = urlparse.parse_qs( parsed.query )
        yt_id = "%s" % qd["v"][0]
        
        # construct item dict
        this_item["title"] = entry_tag.find("title").string
        this_item["pub_date"] = format_date( entry_tag.find("published").string )
        this_item["guid"] = entry_tag.find("id").string
        this_item["content"] = entry_tag.find("content").string
        
        this_item["link"] = entry_tag.find( "link", rel="alternate" ).attrs["href"]
        this_item["media_url"] = url_for( "stream", path=yt_id, _external=True )

        this_item["author"] = item_author
        this_item["author_name"] = item_author.find("name").text
        this_item["categories"] = entry_tag.find_all("category")

        this_item["duration"] = item_duration
        this_item["description"] = media_group.find( "media:description" ).string

        this_item["mime_type"] = app.config["MIME_TYPE"]
        this_item["it_duration"] = format_duration( int(item_duration) )
        
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
    
    return render_template( "feed.xml",
                            channel=channel,
                            items=items )

if __name__ == '__main__':
    if len(sys.argv) > 1:
        playlist_id = sys.argv[1]
        channel, items = parse_playlist( playlist_id )
        print channel
        print items
    else:
        app.run()
