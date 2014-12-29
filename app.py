import subprocess
from bs4 import BeautifulSoup as bs
from flask import Flask, Response
import requests
import urlparse 

app = Flask(__name__)
app.debug = True

@app.route('/stream/<path:path>')
def stream( path ):

    path_components = path.split("/")
    youtube_id = path_components[0]
    #TODO: validate youtube id

    yt_args = [ "youtube-dl", "-f", "140", "-q", "--output", "-", youtube_id ]
    ff_args = [ "ffmpeg", "-i", "-", "-loglevel", "quiet", "-acodec", "copy", "-f", "adts", "-" ]

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


@app.route('/feed/<path:path>')
def feed( path ):
    path_components = path.split("/")
    playlist_id = path_components[0]
    #TODO: validate playlist id

    feed_url = "http://gdata.youtube.com/feeds/api/playlists/" + playlist_id
    r = requests.get( feed_url )
    soup = bs( r.text )

    out = ""
    for entry_tag in soup.find_all( "entry" ):
        media_group = entry_tag.find( "media:group" )
        media_player = media_group.find( "media:player" )
        player_url = media_player.attrs[ "url" ]
        parsed = urlparse.urlparse( player_url )
        qd = urlparse.parse_qs( parsed.query )

        yt_id = qd["v"]
        print yt_id

        out += entry_tag.find("title").string

    return out



if __name__ == '__main__':
    app.run()