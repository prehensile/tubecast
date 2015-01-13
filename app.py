import subprocess
from bs4 import BeautifulSoup as bs
from flask import Flask, Response, url_for, render_template, abort, request
import requests
import urlparse 
import sys, os, signal
import re
import datetime, time
from email import utils
from werkzeug.wrappers import Response as ResponseBase

class StreamingResponse( ResponseBase ):
    
    def __init__( self, youtube_id ):
        
        # construct path to heroku vended ffmpeg first...
        ff_path = os.path.dirname(os.path.realpath(__file__))
        ff_path = os.path.join( ff_path, ".heroku/vendor/ffmpeg/bin/ffmpeg")
        is_heroku = True
        ## ...fall back to assuming it's in the system path
        if not os.path.exists( ff_path ):
            ff_path = "ffmpeg"
            is_heroku = False

        acodec = "libmp3lame"
        #acodec = "libvo_aacenc"
        # if is_heroku:
        #     acodec = "libfaac"
        yt_args = [ "youtube-dl", "-f", "140", "-q", "--output", "-", youtube_id ]
        ff_args = [ ff_path, "-loglevel", "quiet", "-i", "-", "-acodec", acodec, "-ab", "128k", "-ac", "2", "-ar", "44100", "-f", "mp3", "-" ]
        #ff_args = [ ff_path, "-loglevel", "quiet", "-i", "-", "-vn", "-acodec", acodec, "-f", "adts", "-" ]
        #ff_args = [ ff_path, "-i", "-", "-acodec", "copy", "-vn", "-f", "adts", "-" ]
        #ff_args = [ ff_path, "-i", "-", "-acodec", "copy", "-vn", "-f", "mp4", "-movflags", "frag_keyframe", "-frag_size", "1024", "-" ]
        #filename = "%s.aac" % youtube_id
        #filename = "%s.adts" % youtube_id
        filename = "%s.mp3" % youtube_id

        print " ".join(yt_args)
        print " ".join(ff_args)

        self._ff_proc = None
        self._yt_proc = None
        try:
            self._yt_proc = subprocess.Popen( yt_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid )
        except:
            pass
        try:
            self._ff_proc = subprocess.Popen( ff_args, stdin=self._yt_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid )    
        except:
            pass

        def stream():
            buf_size = 1024
            finished = False
            streamed = 0
            print "-> begin streaming..."
            while not finished:
                d = self._ff_proc.stdout.read( buf_size )
                yield d
                streamed += len(d)
                if len(d) < buf_size:
                    finished = True
            print "-> stream ended. Streamed %d bytes." % streamed

        response = None
        status = 500
        mimetype = None
        response = "Error"
        
        if (self._yt_proc is not None) and (self._ff_proc is not None):
            response = stream()
            status = 200
            mimetype = app.config['MIME_TYPE']

        super( StreamingResponse, self ).__init__( response=response,
                                                    status=status,
                                                    headers={'Content-Disposition' : 'attachment; filename=%s' % filename},
                                                    mimetype=mimetype,
                                                    content_type=None,
                                                    direct_passthrough=False ) 

        self.call_on_close( self.kill_threads )

    def kill_threads( self ):
        print "kill_threads, _ff_proc=%s, _yt_proc=%s" % ( self._ff_proc, self._yt_proc ) 
        if self._ff_proc is not None:
            print "--> kill ffmpeg"
            #self._ff_proc.wait()
            #self._ff_proc.terminate()
            try:
                os.killpg( self._ff_proc.pid, signal.SIGKILL )
            except Exception, e:
                self._ff_proc.kill()
                pass
            self._ff_proc = None
        if self._yt_proc is not None:
            print "--> kill youtube-dl"
            #self._yt_proc.wait()
            #self._yt_proc.terminate()
            try:
                os.killpg( self._yt_proc.pid, signal.SIGKILL )
            except Exception, e:
                self._yt_proc.kill()
            self._yt_proc = None
        print "kill_threads FINISHED"

app = Flask(__name__)
app.debug = True
#app.config['MIME_TYPE'] = "audio/aac-adts"
#app.config['MIME_TYPE'] = "audio/aac"
#mimetype = "audio/m4a"
#app.config['MIME_TYPE'] = "audio/mp3"
app.config['MIME_TYPE'] = "audio/mpeg"

@app.route('/')
def index():
    return render_template( "index.html" )

@app.route('/stream/<path:path>')
def stream( path ):
    
    mimetype = app.config['MIME_TYPE']
    
    # don't start streaming until we've been asked properly for audio data
    if request.accept_mimetypes[ mimetype ] < 1:
        print "-> return dummy stream"
        def stream():
            yield '0'
        return Response( stream(), mimetype=mimetype )

    print "content accepted"

    path_components = path.split("/")
    if len(path_components) < 1:
        #TODO: more detailed error throwing
        abort(400)

    youtube_id = path_components[0]
    if not re.match( r'[a-zA-Z0-9_-]{11}', youtube_id ):
        #TODO: more detailed error throwing
        abort(400)

    r = StreamingResponse( youtube_id=youtube_id )
    return r

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
